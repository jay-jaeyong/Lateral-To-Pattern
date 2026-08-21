#!/usr/bin/env python3
"""images/color_patterns의 *_color 이미지에 Step 3 프롬프트를 적용합니다.

Step 3(line_art_conversion)는 파이프라인에서 enabled=False로 꺼져 있어
main.py 실행으로는 도달하지 않습니다. 이미 만들어둔 컬러 패턴들에 대해
스케치 패턴 변환만 독립적으로 돌려볼 때 이 스크립트를 씁니다.

각 컬러 패턴은 독립된 요청이라 서로의 채팅 히스토리를 공유할 필요가
없으므로 이미지마다 새 GeminiClient(=새 채팅 세션)를 만들어 스레드로
병렬 실행합니다.

사용법:
    uv run python scripts/run_step3_on_color_patterns.py
"""

from __future__ import annotations

import logging
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.pipeline import Pipeline  # noqa: F401  (import 순서로 순환참조를 피함)
from config.prompts import PIPELINE_STEPS
from handlers.image_handler import ImageHandler
from services.gemini_client import GeminiClient
from utils.sketch_postprocessor import postprocess_sketch

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger("run_step3_on_color_patterns")
logging.getLogger("google_genai").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)

SRC_DIR = Path("images/new_patterns")
OUT_DIR = SRC_DIR / "v2"
STEP3_PROMPT = next(s["prompt"] for s in PIPELINE_STEPS if s["name"] == "line_art_conversion")
MAX_WORKERS = 6


def find_color_patterns(folder: Path) -> list[Path]:
    files = ImageHandler.list_image_files(folder, exclude_guideline=True)
    return [f for f in files if "_color" in f.stem]


def sketch_output_path(color_path: Path, output_dir: Path = OUT_DIR) -> Path:
    stem = color_path.stem
    new_stem = stem.replace("_color", "_sketch") if "_color" in stem else f"{stem}_sketch"
    return output_dir / f"{new_stem}.png"


def convert_one(color_path: Path, output_dir: Path = OUT_DIR) -> Path | None:
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = sketch_output_path(color_path, output_dir)
    logger.info("시작: %s → %s", color_path.name, out_path.name)

    image = ImageHandler.load(color_path)
    client = GeminiClient()
    client.start_chat()
    response = client.send([image, STEP3_PROMPT])

    if not response.images:
        logger.error("실패(이미지 없음): %s — 응답 텍스트: %s", color_path.name, response.text[:300])
        return None

    postprocess_sketch(response.images[0]).save(out_path)
    logger.info("완료: %s", out_path)
    return out_path


def main() -> None:
    targets = find_color_patterns(SRC_DIR)
    if not targets:
        logger.error("%s 안에 '_color'가 포함된 이미지가 없습니다.", SRC_DIR)
        sys.exit(1)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    logger.info("대상 %d개, 동시 실행 %d개", len(targets), MAX_WORKERS)

    succeeded: list[Path] = []
    failed: list[Path] = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        future_to_path = {pool.submit(convert_one, path, OUT_DIR): path for path in targets}
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
