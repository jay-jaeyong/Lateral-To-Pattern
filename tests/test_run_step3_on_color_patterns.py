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

    def test_routes_output_to_v2_without_touching_source(self):
        source = Path("images/new_patterns/model_color.png")
        output = runner.sketch_output_path(source, Path("images/new_patterns/v2"))
        self.assertEqual(output, Path("images/new_patterns/v2/model_sketch.png"))

    def test_convert_one_postprocesses_before_save(self):
        raw = Image.new("RGB", (20, 20), "blue")
        processed = Image.new("RGB", (20, 20), "white")

        class FakeClient:
            def start_chat(self):
                pass

            def send(self, parts):
                from core.models import StepResponse
                return StepResponse(images=[raw])

        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            source = folder / "model_color.png"
            output_dir = folder / "v2"
            Image.new("RGB", (20, 20), "white").save(source)
            with patch.object(runner, "GeminiClient", return_value=FakeClient()), patch.object(
                runner, "postprocess_sketch", return_value=processed
            ) as postprocess:
                output = runner.convert_one(source, output_dir)

            self.assertIs(postprocess.call_args.args[0], raw)
            self.assertEqual(output, output_dir / "model_sketch.png")
            self.assertEqual(Image.open(output).getpixel((10, 10)), (255, 255, 255))


if __name__ == "__main__":
    unittest.main()
