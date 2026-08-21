"""프롬프트 3스텝 구조와 라벨 문자열 일치 테스트."""

import re
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

    def test_unfold_keeps_every_rule_block(self):
        """규칙 블록이 통째로 사라지면 방향·솔 제외·힐 절개 같은 제약이 함께 없어집니다."""
        expected = [
            "priority", "input", "multiview_rule", "reconstruct_rule",
            "count_rule", "pair_rule", "task", "fit_rule", "exclude", "heel_rule",
            "part_rule", "flat_rule", "task_rule", "lighting_rule", "guideline_rule",
            "outline_rule", "empty_rule", "background_rule", "caution",
        ]
        found = re.findall(r'"([a-z_]+)": \[', PIPELINE_STEPS[1]["prompt"])
        self.assertEqual(found, expected)

    def test_unfold_keeps_orientation_rules(self):
        """Toe가 아래, Heel이 위라는 방향 규칙이 있어야 결과가 뒤집히지 않습니다."""
        unfold = PIPELINE_STEPS[1]["prompt"]
        self.assertIn("Toe(앞코)가 아래쪽", unfold)
        self.assertIn("Heel(뒤꿈치)이 위쪽", unfold)

    def test_unfold_reconstructs_unphotographed_faces(self):
        """사진에 안 찍힌 면을 비우면 패턴의 절반이 빈 채로 나옵니다."""
        unfold = PIPELINE_STEPS[1]["prompt"]
        self.assertIn('"reconstruct_rule"', unfold)
        self.assertIn("좌우 반전", unfold)
        self.assertIn("사진에 안 찍힌 면은 '비어야 할 곳'이 아니야", unfold)

    def test_unfold_scopes_blankness_to_missing_fabric(self):
        """'비워라'가 원단 없는 세 자리로 한정되어야 면 전체가 비지 않습니다."""
        unfold = PIPELINE_STEPS[1]["prompt"]
        self.assertIn("원단이 실제로 없는 자리", unfold)
        for place in ("TONGUE(설포)", "throat", "Heel 절개"):
            self.assertIn(place, unfold)

    def test_survey_judges_material_by_optics_not_by_name(self):
        """부품 이름으로 재질을 추측하면 브랜드 관행이 실물을 덮어씁니다."""
        survey = PIPELINE_STEPS[0]["prompt"]
        self.assertIn('"material_rule"', survey)
        self.assertIn("광학적 특징으로 판정", survey)
        self.assertIn("정반사 하이라이트", survey)

    def test_survey_treats_uneven_brightness_as_lighting(self):
        """같은 부품의 조각별 밝기 차이를 재질 차이로 읽으면 삼선이 갈립니다."""
        survey = PIPELINE_STEPS[0]["prompt"]
        self.assertIn("재질을 한 번만 판정하고 전부 같게", survey)
        self.assertIn("조명 차이", survey)

    def test_unfold_renders_under_uniform_light(self):
        """원본 하이라이트를 옮기면 조명 얼룩이 소재 차이처럼 보입니다."""
        unfold = PIPELINE_STEPS[1]["prompt"]
        self.assertIn('"lighting_rule"', unfold)
        self.assertIn("균일한 확산광", unfold)
        self.assertIn("하이라이트 위치를 그대로 옮기지 마", unfold)
        self.assertIn("같은 광택으로 그려", unfold)

    def test_line_art_does_not_outline_highlights(self):
        """광택 경계를 재단선으로 착각하면 없는 재단선이 생깁니다."""
        self.assertIn("하이라이트 경계를 재단선으로 착각", PIPELINE_STEPS[2]["prompt"])

    def test_survey_splits_unconfirmed_into_two_kinds(self):
        """면 전체 미확인과 개별 특징 미확인을 구분해야 복원 판단이 됩니다."""
        survey = PIPELINE_STEPS[0]["prompt"]
        self.assertIn("두 종류로 나눠서 적어", survey)
        self.assertIn("사진 없음", survey)

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

    def test_line_art_does_not_reference_the_survey(self):
        """Step 3는 이제 독립 채팅 세션(fresh_session)으로 돌아가 명세서가
        존재하지 않습니다. survey_rule(명세서 대조 규칙)은 없어야 하고,
        광택/하이라이트를 재단선으로 착각하지 말라는 규칙은 remove_rule로
        옮겨져 남아 있어야 합니다. 이전 문구는 '실제 부품 경계와 재봉선에만
        그어'라서 재봉선을 그리라고 지시하고 있었습니다."""
        prompt = PIPELINE_STEPS[2]["prompt"]
        self.assertNotIn('"survey_rule"', prompt)
        self.assertNotIn("재봉선에만 그어", prompt)
        self.assertIn(
            "**광택 차이나 하이라이트 경계를 재단선으로 착각해서 선을 긋지 마. 선은 원단을 잘라내는 재단선에만 그어**",
            prompt,
        )
        self.assertTrue(PIPELINE_STEPS[2].get("fresh_session"))

    def test_survey_records_left_right_presence_and_counts(self):
        """좌우 판정과 개수가 없으면 복원 단계가 몇 개를 그릴지 정하지 못합니다."""
        survey = PIPELINE_STEPS[0]["prompt"]
        self.assertIn('"symmetry_rule"', survey)
        self.assertIn("'중앙(좌우 구분 없음)'", survey)
        # 대칭성 카테고리는 이제 response_schema(Survey)로 기계적으로 강제됩니다.
        # 프롬프트의 중복 나열 대신 schema 검증을 사용합니다.
        self.assertIn("response_schema", str(PIPELINE_STEPS[0]))
        self.assertIn("개수를 반드시 숫자로 적어", survey)

    def test_unfold_forbids_partial_counts(self):
        """세 줄 중 한 줄만 그리는 절충이 이번 실패의 형태였습니다."""
        unfold = PIPELINE_STEPS[1]["prompt"]
        self.assertIn('"count_rule"', unfold)
        self.assertIn("절충은 실패야", unfold)
        self.assertIn("좌우 개수가 같아야", unfold)

    def test_unfold_keeps_stitched_overlays_on_the_restored_face(self):
        """오버레이 패널을 '브랜드 표식'으로 묶으면 복원면에서 삼선이 사라집니다."""
        unfold = PIPELINE_STEPS[1]["prompt"]
        self.assertIn("구조 부품", unfold)
        self.assertIn("복원면에서 빼지 마", unfold)
        self.assertIn("명세서의 좌우 판정을 따라", unfold)

    def test_unfold_forbids_annotations_and_grey_background(self):
        """라벨·기호가 찍히면 재단 패턴이 아니라 도해가 됩니다."""
        unfold = PIPELINE_STEPS[1]["prompt"]
        self.assertIn("부품 도해가 아니야", unfold)
        self.assertIn("알파벳 기호", unfold)
        self.assertIn("순백(#FFFFFF)", unfold)
        self.assertIn("원래 박혀 있는 로고와 글자는 실물의 일부", unfold)

    def test_survey_judges_thread_colour_per_seam(self):
        """한 부위가 흰색 실이라고 전체를 흰색으로 일반화하면 톤온톤 스티치를 놓칩니다."""
        survey = PIPELINE_STEPS[0]["prompt"]
        self.assertIn("실 색은 재봉선마다 따로 판정해", survey)
        self.assertIn("톤온톤", survey)

    def test_survey_sweeps_low_contrast_features(self):
        """음각 로고처럼 바탕과 같은 색인 특징은 따로 찾으라고 해야 찾습니다."""
        survey = PIPELINE_STEPS[0]["prompt"]
        self.assertIn('"lowcontrast_rule"', survey)
        self.assertIn("음각", survey)
        self.assertIn("안 보인다고 없다고 단정하지 마", survey)

    def test_survey_unifies_only_repeated_instances(self):
        """반복 조각은 통일하되 다른 부품끼리 통일하면 이번 같은 오류가 납니다."""
        survey = PIPELINE_STEPS[0]["prompt"]
        self.assertIn("통일은 같은 부품의 반복 조각에만 적용해", survey)
        self.assertIn("서로 다른 부품끼리는 통일하지 마", survey)

    def test_survey_asks_whether_a_seam_is_sewn_at_all(self):
        """'부품 경계마다 실이 몇 줄'은 모든 경계에 봉제가 있다고 전제해 버립니다."""
        survey = PIPELINE_STEPS[0]["prompt"]
        self.assertIn("접합 방식", survey)
        self.assertIn("열접착·본딩(무봉제)", survey)
        self.assertIn("실이 눈에 보이지 않으면 재봉이 아니야", survey)

    def test_survey_relief_covers_both_directions_and_non_logos(self):
        """음각을 로고 예시와만 묶어두면 반복 문양과 홈을 놓칩니다."""
        survey = PIPELINE_STEPS[0]["prompt"]
        self.assertIn("음각(파인 것)·양각(솟은 것)", survey)
        self.assertIn("홈·리브·슬롯·격자", survey)
        self.assertIn("종류와 개수와 방향", survey)
        self.assertIn("저대비든 고대비든 상관없어", survey)

    def test_survey_anchors_parts_to_landmarks(self):
        """랜드마크 없이 '측면 하단'만 적으면 펼치기가 부품을 옮겨버립니다."""
        survey = PIPELINE_STEPS[0]["prompt"]
        for landmark in ("미드솔 라인", "앞코 끝", "뒤꿈치 중심", "아일릿 줄"):
            self.assertIn(landmark, survey, msg=landmark)
        self.assertIn("랜드마크 없는 서술만 적지 마", survey)

    def test_unfold_honours_bonding_and_landmarks(self):
        """무봉제 경계에 스티치를 그리거나 부품을 옮기면 소재와 위치가 틀립니다."""
        unfold = PIPELINE_STEPS[1]["prompt"]
        self.assertIn("무봉제", unfold)
        self.assertIn("스티치를 그리지 마", unfold)
        self.assertIn("랜드마크 위치에 놓아", unfold)

    def test_survey_requires_a_relief_field_for_every_part(self):
        """저대비 훑기로만 두면 색이 있는 부품의 뚜렷한 홈을 건너뜁니다."""
        survey = PIPELINE_STEPS[0]["prompt"]
        self.assertIn("표면 요철", survey)
        self.assertIn("부품마다 빠짐없이 적어야 하는 필수 항목", survey)
        self.assertIn("없으면 '없음'이라고 적어", survey)
        self.assertIn("모든 부품에 '표면 요철' 항목이 채워져 있는지", survey)


