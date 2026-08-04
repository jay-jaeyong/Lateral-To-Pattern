"""스텝별 응답 모달리티 config 생성과 전달 테스트."""

import unittest

from config.gemini_config import IMAGE_CONFIG, build_response_config
from core.models import StepResponse
from services.gemini_client import GeminiClient


class BuildResponseConfigTest(unittest.TestCase):
    def test_none_means_use_session_default(self):
        self.assertIsNone(build_response_config(None))

    def test_empty_list_means_use_session_default(self):
        self.assertIsNone(build_response_config([]))

    def test_text_only_has_no_image_config(self):
        config = build_response_config(["TEXT"])
        self.assertEqual(list(config.response_modalities), ["TEXT"])
        self.assertIsNone(config.image_config)

    def test_image_keeps_image_config(self):
        config = build_response_config(["TEXT", "IMAGE"])
        self.assertEqual(list(config.response_modalities), ["TEXT", "IMAGE"])
        self.assertIs(config.image_config, IMAGE_CONFIG)


class FakeResponse:
    parts: list = []


class FakeChat:
    def __init__(self):
        self.calls: list = []

    def send_message(self, message, config=None):
        self.calls.append((message, config))
        return FakeResponse()


class SendPassesConfigTest(unittest.TestCase):
    def make_client(self) -> GeminiClient:
        client = GeminiClient.__new__(GeminiClient)  # __init__은 API 키를 요구하므로 건너뜁니다
        client._chat = FakeChat()
        return client

    def test_config_is_forwarded(self):
        client = self.make_client()
        config = build_response_config(["TEXT"])
        result = client.send(["hello"], config=config)
        self.assertIsInstance(result, StepResponse)
        self.assertIs(client._chat.calls[0][1], config)

    def test_default_config_is_none(self):
        client = self.make_client()
        client.send(["hello"])
        self.assertIsNone(client._chat.calls[0][1])


if __name__ == "__main__":
    unittest.main()
