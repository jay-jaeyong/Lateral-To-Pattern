"""스크립트 공용 헬퍼."""

from __future__ import annotations

import logging
import sys
from datetime import datetime
from pathlib import Path

from services.color_pattern import service as color_pattern
from services.sketch_pattern import service as sketch_pattern
from utils.logging_utils import StepFilter

SERVICES = {
    "color_pattern": color_pattern,
    "sketch_pattern": sketch_pattern,
}

DEFAULT_GUIDE = Path("inputs/guides/가이드라인_회전5도_여백표시.png")


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
        for name in ("google_genai", "google_genai.models", "httpx", "urllib3"):
            logging.getLogger(name).setLevel(logging.WARNING)


def derive_label(input_path: Path) -> str:
    """입력 경로에서 실행 레이블을 만든다."""
    path = Path(input_path)
    return path.name if path.is_dir() else path.stem


def run_labels(label: str, repeat: int) -> list[str]:
    """--repeat 1이면 접미사를 붙이지 않는다."""
    if repeat <= 1:
        return [label]
    return [f"{label}-{n}" for n in range(1, repeat + 1)]


def timestamp_label() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")
