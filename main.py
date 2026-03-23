"""
Lateral-To-Pattern — 메인 실행 파일
=====================================

실행 방법:
    python main.py
    python main.py --run-label my_experiment
    python main.py --output-dir results
    python main.py --step1-image path/to/img.png --step2-image path/to/img2.png

파이프라인 흐름:
    이미지 + 프롬프트
        → Gemini API (Step 1)
        → 이미지 + 프롬프트
        → Gemini API (Step 2)
        → 이미지 + 프롬프트
        → Gemini API (Step 3)
        → output/ 저장
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from src.pipeline import Pipeline
from config.prompts import PIPELINE_STEPS


# ─────────────────────────────────────────────
# 로깅 설정
# ─────────────────────────────────────────────

def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
        datefmt="%H:%M:%S",
        handlers=[logging.StreamHandler(sys.stdout)],
    )


# ─────────────────────────────────────────────
# CLI 인자 파서
# ─────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
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


# ─────────────────────────────────────────────
# 이미지 경로 오버라이드
# ─────────────────────────────────────────────

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


# ─────────────────────────────────────────────
# 메인
# ─────────────────────────────────────────────

def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    setup_logging(verbose=args.verbose)
    logger = logging.getLogger(__name__)

    logger.info("=" * 60)
    logger.info("Lateral-To-Pattern 파이프라인 시작")
    logger.info("=" * 60)

    # CLI 이미지 경로 오버라이드 적용
    image_overrides = {
        1: args.step1_image,
        2: args.step2_image,
        3: args.step3_image,
    }
    steps = apply_image_overrides(PIPELINE_STEPS, image_overrides)

    # 파이프라인 실행
    pipeline = Pipeline(
        steps=steps,
        output_dir=Path(args.output_dir),
        run_label=args.run_label,
    )

    try:
        result = pipeline.run()
    except EnvironmentError as exc:
        logger.error("환경 설정 오류: %s", exc)
        sys.exit(1)
    except FileNotFoundError as exc:
        logger.error("파일 오류: %s", exc)
        sys.exit(1)
    except Exception as exc:  # noqa: BLE001
        logger.error("예상치 못한 오류 발생: %s", exc, exc_info=True)
        sys.exit(1)

    # 결과 요약 출력
    print("\n" + result.summary())
    print("\n[최종 출력 미리보기]")
    print("-" * 60)
    preview = result.final_output[:500]
    print(preview + ("..." if len(result.final_output) > 500 else ""))


if __name__ == "__main__":
    main()
