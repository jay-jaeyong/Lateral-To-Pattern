"""services/engine.py 세션·저장·히스토리 테스트."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from PIL import Image

from services import engine


class NewSessionTest(unittest.TestCase):
    def test_new_session_passes_the_given_model(self):
        """모델은 서비스가 정한다. 엔진이 고정 상수를 쓰면 안 된다."""
        with patch.object(engine, "genai") as mock_genai:
            engine.new_session("some-model")
        kwargs = mock_genai.Client.return_value.chats.create.call_args.kwargs
        self.assertEqual(kwargs["model"], "some-model")

    def test_send_retries_then_raises(self):
        with patch.object(engine, "genai") as mock_genai, \
             patch.object(engine.time, "sleep"):
            chat = mock_genai.Client.return_value.chats.create.return_value
            chat.send_message.side_effect = RuntimeError("boom")
            session = engine.new_session("m")
            with self.assertRaises(RuntimeError):
                session.send(["hi"])
        self.assertEqual(chat.send_message.call_count, engine.MAX_RETRIES)


class RunOutputTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)

    def test_save_step_writes_under_the_service_folder(self):
        """스텝 번호는 서비스 폴더 안에서 1부터 다시 매긴다."""
        out = engine.RunOutput(self.tmp, "run1")
        path = out.save_step(
            service="sketch_pattern", step=1, name="line_art",
            description="스케치", prompt="p", response="r",
            generated_images=[Image.new("RGB", (2, 2))],
        )
        self.assertEqual(path.parent.name, "sketch_pattern")
        self.assertEqual(path.name, "step_1_line_art.md")
        self.assertTrue(
            (self.tmp / "run1" / "sketch_pattern" / "step_1_line_art_generated_01.png").exists()
        )

    def test_run_dir_is_not_created_until_a_save(self):
        engine.RunOutput(self.tmp, "run2")
        self.assertFalse((self.tmp / "run2").exists())


class HistoryArchiveTest(unittest.TestCase):
    def test_archive_keeps_turns_from_every_session(self):
        """서비스마다 세션이 다르므로, 합쳐두지 않으면 앞 서비스의 턴이
        chat_history.json에서 사라진다."""
        archive = engine.HistoryArchive()
        archive.extend(["a", "b"])
        archive.extend(["c"])
        self.assertEqual(archive.all(), ["a", "b", "c"])


if __name__ == "__main__":
    unittest.main()
