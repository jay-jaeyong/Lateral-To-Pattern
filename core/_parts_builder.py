"""
Parts Builder
--------------
각 파이프라인 단계의 OpenAI Responses API 입력 parts를 조립합니다.

Responses API + previous_response_id 체이닝 사용 시 이전 단계 컨텍스트는
서버가 자동으로 이어주므로, 매 단계에는 **현재 단계의 새 입력만** 보냅니다.

조립 결과: [현재_단계_이미지(들)..., 프롬프트]
"""

from __future__ import annotations

import logging
from pathlib import Path

from handlers.image_handler import ImageHandler

logger = logging.getLogger(__name__)


def build_step_parts(
    step_num: int,
    prompt: str,
    image_path: Path | str | None,
    prev_images: list | None = None,   # 사용되지 않음 (인터페이스 호환)
    prev_texts: list[str] | None = None,  # 사용되지 않음 (인터페이스 호환)
    prebuilt_parts: list | None = None,
) -> list:
    """현재 단계 입력만 담은 parts 리스트를 반환합니다.

    Args:
        step_num     : 현재 단계 번호 (로깅용)
        prompt       : 텍스트 프롬프트
        image_path   : 현재 단계 이미지 경로 (None 가능)
        prev_images  : (미사용, 서버측 체이닝 사용)
        prev_texts   : (미사용, 서버측 체이닝 사용)
        prebuilt_parts: 이미 조립된 parts (Step 1 사전 선택 시 재사용)
    """
    if prebuilt_parts is not None:
        return list(prebuilt_parts)
    return _load_images(step_num, prompt, image_path)


def _load_images(step_num: int, prompt: str, image_path: Path | str | None) -> list:
    """단계별 이미지를 로드해 [이미지..., 프롬프트] 형태로 반환합니다."""
    if step_num == 2:
        try:
            if image_path is not None:
                return ImageHandler.build_parts(prompt, image_path)
            logger.info("Step %d: image_path 없음 — 프롬프트만 사용합니다.", step_num)
            return [prompt]
        except Exception:
            logger.exception("Step %d: 가이드라인 이미지 로드 실패 — 프롬프트만 사용합니다.", step_num)
            return [prompt]
    return ImageHandler.build_parts(prompt, image_path)