if __name__ == "__main__":
    unittest.main()


class HeelViewRuleTest(unittest.TestCase):
    def test_survey_reads_the_heel_only_from_the_heel_photo(self):
        """측면 사진에는 뒤축 뒷면이 없어서, 없는 힐 컵을 지어내곤 했습니다."""
        survey = PIPELINE_STEPS[0]["prompt"]
        self.assertIn('"heel_view_rule"', survey)
        self.assertIn("힐 카운터나 힐 컵이 있을 거라고 넘겨짚지 마", survey)
        self.assertIn("측면 소재가 이어짐", survey)

    def test_survey_guards_against_quarter_view_foreshortening(self):
        """쿼터 뷰에서 중족부 부품이 뒤꿈치 것으로 잘못 기록됐습니다."""
        survey = PIPELINE_STEPS[0]["prompt"]
        self.assertIn("원근에 눌려서", survey)
        self.assertIn("뒤축 중심선", survey)


class MidsoleBoundaryTest(unittest.TestCase):
    def test_sole_is_judged_by_construction(self):
        """겉보기로 가르면 원단에 붙은 Upper 부품까지 솔로 빠집니다."""
        survey = PIPELINE_STEPS[0]["prompt"]
        self.assertIn("접합 구조로 판정해", survey)
        self.assertIn("솔 몸체와 한 덩어리로 성형돼 있으면 솔", survey)
        self.assertIn("재봉선이나 접착 경계가 보이면 Upper", survey)

    def test_unfold_defers_the_sole_call_to_the_survey(self):
        self.assertIn("여기서 다시 판정하지 마", PIPELINE_STEPS[1]["prompt"])

    def test_survey_defines_where_the_midsole_line_is(self):
        survey = PIPELINE_STEPS[0]["prompt"]
        self.assertIn("거품·고무 솔이 끝나고 원단·오버레이가 시작되는 경계", survey)


