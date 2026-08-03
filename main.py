"""
Lateral-To-Pattern — 메인 실행 파일
=====================================

실행 방법:
    python main.py
    python main.py --run-label my_experiment
    python main.py --output-dir results
    python main.py --shoe-image path/to/side_view.png --guide-image path/to/guideline.jpg
    python main.py --shoe-image shoe_a.jpg shoe_b.jpg shoe_c.jpg   # 이미지마다 개별 실행
    python main.py --lateral lat.webp --medial med.webp --top top.webp   # 한 켤레 멀티뷰

파이프라인 흐름:
    신발 실물 사진(여러 각도)
        → Gemini API (부품 관찰)      → 부품 명세서 텍스트
        → Gemini API (패턴 펼치기)    → 2D 전개 패턴 이미지
        → Gemini API (라인 아트 변환) → 라인 아트 이미지
        → output/ 저장
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from core.pipeline import Pipeline
from config.prompts import PIPELINE_STEPS
from utils.logging_utils import StepFilter
from utils.cli import (
    apply_image_overrides,
    collect_view_images,
    derive_run_label,
    guide_path_problem,
    parse_args,
)


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
    args = parse_args()

    setup_logging(verbose=args.verbose)
    logger = logging.getLogger(__name__)

    logger.info("=" * 60)
    logger.info("Lateral-To-Pattern 파이프라인 시작")
    logger.info("=" * 60)

    # 뷰 플래그가 하나라도 있으면 그것들이 신발 사진 전체를 정의합니다.
    view_images = collect_view_images(args)
    if view_images and not args.lateral:
        logger.warning(
            "기준이 되는 --lateral 사진이 없습니다. "
            "받은 사진 중 옆면에 해당하는 것을 기준으로 삼습니다."
        )

    # CLI 이미지 경로 오버라이드 적용
    steps = apply_image_overrides(
        PIPELINE_STEPS,
        shoe_image=args.shoe_image,
        guide_image=args.guide_image,
        view_images=view_images,
    )

    # --guide-image를 생략하면 config/prompts.py의 기본 경로가 쓰입니다. 그 경로에
    # 가이드라인이 없어도 파이프라인은 경고만 남기고 끝까지 도는데, 그러면 틀 없이
    # 펼친 결과가 나옵니다. 실제로 쓰일 경로를 여기서 미리 검사합니다.
    for step_config in steps:
        guide_path = step_config.get("guide_image_path")
        if guide_path is None:
            continue
        problem = guide_path_problem(Path(guide_path))
        if problem:
            logger.error("Step %s 가이드라인 오류 — %s", step_config.get("step"), problem)
            sys.exit(1)

    # 뷰 플래그를 쓰면 모델 폴더 이름이 없으므로 lateral 파일명을 출력 폴더로 씁니다.
    # 그 외에는 Pipeline이 선택된 이미지 이름으로 레이블을 정합니다.
    run_label = args.run_label or derive_run_label(view_images)

    # 신발 이미지를 2개 이상 받았다면 각각 개별 실행합니다.
    shoe_images = [] if view_images else (args.shoe_image or [])
    batch_targets = [Path(p) for p in shoe_images] if len(shoe_images) > 1 else None

    # 파이프라인 실행
    pipeline = Pipeline(
        steps=steps,
        output_dir=Path(args.output_dir),
        run_label=run_label,
        batch_targets=batch_targets,
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
