from __future__ import annotations

from PIL import Image, ImageChops, ImageFilter

REFERENCE_SHORT_SIDE = 3392
REFERENCE_LINE_WIDTH = 5
WHITE_THRESHOLD = 250


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
    centerlines = _skeletonize(retained_lines)
    normalized_lines = centerlines.filter(ImageFilter.MaxFilter(width))

    white = Image.new("L", image.size, 255)
    white.paste(0, mask=normalized_lines)
    return Image.merge("RGB", (white, white, white))
