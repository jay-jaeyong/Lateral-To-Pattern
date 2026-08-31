"""프롬프트 상수가 비어 있지 않은지, 라벨 값이 그대로인지 확인한다."""

import unittest

from services.color_pattern.prompts import PART_SURVEY_PROMPT, PATTERN_UNFOLD_PROMPT
from services.sketch_pattern.prompts import LINE_ART_PROMPT, ORIGINAL_PATTERN_LABEL


class PromptsNotEmptyTest(unittest.TestCase):
    def test_part_survey_prompt_is_not_empty(self):
        self.assertTrue(PART_SURVEY_PROMPT)

    def test_pattern_unfold_prompt_is_not_empty(self):
        self.assertTrue(PATTERN_UNFOLD_PROMPT)

    def test_line_art_prompt_is_not_empty(self):
        self.assertTrue(LINE_ART_PROMPT)


class OriginalPatternLabelTest(unittest.TestCase):
    def test_label_value_is_unchanged(self):
        self.assertEqual(ORIGINAL_PATTERN_LABEL, "원본 컬러 패턴")


if __name__ == "__main__":
    unittest.main()
