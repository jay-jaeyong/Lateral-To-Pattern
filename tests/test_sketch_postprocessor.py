import unittest

from PIL import Image, ImageDraw

from utils.sketch_postprocessor import postprocess_sketch, scaled_line_width


class SketchPostprocessorTest(unittest.TestCase):
    def test_scales_five_pixels_from_reference_short_side(self):
        self.assertEqual(scaled_line_width((3392, 5056)), 5)
        self.assertEqual(scaled_line_width((6784, 10112)), 11)

    def test_hollows_black_gray_and_colored_fills(self):
        image = Image.new("RGB", (80, 40), "white")
        draw = ImageDraw.Draw(image)
        draw.rectangle((5, 5, 24, 34), fill="black")
        draw.rectangle((30, 5, 49, 34), fill=(120, 120, 120))
        draw.rectangle((55, 5, 74, 34), fill=(20, 80, 220))

        result = postprocess_sketch(image, line_width=3)

        for point in ((14, 20), (39, 20), (64, 20)):
            self.assertEqual(result.getpixel(point), (255, 255, 255))
        for point in ((5, 20), (30, 20), (55, 20)):
            self.assertEqual(result.getpixel(point), (0, 0, 0))

    def test_preserves_thin_connected_lines(self):
        image = Image.new("RGB", (50, 50), "white")
        draw = ImageDraw.Draw(image)
        draw.line((5, 25, 45, 25), fill=(100, 100, 100), width=1)
        draw.line((25, 5, 25, 45), fill=(10, 10, 10), width=1)

        result = postprocess_sketch(image, line_width=3)

        self.assertEqual(result.getpixel((25, 25)), (0, 0, 0))
        self.assertEqual(result.getpixel((5, 25)), (0, 0, 0))
        self.assertEqual(result.getpixel((25, 5)), (0, 0, 0))

    def test_preserves_closed_circle_and_ellipse(self):
        image = Image.new("RGB", (80, 50), "white")
        draw = ImageDraw.Draw(image)
        draw.ellipse((5, 10, 25, 30), outline="black", width=1)
        draw.ellipse((35, 10, 70, 30), outline="black", width=1)

        result = postprocess_sketch(image, line_width=3)

        self.assertEqual(result.getpixel((5, 20)), (0, 0, 0))
        self.assertEqual(result.getpixel((15, 10)), (0, 0, 0))
        self.assertEqual(result.getpixel((35, 20)), (0, 0, 0))
        self.assertEqual(result.getpixel((52, 10)), (0, 0, 0))

    def test_output_is_binary_rgb_with_unchanged_canvas(self):
        image = Image.new("RGB", (31, 47), "white")
        draw = ImageDraw.Draw(image)
        draw.rectangle((5, 5, 25, 40), fill=(240, 200, 120))
        result = postprocess_sketch(image, line_width=3)

        self.assertEqual(result.size, image.size)
        self.assertEqual(result.mode, "RGB")
        self.assertLessEqual(set(result.getdata()), {(0, 0, 0), (255, 255, 255)})

    def test_raises_when_background_is_not_pure_white(self):
        """배경이 순백(darkest channel < 250)이 아니면 캔버스 전체가 ink로
        판정되어 아무 선도 살아남지 못한다 — 이때는 조용히 빈 이미지를 내놓지
        않고 명확히 실패해야 한다."""
        image = Image.new("RGB", (40, 40), (240, 240, 240))
        draw = ImageDraw.Draw(image)
        draw.rectangle((10, 10, 29, 29), fill="black")

        with self.assertRaises(ValueError):
            postprocess_sketch(image, line_width=3)

    def test_pure_white_blank_input_does_not_raise(self):
        """선이 전혀 없는 순백 입력은 ink 자체가 비어 있으므로(getbbox() is
        None) 예외를 던지지 말고 그대로 흰 이미지를 반환해야 한다."""
        image = Image.new("RGB", (40, 40), "white")

        result = postprocess_sketch(image, line_width=3)

        self.assertEqual(set(result.getdata()), {(255, 255, 255)})

    def test_touching_fills_lose_their_shared_internal_boundary(self):
        """알고리즘이 흑백 마스크만 보므로, 흰 여백 없이 맞닿은 두 채움 영역의
        경계는 사라지고 외곽 실루엣만 남는다 — 이것은 알려진 한계다."""
        image = Image.new("RGB", (60, 40), "white")
        draw = ImageDraw.Draw(image)
        draw.rectangle((5, 5, 29, 34), fill=(20, 80, 220))
        draw.rectangle((30, 5, 54, 34), fill=(220, 80, 20))  # touches at x=29/30, no white gap

        result = postprocess_sketch(image, line_width=3)

        # 맞닿은 경계(x=29~30 부근)는 사라져야 한다 — 두 영역이 하나로 합쳐진다는 뜻
        self.assertEqual(result.getpixel((29, 20)), (255, 255, 255))
        self.assertEqual(result.getpixel((30, 20)), (255, 255, 255))

    def test_a_stroke_near_the_hollowing_threshold_becomes_a_double_line(self):
        """굵기가 2*line_width+1 근처인 선은 홀로우잉 임계값을 넘어 두 개의
        평행선으로 갈라진다 — 알려진 한계다."""
        image = Image.new("RGB", (60, 60), "white")
        draw = ImageDraw.Draw(image)
        draw.rectangle((10, 25, 49, 25 + 14), fill="black")  # 15px thick horizontal band

        result = postprocess_sketch(image, line_width=3)

        column = [result.getpixel((30, y))[0] for y in range(20, 45)]
        black_runs = []
        in_run = False
        for value in column:
            if value == 0 and not in_run:
                black_runs.append(1)
                in_run = True
            elif value == 0:
                black_runs[-1] += 1
            else:
                in_run = False
        self.assertEqual(len(black_runs), 2, f"expected two separate black runs (doubled line), got {black_runs}")


if __name__ == "__main__":
    unittest.main()
