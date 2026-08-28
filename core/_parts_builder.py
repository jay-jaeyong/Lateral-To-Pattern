"""
Parts Builder
--------------
각 파이프라인 단계(step)에 맞게 Gemini API 전송용 parts 리스트를 조립합니다.

조립 순서:
  [이전_생성_이미지들, 주_입력_이미지, 가이드라인_이미지, 이전_텍스트, 프롬프트]

3스텝 파이프라인에서는 각 단계별로 다음과 같이 됩니다.
  Step 1: [라벨, 신발 사진, 라벨, 신발 사진, ..., 프롬프트]
  Step 2: [가이드라인, Step 1 명세서, 프롬프트]
  Step 3: [Step 2 생성 이미지, 프롬프트] (명세서 미포함 — include_prev_texts=False)
"""

from __future__ import annotations

import logging
from pathlib import Path

from handlers.image_handler import ImageHandler

logger = logging.getLogger(__name__)

# 가이드라인 이미지 앞에 붙는 라벨. 실물 사진의 "[사진 N]" 번호와
# 섞이지 않도록 번호를 쓰지 않습니다.
GUIDE_LABEL = "[가이드라인] 2D 펼침 틀 — 신발 사진이 아니야"


def build_step_parts(
    step_num: int,
    prompt: str,
    image_path: Path | str | None,
    prev_images: list,
    prev_texts: list[str],
    prebuilt_parts: list | None = None,
    guide_image_path: Path | str | None = None,
    max_images: int | None = None,
    view_images: list[tuple[str, Path]] | None = None,
    reference_images: list[tuple[str, object]] | None = None,
    include_prev_texts: bool = True,
    prev_image_label: str | None = None,
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
        view_images     : (라벨, 경로) 목록. 주어지면 image_path 대신 이것을 쓴다
        reference_images: (라벨, 이미 로드된 이미지) 목록. parts 맨 앞에 붙는다
        include_prev_texts: False면 이전 단계 텍스트(명세서 등)를 넣지 않는다
        prev_image_label: 이전 단계 생성 이미지에 붙일 라벨 (None이면 라벨 없이 넣는다)
    """
    # ── 1. 현재 단계의 주 입력 이미지 + 프롬프트 로드 ──────────────────
    if prebuilt_parts is not None:
        parts = list(prebuilt_parts)
    elif view_images:
        # 뷰 플래그로 받은 사진이 있으면 image_path는 무시합니다.
        parts = ImageHandler.build_labeled_parts(view_images, prompt)
    else:
        parts = _load_images(prompt, image_path, max_images)

    # ── 2. 가이드라인 이미지를 프롬프트 바로 앞에 삽입 ─────────────────
    parts = _insert_guide_images(parts, guide_image_path)

    # ── 3. 이전 생성 이미지를 parts 앞에 추가 ──────────────────────────
    parts = _prepend_prev_images(parts, prev_images, prev_image_label)

    # ── 3-1. 앞 단계에서 쓴 실물 사진을 다시 맨 앞에 붙인다 ────────────
    parts = _prepend_reference_images(parts, reference_images)

    # ── 4. 이전 단계 텍스트를 프롬프트 바로 앞에 삽입 ──────────────────
    if include_prev_texts:
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
    # 라벨 없이 넣으면 앞의 실물 사진 뒤에 붙어서 '[사진 N]' 중 하나로 읽힙니다.
    labelled: list = []
    for guide in guides:
        labelled.append(GUIDE_LABEL)
        labelled.append(guide)
    return _insert_before_prompt(parts, labelled)


def _load_guide_images(guide_path: Path) -> list:
    """명시적 가이드라인 파일에서 이미지를 로드합니다.

    파일 경로만 허용합니다. 폴더가 주어지면 경고를 기록하고 빈 리스트를 반환합니다.
    Step 2는 런타임 폴더 검색을 하지 않습니다. 가이드라인 검색은 CLI 계층에서
    미리 끝나야 합니다.
    """
    if guide_path.is_file():
        return [ImageHandler.load(guide_path)]

    if guide_path.is_dir():
        logger.warning(
            "'%s'는 폴더입니다. Step 2는 명시적 가이드라인 파일만 허용합니다. "
            "폴더에서 가이드라인을 찾아내지 않습니다.",
            guide_path,
        )
        return []

    return []


def _prepend_reference_images(parts: list, references: list | None) -> list:
    """앞 단계에서 쓴 실물 사진을 라벨과 함께 parts 맨 앞에 붙입니다.

    채팅 히스토리에만 의존하면 모델이 원본을 흐릿하게 참조합니다. 같은 요청 안에
    다시 넣어주면 세부를 직접 대조할 수 있습니다.
    """
    if not references:
        return parts

    prefixed: list = []
    for label, image in references:
        prefixed.append(label)
        prefixed.append(image)
    logger.info("실물 참조 사진 %d장을 현재 요청에 다시 포함했습니다.", len(references))
    return [*prefixed, *parts]


def _prepend_prev_images(parts: list, prev_imgs: list, label: str | None = None) -> list:
    """이전 생성 이미지를 parts 앞에 추가합니다.

    label이 있으면 이미지마다 앞에 라벨을 붙입니다. 라벨 없이 넣으면 모델이
    이 이미지를 프롬프트가 지목하는 대상으로 읽지 못하고 참고 사진 하나로
    흘려봅니다. Step 3의 컬러 패턴이 그런 경우입니다.
    """
    if not prev_imgs:
        return parts

    logger.info("이전 단계 생성 이미지(%d개)를 현재 요청에 포함했습니다.", len(prev_imgs))
    if label is None:
        return [*prev_imgs, *parts]

    labelled: list = []
    for image in prev_imgs:
        labelled.append(ImageHandler.LABEL_FORMAT.format(label=label))
        labelled.append(image)
    return [*labelled, *parts]


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
