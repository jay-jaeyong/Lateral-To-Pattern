"""앞 단계에서 생성된 이미지가 다음 스텝으로 이미지로 전달되는지 테스트.

Gemini가 돌려주는 생성 이미지는 genai types.Image입니다. SDK의 send_message가
받는 타입 목록에 없어서, 그냥 넘기면 sanitizer가 repr 문자열로 바꿔버립니다.
그러면 라인 아트 스텝이 패턴 이미지 대신 바이너리 문자열을 받습니다.
"""

import unittest

from google.genai import types as genai_types

from core.models import StepResponse
from services.gemini_client import GeminiClient


class FakeResponse:
    parts: list = []


class FakeChat:
    def __init__(self):
        self.calls: list = []

    def send_message(self, message, config=None):
        self.calls.append(message)
        return FakeResponse()


def make_client() -> GeminiClient:
    client = GeminiClient.__new__(GeminiClient)  # __init__은 API 키를 요구합니다
    client._chat = FakeChat()
    return client


class GeneratedImagePassthroughTest(unittest.TestCase):
    def test_generated_image_becomes_an_inline_part(self):
        raw = b"\xff\xd8\xff\xe0 pretend this is a jpeg"
        client = make_client()
        result = client.send(
            [genai_types.Image(image_bytes=raw, mime_type="image/jpeg"), "PROMPT"]
        )
        self.assertIsInstance(result, StepResponse)

        sent = client._chat.calls[0]
        self.assertIsInstance(sent[0], genai_types.Part)
        self.assertEqual(sent[0].inline_data.mime_type, "image/jpeg")
        self.assertEqual(sent[0].inline_data.data, raw)
        self.assertEqual(sent[1], "PROMPT")

    def test_generated_image_is_never_stringified(self):
        client = make_client()
        client.send([genai_types.Image(image_bytes=b"\x89PNG", mime_type="image/png"), "P"])
        for part in client._chat.calls[0]:
            if isinstance(part, str):
                self.assertNotIn("image_bytes", part)

    def test_missing_mime_type_falls_back_to_png(self):
        client = make_client()
        client.send([genai_types.Image(image_bytes=b"\x89PNG"), "P"])
        self.assertEqual(client._chat.calls[0][0].inline_data.mime_type, "image/png")

    def test_plain_string_and_none_image_parts_are_untouched(self):
        client = make_client()
        client.send(["only text"])
        self.assertEqual(client._chat.calls[0], ["only text"])

    def test_pil_images_are_sent_as_high_resolution_parts(self):
        """사진을 고해상도로 넣어야 요철·톤온톤 스티치가 보입니다."""
        from PIL import Image

        client = make_client()
        client.send([Image.new("RGB", (8, 8), (1, 2, 3)), "PROMPT"])

        sent = client._chat.calls[0]
        self.assertIsInstance(sent[0], genai_types.Part)
        self.assertEqual(sent[0].inline_data.mime_type, "image/png")
        self.assertEqual(
            sent[0].media_resolution.level,
            genai_types.PartMediaResolutionLevel.MEDIA_RESOLUTION_HIGH,
        )

    def test_generated_images_also_go_high_resolution(self):
        client = make_client()
        client.send([genai_types.Image(image_bytes=b"\x89PNG", mime_type="image/png"), "P"])
        self.assertEqual(
            client._chat.calls[0][0].media_resolution.level,
            genai_types.PartMediaResolutionLevel.MEDIA_RESOLUTION_HIGH,
        )


if __name__ == "__main__":
    unittest.main()
