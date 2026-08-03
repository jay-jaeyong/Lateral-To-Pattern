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

    def test_unfold_names_view_labels_exactly(self):
        """펼치기 프롬프트가 지목하는 뷰 라벨은 VIEW_FLAGS와 한 글자도 달라선 안 됩니다."""
        labels = dict(VIEW_FLAGS)
        unfold = PIPELINE_STEPS[1]["prompt"]
        for name in ("lateral", "medial", "top", "front", "heel"):
            self.assertIn(labels[name], unfold, msg=name)

    def test_survey_names_the_front_and_heel_labels_exactly(self):
        """front/heel 각도 설명은 관찰 스텝에도 있고, 거기서도 라벨이 정확해야 합니다."""
        labels = dict(VIEW_FLAGS)
        survey = PIPELINE_STEPS[0]["prompt"]
        for name in ("front", "heel"):
            self.assertIn(labels[name], survey, msg=name)

    def test_labels_are_never_written_without_the_parenthetical(self):
        """'앞쪽에서 본 모습'만 쓰고 '(front)'를 빼면 라벨과 어긋납니다.

        괄호 없는 표기는 산문으로 읽혀서 어느 사진을 가리키는지 모호해집니다.
        신발 부위를 뜻하는 말은 라벨과 겹치지 않는 표현('안쪽면' 등)을 씁니다.
        """
        for step in PIPELINE_STEPS:
            prompt = step["prompt"]
            for _name, full in VIEW_FLAGS:
                bare = full.split("(")[0]
                self.assertEqual(
                    prompt.count(bare),
                    prompt.count(full),
                    msg=f"{step['name']}: '{bare}'가 '{full}' 밖에서 쓰였습니다",
                )

    def test_front_and_heel_angle_is_not_asserted(self):
        """front/heel은 정면일 수도 쿼터일 수도 있으므로 프롬프트가 단정하면 안 됩니다."""
        for index in (0, 1):
            prompt = PIPELINE_STEPS[index]["prompt"]
            self.assertIn("쿼터", prompt, msg=PIPELINE_STEPS[index]["name"])
            self.assertIn("사진을 보고", prompt, msg=PIPELINE_STEPS[index]["name"])

    def test_both_prompts_handle_a_pair_in_one_photo(self):
        """한 켤레가 같이 찍힌 사진에서 두 짝을 섞지 않도록 규칙이 있어야 합니다."""
        for index in (0, 1):
            self.assertIn('"pair_rule"', PIPELINE_STEPS[index]["prompt"],
                          msg=PIPELINE_STEPS[index]["name"])

    def test_survey_demands_unconfirmed_list(self):
        survey = PIPELINE_STEPS[0]["prompt"]
        self.assertIn("미확인", survey)
        self.assertIn('"coverage"', survey)

    def test_line_art_cross_checks_the_survey(self):
        self.assertIn('"survey_rule"', PIPELINE_STEPS[2]["prompt"])


if __name__ == "__main__":
    unittest.main()
