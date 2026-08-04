"""부품 명세서 스키마 검증 테스트."""

import unittest
from pydantic import ValidationError

from config.survey_schema import Survey, Part, Marking, Symmetry
from config.gemini_config import build_response_config


class SymmetryValidationTest(unittest.TestCase):
    """대칭성 리터럴 검증."""

    def test_rejects_invalid_symmetry_value(self):
        """정해진 다섯 가지 이외의 대칭성 값을 거부합니다."""
        with self.assertRaises(ValidationError):
            Survey(
                분석대상짝="왼발",
                부품목록=[
                    Part(
                        부품명="패널1",
                        재질="천",
                        색상="검은색",
                        형태="직사각형",
                        평면형태="앞으로 갈수록 모이는 V자",
                        경계="옆 패널과 만남",
                        위치="발등",
                        접합방식="재봉",
                        재봉선="싱글",
                        표면요철="없음",
                        대칭성="양옆",  # 잘못된 값 — 대칭성은 정확히 5가지만 가능
                        모양차이="없음",
                        확인사진="lateral",
                    )
                ],
                표식목록=[],
                미확인목록=[],
            )

    def test_accepts_valid_symmetry_values(self):
        """정해진 다섯 가지 대칭성 값을 모두 수용합니다."""
        symmetries = [
            "양쪽",
            "한쪽만(바깥쪽)",
            "한쪽만(안쪽)",
            "중앙(좌우 구분 없음)",
            "확인 불가",
        ]
        for sym in symmetries:
            survey = Survey(
                분석대상짝="왼발",
                부품목록=[
                    Part(
                        부품명="패널1",
                        재질="천",
                        색상="검은색",
                        형태="직사각형",
                        평면형태="앞으로 갈수록 모이는 V자",
                        경계="옆 패널과 만남",
                        위치="발등",
                        접합방식="재봉",
                        재봉선="싱글",
                        표면요철="없음",
                        대칭성=sym,
                        모양차이="없음",
                        확인사진="lateral",
                    )
                ],
                표식목록=[],
                미확인목록=[],
            )
            # 검증 성공 확인
            self.assertEqual(survey.부품목록[0].대칭성, sym)


class PartRequiredFieldsTest(unittest.TestCase):
    """부품 필드 검증 — 특히 경계 필드 필수."""

    def test_part_rejects_missing_boundary(self):
        """경계 필드가 없는 부품을 거부합니다."""
        with self.assertRaises(ValidationError):
            Part(
                부품명="패널1",
                재질="천",
                색상="검은색",
                형태="직사각형",
                평면형태="앞으로 갈수록 모이는 V자",
                # 경계 필드 없음 — 실패해야 함
                위치="발등",
                접합방식="재봉",
                재봉선="싱글",
                표면요철="없음",
                대칭성="양쪽",
                모양차이="없음",
                확인사진="lateral",
            )

    def test_part_requires_all_fields(self):
        """모든 필드가 있는 부품은 검증됩니다."""
        part = Part(
            부품명="패널1",
            재질="천",
            색상="검은색",
            형태="직사각형",
            평면형태="앞으로 갈수록 모이는 V자",
            경계="옆 패널과 만남",
            위치="발등",
            접합방식="재봉",
            재봉선="싱글",
            표면요철="없음",
            대칭성="양쪽",
            모양차이="없음",
            확인사진="lateral",
        )
        self.assertEqual(part.부품명, "패널1")
        self.assertEqual(part.경계, "옆 패널과 만남")


