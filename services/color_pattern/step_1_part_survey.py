"""Step 1 — 신발 사진에서 부품 명세서를 만든다."""

from __future__ import annotations

from config.gemini import build_response_config
from services.color_pattern import photo_input
from services.color_pattern.prompts import PART_SURVEY_PROMPT
from services.color_pattern.schema import Survey

SURVEY_CONFIG = build_response_config(["TEXT"], response_schema=Survey)


def run(session, photos) -> str:
    """명세서 원문을 반환한다.

    Survey는 검증 전용이다. 파싱 결과를 다시 직렬화해 다음 스텝의
    프롬프트에 넣지 않는다 - 키 순서나 공백이 달라지면 Step 2가 보는
    토큰이 달라진다.
    """
    parts = photo_input.build_survey_parts(photos, PART_SURVEY_PROMPT)
    text = session.send(parts, config=SURVEY_CONFIG).text
    Survey.model_validate_json(text)
    return text
