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
            path = Path(image_path)

            # 디렉터리인 경우 내부의 모든 지원 이미지 파일을 로드합니다.
            if path.is_dir():
                images: list[Image.Image] = []
                for child in sorted(path.iterdir()):
                    if child.is_file() and child.suffix.lower() in ImageHandler.SUPPORTED_EXTENSIONS:
                        try:
                            images.append(ImageHandler.load(child))
                        except Exception as exc:  # 로그는 남기고 다음 파일로 진행
                            logger.warning("이미지 로드 실패: %s — %s", child, exc)

                # 이미지가 하나도 없으면 프롬프트만으로 진행하도록 합니다 (채팅 컨텍스트 유지)
                if not images:
                    logger.info("이미지 없음: %s — 프롬프트만으로 진행합니다.", path)
                    return [prompt]

                return [*images, prompt]

            # 파일인 경우 기존 동작 유지
            image = ImageHandler.load(path)
            return [image, prompt]
        return [prompt]
