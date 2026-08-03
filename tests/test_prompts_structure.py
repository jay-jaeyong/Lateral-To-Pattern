"""프롬프트 3스텝 구조와 라벨 문자열 일치 테스트."""

import unittest

from config.prompts import PIPELINE_STEPS
from utils.cli import VIEW_FLAGS


class PipelineShapeTest(unittest.TestCase):
    def test_three_steps_in_order(self):
        self.assertEqual([s["step"] for s in PIPELINE_STEPS], [1, 2, 3])
        self.assertEqual(
            [s["name"] for s in PIPELINE_STEPS],
            ["part_survey", "pattern_unfold", "line_art_conversion"],
        )

    def test_survey_step_asks_for_text_and_all_images(self):
        survey = PIPELINE_STEPS[0]
        self.assertEqual(survey["response_modalities"], ["TEXT"])
        self.assertIsNone(survey["max_images"])
        self.assertIsNone(survey["guide_image_path"])
        self.assertIsNotNone(survey["image_path"])

    def test_unfold_step_relies_on_history_and_takes_the_guide(self):
        unfold = PIPELINE_STEPS[1]
        self.assertIsNone(unfold["image_path"])
        self.assertIsNotNone(unfold["guide_image_path"])
        self.assertNotIn("response_modalities", unfold)


class PromptContentTest(unittest.TestCase):
    def prompts(self) -> list[str]:
        return [step["prompt"] for step in PIPELINE_STEPS]

    def test_no_positional_photo_references(self):
        for step, prompt in zip(PIPELINE_STEPS, self.prompts()):
            self.assertNotIn("첫번째 사진", prompt, msg=step["name"])
            self.assertNotIn("두번째 사진", prompt, msg=step["name"])

    def test_spelling_is_ailrit(self):
        for step, prompt in zip(PIPELINE_STEPS, self.prompts()):
            self.assertNotIn("아일렛", prompt, msg=step["name"])

    def test_unfold_has_priority_block(self):
        unfold = PIPELINE_STEPS[1]["prompt"]
        self.assertIn('"priority"', unfold)
        for rank in ("1순위", "2순위", "3순위", "4순위"):
            self.assertIn(rank, unfold)

    def test_unfold_has_multiview_rule(self):
        self.assertIn('"multiview_rule"', PIPELINE_STEPS[1]["prompt"])

    def test_unfold_names_the_lateral_label_exactly(self):
        lateral_label = dict(VIEW_FLAGS)["lateral"]
        self.assertIn(lateral_label, PIPELINE_STEPS[1]["prompt"])

    def test_unfold_names_the_medial_label_exactly(self):
        medial_label = dict(VIEW_FLAGS)["medial"]
        self.assertIn(medial_label, PIPELINE_STEPS[1]["prompt"])

    def test_unfold_names_the_top_label_exactly(self):
        top_label = dict(VIEW_FLAGS)["top"]
        self.assertIn(top_label, PIPELINE_STEPS[1]["prompt"])

    def test_unfold_names_the_front_label_exactly(self):
        front_label = dict(VIEW_FLAGS)["front"]
        self.assertIn(front_label, PIPELINE_STEPS[1]["prompt"])

    def test_unfold_names_the_heel_label_exactly(self):
        heel_label = dict(VIEW_FLAGS)["heel"]
        self.assertIn(heel_label, PIPELINE_STEPS[1]["prompt"])

    def test_survey_demands_unconfirmed_list(self):
        survey = PIPELINE_STEPS[0]["prompt"]
        self.assertIn("미확인", survey)
        self.assertIn('"coverage"', survey)

    def test_line_art_cross_checks_the_survey(self):
        self.assertIn('"survey_rule"', PIPELINE_STEPS[2]["prompt"])


if __name__ == "__main__":
    unittest.main()
