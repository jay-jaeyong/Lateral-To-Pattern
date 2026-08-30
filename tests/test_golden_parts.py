"""재구조화 전후로 Gemini가 받는 것이 동일한지 검증한다.

이 파일 자체는 재구조화 때 다시 쓰인다. 호출 진입점이 Pipeline에서
서비스 함수로 바뀌기 때문이다. 그러나 tests/golden/*.json은
한 바이트도 바뀌면 안 된다.
"""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from PIL import Image

import core.pipeline as pipeline_module
from config.prompts import PIPELINE_STEPS
from core.models import StepResponse
from core.pipeline import Pipeline
from tests.golden_parts import (
    RecordingClient,
    assert_golden,
    make_fixture_color_pattern,
    make_fixture_guide,
    make_fixture_photos,
)


class GoldenPartsTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.out = self.tmp / "out"

    def _run_pipeline(self, color_pattern_image):
        photos = make_fixture_photos(self.tmp / "photos")
        guide = make_fixture_guide(self.tmp / "guides")

        steps = [dict(s) for s in PIPELINE_STEPS]
        steps[0]["image_path"] = None
        steps[0]["view_images"] = photos
        steps[1]["guide_image_path"] = guide

        client = RecordingClient([
            StepResponse(text='{"분석대상짝": "왼발", "부품목록": [], "표식목록": [], "미확인목록": []}', images=[]),
            StepResponse(text="", images=[color_pattern_image]),
            StepResponse(text="", images=[Image.new("RGB", (4, 4))]),
        ])
        with patch.object(pipeline_module, "GeminiClient", lambda *a, **k: client), \
             patch.object(pipeline_module.OutputHandler, "save_step"), \
             patch.object(pipeline_module.OutputHandler, "save_final"):
            Pipeline(steps=steps, output_dir=self.out, run_label="golden").run(
                skip_initial_selection=True
            )
        return client.calls

    def test_golden_color_pattern_step_1(self):
        calls = self._run_pipeline(Image.new("RGB", (10, 15), (200, 30, 30)))
        assert_golden(self, "color_pattern__step_1_part_survey", calls[0])

    def test_golden_color_pattern_step_2(self):
        calls = self._run_pipeline(Image.new("RGB", (10, 15), (200, 30, 30)))
        assert_golden(self, "color_pattern__step_2_pattern_unfold", calls[1])

    def test_golden_sketch_pattern_step_1(self):
        color = Image.open(make_fixture_color_pattern(self.tmp / "patterns")).convert("RGB")
        calls = self._run_pipeline(color)
        assert_golden(self, "sketch_pattern__step_1_line_art", calls[2])


if __name__ == "__main__":
    unittest.main()
