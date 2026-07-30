"""
Lateral-To-Pattern — 메인 실행 파일
=====================================

실행 방법:
    python main.py
    python main.py --run-label my_experiment
    python main.py --output-dir results
    python main.py --shoe-image path/to/side_view.png --guide-image path/to/guideline.jpg

파이프라인 흐름:
    신발 실물 사진(사이드뷰) + 2D 펼침 가이드라인(틀) + 프롬프트
        → Gemini API (패턴 펼치기)
        → output/ 저장
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from core.pipeline import Pipeline
from config.prompts import PIPELINE_STEPS
from utils.logging_utils import StepFilter
from utils.cli import build_parser, apply_image_overrides


# ─────────────────────────────────────────────
# 로깅 설정
# ─────────────────────────────────────────────

def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s%(step_label)s] %(name)s - %(message)s",
        datefmt="%H:%M:%S",
    )
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    handler.addFilter(StepFilter())
    logging.basicConfig(level=level, handlers=[handler])
    if not verbose:
        logging.getLogger("google_genai").setLevel(logging.WARNING)
        logging.getLogger("google_genai.models").setLevel(logging.WARNING)
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("urllib3").setLevel(logging.WARNING)


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
    steps = apply_image_overrides(
        PIPELINE_STEPS,
        shoe_image=args.shoe_image,
        guide_image=args.guide_image,
    )

    # If the user provided an explicit run label, use it; otherwise we allow
    # the Pipeline to set the label based on the selected image later.
    run_label = args.run_label

    # 파이프라인 실행
    pipeline = Pipeline(
        steps=steps,
        output_dir=Path(args.output_dir),
        run_label=run_label,
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
