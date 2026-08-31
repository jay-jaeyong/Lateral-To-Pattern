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
from services.utils import images  # noqa: E402


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

    # sketch_pattern은 컬러 패턴 파일 하나 또는 그것들이 든 폴더를 받는다.
    # 폴더면 안의 이미지 파일마다 한 번씩 돌린다. 파일 stem을 레이블에 넣지
    # 않으면 여러 장을 처리할 때 출력이 서로 덮어쓴다.
    if args.service == "sketch_pattern" and source.is_dir():
        sources = [(f, f.stem) for f in images.list_image_files(source)]
        if not sources:
            raise FileNotFoundError(
                f"폴더에 지원하는 이미지 파일이 없습니다: {source}\n"
                f"지원 형식: {', '.join(images.SUPPORTED_EXTENSIONS)}"
            )
    else:
        sources = [(source, None)]

    for file_path, suffix in sources:
        file_base = f"{base}_{suffix}" if suffix else base
        for label in run_labels(file_base, args.repeat):
            out = engine.RunOutput(Path(args.out), label)
            archive = engine.HistoryArchive()
            if args.service == "color_pattern":
                module.run(file_path, Path(args.guide), out, archive)
            else:
                module.run(file_path, out, archive)
            out.save_final(text="", generated_images=[], chat_history=archive.all())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
