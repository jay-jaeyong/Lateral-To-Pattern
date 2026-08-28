"""Dataset manifest 후보 탐색, 스키마 검증과 읽기 전용 경로 해석.

manifest는 컬러 원본과 여러 출력 판본을 명시적으로 연결하는 권위 문서입니다.
파일명 접미사(`_color`, `_sketch`)는 후보 탐색에만 쓰고 실제 채점은 확정된
manifest 경로를 따릅니다. 표시 이름은 NFC로 정규화하지만 파일 경로는 디스크에
있는 바이트(NFD 한글 포함)를 그대로 보존합니다.
"""

from __future__ import annotations

import copy
import json
import re
import unicodedata
from collections.abc import Sequence
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

SCHEMA_VERSION = 1
DEFAULT_CANVAS_RATIO = "2:3"
OUTPUT_KINDS = {"clean", "annotated_only"}
SUPPORTED_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
SOURCE_SUFFIX = "_color"
OUTPUT_SUFFIX = "_sketch"

# medial·lateral 대칭, 좌우 반전과 반대쪽 유사도 지표는 설계상 만들지 않습니다.
# manifest에 이런 필드가 들어오면 조용히 무시하지 않고 거부합니다.
FORBIDDEN_COMPARISON_KEYS = {
    "mirror",
    "symmetry",
    "opposite_side",
    "medial_lateral_similarity",
}

_RATIO_PATTERN = re.compile(r"^\d+:\d+$")


class ManifestError(ValueError):
    """manifest 스키마 또는 경로 안전성 위반."""


def canonical_display_name(name: str) -> str:
    """표시용 이름을 NFC로 정규화합니다(파일 경로에는 쓰지 않습니다)."""
    return unicodedata.normalize("NFC", name)


def version_sort_key(version: str) -> tuple[int, str]:
    """`output-2`가 `output-10`보다 앞에 오도록 판본을 정렬합니다."""
    match = re.search(r"(\d+)$", str(version))
    return (int(match.group(1)) if match else -1, str(version))


def _resolve_within_roots(
    project_root: Path, value: str, allowed_roots: Sequence[Path]
) -> Path:
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts:
        raise ManifestError("manifest path is outside the allowed image roots")
    resolved = (project_root / relative).resolve()
    if not any(resolved.is_relative_to(root.resolve()) for root in allowed_roots):
        raise ManifestError("manifest path is outside the allowed image roots")
    return resolved


def resolve_read_path(
    project_root: Path, value: str, *, allowed_roots: Sequence[Path]
) -> Path:
    """허용된 이미지 루트 안의 기존 파일만 해석합니다(심볼릭 링크 탈출 포함 차단)."""
    resolved = _resolve_within_roots(project_root, value, allowed_roots)
    if not resolved.is_file():
        raise ManifestError("manifest path is outside the allowed image roots")
    return resolved


def allowed_image_roots(project_root: Path) -> list[Path]:
    """읽기 전용으로 허용된 이미지 루트."""
    return [Path(project_root) / "images"]


def resolve_write_path(
    project_root: Path, value: Path | str, *, allowed_root: Path | str
) -> Path:
    """쓰기가 허용된 루트 안의 경로만 해석합니다.

    심볼릭 링크를 먼저 따라가므로 허용 루트 안에 만든 링크로 이미지나 다른
    저장소 파일을 가리켜도 거부됩니다. 절대 경로와 `..`도 같은 검사로 걸립니다.
    """
    root = Path(project_root)
    resolved_root = (root / Path(allowed_root)).resolve()
    candidate = Path(value)
    resolved = (candidate if candidate.is_absolute() else root / candidate).resolve()
    if not resolved.is_relative_to(resolved_root):
        raise ManifestError(
            f"쓰기 경로가 허용된 루트({allowed_root}) 밖임: {value}"
        )
    return resolved


def _reject_forbidden_keys(value: object, item_id: str) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            lowered = str(key).lower()
            if any(token in lowered for token in FORBIDDEN_COMPARISON_KEYS):
                raise ManifestError(
                    f"{item_id}: 대칭·반전 비교 필드는 지원하지 않음 ({key})"
                )
            _reject_forbidden_keys(child, item_id)
    elif isinstance(value, list):
        for child in value:
            _reject_forbidden_keys(child, item_id)


