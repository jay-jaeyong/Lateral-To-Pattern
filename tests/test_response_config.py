"""스텝별 응답 모달리티 config 생성과 전달 테스트."""

import unittest

from google.genai import types

from config.gemini_config import CHAT_CONFIG, IMAGE_CONFIG, build_response_config
from core.models import StepResponse
from services.gemini_client import GeminiClient


class BuildResponseConfigTest(unittest.TestCase):
    def test_image_output_is_portrait_two_to_three(self):
        self.assertEqual(IMAGE_CONFIG.aspect_ratio, "2:3")

    def test_default_chat_uses_high_media_resolution_and_default_temperature(self):
        self.assertEqual(
            CHAT_CONFIG.media_resolution,
            types.MediaResolution.MEDIA_RESOLUTION_HIGH,
        )
        self.assertIsNone(CHAT_CONFIG.temperature)

    def test_text_override_keeps_high_media_resolution_and_default_temperature(self):
        config = build_response_config(["TEXT"])
        self.assertEqual(
            config.media_resolution,
            types.MediaResolution.MEDIA_RESOLUTION_HIGH,
        )
        self.assertIsNone(config.temperature)

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
