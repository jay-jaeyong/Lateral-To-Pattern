"""
Parts Builder
--------------
각 파이프라인 단계(step)에 맞게 Gemini API 전송용 parts 리스트를 조립합니다.

조립 순서:
  [이전_생성_이미지들, 주_입력_이미지, 가이드라인_이미지, 이전_텍스트, 프롬프트]

단일 스텝(패턴 펼치기)에서는 실제로 다음 순서가 됩니다.
  [신발 실물 사진(사이드뷰), 2D 펼침 가이드라인(틀), 프롬프트]
"""

from __future__ import annotations

import logging
from pathlib import Path

from config.prompts import GUIDELINE_OPACITY
from handlers.image_handler import ImageHandler

logger = logging.getLogger(__name__)


def build_step_parts(
    step_num: int,
    prompt: str,
    image_path: Path | str | None,
    prev_images: list,
    prev_texts: list[str],
    prebuilt_parts: list | None = None,
    guide_image_path: Path | str | None = None,
    max_images: int | None = None,
) -> list:
    """각 단계별 parts 리스트를 조립하여 반환합니다.

    Args:
        step_num        : 현재 단계 번호
        prompt          : 텍스트 프롬프트
        image_path      : 현재 단계의 주 입력 이미지 경로 (None 가능)
        prev_images     : 이전 단계에서 생성된 이미지 목록
        prev_texts      : 이전 단계 텍스트 응답 목록
        prebuilt_parts  : 이미 조립된 parts (첫 스텝 사전 선택 시 재사용)
        guide_image_path: 가이드라인(틀) 이미지 경로 (None 가능)
        max_images      : 폴더에서 불러올 이미지 최대 장수 (None이면 전부)
    """
    # ── 1. 현재 단계의 주 입력 이미지 + 프롬프트 로드 ──────────────────
    parts = list(prebuilt_parts) if prebuilt_parts is not None else _load_images(prompt, image_path, max_images)

    # ── 2. 가이드라인 이미지를 프롬프트 바로 앞에 삽입 ─────────────────
    parts = _insert_guide_images(parts, guide_image_path)

    # ── 3. 이전 생성 이미지를 parts 앞에 추가 ──────────────────────────
    parts = _prepend_prev_images(parts, prev_images)

    # ── 4. 이전 단계 텍스트를 프롬프트 바로 앞에 삽입 ──────────────────
    parts = _insert_prev_texts(parts, prev_texts)

    return parts


# ──────────────────────────────────────────────────────────────────────────────
# 내부 헬퍼
# ──────────────────────────────────────────────────────────────────────────────

def _load_images(prompt: str, image_path: Path | str | None, max_images: int | None) -> list:
    """주 입력 이미지를 로드해 [이미지..., 프롬프트] 형태로 반환합니다."""
    if image_path is None:
        logger.info("image_path 없음 — 프롬프트만 사용합니다.")
        return [prompt]
    return ImageHandler.build_parts(prompt, image_path, max_images=max_images)


def _insert_guide_images(parts: list, guide_image_path: Path | str | None) -> list:
    """가이드라인(틀) 이미지를 프롬프트 바로 앞에 삽입합니다."""
    if guide_image_path is None:
        return parts

    try:
        guides = _load_guide_images(Path(guide_image_path))
    except Exception:
        logger.exception("가이드라인 이미지 로드 실패 — 가이드 없이 진행합니다: %s", guide_image_path)
        return parts

    if not guides:
        logger.warning("가이드라인 이미지를 찾지 못했습니다: %s", guide_image_path)
        return parts

    logger.info("가이드라인 이미지 %d장 포함: %s", len(guides), guide_image_path)
    return _insert_before_prompt(parts, guides)


def _load_guide_images(guide_path: Path) -> list:
    """가이드라인 경로(파일 또는 폴더)에서 이미지를 로드합니다.

    폴더라면 파일명에 '가이드라인'(또는 guideline) 키워드가 들어간 이미지를 먼저 찾고,
    없으면 폴더 안의 이미지를 전부 사용합니다.

    로드한 가이드라인은 config.prompts.GUIDELINE_OPACITY 만큼 연하게 처리해서
    전달합니다(모델이 가이드 선을 결과물에 따라 그리지 않게 하기 위함).
    """
    if guide_path.is_file():
        return [ImageHandler.load_faded(guide_path, GUIDELINE_OPACITY)]

    if guide_path.is_dir():
        found = ImageHandler.find_guideline(guide_path)
        if found:
            return [ImageHandler.load_faded(found, GUIDELINE_OPACITY)]

        logger.warning(
            "'%s'에서 가이드라인 키워드(%s)가 들어간 파일을 찾지 못했습니다 — 폴더 내 이미지를 사용합니다.",
            guide_path,
            ", ".join(ImageHandler.GUIDELINE_KEYWORDS),
        )
        images = []
        for f in ImageHandler.list_image_files(guide_path):
            try:
                images.append(ImageHandler.load_faded(f, GUIDELINE_OPACITY))
            except Exception as exc:
                logger.warning("가이드라인 이미지 로드 실패: %s — %s", f, exc)
        return images

    return []


def _prepend_prev_images(parts: list, prev_imgs: list) -> list:
    """이전 생성 이미지를 parts 앞에 추가합니다."""
    if not prev_imgs:
        return parts

    logger.info("이전 단계 생성 이미지(%d개)를 현재 요청에 포함했습니다.", len(prev_imgs))
    return [*prev_imgs, *parts]


def _insert_prev_texts(parts: list, prev_texts: list[str]) -> list:
    """이전 단계 텍스트 응답을 프롬프트 바로 앞에 삽입합니다."""
    if not prev_texts:
        return parts
    try:
        prev_combined = "\n\n".join(
            f"[Previous Step {i+1} Output]\n{txt}"
            for i, txt in enumerate(prev_texts) if txt
        )
        parts = _insert_before_prompt(parts, [prev_combined])
        logger.info("이전 단계 출력(%d개)을 현재 요청에 포함했습니다.", len(prev_texts))
    except Exception:
        logger.info("이전 단계 출력을 요청에 포함하지 못했습니다.")
    return parts


def _insert_before_prompt(parts: list, items: list) -> list:
    """parts 끝의 프롬프트 문자열 바로 앞에 items를 끼워 넣습니다."""
    if parts and isinstance(parts[-1], str):
        return [*parts[:-1], *items, parts[-1]]
    return [*parts, *items]
