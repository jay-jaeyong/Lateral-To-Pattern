#!/usr/bin/env python3
"""가이드라인에 뒤축 절개면과 좌우 면을 문자로 표시합니다.

images/가이드라인.jpg → guides/가이드라인_절개표시.png

원본 가이드라인은 외곽 형태만 줍니다. 두 가지 정보가 이미지에 없었습니다.

1. 절개선 양옆 두 변이 실물에서 맞닿아 있던 한 자리라는 것
   → 뒤축 중앙 로고가 좌우에 온전히 복제되는 실패가 반복됐습니다.
2. 좌우 두 반쪽이 서로 다른 면(바깥쪽/안쪽)이라는 것
   → 한쪽 면에만 있는 부품이 양쪽에 대칭으로 그려지는 실패가 반복됐습니다.

처음에는 색(자홍·하늘·주황)으로 표시했으나 두 결함 모두 그대로였습니다.
그래서 프롬프트와 똑같은 문자를 직접 적습니다. 결과물에 이 글자가 나오면
안 된다는 것은 config/prompts.py의 guideline_rule이 막습니다. 표시의 뜻은
heel_rule(절개면)과 reconstruct_rule(좌우 면)이 설명합니다.

guides/는 .gitignore에 있어 추적되지 않습니다. 파일이 사라졌을 때 이 스크립트로
다시 만듭니다:  uv run python scripts/mark_guideline.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

SRC = Path("images/가이드라인.jpg")
DST = Path("guides/가이드라인_절개표시.png")

# 한글이 렌더링되는 폰트. 앞에 있는 것부터 시도합니다.
FONT_CANDIDATES = (
    "/System/Library/Fonts/AppleSDGothicNeo.ttc",
    "/System/Library/Fonts/Supplemental/AppleGothic.ttf",
)

INK = (0, 0, 0)

# 프롬프트가 쓰는 표현과 글자까지 똑같아야 합니다. 여기만 바꾸면 프롬프트와
# 어긋나므로 config/prompts.py도 같이 고쳐야 합니다.
CUT_TEXT = "절개면"
LATERAL_TEXT = "바깥쪽 측면(lateral)"
MEDIAL_TEXT = "안쪽 측면(medial)"

CUT_ROW = 95        # 절개면 두 변이 서로 마주보는 구간
FACE_ROW = 600      # 발목·설포 구조가 없는 몸통 구간
CUT_FONT_SIZE = 30
FACE_FONT_SIZE = 30
GAP = 12            # 선과 글자 사이 여백


def load_font(size: int) -> ImageFont.FreeTypeFont:
    for path in FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    raise SystemExit(
        "한글 폰트를 찾지 못했습니다. FONT_CANDIDATES에 사용 가능한 경로를 추가하세요."
    )


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


def cut_edges(image: Image.Image, y: int) -> tuple[int, int] | None:
    """절개면 두 변의 마주보는 쪽 x 좌표.

    한 행에는 잉크 구간이 네 개 있습니다(바깥 외곽선 2개 + 절개면 2개).
    가운데 두 개가 절개면입니다.
    """
    width = image.width
    middle = [r for r in ink_runs(image, y) if 150 < (r[0] + r[1]) / 2 < width - 150]
    if len(middle) != 2:
        return None
    return middle[0][1], middle[1][0]


def half_centers(image: Image.Image, y: int) -> tuple[int, int] | None:
    """좌우 두 반쪽의 가로 중심 x 좌표."""
    runs = ink_runs(image, y)
    if len(runs) < 3:
        return None
    outer_left, outer_right = runs[0][1], runs[-1][0]
    center = [r for r in runs[1:-1]]
    if not center:
        return None
    center_left, center_right = center[0][0], center[-1][1]
    return (outer_left + center_left) // 2, (center_right + outer_right) // 2


def draw_centered(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str, font) -> None:
    draw.text(xy, text, fill=INK, font=font, anchor="mm")


def main() -> None:
    image = Image.open(SRC).convert("RGB")
    draw = ImageDraw.Draw(image)
    cut_font = load_font(CUT_FONT_SIZE)
    face_font = load_font(FACE_FONT_SIZE)

    edges = cut_edges(image, CUT_ROW)
    if edges is None:
        raise SystemExit(f"y={CUT_ROW}에서 절개면을 찾지 못했습니다. {SRC}의 형태를 확인하세요.")
    left, right = edges
    # 절개면 두 변 바로 옆에, 패턴 몸통 쪽으로 적습니다. 두 변 사이 틈은
    # 좁아서 글자가 들어가지 않습니다.
    draw.text((left - GAP, CUT_ROW), CUT_TEXT, fill=INK, font=cut_font, anchor="rm")
    draw.text((right + GAP, CUT_ROW), CUT_TEXT, fill=INK, font=cut_font, anchor="lm")

    centers = half_centers(image, FACE_ROW)
    if centers is None:
        raise SystemExit(f"y={FACE_ROW}에서 좌우 반쪽을 찾지 못했습니다.")
    left_center, right_center = centers
    draw_centered(draw, (left_center, FACE_ROW), LATERAL_TEXT, face_font)
    draw_centered(draw, (right_center, FACE_ROW), MEDIAL_TEXT, face_font)

    DST.parent.mkdir(parents=True, exist_ok=True)
    image.save(DST)
    print(f"'{CUT_TEXT}' 2개, '{LATERAL_TEXT}'·'{MEDIAL_TEXT}' → {DST}")


if __name__ == "__main__":
    main()
