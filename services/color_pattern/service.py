"""컬러 패턴 서비스 — 신발 사진에서 컬러 패턴 한 장을 만든다.

Step 1(부품 관찰)과 Step 2(패턴 펼치기)는 서로 다른 모델을 쓰므로
세션도 따로 연다. chats.create(model=...)가 세션 생성 시점에 모델을
고정하기 때문이다. 그 결과 정면·위 사진은 Step 1 세션에만 보이고
Step 2로는 넘어가지 않는다. Step 2는 측면(lateral·medial) 사진,
가이드라인, Step 1이 만든 부품 명세서를 parts에 직접 받는다.
"""

from __future__ import annotations

from pathlib import Path

from services import engine
from services.color_pattern import (
    photo_input,
    step_1_part_survey,
    step_2_pattern_unfold,
)
from services.color_pattern.prompts import PART_SURVEY_PROMPT, PATTERN_UNFOLD_PROMPT
from services.utils import images

# Step 1(TEXT+JSON)과 Step 2(IMAGE)는 서로 다른 모델을 쓴다. chats.create가
# 세션 생성 시점에 모델을 고정하므로 스텝마다 세션을 따로 연다.
PART_SURVEY_MODEL = "gemini-3.6-flash"
PATTERN_UNFOLD_MODEL = "gemini-3.1-flash-image"

SERVICE = "color_pattern"


def run(shoe_dir: Path, guide_path: Path, out, archive=None) -> Path:
    """저장된 컬러 패턴 PNG 경로를 반환한다."""
    # Step 2에서야 처음 열리는 파일이라, 여기서 미리 확인하지 않으면
    # 잘못된 경로가 Step 1의 유료 API 호출을 태운 뒤에야 걸린다.
    images.load(guide_path)

    photos = photo_input.resolve(shoe_dir)

    survey_session = engine.new_session(PART_SURVEY_MODEL)
    survey_text = step_1_part_survey.run(survey_session, photos)
    out.save_step(
        service=SERVICE, step=1, name="part_survey",
        description="부품 관찰 - 신발 사진 → 부품 명세서",
        prompt=PART_SURVEY_PROMPT, response=survey_text, generated_images=[],
    )

    unfold_session = engine.new_session(PATTERN_UNFOLD_MODEL)
    generated = step_2_pattern_unfold.run(unfold_session, photos, guide_path, survey_text)
    out.save_step(
        service=SERVICE, step=2, name="pattern_unfold",
        description="패턴 펼치기 - 명세서 → 컬러 패턴",
        prompt=PATTERN_UNFOLD_PROMPT, response="", generated_images=generated,
    )

    if archive is not None:
        archive.extend(survey_session.history)
        archive.extend(unfold_session.history)

    image_path = out.service_dir(SERVICE) / "step_2_pattern_unfold_generated_01.png"
    if not image_path.exists():
        raise RuntimeError(
            f"{SERVICE} step 2(pattern_unfold)가 이미지를 만들지 못했습니다: {image_path}\n"
            f"Gemini가 안전 필터나 일시 오류로 이미지 없이 응답했을 수 있습니다."
        )
    return image_path