def _validated_ratio(value: object, item_id: str) -> str:
    if value is None:
        return DEFAULT_CANVAS_RATIO
    text = str(value)
    if not _RATIO_PATTERN.match(text):
        raise ManifestError(f"{item_id}: expected_canvas_ratio 형식이 잘못됨 ({value})")
    width, height = (int(part) for part in text.split(":"))
    if width <= 0 or height <= 0:
        raise ManifestError(f"{item_id}: expected_canvas_ratio 값이 0 이하 ({value})")
    return text


def _canonical_output_record(
    record: object, item_id: str, version: str, *, require_path: bool = True
) -> dict:
    if isinstance(record, str):
        record = {"path": record, "kind": "clean"}
    if not isinstance(record, dict):
        raise ManifestError(f"{item_id}/{version}: 출력 레코드 형식이 잘못됨")
    kind = record.get("kind", "clean")
    if kind not in OUTPUT_KINDS:
        raise ManifestError(f"{item_id}/{version}: 알 수 없는 출력 종류 ({kind})")
    path = record.get("path")
    if not isinstance(path, str) or not path:
        candidates = record.get("candidates")
        if not require_path and isinstance(candidates, list) and candidates:
            # 후보가 여러 개인 미확정 슬롯은 탐색 단계에서 그대로 보존합니다.
            return {"kind": kind, "candidates": [str(item) for item in candidates]}
        if isinstance(candidates, list) and candidates:
            raise ManifestError(
                f"{item_id}/{version}: 출력 후보가 확정되지 않음 {candidates}"
            )
        raise ManifestError(f"{item_id}/{version}: 출력 경로가 없음")
    return {"path": path, "kind": kind}


def load_manifest(path: Path, *, project_root: Path | None = None) -> dict:
    """manifest를 검증하고 정규화된 메모리 표현으로 돌려줍니다."""
    path = Path(path)
    root = Path(project_root) if project_root is not None else PROJECT_ROOT
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ManifestError(f"manifest를 읽을 수 없음: {path}") from exc
    if not isinstance(raw, dict):
        raise ManifestError("manifest 루트가 객체가 아님")
    if raw.get("schema_version") != SCHEMA_VERSION:
        raise ManifestError(f"지원하지 않는 manifest schema_version: {raw.get('schema_version')}")
    items = raw.get("items")
    if not isinstance(items, dict):
        raise ManifestError("manifest items가 객체가 아님")

    roots = allowed_image_roots(root)
    loaded: dict[str, dict] = {}
    for key, item in items.items():
        item_id = canonical_display_name(str(key))
        if not isinstance(item, dict):
            raise ManifestError(f"{item_id}: 항목이 객체가 아님")
        _reject_forbidden_keys(item, item_id)

        source = item.get("source")
        if not isinstance(source, str) or not source:
            raise ManifestError(f"{item_id}: source 경로가 확정되지 않음")
        resolve_read_path(root, source, allowed_roots=roots)

        outputs_raw = item.get("outputs") or {}
        if not isinstance(outputs_raw, dict):
            raise ManifestError(f"{item_id}: outputs가 객체가 아님")
        outputs: dict[str, dict] = {}
        for version, record in outputs_raw.items():
            canonical = _canonical_output_record(record, item_id, str(version))
            # 출력 파일은 판본에 따라 없을 수 있으므로 존재 여부는 채점 시점에
            # 판단합니다. 여기서는 경로가 허용된 루트 안인지만 확인합니다.
            _resolve_within_roots(root, canonical["path"], roots)
            outputs[str(version)] = canonical

        loaded[item_id] = {
            "display_name": canonical_display_name(
                str(item.get("display_name") or item_id)
            ),
            "source": source,
            "expected_canvas_ratio": _validated_ratio(
                item.get("expected_canvas_ratio"), item_id
            ),
            "needs_review": bool(item.get("needs_review", False)),
            "outputs": outputs,
        }
    return {"schema_version": SCHEMA_VERSION, "items": loaded}


