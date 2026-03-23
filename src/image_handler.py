"""
Image Handler
--------------
이미지 파일을 로드하고 Gemini API에 전달 가능한 형태로 변환합니다.
"""

from __future__ import annotations

import logging
from pathlib import Path

from PIL import Image

logger = logging.getLogger(__name__)


class ImageHandler:
    """이미지 로드 및 전처리 유틸리티."""

    # Gemini가 지원하는 이미지 확장자
    SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}

    @staticmethod
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

        if path.suffix.lower() not in ImageHandler.SUPPORTED_EXTENSIONS:
            raise ValueError(
                f"지원하지 않는 이미지 형식입니다: {path.suffix}\n"
                f"지원 형식: {', '.join(ImageHandler.SUPPORTED_EXTENSIONS)}"
            )

        image = Image.open(path).convert("RGB")
        logger.info("이미지 로드 완료: %s (크기: %dx%d)", path, *image.size)
        return image

    @staticmethod
    def build_parts(prompt: str, image_path: Path | str | None) -> list:
        """Gemini API에 전달할 parts 리스트를 구성합니다.

        이미지가 있으면 [image, prompt] 순서로 구성합니다.
        이미지가 없으면 [prompt]만 반환합니다.

        Args:
            prompt: 텍스트 프롬프트.
            image_path: 이미지 파일 경로 (None이면 텍스트만).

        Returns:
            Gemini API에 전달할 parts 리스트.
        """
        if image_path is not None:
            image = ImageHandler.load(image_path)
            return [image, prompt]
        return [prompt]
