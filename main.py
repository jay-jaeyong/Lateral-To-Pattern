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
    image_overrides = {
        1: args.step1_image,
        2: args.step2_image,
        3: args.step3_image,
    }
    steps = apply_image_overrides(PIPELINE_STEPS, image_overrides)
    # 콘솔에서 시작 단계를 선택하도록 대화형으로 묻습니다 (터미널이 아닐 경우 기본값 사용)
    # Non-interactive: use CLI argument only. Remove interactive prompt.
    start_step = args.start_step

    max_step = max(s.get("step", 0) for s in PIPELINE_STEPS)
    if start_step < 1 or start_step > max_step:
        logger.error("유효하지 않은 start-step: %d (1-%d)", start_step, max_step)
        sys.exit(2)

    steps = [s for s in steps if s.get("step", 0) >= start_step]

    # 실행 레이블(run_label)을 첫 단계의 입력 이미지 이름으로 설정합니다(가능한 경우).
    def _derive_run_label(steps_list):
        from pathlib import Path
        from handlers.image_handler import ImageHandler

        if not steps_list:
            return None
        first = steps_list[0]
        img_path = first.get("image_path")
        if not img_path:
            return None
        p = Path(img_path)
        # 디렉터리면 내부 첫 이미지 파일명을 사용 (숨김파일 및 지원 확장자만)
        if p.is_dir():
            for child in sorted(p.iterdir()):
                if child.is_file() and child.suffix.lower() in ImageHandler.SUPPORTED_EXTENSIONS:
                    return child.stem.replace(" ", "_")
            return None
        # 파일이면 파일명 기반으로 레이블 생성
        if p.is_file():
            if p.suffix.lower() in ImageHandler.SUPPORTED_EXTENSIONS:
                return p.stem.replace(" ", "_")
            return None
        return None

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
