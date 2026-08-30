"""sketch_pattern 서비스 테스트."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from services import engine
from services.sketch_pattern import prompts, service
from tests.golden_parts import RecordingClient


class SketchPatternTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.color = self.tmp / "shoe_color.png"
        Image.new("RGB", (10, 15), (200, 30, 30)).save(self.color)

    def _run(self):
        client = RecordingClient([
            engine.StepResponse(text="", images=[Image.new("RGB", (10, 15))]),
        ])
        out = engine.RunOutput(self.tmp / "outputs", "run1")
        with patch.object(service.engine, "new_session", lambda model: client):
            path = service.run(self.color, out)
        return client, path

    def test_parts_are_label_then_image_then_prompt(self):
        """라벨이 없으면 모델이 이 이미지를 프롬프트가 지목하는 '원본'으로
        읽지 못하고 참고 사진 하나로 흘려본다."""
        client, _ = self._run()
        parts = client.calls[0]["parts"]
        self.assertEqual(len(parts), 3)
        self.assertEqual(parts[0]["kind"], "text")
        self.assertEqual(parts[0]["len"], len("[원본 컬러 패턴]"))
        self.assertEqual(parts[1]["kind"], "pil")
        self.assertEqual(parts[2]["len"], len(prompts.LINE_ART_PROMPT))

    def test_service_does_not_require_shoe_photos(self):
        """이 서비스는 컬러 패턴 경로 하나만 받는다. 신발 사진을 모른다."""
        import inspect
        params = list(inspect.signature(service.run).parameters)
        self.assertEqual(params[0], "color_pattern_path")
        self.assertNotIn("shoe_dir", params)

    def test_config_is_none_so_the_session_default_applies(self):
        client, _ = self._run()
        self.assertIsNone(client.calls[0]["config"])

    def test_service_opens_its_own_session(self):
        """서비스 경계가 세션 경계다. fresh_session 플래그를 대신한다."""
        client, _ = self._run()
        self.assertEqual(client.start_chat_call_count, 0)  # new_session이 스텁이므로
        self.assertEqual(len(client.calls), 1)

    def test_saved_under_the_sketch_pattern_folder(self):
        _, path = self._run()
        self.assertTrue(path.exists())
        self.assertEqual(path.parent.name, "sketch_pattern")

    def test_label_value_is_unchanged(self):
        self.assertEqual(prompts.ORIGINAL_PATTERN_LABEL, "원본 컬러 패턴")


if __name__ == "__main__":
    unittest.main()
