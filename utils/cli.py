"""
CLI Utilities
--------------
커맨드라인 인자 파싱 및 이미지 경로 오버라이드 유틸리티.
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


# 뷰 플래그 정의: (플래그 이름, 프롬프트에 붙일 라벨)
# 이 튜플의 순서가 곧 API 전송 순서입니다. 사용자가 플래그를 준 순서와 무관합니다.
# 라벨 문자열은 config/prompts.py의 프롬프트가 그대로 지칭하므로 바꾸면 안 됩니다.
VIEW_FLAGS: tuple[tuple[str, str], ...] = (
    ("lateral", "바깥쪽 측면(lateral)"),
    ("medial", "안쪽 측면(medial)"),
    ("front", "앞에서 본 모습(front)"),
    ("heel", "뒤꿈치(heel)"),
    ("top", "위에서 본 모습(top)"),
    ("bottom", "바닥(bottom)"),
)


def build_parser() -> argparse.ArgumentParser:
    """CLI 인자 파서를 구성합니다."""
    parser = argparse.ArgumentParser(
        description="Lateral-To-Pattern: 신발 실물 사진을 2D 패턴으로 펼치는 Gemini 파이프라인"
    )
    parser.add_argument(
        "--run-label",
        default=None,
        help="실행 식별자 (출력 폴더명). 미입력 시 타임스탬프 자동 생성.",
    )
    parser.add_argument(
        "--output-dir",
        default="output",
        help="결과를 저장할 최상위 디렉터리 (기본값: output/)",
    )
    for name, label in VIEW_FLAGS:
        parser.add_argument(
            f"--{name}",
            default=None,
            metavar="PATH",
            help=f"{label} 사진 경로. 뷰 플래그를 하나라도 주면 --shoe-image와 폴더 선택은 무시됩니다.",
        )
    parser.add_argument(
        "--shoe-image",
        nargs="+",
        metavar="PATH",
        default=None,
        help="신발 실물 사진(사이드뷰) 경로 또는 폴더. 여러 개를 주면 각각 따로 실행합니다. "
             "(미입력 시 config/prompts.py 설정 사용)",
    )
    parser.add_argument(
        "--guide-image",
        default=None,
        help="2D 펼침 가이드라인(틀) 이미지 경로 또는 폴더 (미입력 시 config/prompts.py 설정 사용)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="상세 로그 출력",
    )
    return parser


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """인자를 파싱하고 뷰 플래그 경로가 실제로 있는지 검사합니다.

    없는 파일을 가리키면 API를 부르기 전에 여기서 종료합니다.
    """
    parser = build_parser()
    args = parser.parse_args(argv)

    for name, _label in VIEW_FLAGS:
        value = getattr(args, name, None)
        if value and not Path(value).is_file():
            parser.error(f"--{name} 경로를 찾을 수 없습니다: {value}")

    return args


def collect_view_images(args: argparse.Namespace) -> list[tuple[str, Path]]:
    """주어진 뷰 플래그를 VIEW_FLAGS 순서대로 (라벨, 경로) 목록으로 모읍니다."""
    collected: list[tuple[str, Path]] = []
    for name, label in VIEW_FLAGS:
        value = getattr(args, name, None)
        if value:
            collected.append((label, Path(value)))
    return collected


def derive_run_label(view_images: list[tuple[str, Path]]) -> str | None:
    """뷰 플래그 목록에서 출력 폴더 이름을 유도합니다.

    VIEW_FLAGS 순서상 lateral이 맨 앞이므로, lateral이 있으면 그 파일명이 됩니다.
    """
    return view_images[0][1].stem if view_images else None


def apply_image_overrides(
    steps: list[dict],
    shoe_image: str | list[str] | None = None,
    guide_image: str | None = None,
    view_images: list[tuple[str, Path]] | None = None,
) -> list[dict]:
    """CLI 인자로 전달된 이미지를 첫 단계 설정에 덮어씁니다.

    view_images가 있으면 그것이 신발 사진 전체를 정의하고 image_path는 비웁니다.
    shoe_image가 여러 개면 첫 번째 경로만 단계 설정에 넣습니다.
    나머지는 Pipeline(batch_targets=...)이 개별 실행으로 처리합니다.
    """
    updated = [dict(step_config) for step_config in steps]
    if not updated:
        return updated

    if view_images:
        updated[0]["view_images"] = list(view_images)
        updated[0]["image_path"] = None
        if shoe_image:
            logger.warning("뷰 플래그가 있어 --shoe-image를 무시합니다: %s", shoe_image)
    elif shoe_image:
        first = shoe_image[0] if isinstance(shoe_image, list) else shoe_image
        updated[0]["image_path"] = Path(first)

    if guide_image:
        updated[0]["guide_image_path"] = Path(guide_image)

    return updated
