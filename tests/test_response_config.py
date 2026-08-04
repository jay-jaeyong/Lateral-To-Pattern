"""스텝별 응답 모달리티 config 생성과 전달 테스트."""

import unittest

from google.genai import types

from config.gemini_config import (
    CHAT_CONFIG,
    IMAGE_CONFIG,
    INPUT_MEDIA_RESOLUTION,
    build_response_config,
)
from core.models import StepResponse
from services.gemini_client import GeminiClient


class BuildResponseConfigTest(unittest.TestCase):
    def test_image_output_is_portrait_two_to_three(self):
        self.assertEqual(IMAGE_CONFIG.aspect_ratio, "2:3")

    def test_input_images_ask_for_high_media_resolution(self):
        """요철·톤온톤 스티치를 읽으려면 사진을 고해상도로 넣어야 합니다."""
        self.assertEqual(
            INPUT_MEDIA_RESOLUTION,
            types.MediaResolution.MEDIA_RESOLUTION_HIGH,
        )

    def test_configs_never_carry_media_resolution(self):
        """config에 실으면 gemini-3-pro-image가 400으로 거절합니다.

        같은 값을 파트 단위로 붙이면 통과하므로, 해상도 지정은
        services/gemini_client.py의 이미지 파트에만 실립니다.
        """
        self.assertIsNone(CHAT_CONFIG.media_resolution)
        for modalities in (["TEXT"], ["IMAGE"]):
            self.assertIsNone(
                build_response_config(modalities).media_resolution, msg=str(modalities)
            )

    def test_temperature_stays_at_the_api_default(self):
        self.assertIsNone(CHAT_CONFIG.temperature)
        self.assertIsNone(build_response_config(["TEXT"]).temperature)

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
