#!/usr/bin/env python3
"""가이드라인 라벨을 패턴 밖 여백으로 빼서 표시합니다. (P3-1 실험, 안 1)

images/가이드라인.jpg → guides/가이드라인_여백표시.png

기존 guides/가이드라인_절개표시.png는 라벨을 패턴 내부 빈 공간에 크게 적었습니다.
P3 실험에서 그것이 SONOMA의 아식스 교차 스트라이프 소실과 외곽 둥글어짐의
단독 원인으로 확인됐습니다(v19 2/2 실패 → v20 2/2 복원, Step 1 명세서 동일).

모델이 그 이미지를 '따라 그릴 재단 틀'이 아니라 '주석 달린 설명 도해'로 읽는
것으로 봅니다. 그래서 정보는 유지하되 글자를 패턴 바깥으로 옮깁니다.

  - 캔버스를 좌우·위로 넓히고 원본 형태는 한 픽셀도 건드리지 않습니다.
  - 라벨은 넓힌 여백에만 놓고, 얇은 회색 지시선으로 대상을 가리킵니다.
  - 지시선은 외곽선에 닿기 전에 멈춥니다(패턴 내부로 들어가지 않습니다).
  - 좌우 면 라벨은 90도 돌려서 좁은 여백에 넣습니다.

프롬프트가 지칭하는 글자는 그대로이므로 config/prompts.py 수정이 필요 없습니다.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# 입력·출력을 인자로 받습니다. 비대칭 판본에도 같은 라벨을 얹기 위한 것입니다.
#   uv run python scripts/mark_guideline_margin.py \
#       guides/가이드라인_비대칭.png guides/가이드라인_비대칭_여백표시.png
SRC = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("images/가이드라인.jpg")
DST = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("guides/가이드라인_여백표시.png")

FONT_CANDIDATES = (
    "/System/Library/Fonts/AppleSDGothicNeo.ttc",
    "/System/Library/Fonts/Supplemental/AppleGothic.ttf",
)

INK = (0, 0, 0)
LEADER = (150, 150, 150)      # 지시선. 패턴 재단선과 구별되도록 옅은 회색
FONT_SIZE = 30

# 넓히는 여백. 라벨과 지시선은 전부 이 안에만 들어갑니다.
PAD_L = PAD_R = 190
PAD_T = 110
PAD_B = 0

CUT_TEXT = "절개면"
LATERAL_TEXT = "바깥쪽 측면(lateral)"
MEDIAL_TEXT = "안쪽 측면(medial)"

CUT_ROW = 110      # 절개면 두 변이 마주보는 구간 (원본 좌표)
FACE_ROW = 640     # 발목·설포 구조가 없는 몸통 구간 (원본 좌표)


def load_font(size: int) -> ImageFont.FreeTypeFont:
    for path in FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    raise SystemExit("한글 폰트를 찾지 못했습니다.")


def ink_runs(image: Image.Image, y: int, threshold: int = 200) -> list[tuple[int, int]]:
    """y행의 잉크 구간들을 왼쪽부터 반환합니다."""
    width = image.width
    px = image.load()
    cols = [x for x in range(width) if min(px[x, y]) < threshold]
    if not cols:
        return []
    runs: list[tuple[int, int]] = []
    start = cols[0]
    for a, b in zip(cols, cols[1:]):
        if b - a > 5:
            runs.append((start, a))
            start = b
    runs.append((start, cols[-1]))
    return runs


def cut_edges(image: Image.Image, y: int) -> tuple[int, int]:
    """절개면 두 변의 마주보는 쪽 x 좌표 (원본 좌표)."""
    width = image.width
    middle = [r for r in ink_runs(image, y) if 150 < (r[0] + r[1]) / 2 < width - 150]
    if len(middle) != 2:
        raise SystemExit(f"y={y}에서 절개면을 찾지 못했습니다.")
    return middle[0][1], middle[1][0]


def outer_edges(image: Image.Image, y: int) -> tuple[int, int]:
    """외곽선 좌우 x 좌표 (원본 좌표)."""
    runs = ink_runs(image, y)
    if len(runs) < 2:
        raise SystemExit(f"y={y}에서 외곽선을 찾지 못했습니다.")
    return runs[0][0], runs[-1][1]


def paste_rotated(canvas: Image.Image, text: str, font, center: tuple[int, int],
                  angle: int) -> None:
    """글자를 회전시켜 좁은 여백에 넣습니다."""
    left, top, right, bottom = font.getbbox(text)
    strip = Image.new("RGBA", (right - left + 8, bottom - top + 8), (0, 0, 0, 0))
    ImageDraw.Draw(strip).text((4 - left, 4 - top), text, fill=INK + (255,), font=font)
    strip = strip.rotate(angle, expand=True, resample=Image.BICUBIC)
    canvas.paste(strip, (center[0] - strip.width // 2, center[1] - strip.height // 2), strip)


def main() -> None:
    src = Image.open(SRC).convert("RGB")

    cut_left, cut_right = cut_edges(src, CUT_ROW)
    outer_left, outer_right = outer_edges(src, FACE_ROW)

    canvas = Image.new("RGB", (src.width + PAD_L + PAD_R, src.height + PAD_T + PAD_B),
                       (255, 255, 255))
    canvas.paste(src, (PAD_L, PAD_T))
    draw = ImageDraw.Draw(canvas)
    font = load_font(FONT_SIZE)

    # ── 절개면: 위쪽 여백에 적고 두 변으로 지시선을 내림 ──────────────────
    # 지시선은 두 절개면 사이의 빈 구간(설포·throat 자리)만 지나갑니다.
    cut_y = CUT_ROW + PAD_T
    for edge_x, side in ((cut_left + PAD_L, -1), (cut_right + PAD_L, +1)):
        text_x = edge_x + side * 78
        draw.text((text_x, 46), CUT_TEXT, fill=INK, font=font, anchor="mm")
        draw.line([(text_x, 68), (edge_x + side * 6, cut_y - 4)], fill=LEADER, width=2)

    # ── 좌우 면: 바깥 여백에 90도로 세워 적고 외곽선 앞까지 지시선 ────────
    face_y = FACE_ROW + PAD_T
    left_x, right_x = outer_left + PAD_L, outer_right + PAD_L
    paste_rotated(canvas, LATERAL_TEXT, font, (PAD_L // 2 - 8, face_y), 90)
    paste_rotated(canvas, MEDIAL_TEXT, font, (canvas.width - PAD_R // 2 + 8, face_y), -90)
    draw.line([(PAD_L // 2 + 26, face_y), (left_x - 10, face_y)], fill=LEADER, width=2)
    draw.line([(canvas.width - PAD_R // 2 - 26, face_y), (right_x + 10, face_y)],
              fill=LEADER, width=2)

    DST.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(DST)
    print(f"{DST}  ({canvas.width}x{canvas.height})")
    print(f"  절개면 → x={cut_left},{cut_right} (원본) / 좌우면 → x={outer_left},{outer_right}")


if __name__ == "__main__":
    main()
