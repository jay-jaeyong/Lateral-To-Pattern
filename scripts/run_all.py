"""두 서비스를 순서대로 실행한다.

    python scripts/run_all.py --input inputs/photos/adidas_ORKETRO
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts._common import (  # noqa: E402
    DEFAULT_GUIDE, derive_label, run_labels, setup_logging, timestamp_label,
)
from services import engine  # noqa: E402
from services.color_pattern import service as color_pattern  # noqa: E402
from services.sketch_pattern import service as sketch_pattern  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="모든 서비스를 순서대로 실행합니다.")
    parser.add_argument("--input", required=True, help="inputs/photos/<신발>/")
    parser.add_argument("--out", default="outputs")
    parser.add_argument("--label", default=None)
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--guide", default=str(DEFAULT_GUIDE))
    parser.add_argument("--verbose", "-v", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    setup_logging(args.verbose)

    shoe_dir = Path(args.input)
    base = args.label or derive_label(shoe_dir) or timestamp_label()

    for label in run_labels(base, args.repeat):
        out = engine.RunOutput(Path(args.out), label)
        archive = engine.HistoryArchive()
        color_path = color_pattern.run(shoe_dir, Path(args.guide), out, archive)
        sketch_pattern.run(color_path, out, archive)
        out.save_final(text="", generated_images=[], chat_history=archive.all())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
