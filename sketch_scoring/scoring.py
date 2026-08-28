"""출력 한 장과 dataset 전체의 채점 오케스트레이션.

이미지는 읽기 전용으로만 열고 어떤 경로에도 이미지를 쓰지 않습니다. 외부 API,
AI 판정과 이미지 임베딩을 쓰지 않으며 지표를 총점으로 합치지 않습니다. 지표
하나가 실패하면 그 지표만 `not_scored`가 되고 항목 채점은 계속됩니다.
manifest·주석 스키마 오류, 필수 원본 파일 읽기·디코드 실패와 manifest가 가리키는
깨끗한 출력의 디코드 실패는 치명적입니다. 출력 파일이 아예 없는 경우만 항목별
미채점으로 남깁니다.
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from . import __version__
from .annotations import annotation_path, load_annotations
from .manifest import (
    PROJECT_ROOT,
    ManifestError,
    allowed_image_roots,
    load_manifest,
    resolve_read_path,
    version_sort_key,
)
from .metrics import (
    MetricResult,
    ScoringConfig,
    load_rgb,
    safe_metric,
    score_annotation,
    score_global_metrics,
)

SCHEMA_VERSION = 1
GLOBAL_METRIC_NAMES = (
    "aspect_ratio",
    "silhouette_iou",
    "colored_pixels",
    "black_fill",
    "faint_strokes",
)
ANNOTATED_ONLY_REASON = "빨간 표시가 합성된 주석 자료이며 깨끗한 출력이 없음"
MISSING_OUTPUT_REASON = "출력 파일이 없음"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _annotation_entry(annotation: dict, metric: MetricResult) -> dict:
    return {
        "id": annotation["id"],
        "type": annotation["type"],
        "label": annotation.get("label"),
        "metric": metric.to_dict(),
    }


def _not_scored_output(annotations: list[dict], reason: str) -> tuple[dict, list[dict]]:
    """픽셀 지표를 계산할 수 없을 때 쓰는 표준 미채점 결과."""
    metrics = {
        name: MetricResult.not_scored(reason, 0.0).to_dict()
        for name in GLOBAL_METRIC_NAMES
    }
    entries = [
        _annotation_entry(annotation, MetricResult.not_scored(reason, 0.0))
        for annotation in annotations
    ]
    return metrics, entries


def score_output(
    item_id: str,
    item: dict,
    version: str,
    output_record: dict,
    *,
    project_root: Path,
    annotation_root: Path,
    config: ScoringConfig,
) -> dict:
    """출력 한 장을 채점합니다. 파일을 읽기만 하고 아무것도 쓰지 않습니다."""
    project_root = Path(project_root)
    roots = allowed_image_roots(project_root)
    # 필수 원본은 출력 종류와 무관하게 먼저 해석하고 디코드합니다. 주석 자료나
    # 출력 부재로 조기 반환하기 전에 확인해야, 원본이 깨진 상태가 미채점 결과에
    # 가려지지 않습니다. 원본을 읽거나 디코드할 수 없으면 치명적입니다.
    source_path = resolve_read_path(project_root, item["source"], allowed_roots=roots)
    source_rgb = load_rgb(source_path)
    document = load_annotations(annotation_root, item_id)
    annotations = document["annotations"]

    kind = output_record.get("kind", "clean")
    relative = output_record["path"]
    try:
        output_path = resolve_read_path(project_root, relative, allowed_roots=roots)
    except ManifestError:
        output_path = None

    result = {
        "version": version,
        "kind": kind,
        "path": relative,
        "source_sha256": sha256_file(source_path),
        # 주석 자료도 해시는 남기지만 깨끗한 출력으로 디코드하지는 않습니다.
        "output_sha256": sha256_file(output_path) if output_path else None,
        "annotation_count": len(annotations),
    }

    if kind == "annotated_only":
        reason = ANNOTATED_ONLY_REASON
    elif output_path is None:
        reason = f"{MISSING_OUTPUT_REASON}: {relative}"
    else:
        reason = None

    if reason is not None:
        # 빨간 픽셀을 지우거나 복원하지 않고 미채점으로 남깁니다.
        result["metrics"], result["annotations"] = _not_scored_output(annotations, reason)
        return result

    # manifest가 가리키는 깨끗한 출력이 실제로 있는데 디코드되지 않으면 치명적
    # 입니다. 미채점으로 덮으면 깨진 파일이 정상적인 미측정처럼 보입니다.
    # (파일이 아예 없는 경우는 위에서 항목별 미채점으로 처리했습니다.)
    output_rgb = load_rgb(output_path)

    # 위에서 이미 디코드한 원본을 그대로 재사용합니다.
    metrics = score_global_metrics(
        source_rgb, output_rgb, item["expected_canvas_ratio"], config
    )
    result["metrics"] = {name: metric.to_dict() for name, metric in metrics.items()}
    result["annotations"] = [
        _annotation_entry(
            annotation, safe_metric(score_annotation, output_rgb, annotation, config)
        )
        for annotation in annotations
    ]
    return result


def score_dataset(
    manifest_path: Path,
    *,
    versions: set[str] | None = None,
    annotation_root: Path,
    config: ScoringConfig | None = None,
    project_root: Path | None = None,
) -> dict:
    """manifest에 적힌 항목만 채점하고 출처 정보를 함께 기록합니다."""
    started_at = _utc_now()
    root = Path(project_root) if project_root is not None else PROJECT_ROOT
    config = config or ScoringConfig()
    manifest_path = Path(manifest_path)
    annotation_root = Path(annotation_root)
    manifest = load_manifest(manifest_path, project_root=root)

    items: dict[str, dict] = {}
    annotation_hashes: dict[str, str] = {}
    for item_id, item in sorted(manifest["items"].items()):
        sidecar = annotation_path(annotation_root, item_id)
        if sidecar.is_file():
            annotation_hashes[item_id] = sha256_file(sidecar)
        scored: dict[str, dict] = {}
        for version in sorted(item["outputs"], key=version_sort_key):
            if versions is not None and version not in versions:
                continue
            scored[version] = score_output(
                item_id,
                item,
                version,
                item["outputs"][version],
                project_root=root,
                annotation_root=annotation_root,
                config=config,
            )
        items[item_id] = scored

    try:
        recorded_manifest = manifest_path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        recorded_manifest = manifest_path.as_posix()

    return {
        "schema_version": SCHEMA_VERSION,
        "diagnostic_only": True,
        "provenance": {
            "started_at": started_at,
            "manifest_path": recorded_manifest,
            "manifest_sha256": sha256_file(manifest_path),
            "annotation_sha256": annotation_hashes,
            # 하네스는 git을 호출하지 않습니다. 필요하면 호출자가 채웁니다.
            "git_commit": None,
            "harness_version": __version__,
            "config": asdict(config),
        },
        "items": items,
    }
