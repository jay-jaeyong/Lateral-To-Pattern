"""서비스 하나를 실행한다.

    python scripts/run_service.py color_pattern  --input inputs/photos/adidas_ORKETRO
    python scripts/run_service.py sketch_pattern --input inputs/color_patterns/a_color.png
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts._common import (  # noqa: E402
    DEFAULT_GUIDE, SERVICES, derive_label, run_labels, setup_logging, timestamp_label,
)
from services import engine  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="서비스 하나를 실행합니다.")
    parser.add_argument("service", choices=sorted(SERVICES))
    parser.add_argument("--input", required=True,
                        help="color_pattern이면 inputs/photos/<신발>/, "
                             "sketch_pattern이면 컬러 패턴 파일 또는 폴더")
    parser.add_argument("--out", default="outputs")
    parser.add_argument("--label", default=None)
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--guide", default=str(DEFAULT_GUIDE))
    parser.add_argument("--verbose", "-v", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    setup_logging(args.verbose)

    module = SERVICES[args.service]
    source = Path(args.input)
    base = args.label or derive_label(source) or timestamp_label()

    for label in run_labels(base, args.repeat):
        out = engine.RunOutput(Path(args.out), label)
        archive = engine.HistoryArchive()
        if args.service == "color_pattern":
            module.run(source, Path(args.guide), out, archive)
        else:
            module.run(source, out, archive)
        out.save_final(text="", generated_images=[], chat_history=archive.all())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
