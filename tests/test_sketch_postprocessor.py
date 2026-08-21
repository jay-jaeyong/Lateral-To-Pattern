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
        image = Image.new("RGB", (31, 47), (240, 200, 120))
        result = postprocess_sketch(image, line_width=3)

        self.assertEqual(result.size, image.size)
        self.assertEqual(result.mode, "RGB")
        self.assertLessEqual(set(result.getdata()), {(0, 0, 0), (255, 255, 255)})


if __name__ == "__main__":
    unittest.main()
