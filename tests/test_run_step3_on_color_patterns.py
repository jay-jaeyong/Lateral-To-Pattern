import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from scripts import run_step3_on_color_patterns as runner


class Step3BatchRunnerTest(unittest.TestCase):
    def test_discovers_only_color_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            Image.new("RGB", (2, 2), "white").save(folder / "a_color.png")
            Image.new("RGB", (2, 2), "white").save(folder / "a_sketch.png")
            self.assertEqual(
                [path.name for path in runner.find_color_patterns(folder)],
                ["a_color.png"],
            )

    def test_routes_output_to_v3_without_touching_source(self):
        source = Path("images/new_patterns/model_color.png")
        output = runner.sketch_output_path(source, Path("images/new_patterns/v3"))
        self.assertEqual(output, Path("images/new_patterns/v3/model_sketch.png"))

    def test_convert_one_passes_input_aspect_config_and_saves_raw_image(self):
        raw = Image.new("RGB", (20, 30), "blue")
        sent_configs = []

        class FakeClient:
            def start_chat(self):
                pass

            def send(self, parts, config=None):
                from core.models import StepResponse

                sent_configs.append(config)
                return StepResponse(images=[raw])

        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            source = folder / "model_color.png"
            output_dir = folder / "v3"
            Image.new("RGB", (20, 30), "white").save(source)

            with patch.object(runner, "GeminiClient", return_value=FakeClient()):
                output = runner.convert_one(source, output_dir)

            self.assertEqual(output, output_dir / "model_sketch.png")
            self.assertEqual(sent_configs[0].image_config.image_size, "4K")
            self.assertIsNone(sent_configs[0].image_config.aspect_ratio)
            self.assertEqual(Image.open(output).getpixel((10, 15)), (0, 0, 255))

    def test_convert_one_does_not_regenerate_when_response_has_no_image(self):
        class FakeClient:
            def __init__(self):
                self.send_calls = 0

            def start_chat(self):
                pass

            def send(self, parts, config=None):
                from core.models import StepResponse

                self.send_calls += 1
                return StepResponse(text="no image", images=[])

        client = FakeClient()
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            source = folder / "model_color.png"
            output_dir = folder / "v3"
            Image.new("RGB", (20, 30), "white").save(source)

            with patch.object(runner, "GeminiClient", return_value=client):
                output = runner.convert_one(source, output_dir)

            self.assertIsNone(output)
            self.assertEqual(client.send_calls, 1)
            self.assertFalse((output_dir / "model_sketch.png").exists())

    def test_convert_one_skips_when_output_already_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            source = folder / "model_color.png"
            output_dir = folder / "v3"
            output_dir.mkdir(parents=True)
            Image.new("RGB", (20, 20), "white").save(source)

            existing_out = output_dir / "model_sketch.png"
            Image.new("RGB", (5, 5), "black").save(existing_out)
            existing_bytes = existing_out.read_bytes()

            with patch.object(
                runner, "GeminiClient", side_effect=AssertionError("should not be called")
            ):
                output = runner.convert_one(source, output_dir)

            self.assertEqual(output, existing_out)
            self.assertEqual(existing_out.read_bytes(), existing_bytes)


if __name__ == "__main__":
    unittest.main()
