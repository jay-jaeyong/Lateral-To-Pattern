#!/usr/bin/env python3
"""스케치 출력 진단 하네스 CLI.

진단 전용입니다. 이미지를 수정하거나 삭제하지 않고, Gemini를 호출하지 않으며,
채점 결과가 저장·재생성 동작을 유발하지 않습니다. 쓰기가 허용된 경로는
`annotations/sketch-scoring/`와 `reports/sketch-scoring/`뿐입니다.

사용법:
    uv run python scripts/score_sketch_outputs.py manifest \\
        --images-dir images --manifest annotations/sketch-scoring/dataset.json

    uv run python scripts/score_sketch_outputs.py score \\
        --manifest annotations/sketch-scoring/dataset.json --label output-5-baseline

상대 경로는 현재 작업 디렉터리(보통 저장소 루트)를 기준으로 해석합니다.
개별 지표가 `fail`이나 `not_scored`여도 종료 코드는 0입니다. manifest·주석
스키마 오류, 필수 파일 읽기 실패와 보고서 저장 실패는 0이 아닌 코드입니다.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sketch_scoring.annotations import AnnotationError
from sketch_scoring.manifest import (
    ManifestError,
    discover_manifest,
    resolve_write_path,
    write_manifest,
)
from sketch_scoring.metrics import ImageDecodeError, ScoringConfig
from sketch_scoring.reporting import LATEST_NAME, write_run_reports
from sketch_scoring.scoring import score_dataset

# 하네스가 쓸 수 있는 루트는 이 둘뿐입니다. `images/`는 읽기 전용입니다.
WRITABLE_ANNOTATION_ROOT = Path("annotations/sketch-scoring")
WRITABLE_REPORTS_ROOT = Path("reports/sketch-scoring")

DEFAULT_MANIFEST = WRITABLE_ANNOTATION_ROOT / "dataset.json"
DEFAULT_ANNOTATION_ROOT = WRITABLE_ANNOTATION_ROOT / "items"
DEFAULT_REPORTS_ROOT = WRITABLE_REPORTS_ROOT


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="스케치 출력 진단 하네스")
    sub = parser.add_subparsers(dest="command", required=True)

    manifest = sub.add_parser("manifest", help="후보 탐색으로 manifest를 만들거나 갱신")
    manifest.add_argument("--images-dir", type=Path, default=Path("images"))
    manifest.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)

    score = sub.add_parser("score", help="manifest에 적힌 출력을 채점")
    score.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    score.add_argument("--annotation-root", type=Path, default=DEFAULT_ANNOTATION_ROOT)
    score.add_argument("--reports-root", type=Path, default=DEFAULT_REPORTS_ROOT)
    score.add_argument("--label", required=True)
    score.add_argument("--version", action="append", dest="versions")
    return parser


def _resolve(project_root: Path, path: Path) -> Path:
    return path if path.is_absolute() else project_root / path


def _read_existing(path: Path) -> dict | None:
    """탐색 단계에서는 미확정 후보도 보존해야 하므로 원본 JSON을 그대로 읽습니다."""
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ManifestError(f"기존 manifest를 읽을 수 없음: {path}") from exc


def _run_manifest(args: argparse.Namespace, project_root: Path) -> int:
    # 쓰기 전에 목적지를 먼저 검사합니다.
    manifest_path = resolve_write_path(
        project_root, args.manifest, allowed_root=WRITABLE_ANNOTATION_ROOT
    )
    found = discover_manifest(
        _resolve(project_root, args.images_dir), _read_existing(manifest_path)
    )
    write_manifest(manifest_path, found)
    review = sorted(
        item_id
        for item_id, item in found["items"].items()
        if item.get("needs_review")
    )
    print(f"manifest 항목 {len(found['items'])}개를 {manifest_path}에 기록했습니다.")
    if review:
        print(f"확인이 필요한 항목 {len(review)}개: {', '.join(review)}")
    return 0


def _run_score(args: argparse.Namespace, project_root: Path) -> int:
    # 보고서 목적지와 주석 루트를 채점 전에 검사합니다. 채점 자체는 읽기
    # 전용이지만 하네스가 손대는 트리를 허용된 루트로 묶어 둡니다.
    reports_root = resolve_write_path(
        project_root, args.reports_root, allowed_root=WRITABLE_REPORTS_ROOT
    )
    annotation_root = resolve_write_path(
        project_root, args.annotation_root, allowed_root=WRITABLE_ANNOTATION_ROOT
    )
    result = score_dataset(
        _resolve(project_root, args.manifest),
        versions=set(args.versions) if args.versions else None,
        annotation_root=annotation_root,
        config=ScoringConfig(),
        project_root=project_root,
    )
    run_dir = write_run_reports(result, reports_root, args.label)
    scored = sum(len(versions) for versions in result["items"].values())
    print(f"출력 {scored}건을 채점했습니다(진단 전용, 총점 없음).")
    print(f"결과: {run_dir}")
    print(f"최신 포인터: {reports_root / LATEST_NAME}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    project_root = Path.cwd()
    try:
        if args.command == "manifest":
            return _run_manifest(args, project_root)
        return _run_score(args, project_root)
    except (ManifestError, AnnotationError, ImageDecodeError, OSError) as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
