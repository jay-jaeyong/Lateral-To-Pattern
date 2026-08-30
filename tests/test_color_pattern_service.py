"""color_pattern 서비스 테스트."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image
from pydantic import ValidationError

from services import engine
from services.color_pattern import photo_input, service, step_1_part_survey
from tests.golden_parts import RecordingClient


VALID_SURVEY = (
    '{"분석대상짝": "왼발", "부품목록": [], "표식목록": [], "미확인목록": []}'
)


class SurveyValidationTest(unittest.TestCase):
    def test_broken_json_raises_at_step_1(self):
        """지금은 빈 응답이나 깨진 JSON이 Step 2까지 조용히 흘러간다."""
        client = RecordingClient([engine.StepResponse(text="not json", images=[])])
        with self.assertRaises(ValidationError):
            step_1_part_survey.run(client, [])

    def test_empty_response_raises_at_step_1(self):
        client = RecordingClient([engine.StepResponse(text="", images=[])])
        with self.assertRaises(ValidationError):
            step_1_part_survey.run(client, [])

    def test_valid_survey_returns_the_raw_text_unchanged(self):
        """검증은 하되 재직렬화하지 않는다. 키 순서나 공백이 달라지면
        Step 2가 보는 토큰이 달라진다."""
        client = RecordingClient([engine.StepResponse(text=VALID_SURVEY, images=[])])
        self.assertEqual(step_1_part_survey.run(client, []), VALID_SURVEY)


class ServiceTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.shoe = self.tmp / "photos" / "shoe"
        self.shoe.mkdir(parents=True)
        for name in ("lateral.png", "medial.png"):
            Image.new("RGB", (4, 4)).save(self.shoe / name)
        self.guide = self.tmp / "가이드라인.png"
        Image.new("RGB", (4, 4)).save(self.guide)

    def _run(self):
        client = RecordingClient([
            engine.StepResponse(text=VALID_SURVEY, images=[]),
            engine.StepResponse(text="", images=[Image.new("RGB", (4, 4))]),
        ])
        out = engine.RunOutput(self.tmp / "outputs", "run1")
        with patch.object(service.engine, "new_session", lambda model: client):
            path = service.run(self.shoe, self.guide, out)
        return client, path

    def test_service_opens_exactly_one_session_for_two_steps(self):
        """두 스텝은 세션을 공유한다. 정면·뒤꿈치·위 사진이 히스토리로만
        Step 2에 닿는 현 구조를 유지하기 위해서다."""
        client, _ = self._run()
        self.assertEqual(len(client.calls), 2)

    def test_step_1_survey_text_reaches_step_2_verbatim(self):
        client, _ = self._run()
        step2_texts = [p for p in client.calls[1]["parts"] if p["kind"] == "text"]
        self.assertTrue(any(
            t["len"] == len(f"[Previous Step 1 Output]\n{VALID_SURVEY}")
            for t in step2_texts
        ))

    def test_service_returns_the_saved_color_pattern_path(self):
        """서비스 간 핸드오프는 파일이다."""
        _, path = self._run()
        self.assertTrue(path.exists())
        self.assertEqual(path.suffix, ".png")
        self.assertEqual(path.parent.name, "color_pattern")

    def test_model_is_declared_by_the_service(self):
        self.assertEqual(service.MODEL, "gemini-3.1-flash-image")


if __name__ == "__main__":
    unittest.main()