class FrontViewRuleTest(unittest.TestCase):
    def test_survey_reads_the_toe_only_from_the_front_photo(self):
        """옆에서 찍은 사진에는 앞코 앞면이 없어서 토 캡을 지어내곤 합니다."""
        survey = PIPELINE_STEPS[0]["prompt"]
        self.assertIn('"front_view_rule"', survey)
        self.assertIn("토 캡이 있을 거라고 넘겨짚지 마", survey)

    def test_front_rule_handles_both_straight_and_diagonal_views(self):
        survey = PIPELINE_STEPS[0]["prompt"]
        self.assertIn("위쪽에서 대각선으로 내려다본 것인지", survey)
        self.assertIn("앞코 중심선", survey)


class UpperOnlySurveyTest(unittest.TestCase):
    def test_sole_parts_are_left_out_of_the_list_entirely(self):
        """'제외함'으로 적어두면 다음 단계가 그걸 부품으로 읽습니다."""
        survey = PIPELINE_STEPS[0]["prompt"]
        self.assertIn("명세서에는 Upper 부품만 적어", survey)
        self.assertIn("'제외함'이라고 적지도 마", survey)


class TopViewAndEyestayTest(unittest.TestCase):
    def test_survey_reads_the_instep_from_the_top_photo(self):
        survey = PIPELINE_STEPS[0]["prompt"]
        self.assertIn('"top_view_rule"', survey)
        self.assertIn("바로 위에서 수직으로 내려다본 것인지", survey)
        self.assertIn("발등 중심선", survey)

    def test_survey_judges_the_eyestay_material_separately(self):
        """옆에서 보면 아이스테이가 비스듬해 광택이 죽어 보여 흰색으로 기록됐습니다."""
        survey = PIPELINE_STEPS[0]["prompt"]
        self.assertIn('"eyestay_rule"', survey)
        self.assertIn("주변 갑피와 같은 재질이라고 넘겨짚지 마", survey)
        self.assertIn("정면으로 보이는 사진", survey)