class SurveyRequiredFieldsTest(unittest.TestCase):
    """명세서 필드 검증."""

    def test_survey_rejects_invalid_foot_side(self):
        """분석대상짝이 왼발/오른발 이외인 값을 거부합니다."""
        with self.assertRaises(ValidationError):
            Survey(
                분석대상짝="양발",  # 잘못된 값
                부품목록=[],
                표식목록=[],
                미확인목록=[],
            )

    def test_survey_accepts_valid_foot_sides(self):
        """분석대상짝이 왼발/오른발 중 하나이면 수용합니다."""
        for foot in ["왼발", "오른발"]:
            survey = Survey(
                분석대상짝=foot,
                부품목록=[],
                표식목록=[],
                미확인목록=[],
            )
            self.assertEqual(survey.분석대상짝, foot)

    def test_survey_fully_populated(self):
        """모든 필드가 채워진 명세서는 검증됩니다."""
        survey = Survey(
            분석대상짝="왼발",
            부품목록=[
                Part(
                    부품명="메인 패널",
                    재질="메시",
                    색상="검은색",
                    형태="곡선형",
                    평면형태="앞으로 갈수록 모이는 V자",
                    경계="측면 패널과 만남",
                    위치="발등 중심",
                    접합방식="재봉",
                    재봉선="더블 직선",
                    표면요철="천공 20개",
                    대칭성="양쪽",
                    모양차이="없음",
                    확인사진="lateral medial",
                ),
                Part(
                    부품명="측면 오버레이",
                    재질="합성피혁",
                    색상="흰색",
                    형태="L자형",
                    평면형태="앞으로 갈수록 모이는 V자",
                    경계="메인 패널 위에 겹침",
                    위치="발등 옆",
                    접합방식="열접착",
                    재봉선="없음",
                    표면요철="없음",
                    대칭성="양쪽",
                    모양차이="없음",
                    확인사진="lateral",
                ),
            ],
            표식목록=[
                Marking(
                    이름="로고",
                    재질="합성피혁",
                    색상="검은색",
                    형태="동그란 배지",
                    평면형태="앞으로 갈수록 모이는 V자",
                    위치="발등 상단",
                    접합방식="본딩",
                    대칭성="한쪽만(바깥쪽)",
                    확인사진="lateral",
                )
            ],
            미확인목록=["안쪽면 아일릿"],
        )
        self.assertEqual(len(survey.부품목록), 2)
        self.assertEqual(len(survey.표식목록), 1)
        self.assertEqual(len(survey.미확인목록), 1)


class BuildResponseConfigWithSchemaTest(unittest.TestCase):
    """build_response_config 함수의 response_schema 파라미터 테스트."""

    def test_config_with_schema_sets_json_mime_type(self):
        """response_schema를 지정하면 response_mime_type이 application/json으로 설정됩니다."""
        config = build_response_config(["TEXT"], response_schema=Survey)
        self.assertIsNotNone(config)
        self.assertEqual(config.response_mime_type, "application/json")
        self.assertIs(config.response_schema, Survey)

    def test_config_without_schema_has_no_mime_type(self):
        """response_schema를 지정하지 않으면 response_mime_type이 설정되지 않습니다."""
        config = build_response_config(["TEXT"])
        self.assertIsNotNone(config)
        # response_mime_type과 response_schema 속성이 없거나 None이어야 함
        self.assertFalse(hasattr(config, "response_mime_type") and config.response_mime_type)
        self.assertFalse(hasattr(config, "response_schema") and config.response_schema)

    def test_none_modalities_ignores_schema(self):
        """modalities가 None이면 response_schema가 있어도 None을 반환합니다."""
        config = build_response_config(None, response_schema=Survey)
        self.assertIsNone(config)

    def test_empty_modalities_ignores_schema(self):
        """modalities가 빈 목록이면 response_schema가 있어도 None을 반환합니다."""
        config = build_response_config([], response_schema=Survey)
        self.assertIsNone(config)


class PipelineWiringTest(unittest.TestCase):
    """파이프라인 스텝 구성 검증."""

    def test_step_1_has_response_schema(self):
        """Step 1의 설정에 response_schema가 포함되어 있습니다."""
        from config.prompts import PIPELINE_STEPS

        step1 = PIPELINE_STEPS[0]
        self.assertEqual(step1["name"], "part_survey")
        self.assertIn("response_schema", step1)
        self.assertIs(step1["response_schema"], Survey)

    def test_step_2_does_not_have_response_schema(self):
        """Step 2의 설정에는 response_schema가 없습니다."""
        from config.prompts import PIPELINE_STEPS

        step2 = PIPELINE_STEPS[1]
        self.assertEqual(step2["name"], "pattern_unfold")
        self.assertNotIn("response_schema", step2)


if __name__ == "__main__":
    unittest.main()
