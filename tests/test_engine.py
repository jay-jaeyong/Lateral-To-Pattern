"""services/engine.py 세션·저장·히스토리 테스트."""

import gc
import tempfile
import unittest
import weakref
from pathlib import Path
from unittest.mock import MagicMock, patch

from PIL import Image

from services import engine


class NewSessionTest(unittest.TestCase):
    def test_new_session_passes_the_given_model(self):
        """모델은 서비스가 정한다. 엔진이 고정 상수를 쓰면 안 된다."""
        with patch.object(engine, "genai") as mock_genai, \
             patch.object(engine, "get_api_key", return_value="test-key"):
            engine.new_session("some-model")
        kwargs = mock_genai.Client.return_value.chats.create.call_args.kwargs
        self.assertEqual(kwargs["model"], "some-model")

    def test_new_session_keeps_client_alive_after_gc(self):
        """chat은 client의 httpx 연결에 의존한다. new_session이 client를
        로컬 변수로만 들고 있으면 GC 시 client가 수거되어 httpx 연결이
        끊긴다. Session이 client를 계속 참조해 살아있어야 한다."""
        with patch.object(engine, "genai") as mock_genai, \
             patch.object(engine, "get_api_key", return_value="test-key"):
            client_instance = mock_genai.Client.return_value
            client_ref = weakref.ref(client_instance)
            session = engine.new_session("some-model")

        # new_session의 지역 변수 client, 그리고 mock_genai(테스트용 patch
        # 대상)까지 스코프를 벗어나야 실제 상황(요청 함수 반환 후 client가
        # 다른 곳에서 참조되지 않는 상황)을 재현한다.
        del client_instance
        del mock_genai
        gc.collect()

        self.assertIsNotNone(
            client_ref(),
            "Session이 client를 붙잡고 있지 않아 GC로 수거되었습니다.",
        )
        self.assertIs(session._client, client_ref())

    def test_send_retries_then_raises(self):
        with patch.object(engine, "genai") as mock_genai, \
             patch.object(engine, "get_api_key", return_value="test-key"), \
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
