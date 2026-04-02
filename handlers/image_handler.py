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

    # 최근 선택된 파일 목록 (빌드 파트에서 채워짐)
    _last_selected_files: list[Path] | None = None
    # 마지막 선택이 'all'로 이루어졌는지 여부 (빌드 파트에서 설정)
    _last_selection_was_all: bool = False

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
        # 초기화: 이전 선택 관련 상태 리셋
        ImageHandler._last_selection_was_all = False

        if image_path is not None:
            path = Path(image_path)

            if path.is_dir():
                # ── 서브폴더가 있으면 폴더 선택 모드 ──────────────────────────────
                subdirs = sorted(
                    [child for child in path.iterdir()
                     if child.is_dir() and not child.name.startswith(".")]
                )

                if subdirs:
                    selected_dirs = ImageHandler._select_subdir(path, subdirs)
                    ImageHandler._last_selected_files = selected_dirs
                    ImageHandler._last_selection_was_all = len(selected_dirs) == len(subdirs)

                    # 선택된 첫 번째 폴더의 이미지를 전부 로드합니다.
                    # (batch "all" 실행 시 pipeline이 나머지 폴더를 순회합니다.)
                    return ImageHandler._load_dir_images(selected_dirs[0], prompt)

                # ── 서브폴더 없음 → 현재 디렉터리의 이미지 파일을 그대로 로드 ──
                return ImageHandler._load_dir_images(path, prompt)

            # ── 단일 파일 ────────────────────────────────────────────────────────
            if path.is_file():
                ImageHandler._last_selected_files = [path]
                image = ImageHandler.load(path)
                return [image, prompt]

        return [prompt]

    # ──────────────────────────────────────────────────
    # 내부 헬퍼
    # ──────────────────────────────────────────────────

    @staticmethod
    def _select_subdir(base: Path, subdirs: list[Path]) -> list[Path]:
        """콘솔에서 서브폴더를 선택합니다. 비대화형이면 전체를 반환합니다."""
        import sys

        if len(subdirs) == 1 or not sys.stdin.isatty():
            return subdirs

        print(f"\n[{base.name}] 다음 모델 폴더들이 발견되었습니다:")
        for i, d in enumerate(subdirs, start=1):
            # 폴더 안 이미지 수도 함께 표시
            img_count = sum(
                1 for f in d.iterdir()
                if f.is_file() and f.suffix.lower() in ImageHandler.SUPPORTED_EXTENSIONS
            )
            print(f"  {i}) {d.name}  ({img_count}장)")

        raw = input(
            "폴더 번호를 입력하세요 (예: 2). 'all' 또는 빈값은 전체 폴더를 순서대로 실행합니다: "
        ).strip()

        if raw == "" or raw.lower() in ("all", "a"):
            return subdirs

        try:
            idx = int(raw) - 1
            if 0 <= idx < len(subdirs):
                return [subdirs[idx]]
            logger.info("범위를 벗어난 번호 — 첫 번째 폴더를 사용합니다.")
            return [subdirs[0]]
        except ValueError:
            logger.info("올바르지 않은 입력 — 첫 번째 폴더를 사용합니다.")
            return [subdirs[0]]

    @staticmethod
    def _load_dir_images(folder: Path, prompt: str) -> list:
        """폴더 안의 지원 이미지를 전부 로드해 [*images, prompt]를 반환합니다."""
        image_files = sorted(
            f for f in folder.iterdir()
            if f.is_file() and f.suffix.lower() in ImageHandler.SUPPORTED_EXTENSIONS
        )
        if not image_files:
            logger.info("폴더에 이미지 없음: %s — 프롬프트만으로 진행합니다.", folder)
            return [prompt]

        images: list[Image.Image] = []
        for f in image_files:
            try:
                images.append(ImageHandler.load(f))
            except Exception as exc:
                logger.warning("이미지 로드 실패: %s — %s", f, exc)

        if not images:
            logger.info("로드된 이미지 없음: %s — 프롬프트만으로 진행합니다.", folder)
            return [prompt]

        logger.info("폴더 '%s'에서 이미지 %d장 로드 완료", folder.name, len(images))
        return [*images, prompt]
