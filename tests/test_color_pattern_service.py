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

    def _run(self, archive=None):
        survey_client = RecordingClient([
            engine.StepResponse(text=VALID_SURVEY, images=[]),
        ])
        unfold_client = RecordingClient([
            engine.StepResponse(text="", images=[Image.new("RGB", (4, 4))]),
        ])
        clients = [survey_client, unfold_client]
        models: list[str] = []

        def fake_new_session(model):
            models.append(model)
            return clients.pop(0)

        out = engine.RunOutput(self.tmp / "outputs", "run1")
        with patch.object(service.engine, "new_session", fake_new_session):
            path = service.run(self.shoe, self.guide, out, archive=archive)
        return survey_client, unfold_client, models, path

    def test_service_opens_two_sessions_for_two_steps(self):
        """Step 1과 Step 2는 서로 다른 모델을 쓰므로 세션도 따로 연다.
        세션이 갈리면서 정면·위 사진은 더 이상 Step 2로 넘어가지 않는다."""
        survey_client, unfold_client, models, _ = self._run()
        self.assertEqual(models, [service.PART_SURVEY_MODEL, service.PATTERN_UNFOLD_MODEL])
        self.assertEqual(len(survey_client.calls), 1)
        self.assertEqual(len(unfold_client.calls), 1)

    def test_step_1_survey_text_reaches_step_2_verbatim(self):
        _, unfold_client, _, _ = self._run()
        step2_texts = [p for p in unfold_client.calls[0]["parts"] if p["kind"] == "text"]
        self.assertTrue(any(
            t["len"] == len(f"[Previous Step 1 Output]\n{VALID_SURVEY}")
            for t in step2_texts
        ))

    def test_service_returns_the_saved_color_pattern_path(self):
        """서비스 간 핸드오프는 파일이다."""
        _, _, _, path = self._run()
        self.assertTrue(path.exists())
        self.assertEqual(path.suffix, ".png")
        self.assertEqual(path.parent.name, "color_pattern")

    def test_model_is_declared_by_the_service(self):
        self.assertEqual(service.PART_SURVEY_MODEL, "gemini-3.6-flash")
        self.assertEqual(service.PATTERN_UNFOLD_MODEL, "gemini-3.1-flash-image")

    def test_archive_receives_both_sessions_histories_in_order(self):
        """chat_history.json이 전체 대화를 유지하려면 세션이 갈려도
        Step 1 다음 Step 2 순서로 히스토리가 모두 archive에 쌓여야 한다."""
        archive = engine.HistoryArchive()
        survey_client, unfold_client, _, _ = self._run(archive=archive)
        self.assertEqual(archive.all(), survey_client.history + unfold_client.history)

    def test_missing_generated_image_raises_instead_of_returning_a_ghost_path(self):
        """Gemini가 안전 필터 등으로 이미지 없이 응답하면, 존재하지 않는
        경로를 성공처럼 반환해선 안 된다."""
        client = RecordingClient([
            engine.StepResponse(text=VALID_SURVEY, images=[]),
            engine.StepResponse(text="", images=[]),
        ])
        out = engine.RunOutput(self.tmp / "outputs", "run_missing")
        with patch.object(service.engine, "new_session", lambda model: client):
            with self.assertRaises(RuntimeError):
                service.run(self.shoe, self.guide, out)

    def test_bad_guide_path_fails_before_any_api_call(self):
        """가이드 경로 검증은 Step 1의 유료 API 호출보다 먼저 일어나야 한다."""
        calls = []

        def fake_new_session(model):
            calls.append(model)
            raise AssertionError("guide 검증 전에 세션을 만들면 안 된다")

        out = engine.RunOutput(self.tmp / "outputs", "run_bad_guide")
        bad_guide = self.tmp / "no_such_guide.png"
        with patch.object(service.engine, "new_session", fake_new_session):
            with self.assertRaises(FileNotFoundError):
                service.run(self.shoe, bad_guide, out)
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
