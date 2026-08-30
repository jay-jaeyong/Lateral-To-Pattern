"""스텝별 응답 모달리티 config 생성과 전달 테스트."""

import unittest

from config.gemini import IMAGE_CONFIG, build_response_config
from services.engine import Session, StepResponse


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
    def make_client(self) -> Session:
        return Session(FakeChat())

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


class AspectRatioTest(unittest.TestCase):
    def test_output_is_locked_to_portrait(self):
        """비율을 비워두면 모델이 가로를 골라 방향 규칙이 깨집니다."""
        from config.gemini import IMAGE_CONFIG

        self.assertEqual(IMAGE_CONFIG.aspect_ratio, "2:3")