class SurveyPriorityTest(unittest.TestCase):
    """전역 재질 통일 규칙이 부위별 판정을 덮어써 은색이 번졌습니다."""

    def test_survey_has_a_priority_block_first(self):
        survey = PIPELINE_STEPS[0]["prompt"]
        self.assertIn('"priority"', survey)
        blocks = re.findall(r'"([a-z_]+)":\s*\[', survey)
        self.assertEqual(blocks[0], "priority")

    def test_region_rules_outrank_view_rules_outrank_global(self):
        survey = PIPELINE_STEPS[0]["prompt"]
        for rank, names in (
            ("1순위", "eyestay_rule"),
            ("2순위", "top_view_rule"),
            ("3순위", "material_rule"),
        ):
            self.assertIn(rank, survey)
            self.assertIn(names, survey)
        self.assertIn("주변 부품까지 같은 재질로 번지게 하지 마", survey)

    def test_top_view_defers_eyestay_material_to_its_own_rule(self):
        self.assertIn("아이스테이)의 재질은 eyestay_rule을 따라", PIPELINE_STEPS[0]["prompt"])


class MaterialEvidenceTest(unittest.TestCase):
    """'주변과 동일'을 근거로 쓰면 한 부품의 오판이 이웃으로 번집니다."""

    def test_material_evidence_must_come_from_the_part_itself(self):
        survey = PIPELINE_STEPS[0]["prompt"]
        self.assertIn("판정 근거는 그 부품 자체에서만 가져와", survey)
        self.assertIn("판정 근거가 아니야", survey)

    def test_priority_blocks_borrowing_in_both_directions(self):
        survey = PIPELINE_STEPS[0]["prompt"]
        self.assertIn("주변 부품까지 같은 재질로 번지게 하지 마", survey)
        self.assertIn("주변 부품에서 빌려오지도 마", survey)


