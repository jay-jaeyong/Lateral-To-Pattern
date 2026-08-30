"""재구조화 전후로 Gemini가 받는 것이 동일한지 검증한다.

이 파일 자체는 재구조화 때 다시 쓰인다. 호출 진입점이 Pipeline에서
서비스 함수로 바뀌기 때문이다. 그러나 tests/golden/*.json은
한 바이트도 바뀌면 안 된다.
"""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from services import engine
from services.engine import StepResponse
from services.color_pattern import service as cp_service
from services.sketch_pattern import service as sp_service
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

    def _run_color_pattern(self):
        shoe = self.tmp / "photos" / "shoe"
        make_fixture_photos(shoe)
        guide = make_fixture_guide(self.tmp / "guides")
        client = RecordingClient([
            StepResponse(
                text='{"분석대상짝": "왼발", "부품목록": [], "표식목록": [], "미확인목록": []}',
                images=[],
            ),
            StepResponse(text="", images=[Image.new("RGB", (10, 15))]),
        ])
        out = engine.RunOutput(self.tmp / "outputs", "golden")
        with patch.object(cp_service.engine, "new_session", lambda model: client):
            cp_service.run(shoe, guide, out)
        return client.calls

    def test_golden_color_pattern_step_1(self):
        calls = self._run_color_pattern()
        assert_golden(self, "color_pattern__step_1_part_survey", calls[0])

    def test_golden_color_pattern_step_2(self):
        calls = self._run_color_pattern()
        assert_golden(self, "color_pattern__step_2_pattern_unfold", calls[1])

    def test_golden_sketch_pattern_step_1(self):
        color = make_fixture_color_pattern(self.tmp / "patterns")
        client = RecordingClient([engine.StepResponse(text="", images=[Image.new("RGB", (4, 4))])])
        out = engine.RunOutput(self.tmp / "outputs", "golden")
        with patch.object(sp_service.engine, "new_session", lambda model: client):
            sp_service.run(color, out)
        assert_golden(self, "sketch_pattern__step_1_line_art", client.calls[0])


if __name__ == "__main__":
    unittest.main()
