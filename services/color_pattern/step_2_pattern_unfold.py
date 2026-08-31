"""Step 2 — 사진과 명세서로 컬러 패턴을 펼친다."""

from __future__ import annotations

from pathlib import Path

from services.color_pattern import photo_input
from services.color_pattern.prompts import PATTERN_UNFOLD_PROMPT


def run(session, photos, guide_path: Path, survey_text: str) -> list:
    """생성된 컬러 패턴 이미지 목록을 반환한다.

    config를 넘기지 않는다. 세션 기본값(CHAT_CONFIG, 4K/2:3)을 그대로 쓴다.
    """
    parts = photo_input.build_unfold_parts(
        photos, guide_path, survey_text, PATTERN_UNFOLD_PROMPT
    )
    return session.send(parts).images
