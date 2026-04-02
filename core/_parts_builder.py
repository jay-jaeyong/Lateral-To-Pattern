"""
Parts Builder
--------------
각 파이프라인 단계(step)에 맞게 Gemini API 전송용 parts 리스트를 조립합니다.

조립 순서 (단계별):
  Step 2: [이전_생성_이미지들, 가이드라인_이미지, 이전_텍스트, 프롬프트]
  Step 3: [이전_생성_이미지들, 가이드라인_이미지, 이전_텍스트, 프롬프트]
  기타:   [이전_생성_이미지들, step_이미지, 이전_텍스트, 프롬프트]
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
    prev_images: list,
    prev_texts: list[str],
    prebuilt_parts: list | None = None,
) -> list:
    """각 단계별 parts 리스트를 조립하여 반환합니다.

    Args:
        step_num     : 현재 단계 번호
        prompt       : 텍스트 프롬프트
        image_path   : 현재 단계 이미지 경로 (None 가능)
        prev_images  : 이전 단계에서 생성된 이미지 목록
        prev_texts   : 이전 단계 텍스트 응답 목록
        prebuilt_parts: 이미 조립된 parts (Step 1 사전 선택 시 재사용)
    """
    # ── 1. 현재 단계의 이미지 + 프롬프트 로드 ──────────────────────────
    parts = list(prebuilt_parts) if prebuilt_parts is not None else _load_images(step_num, prompt, image_path)

    # ── 2. 이전 생성 이미지를 parts 앞에 추가 ──────────────────────────
    parts = _prepend_prev_images(step_num, parts, prev_images)

    # ── 3. 이전 단계 텍스트를 프롬프트 바로 앞에 삽입 ──────────────────
    parts = _insert_prev_texts(parts, prev_texts)

    return parts


# ──────────────────────────────────────────────────────────────────────────────
# 내부 헬퍼
# ──────────────────────────────────────────────────────────────────────────────

def _load_images(step_num: int, prompt: str, image_path: Path | str | None) -> list:
    """단계별 이미지를 로드해 [이미지..., 프롬프트] 형태로 반환합니다."""
    if step_num == 2:
        # Step 2는 가이드라인 이미지 로드 실패 시 프롬프트만 사용
        try:
            if image_path is not None:
                return ImageHandler.build_parts(prompt, image_path)
            logger.info("Step %d: image_path 없음 — 프롬프트만 사용합니다.", step_num)
            return [prompt]
        except Exception:
            logger.exception("Step %d: 가이드라인 이미지 로드 실패 — 프롬프트만 사용합니다.", step_num)
            return [prompt]
    else:
        return ImageHandler.build_parts(prompt, image_path)


def _prepend_prev_images(step_num: int, parts: list, prev_imgs: list) -> list:
    """이전 생성 이미지를 parts 앞에 추가합니다."""
    if not prev_imgs:
        return parts

    parts = [*prev_imgs, *parts]

    if step_num == 2:
        logger.info("Step %d: 이전 생성 이미지(%d장) + 가이드라인 이미지 포함", step_num, len(prev_imgs))
    elif step_num == 3:
        logger.info("Step %d에 이전 생성 이미지(%d장)를 포함했습니다.", step_num, len(prev_imgs))
    else:
        logger.info("이전 단계 생성 이미지(%d개)를 현재 요청에 포함했습니다.", len(prev_imgs))

    return parts


def _insert_prev_texts(parts: list, prev_texts: list[str]) -> list:
    """이전 단계 텍스트 응답을 프롬프트 바로 앞에 삽입합니다."""
    if not prev_texts:
        return parts
    try:
        prev_combined = "\n\n".join(
            f"[Previous Step {i+1} Output]\n{txt}"
            for i, txt in enumerate(prev_texts) if txt
        )
        if parts and isinstance(parts[-1], str):
            parts.insert(len(parts) - 1, prev_combined)
        else:
            parts.append(prev_combined)
        logger.info("이전 단계 출력(%d개)을 현재 요청에 포함했습니다.", len(prev_texts))
    except Exception:
        logger.info("이전 단계 출력을 요청에 포함하지 못했습니다.")
    return parts
