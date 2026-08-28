"""
Image Utils
--------------
이미지 파일을 로드하고 Gemini API에 전달 가능한 형태로 변환합니다.
"""

from __future__ import annotations

import logging
from pathlib import Path

from PIL import Image

logger = logging.getLogger(__name__)

# Gemini가 지원하는 이미지 확장자
SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}

# 파일명에 이 키워드가 들어 있으면 가이드라인(틀) 이미지로 봅니다.
GUIDELINE_KEYWORDS = ("가이드라인", "가이드", "guideline", "guide")

# 이미지 앞에 붙는 라벨 텍스트 파트의 형식.
# Pillow가 로드할 때 파일명을 버리므로, 어느 각도 사진인지는 이 라벨로만 전달됩니다.
#
# 번호를 넣지 않습니다. 번호가 있으면 명세서가 '[사진 3]'처럼 번호로 근거를
# 인용하는데, 다음 스텝은 사진을 같은 순서로 받지 않아서 그 번호가 어긋납니다.
# 뷰 이름만 두면 인용할 수단 자체가 뷰 이름뿐입니다.
LABEL_FORMAT = "[{label}]"


# ──────────────────────────────────────────────────
# 파일 탐색
# ──────────────────────────────────────────────────

def is_guideline_file(path: Path) -> bool:
    """파일명으로 가이드라인 이미지인지 판별합니다."""
    name = path.name.lower()
    return any(keyword.lower() in name for keyword in GUIDELINE_KEYWORDS)


def list_image_files(folder: Path, exclude_guideline: bool = False) -> list[Path]:
    """폴더 바로 아래의 지원 이미지 파일을 정렬해서 반환합니다."""
    if not folder.is_dir():
        return []
    files = sorted(
        f for f in folder.iterdir()
        if f.is_file()
        and not f.name.startswith(".")
        and f.suffix.lower() in SUPPORTED_EXTENSIONS
    )
    if exclude_guideline:
        files = [f for f in files if not is_guideline_file(f)]
    return files


def find_guideline(folder: Path) -> Path | None:
    """폴더에서 이름에 가이드라인 키워드가 들어간 이미지를 찾습니다."""
    for f in list_image_files(folder):
        if is_guideline_file(f):
            logger.info("가이드라인 이미지 발견: %s", f)
            return f
    return None


def load(image_path: Path | str) -> Image.Image:
    """이미지 파일을 PIL Image로 로드합니다.

    Args:
        image_path: 이미지 파일 경로.

    Returns:
        PIL.Image.Image 객체.

    Raises:
        FileNotFoundError: 이미지 파일이 존재하지 않을 경우.
        ValueError: 지원하지 않는 이미지 형식일 경우.
    """
    path = Path(image_path)

    if not path.exists():
        raise FileNotFoundError(
            f"이미지 파일을 찾을 수 없습니다: {path}\n"
            f"images/ 폴더에 이미지를 배치했는지 확인하세요."
        )

    if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise ValueError(
            f"지원하지 않는 이미지 형식입니다: {path.suffix}\n"
            f"지원 형식: {', '.join(SUPPORTED_EXTENSIONS)}"
        )

    image = Image.open(path).convert("RGB")
    logger.info("이미지 로드 완료: %s (크기: %dx%d)", path, *image.size)
    return image


def label(text: str) -> str:
    """이미지 앞에 붙는 라벨 텍스트 파트를 만든다."""
    return LABEL_FORMAT.format(label=text)