class LabelFormatTest(unittest.TestCase):
    """라벨에 번호가 있으면 명세서가 번호로 근거를 인용하고, 스텝을 넘으면 어긋납니다."""

    def test_label_carries_no_photo_number(self):
        from handlers.image_handler import ImageHandler

        self.assertEqual(ImageHandler.LABEL_FORMAT, "[{label}]")
        rendered = ImageHandler.LABEL_FORMAT.format(index=1, label="바깥쪽 측면(lateral)")
        self.assertEqual(rendered, "[바깥쪽 측면(lateral)]")
        self.assertNotIn("사진", rendered)

    def test_survey_input_names_all_five_labels(self):
        labels = dict(VIEW_FLAGS)
        survey_input = PIPELINE_STEPS[0]["prompt"]
        for name in ("lateral", "medial", "front", "heel", "top"):
            self.assertIn(labels[name], survey_input, msg=name)
        self.assertIn("다섯 가지야", survey_input)

    def test_survey_says_the_label_does_not_reveal_the_angle_kind(self):
        self.assertIn("정면인지 비스듬한 쿼터 뷰인지는 알려주지 않으니",
                      PIPELINE_STEPS[0]["prompt"])


class HeelSplitContentTest(unittest.TestCase):
    """뒤축 중앙 로고가 양쪽에 온전히 복제되던 문제 — 가장 빈번한 결함이었습니다."""

    def test_heel_ends_are_halves_not_copies(self):
        unfold = PIPELINE_STEPS[1]["prompt"]
        self.assertIn("한 부위를 반으로 자른 두 조각", unfold)
        self.assertIn("복사본이 아니야", unfold)

    def test_back_centre_marks_are_split_in_half(self):
        unfold = PIPELINE_STEPS[1]["prompt"]
        self.assertIn("반씩 갈려", unfold)
        self.assertIn("온전한 로고를 두 번 그리면 실패", unfold)

    def test_each_side_of_the_cut_belongs_to_one_face(self):
        unfold = PIPELINE_STEPS[1]["prompt"]
        self.assertIn("절개선 한쪽은 바깥쪽 면으로, 반대쪽은 안쪽 면으로 이어져", unfold)

    def test_old_identical_wording_is_gone(self):
        """'두 Heel 끝이 똑같아야 해'가 복제를 지시하고 있었습니다."""
        self.assertNotIn("재질·무늬·높이가 똑같아야 해", PIPELINE_STEPS[1]["prompt"])


class TrainingPriorTest(unittest.TestCase):
    def test_unfold_forbids_borrowing_from_remembered_models(self):
        """asics에서 학습한 인기 모델 특징이 결과물에 나타났습니다."""
        unfold = PIPELINE_STEPS[1]["prompt"]
        self.assertIn("네가 아는 유명 모델의 생김새를 가져오면 실패야", unfold)
        self.assertIn("다른 인기 모델과 닮게 만들지 마", unfold)


