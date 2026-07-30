"""
CLI Utilities
--------------
커맨드라인 인자 파싱 및 이미지 경로 오버라이드 유틸리티.
"""

from __future__ import annotations

import argparse
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    """CLI 인자 파서를 구성합니다."""
    parser = argparse.ArgumentParser(
        description="Lateral-To-Pattern: 신발 실물 사이드뷰 사진을 2D 패턴으로 펼치는 Gemini 파이프라인"
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
    parser.add_argument(
        "--shoe-image",
        default=None,
        help="신발 실물 사진(사이드뷰) 경로 또는 폴더 (미입력 시 config/prompts.py 설정 사용)",
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


def apply_image_overrides(
    steps: list[dict],
    shoe_image: str | None = None,
    guide_image: str | None = None,
) -> list[dict]:
    """CLI 인자로 전달된 이미지 경로를 첫 단계 설정에 덮어씁니다."""
    updated = [dict(step_config) for step_config in steps]
    if not updated:
        return updated

    if shoe_image:
        updated[0]["image_path"] = Path(shoe_image)
    if guide_image:
        updated[0]["guide_image_path"] = Path(guide_image)

    return updated