def write_manifest(path: Path, manifest: dict) -> None:
    """같은 디렉터리의 임시 파일에 쓰고 원자적으로 교체합니다."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    try:
        temporary.replace(path)
    except OSError:
        temporary.unlink(missing_ok=True)
        raise


def _image_files(directory: Path) -> list[Path]:
    if not directory.is_dir():
        return []
    return sorted(
        entry
        for entry in directory.iterdir()
        if entry.is_file() and entry.suffix.lower() in SUPPORTED_SUFFIXES
    )


def _blank_item(item_id: str) -> dict:
    return {
        "display_name": item_id,
        "source": None,
        "expected_canvas_ratio": DEFAULT_CANVAS_RATIO,
        "needs_review": False,
        "outputs": {},
    }


def discover_manifest(images_dir: Path, existing: dict | None = None) -> dict:
    """파일명 접미사로 후보를 찾고 기존 확정 연결은 그대로 보존합니다.

    이름이 불규칙하거나 후보가 여러 개인 항목은 추측하지 않고
    `needs_review: true`로 표시합니다.
    """
    images_dir = Path(images_dir)
    prefix = Path(images_dir.name)

    items: dict[str, dict] = {}
    for key, item in ((existing or {}).get("items") or {}).items():
        item_id = canonical_display_name(str(key))
        merged = _blank_item(item_id)
        merged.update(copy.deepcopy(item))
        merged["display_name"] = canonical_display_name(
            str(merged.get("display_name") or item_id)
        )
        merged["outputs"] = {
            str(version): _canonical_output_record(
                record, item_id, str(version), require_path=False
            )
            for version, record in (merged.get("outputs") or {}).items()
        }
        items[item_id] = merged

    # 후보를 먼저 모으고 나서 배정합니다. 같은 슬롯에 후보가 둘 이상이면
    # 확장자만 다른 파일이라도 임의로 고르지 않고 사람에게 넘깁니다.
    source_candidates: dict[str, list[tuple[str, bool]]] = {}
    for entry in _image_files(images_dir):
        regular = entry.stem.endswith(SOURCE_SUFFIX)
        item_id = canonical_display_name(
            entry.stem[: -len(SOURCE_SUFFIX)] if regular else entry.stem
        )
        source_candidates.setdefault(item_id, []).append(
            (str(prefix / entry.name), regular)
        )

    for item_id, candidates in source_candidates.items():
        item = items.setdefault(item_id, _blank_item(item_id))
        if item.get("source"):
            continue  # 사용자가 확정한 경로는 덮어쓰지 않습니다.
        if len(candidates) > 1:
            item["source_candidates"] = [path for path, _ in candidates]
            item["needs_review"] = True
            continue
        path, regular = candidates[0]
        item["source"] = path
        item.pop("source_candidates", None)
        if not regular:
            item["needs_review"] = True

    output_dirs = sorted(
        entry
        for entry in (images_dir.iterdir() if images_dir.is_dir() else [])
        if entry.is_dir() and entry.name.startswith("output-")
    )
    output_candidates: dict[tuple[str, str], list[str]] = {}
    for output_dir in output_dirs:
        for entry in _image_files(output_dir):
            if not entry.stem.endswith(OUTPUT_SUFFIX):
                continue
            item_id = canonical_display_name(entry.stem[: -len(OUTPUT_SUFFIX)])
            key = (item_id, output_dir.name)
            output_candidates.setdefault(key, []).append(
                str(prefix / output_dir.name / entry.name)
            )

    for (item_id, version), candidates in output_candidates.items():
        item = items.get(item_id)
        if item is None:
            # 대응 원본을 찾지 못한 출력은 사람이 원본을 확정해야 합니다.
            item = _blank_item(item_id)
            item["needs_review"] = True
            items[item_id] = item
        if item["outputs"].get(version, {}).get("path"):
            continue  # 사용자가 확정한 출력은 덮어쓰지 않습니다.
        if len(candidates) > 1:
            item["outputs"][version] = {"kind": "clean", "candidates": candidates}
            item["needs_review"] = True
            continue
        item["outputs"][version] = {"path": candidates[0], "kind": "clean"}

    return {"schema_version": SCHEMA_VERSION, "items": items}