class SideViewRuleTest(unittest.TestCase):
    def test_survey_has_both_side_view_rules(self):
        survey = PIPELINE_STEPS[0]["prompt"]
        self.assertIn('"lateral_view_rule"', survey)
        self.assertIn('"medial_view_rule"', survey)

    def test_side_rules_demand_explicit_difference_extraction(self):
        survey = PIPELINE_STEPS[0]["prompt"]
        self.assertEqual(survey.count("나란히 놓고 비교해서"), 2)
        self.assertEqual(survey.count("'차이 없음'이라고 적어"), 2)

    def test_side_rules_are_listed_in_priority(self):
        survey = PIPELINE_STEPS[0]["prompt"]
        self.assertIn("lateral_view_rule, medial_view_rule", survey)

    def test_mirror_fallback_only_when_medial_is_missing(self):
        unfold = PIPELINE_STEPS[1]["prompt"]
        self.assertIn("medial 사진이 있으면 반전 복원을 쓰지 마", unfold)
        self.assertNotIn("신발은 중심선 기준으로 거의 대칭이야", unfold)

    def test_count_equality_is_scoped_to_parts_found_on_both_sides(self):
        """삼선이 한쪽만 세 줄로 나오던 실패를 막는 규칙은 남기되 범위를 좁힙니다."""
        unfold = PIPELINE_STEPS[1]["prompt"]
        self.assertIn("명세서가 '양쪽'으로 판정한 요소는 좌우 개수가 같아야 해", unfold)
        self.assertIn("'한쪽만'으로 판정한 요소는 그 한쪽에만 그려", unfold)

    def test_symmetry_rule_records_shape_differences_too(self):
        survey = PIPELINE_STEPS[0]["prompt"]
        self.assertIn("두 면의 모양이 같은지 다른지 함께 적어", survey)


