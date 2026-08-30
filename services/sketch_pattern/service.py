"""스케치 패턴 서비스 — 컬러 패턴 한 장에서 스케치 패턴을 만든다.

자기 세션을 새로 연다. Step 1 명세서는 측면 사진 기준 3D 서술이라
그것이 히스토리로 닿으면 모델이 평면 패턴을 트레이싱하는 대신 3D
신발을 다시 그려버린다. 서비스가 분리되어 있으므로 그 경로가 없다.
"""

from __future__ import annotations

from pathlib import Path

from services import engine
from services.sketch_pattern import step_1_line_art
from services.sketch_pattern.prompts import LINE_ART_PROMPT

MODEL = "gemini-3.1-flash-image"

SERVICE = "sketch_pattern"


def run(color_pattern_path: Path, out, archive=None) -> Path:
    """저장된 스케치 패턴 PNG 경로를 반환한다."""
    session = engine.new_session(MODEL)
    generated = step_1_line_art.run(session, color_pattern_path)
    out.save_step(
        service=SERVICE, step=1, name="line_art",
        description="스케치 패턴 변환 - 컬러 패턴 → 재단선만 남긴 스케치 패턴",
        prompt=LINE_ART_PROMPT, response="", generated_images=generated,
    )
    if archive is not None:
        archive.extend(session.history)
    return out.service_dir(SERVICE) / "step_1_line_art_generated_01.png"
