#!/usr/bin/env python3
"""images/new_patterns의 *_color 이미지에 Step 3 프롬프트를 적용합니다.

Step 3(line_art_conversion)는 파이프라인에서도 실행되지만, 그 경로는 앞
단계가 방금 만든 패턴만 받습니다. 이미 폴더에 만들어둔 컬러 패턴들을
Step 1·2 없이 일괄로 다시 변환할 때 이 스크립트를 씁니다.

각 컬러 패턴은 독립된 요청이라 서로의 채팅 히스토리를 공유할 필요가
없으므로 이미지마다 새 GeminiClient(=새 채팅 세션)를 만들어 스레드로
병렬 실행합니다.

사용법:
    uv run python scripts/run_step3_on_color_patterns.py
    uv run python scripts/run_step3_on_color_patterns.py <입력폴더> <출력폴더>

인자를 주지 않으면 images/new_patterns 를 읽어 images/new_patterns/v3 에 씁니다.
"""

from __future__ import annotations

import logging
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import core  # noqa: F401  (services보다 먼저 core를 로드해 core.pipeline<->services.gemini_client 순환참조를 피함)
from config.gemini_config import build_response_config
from config.prompts import ORIGINAL_PATTERN_LABEL, PIPELINE_STEPS
from handlers.image_handler import ImageHandler
from services.gemini_client import GeminiClient

logger = logging.getLogger("run_step3_on_color_patterns")

SRC_DIR = Path("images/new_patterns")
STEP3 = next(
    step for step in PIPELINE_STEPS if step["name"] == "line_art_conversion"
)
OUT_DIR = SRC_DIR / "v3"
STEP3_PROMPT = STEP3["prompt"]
MAX_WORKERS = 6



def find_color_patterns(folder: Path) -> list[Path]:
    files = ImageHandler.list_image_files(folder, exclude_guideline=True)
    return [f for f in files if "_color" in f.stem]


def _renamed(color_path: Path, suffix: str, output_dir: Path) -> Path:
    stem = color_path.stem
    new_stem = stem.replace("_color", suffix) if "_color" in stem else f"{stem}{suffix}"
    return output_dir / f"{new_stem}.png"


def sketch_output_path(color_path: Path, output_dir: Path = OUT_DIR) -> Path:
    return _renamed(color_path, "_sketch", output_dir)


def convert_one(color_path: Path, output_dir: Path = OUT_DIR) -> Path | None:
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = sketch_output_path(color_path, output_dir)
    if out_path.exists():
        logger.info("건너뜀(이미 있음): %s", out_path.name)
        return out_path
    logger.info("시작: %s → %s", color_path.name, out_path.name)

    image = ImageHandler.load(color_path)

    label = ImageHandler.LABEL_FORMAT.format
    parts = [label(label=ORIGINAL_PATTERN_LABEL), image, STEP3_PROMPT]

    client = GeminiClient()
    client.start_chat()
    response = client.send(
        parts,
        config=build_response_config(
            None,
            match_input_aspect_ratio=STEP3.get(
                "match_input_aspect_ratio", False
            ),
        ),
    )

    if not response.images:
        logger.error("실패(이미지 없음): %s — 응답 텍스트: %s", color_path.name, response.text[:300])
        return None

    response.images[0].save(out_path)
    logger.info("완료: %s", out_path)
    return out_path


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
    logging.getLogger("google_genai").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)

    src_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else SRC_DIR
    out_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else OUT_DIR

    targets = find_color_patterns(src_dir)
    if not targets:
        logger.error("%s 안에 '_color'가 포함된 이미지가 없습니다.", src_dir)
        sys.exit(1)

    out_dir.mkdir(parents=True, exist_ok=True)
    logger.info("%s → %s / 대상 %d개, 동시 실행 %d개", src_dir, out_dir, len(targets), MAX_WORKERS)

    succeeded: list[Path] = []
    failed: list[Path] = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        future_to_path = {pool.submit(convert_one, path, out_dir): path for path in targets}
        for future in as_completed(future_to_path):
            path = future_to_path[future]
            try:
                result = future.result()
                (succeeded if result else failed).append(path)
            except Exception:
                logger.exception("예외로 실패: %s", path.name)
                failed.append(path)

    logger.info("=" * 60)
    logger.info("완료 %d개 / 실패 %d개", len(succeeded), len(failed))
    if failed:
        logger.info("실패 목록: %s", ", ".join(p.name for p in failed))
        sys.exit(1)


if __name__ == "__main__":
    main()
