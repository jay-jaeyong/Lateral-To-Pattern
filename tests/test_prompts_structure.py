"""프롬프트 상수가 비어 있지 않은지, 라벨 값이 그대로인지 확인한다."""

import json
import unittest

from services.color_pattern.prompts import PART_SURVEY_PROMPT, PATTERN_UNFOLD_PROMPT
from services.sketch_pattern.prompts import LINE_ART_PROMPT, ORIGINAL_PATTERN_LABEL

# heel 뷰가 Step 1 survey에서 빠지므로, heel 전제 지시가 두 프롬프트에
# 남아 있으면 안 된다.
FORBIDDEN_TOKENS = ("heel", "Heel", "힐", "뒤꿈치", "뒤축", "절개면", "뒤끝")


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


class PromptsAreValidJsonTest(unittest.TestCase):
    def test_part_survey_prompt_parses_as_json(self):
        json.loads(PART_SURVEY_PROMPT)

    def test_pattern_unfold_prompt_parses_as_json(self):
        json.loads(PATTERN_UNFOLD_PROMPT)


class NoHeelTokensTest(unittest.TestCase):
    """heel 뷰를 더 이상 survey에 보내지 않으므로, heel 전제 지시를 전부 뺀다."""

    def test_pattern_unfold_prompt_has_no_heel_tokens(self):
        for token in FORBIDDEN_TOKENS:
            self.assertNotIn(token, PATTERN_UNFOLD_PROMPT, f"금지 토큰 잔존: {token}")

    def test_part_survey_prompt_has_no_heel_tokens(self):
        for token in FORBIDDEN_TOKENS:
            self.assertNotIn(token, PART_SURVEY_PROMPT, f"금지 토큰 잔존: {token}")

    def test_part_survey_prompt_has_no_heel_view_rule_section(self):
        data = json.loads(PART_SURVEY_PROMPT)
        self.assertNotIn("heel_view_rule", data)

    def test_part_survey_prompt_labels_five_views_without_heel(self):
        data = json.loads(PART_SURVEY_PROMPT)
        input_section = " ".join(data["input"])
        for label in ("lateral", "medial", "front", "top"):
            self.assertIn(label, input_section)

    def test_part_survey_prompt_has_no_rear_view_interpretation(self):
        """heel 뷰가 없으므로 뒤쪽/정후면으로 해석할 대안을 남겨두면 안 된다."""
        self.assertNotIn("정후면", PART_SURVEY_PROMPT)
        self.assertNotIn("앞(또는 뒤)", PART_SURVEY_PROMPT)


class KeptRulesTest(unittest.TestCase):
    """heel 제거와 무관하게 유지해야 하는 규칙들."""

    def test_guide_is_not_a_clipping_mask(self):
        self.assertIn("클리핑 마스크", PATTERN_UNFOLD_PROMPT)

    def test_actual_part_ratio_and_outline_preserved(self):
        self.assertIn("실물 부품 비율", PATTERN_UNFOLD_PROMPT)

    def test_medial_photo_followed_directly_when_present(self):
        self.assertIn("medial 사진이 있으면", PATTERN_UNFOLD_PROMPT)

    def test_lateral_mirrored_only_when_medial_absent(self):
        self.assertIn("medial 사진이 없을 때만", PATTERN_UNFOLD_PROMPT)
        self.assertIn("좌우 반전", PATTERN_UNFOLD_PROMPT)

    def test_sole_tongue_lace_interior_insole_excluded(self):
        for token in ("SOLE", "TONGUE", "LACE", "신발 내부", "깔창"):
            self.assertIn(token, PATTERN_UNFOLD_PROMPT)

    def test_throat_left_blank(self):
        self.assertIn("throat", PATTERN_UNFOLD_PROMPT)

    def test_toe_bottom_v_is_not_an_internal_incision(self):
        self.assertIn("내부 절개가 아니다", PATTERN_UNFOLD_PROMPT)

    def test_no_new_white_channel_between_toe_cap_vamp_eyestay(self):
        self.assertIn("새로운 세로 흰 통로", PATTERN_UNFOLD_PROMPT)

    def test_pure_white_flat_output(self):
        self.assertIn("순백(#FFFFFF)", PATTERN_UNFOLD_PROMPT)

    def test_toe_down_direction_without_mentioning_heel(self):
        self.assertIn("Toe(앞코)가 아래쪽", PATTERN_UNFOLD_PROMPT)
        self.assertNotIn("Heel", PATTERN_UNFOLD_PROMPT)


if __name__ == "__main__":
    unittest.main()
