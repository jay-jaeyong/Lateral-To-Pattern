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
        description="Lateral-To-Pattern: 멀티스텝 Gemini 이미지+프롬프트 파이프라인"
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
        "--start-step",
        type=int,
        default=1,
        help="어떤 단계부터 실행할지 지정 (기본값: 1)",
    )
    parser.add_argument(
        "--step1-image",
        default=None,
        help="Step 1에서 사용할 이미지 경로 (미입력 시 config/prompts.py 설정 사용)",
    )
    parser.add_argument(
        "--step2-image",
        default=None,
        help="Step 2에서 사용할 이미지 경로 (미입력 시 config/prompts.py 설정 사용)",
    )
    parser.add_argument(
        "--step3-image",
        default=None,
        help="Step 3에서 사용할 이미지 경로 (미입력 시 config/prompts.py 설정 사용)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="상세 로그 출력",
    )
    return parser


def apply_image_overrides(steps: list[dict], overrides: dict[int, str]) -> list[dict]:
    """CLI 인자로 전달된 이미지 경로를 단계 설정에 덮어씁니다."""
    updated = []
    for step_config in steps:
        cfg = dict(step_config)
        step_num = cfg["step"]
        if step_num in overrides and overrides[step_num]:
            cfg["image_path"] = Path(overrides[step_num])
        updated.append(cfg)
    return updated