class SketchPatternContractTest(unittest.TestCase):
    """Step 3는 컬러 패턴에서 재단선만 남긴 스케치 패턴을 만듭니다.

    이전 프롬프트는 메쉬·무늬·재봉선·글자까지 모두 그리라고 지시해서
    도메인 규칙(docs/source_of_truth.md)과 정반대로 움직였습니다.
    """

    def sketch(self) -> str:
        return PIPELINE_STEPS[2]["prompt"]

    def test_keeps_every_rule_block(self):
        """규칙 블록이 통째로 사라지면 유지·제거·좌표 보존 판정이 함께 없어집니다."""
        expected = [
            "priority", "input", "task", "geometry_rule",
            "keep_rule", "remove_rule", "render_rule", "self_check",
        ]
        found = re.findall(r'"([a-z_]+)": \[', self.sketch())
        self.assertEqual(found, expected)

    def test_priority_block_comes_first(self):
        """좌표 보존과 보수적 판정이 다른 규칙에 밀리면 선이 움직입니다."""
        sketch = self.sketch()
        self.assertEqual(re.findall(r'"([a-z_]+)": \[', sketch)[0], "priority")
        for rank in ("1순위", "2순위", "3순위", "4순위", "5순위"):
            self.assertIn(rank, sketch)

    def test_matches_input_aspect_without_requesting_postprocessing(self):
        step = PIPELINE_STEPS[2]
        self.assertIs(step.get("match_input_aspect_ratio"), True)
        self.assertNotIn("postprocess_sketch", step)
        self.assertIs(step.get("enabled"), False)
        self.assertIs(step.get("fresh_session"), True)
        self.assertIs(step.get("include_prev_texts"), False)

    def test_preserves_normalized_geometry_not_exact_pixel_dimensions(self):
        prompt = self.sketch()
        for phrase in (
            "입력과 같은 화면 비율",
            "프레이밍",
            "정규화 좌표",
            "x/width",
            "y/height",
            "곡률",
            "개별 부품을 이동하지 마",
        ):
            self.assertIn(phrase, prompt)
        self.assertNotIn("입력과 동일한 해상도", prompt)
        self.assertNotIn("같은 픽셀 위치", prompt)

    def test_forbids_reframing_and_beautifying_the_lines(self):
        """모델이 선을 다시 래스터화하면서 예쁘게 고치면 좌표가 어긋납니다."""
        sketch = self.sketch()
        self.assertIn("확대·축소·크롭·회전·반전·재배치를 하지 마", sketch)
        self.assertIn("직선화·대칭화·곡선 보정을 하지 마", sketch)
        self.assertIn("곡률", sketch)

    def test_does_not_complete_or_invent_lines(self):
        """가려져 안 보이는 부분을 지어내면 원본에 없는 재단선이 생깁니다.

        이전 문구('끊어진 선을 잇거나 가려진 부분을 완성하지 마')는 관찰된
        위상(닫힌 외곽, 접점)을 보존하라는 규칙과 부딪혀서 생성 잡티로 생긴
        진짜 틈까지 보존하라고 읽혔습니다. 지금은 틈을 메우는 것과 실제로
        가려진 구간을 추론하는 것을 구분합니다."""
        sketch = self.sketch()
        self.assertIn("생성 과정에서 생긴 틈이나 끊김은 남기지 마", sketch)
        self.assertIn("원본에 없는 선을 새로 추가하지 마", sketch)

    def test_keeps_punching_and_nosew_cut_lines(self):
        """펀칭과 노쏘 재단선은 원단에서 잘라내는 선이라 남아야 합니다."""
        sketch = self.sketch()
        self.assertIn("펀칭 재단선", sketch)
        self.assertIn("노쏘 재단선", sketch)
        self.assertIn("별도 선 형식으로 구분하지 마", sketch)
        self.assertIn("고체 패널에 독립된 닫힌 구멍", sketch)

    def test_keeps_mounting_holes_and_cut_logo_parts_only_when_certain(self):
        """하드웨어 아래 구멍과 재단된 로고 부품은 조건이 붙어야 남습니다."""
        sketch = self.sketch()
        self.assertIn("원단을 잘라낸 구멍이 직접 식별될 때", sketch)
        self.assertIn("별도 원단에서 재단한 부품으로 명확히 식별되는", sketch)

    def test_removes_everything_that_is_not_a_cut_line(self):
        """재봉선·표면 조직·하드웨어·음영·재봉 마진은 재단선이 아닙니다."""
        sketch = self.sketch()
        self.assertIn("재봉선과 실 모양", sketch)
        self.assertIn("재단선 가까이에 있거나 나란히 있어도 제거", sketch)
        for surface in ("메쉬", "니트", "격자", "엠보싱"):
            self.assertIn(surface, sketch, msg=surface)
        self.assertIn("인쇄·자수", sketch)
        self.assertIn("금속 아일릿", sketch)
        self.assertIn("버클", sketch)
        self.assertIn("재봉 마진", sketch)
        self.assertIn("새로 추가하지도 마", sketch)

    def test_drops_uncertain_and_hidden_lines(self):
        """불확실하면 제거하는 보수 원칙이 거짓 재단선을 막습니다."""
        sketch = self.sketch()
        self.assertIn("불확실한 선은 제거", sketch)
        self.assertIn("펀칭인지 메쉬인지 불분명하면 제거", sketch)
        self.assertIn("가려져 보이지 않는 재단선", sketch)
        self.assertIn("추론하거나 복원하지 마", sketch)

    def test_renders_one_uniform_black_line_style_on_white(self):
        """선 종류를 색·점선·굵기로 나누면 재단선이 아닌 정보가 들어옵니다."""
        sketch = self.sketch()
        self.assertIn("순백(#FFFFFF)", sketch)
        self.assertIn("동일한 굵기와 색의 검은 실선", sketch)
        self.assertIn("의미별 색상, 점선, 굵기 차이를 두지 마", sketch)
        self.assertIn("한 장의 평면 이미지", sketch)

    def test_self_check_covers_the_acceptance_rules(self):
        """출력 직전 자체 점검이 없으면 위 규칙이 조용히 무시됩니다."""
        sketch = self.sketch()
        self.assertIn('"self_check"', sketch)
        checks = sketch.split('"self_check"', 1)[1]
        for item in ("화면 비율", "정규화 좌표", "곡률", "재봉선", "펀칭", "재봉 마진", "순백"):
            self.assertIn(item, checks, msg=item)

    def test_old_conflicting_instructions_are_gone(self):
        """이 네 지시가 스케치 패턴 규칙과 정면으로 부딪혔습니다."""
        sketch = self.sketch()
        self.assertNotIn("표면의 무늬까지 하나도 빠짐없이", sketch)
        self.assertNotIn("표면의 모든 무늬를 개수와 위치까지", sketch)
        self.assertNotIn("실물과 똑같은 위치에 따로 그려", sketch)
        self.assertNotIn("글자와 실 모양까지 실물과 똑같이", sketch)
        self.assertNotIn("정밀 복제 전문가", sketch)
        self.assertNotIn('"detail_rule"', sketch)

    def test_step_three_stays_isolated_and_disabled(self):
        """명세서 격리와 비활성 상태는 이번 변경 범위가 아닙니다."""
        sketch_step = PIPELINE_STEPS[2]
        self.assertIs(sketch_step["include_prev_texts"], False)
        self.assertIs(sketch_step["fresh_session"], True)
        self.assertIs(sketch_step["enabled"], False)

    def test_unfold_and_sketch_share_the_global_image_config(self):
        """스텝별 이미지 설정이 갈리면 두 결과물의 크기가 어긋납니다."""
        for index in (1, 2):
            self.assertNotIn("image_config", PIPELINE_STEPS[index],
                             msg=PIPELINE_STEPS[index]["name"])
        from config.gemini_config import IMAGE_CONFIG

        self.assertEqual(IMAGE_CONFIG.image_size, "4K")
        self.assertEqual(IMAGE_CONFIG.aspect_ratio, "2:3")

    def test_preserves_observed_cut_line_topology(self):
        sketch = self.sketch()
        self.assertIn("전체 외곽 재단선은 완전히 닫힌", sketch)
        self.assertIn("내부 재단선은 닫힌 루프", sketch)
        self.assertIn("다른 식별된 재단선에 정확히 닿아", sketch)
        self.assertIn("생성 과정에서 생긴 틈", sketch)
        self.assertNotIn("끊어진 선을 잇거나 가려진 부분을 완성하지 마", sketch)

    def test_keeps_mesh_part_boundaries_but_removes_mesh_texture(self):
        sketch = self.sketch()
        self.assertIn("메시 패턴 파트의 재단선", sketch)
        self.assertIn("다른 패턴 파트와 맞닿는지와 관계없이", sketch)
        self.assertIn("메시 조직의 반복 무늬만 제거", sketch)
        self.assertIn("발목", sketch)

    def test_requires_closed_mesh_part_perimeters(self):
        prompt = self.sketch()
        for phrase in (
            "메시 패턴 파트의 둘레",
            "닫힌 순환 경계",
            "정확한 접점",
            "공유 구간",
            "평행한 중복선",
            "메시 조직만 제거",
        ):
            self.assertIn(phrase, prompt)

    def test_keeps_circular_and_elliptical_punching(self):
        sketch = self.sketch()
        self.assertIn("원형 또는 타원형", sketch)
        self.assertIn("닫힌 펀칭 재단선", sketch)

    def test_forbids_every_color_fill_and_faint_cut_lines(self):
        sketch = self.sketch()
        self.assertIn("검정·회색·유채색 채움", sketch)
        self.assertIn("순백(#FFFFFF)", sketch)
        self.assertIn("순검정(#000000)", sketch)
        self.assertIn("흐릿", sketch)

    def test_rendering_allows_only_edge_antialias_gray(self):
        prompt = self.sketch()
        self.assertIn("순백", prompt)
        self.assertIn("순검정", prompt)
        self.assertIn("검은 선 가장자리", prompt)
        self.assertIn("중립 회색 안티앨리어싱", prompt)
        for forbidden in ("유채색 픽셀", "회색 채움", "음영", "재질 표현"):
            self.assertIn(forbidden, prompt)
