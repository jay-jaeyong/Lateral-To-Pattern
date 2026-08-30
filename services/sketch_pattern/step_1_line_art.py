"""Step 1 — 컬러 패턴을 재단선만 남긴 스케치 패턴으로 바꾼다."""

from __future__ import annotations

from pathlib import Path

from services.sketch_pattern.prompts import LINE_ART_PROMPT, ORIGINAL_PATTERN_LABEL
from services.utils import images


def run(session, color_pattern_path: Path) -> list:
    """생성된 스케치 패턴 이미지 목록을 반환한다.

    라벨을 붙여야 모델이 이 이미지를 프롬프트가 말하는 '원본'으로 읽는다.
    라벨 없이 넣으면 그냥 참고 사진 한 장으로 흘려본다.
    """
    parts = [
        images.label(ORIGINAL_PATTERN_LABEL),
        images.load(color_pattern_path),
        LINE_ART_PROMPT,
    ]
    return session.send(parts).images
