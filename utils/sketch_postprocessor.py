from __future__ import annotations

import io

from PIL import Image, ImageChops, ImageFilter

REFERENCE_SHORT_SIDE = 3392
REFERENCE_LINE_WIDTH = 5
WHITE_THRESHOLD = 250


def _as_pil_image(image):
    """Gemini가 돌려주는 genai.types.Image를 PIL Image로 바꿉니다.

    postprocess_sketch는 PIL Image(.size, .load() 등)를 요구하지만, API 응답의
    생성 이미지는 이미 PIL 타입인 경우도(테스트) 있고 genai.types.Image인
    경우도(실제 API 호출) 있어 여기서 통일합니다. 이미 PIL Image면 그대로
    반환합니다(같은 객체를 유지해야 하는 호출부가 있음).
    """
    if isinstance(image, Image.Image):
        return image
    return Image.open(io.BytesIO(image.image_bytes))


def scaled_line_width(size: tuple[int, int]) -> int:
    width = max(1, round(min(size) * REFERENCE_LINE_WIDTH / REFERENCE_SHORT_SIDE))
    return width if width % 2 else width + 1


def _nonwhite_mask(image: Image.Image) -> Image.Image:
    red, green, blue = image.convert("RGB").split()
    darkest = ImageChops.darker(red, ImageChops.darker(green, blue))
    return darkest.point(lambda value: 255 if value < WHITE_THRESHOLD else 0)


def _skeletonize(mask: Image.Image) -> Image.Image:
    current = mask
    skeleton = Image.new("L", mask.size, 0)
    while current.getbbox() is not None:
        eroded = current.filter(ImageFilter.MinFilter(3))
        opened = eroded.filter(ImageFilter.MaxFilter(3))
        skeleton = ImageChops.lighter(
            skeleton,
            ImageChops.subtract(current, opened),
        )
        current = eroded
    return skeleton


def postprocess_sketch(
    image: Image.Image,
    line_width: int | None = None,
) -> Image.Image:
    width = line_width or scaled_line_width(image.size)
    ink = _nonwhite_mask(image)
    core = ink.filter(ImageFilter.MinFilter(width * 2 + 1))
    retained_lines = ImageChops.subtract(ink, core)
    if ink.getbbox() and not retained_lines.getbbox():
        raise ValueError("배경이 순백이 아니어서 전체 캔버스가 채움으로 판정되었습니다")
    centerlines = _skeletonize(retained_lines)
    normalized_lines = centerlines.filter(ImageFilter.MaxFilter(width))

    white = Image.new("L", image.size, 255)
    white.paste(0, mask=normalized_lines)
    return Image.merge("RGB", (white, white, white))
