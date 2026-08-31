"""서비스 사이의 배선 테스트."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from services import engine
from services.color_pattern import service as color_pattern
from services.sketch_pattern import service as sketch_pattern
from tests.golden_parts import RecordingClient

VALID_SURVEY = '{"분석대상짝": "왼발", "부품목록": [], "표식목록": [], "미확인목록": []}'


class ServiceWiringTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.shoe = self.tmp / "shoe"
        self.shoe.mkdir()
        for name in ("lateral.png", "medial.png"):
            Image.new("RGB", (4, 4)).save(self.shoe / name)
        self.guide = self.tmp / "가이드라인.png"
        Image.new("RGB", (4, 4)).save(self.guide)

    def test_the_two_services_use_different_sessions(self):
        """서비스 경계가 세션 경계다. sketch_pattern이 color_pattern의
        히스토리를 이어받으면, Step 1 명세서(측면 사진 기준 3D 서술) 때문에
        모델이 평면 패턴을 트레이싱하는 대신 3D 신발을 다시 그린다."""
        created = []

        def fake_new_session(model):
            # color_pattern 세션은 Step 1(텍스트) + Step 2(이미지) 두 번 부른다.
            # sketch_pattern 세션은 Step 1(이미지) 한 번만 부른다. 세션마다
            # 실제로 소비하는 응답 개수가 다르므로 별도로 준비한다.
            if not created:
                client = RecordingClient([
                    engine.StepResponse(text=VALID_SURVEY, images=[]),
                    engine.StepResponse(text="", images=[Image.new("RGB", (4, 4))]),
                ])
            else:
                client = RecordingClient([
                    engine.StepResponse(text="", images=[Image.new("RGB", (4, 4))]),
                ])
            created.append(client)
            return client

        out = engine.RunOutput(self.tmp / "outputs", "run1")
        archive = engine.HistoryArchive()
        with patch.object(engine, "new_session", fake_new_session):
            color_path = color_pattern.run(self.shoe, self.guide, out, archive)
            sketch_pattern.run(color_path, out, archive)

        self.assertEqual(len(created), 2)
        self.assertIsNot(created[0], created[1])

    def test_sketch_pattern_never_sees_the_survey_text(self):
        created = []

        def fake_new_session(model):
            if not created:
                client = RecordingClient([
                    engine.StepResponse(text=VALID_SURVEY, images=[]),
                    engine.StepResponse(text="", images=[Image.new("RGB", (4, 4))]),
                ])
            else:
                client = RecordingClient([
                    engine.StepResponse(text="", images=[Image.new("RGB", (4, 4))]),
                ])
            created.append(client)
            return client

        out = engine.RunOutput(self.tmp / "outputs", "run2")
        with patch.object(engine, "new_session", fake_new_session):
            color_path = color_pattern.run(self.shoe, self.guide, out)
            sketch_pattern.run(color_path, out)

        sketch_texts = [p for p in created[1].calls[0]["parts"] if p["kind"] == "text"]
        survey_len = len(f"[Previous Step 1 Output]\n{VALID_SURVEY}")
        self.assertFalse(any(t["len"] == survey_len for t in sketch_texts))

    def test_archive_keeps_turns_from_both_services(self):
        """세션이 둘이므로 합쳐두지 않으면 앞 서비스의 턴이
        chat_history.json에서 사라진다."""
        created = []

        def fake_new_session(model):
            if not created:
                client = RecordingClient([
                    engine.StepResponse(text=VALID_SURVEY, images=[]),
                    engine.StepResponse(text="", images=[Image.new("RGB", (4, 4))]),
                ])
            else:
                client = RecordingClient([
                    engine.StepResponse(text="", images=[Image.new("RGB", (4, 4))]),
                ])
            created.append(client)
            return client

        out = engine.RunOutput(self.tmp / "outputs", "run3")
        archive = engine.HistoryArchive()
        with patch.object(engine, "new_session", fake_new_session):
            color_path = color_pattern.run(self.shoe, self.guide, out, archive)
            sketch_pattern.run(color_path, out, archive)

        self.assertEqual(len(archive.all()), 3)


if __name__ == "__main__":
    unittest.main()
