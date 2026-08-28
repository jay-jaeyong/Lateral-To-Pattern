"""config/gemini.py가 모델 이름을 담지 않는지 확인한다."""

import unittest

from config import gemini


class GeminiConfigModuleTest(unittest.TestCase):
    def test_module_has_no_model_name(self):
        """모델 선택은 서비스 단위 설정이다. 전역 상수로 두면 스케치 실험이
        color_pattern까지 끌고 간다."""
        self.assertFalse(hasattr(gemini, "MODEL_NAME"))

    def test_chat_config_keeps_current_values(self):
        self.assertEqual(list(gemini.CHAT_CONFIG.response_modalities), ["IMAGE"])
        self.assertEqual(gemini.CHAT_CONFIG.image_config.image_size, "4K")
        self.assertEqual(gemini.CHAT_CONFIG.image_config.aspect_ratio, "2:3")
        self.assertEqual(gemini.CHAT_CONFIG.temperature, 0)
        self.assertEqual(gemini.CHAT_CONFIG.thinking_config.thinking_level, "HIGH")

    def test_build_response_config_returns_none_without_overrides(self):
        self.assertIsNone(gemini.build_response_config(None))

    def test_retry_settings_present(self):
        self.assertEqual(gemini.MAX_RETRIES, 3)
        self.assertEqual(gemini.RETRY_DELAY, 2.0)


if __name__ == "__main__":
    unittest.main()
