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

    # 파일명에 이 키워드가 들어 있으면 가이드라인(틀) 이미지로 봅니다.
    GUIDELINE_KEYWORDS = ("가이드라인", "가이드", "guideline", "guide")

    # 이미지 앞에 붙는 라벨 텍스트 파트의 형식.
    # Pillow가 로드할 때 파일명을 버리므로, 어느 각도 사진인지는 이 라벨로만 전달됩니다.
    LABEL_FORMAT = "[사진 {index}] {label}"

    # ──────────────────────────────────────────────────
    # 파일 탐색
    # ──────────────────────────────────────────────────

    @staticmethod
    def is_guideline_file(path: Path) -> bool:
        """파일명으로 가이드라인 이미지인지 판별합니다."""
        name = path.name.lower()
        return any(keyword.lower() in name for keyword in ImageHandler.GUIDELINE_KEYWORDS)

    @staticmethod
    def list_image_files(folder: Path, exclude_guideline: bool = False) -> list[Path]:
        """폴더 바로 아래의 지원 이미지 파일을 정렬해서 반환합니다."""
        if not folder.is_dir():
            return []
        files = sorted(
            f for f in folder.iterdir()
            if f.is_file()
            and not f.name.startswith(".")
            and f.suffix.lower() in ImageHandler.SUPPORTED_EXTENSIONS
        )
        if exclude_guideline:
            files = [f for f in files if not ImageHandler.is_guideline_file(f)]
        return files

    @staticmethod
    def find_guideline(folder: Path) -> Path | None:
        """폴더에서 이름에 가이드라인 키워드가 들어간 이미지를 찾습니다."""
        for f in ImageHandler.list_image_files(folder):
            if ImageHandler.is_guideline_file(f):
                logger.info("가이드라인 이미지 발견: %s", f)
                return f
        return None

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
    def build_parts(prompt: str, image_path: Path | str | None, max_images: int | None = None) -> list:
        """Gemini API에 전달할 parts 리스트를 구성합니다.

        이미지가 있으면 [image, prompt] 순서로 구성합니다.
        이미지가 없으면 [prompt]만 반환합니다.

        Args:
            prompt: 텍스트 프롬프트.
            image_path: 이미지 파일 경로 (None이면 텍스트만).
            max_images: 폴더에서 불러올 이미지 최대 장수 (None이면 전부).
                        1이면 정렬 기준 첫 이미지만 사용합니다.

        Returns:
            Gemini API에 전달할 parts 리스트.
        """
        # 초기화: 이전 선택 관련 상태 리셋
        ImageHandler._last_selection_was_all = False

        if image_path is not None:
            path = Path(image_path)

            if path.is_dir():
                # ── 폴더 바로 아래 이미지 파일이 있으면 파일 선택 모드 ────────────
                # (가이드라인 파일은 후보에서 제외합니다.)
                files = ImageHandler.list_image_files(path, exclude_guideline=True)

                if files:
                    selected_files = ImageHandler._select_entries(path, files, kind="이미지")
                    ImageHandler._last_selected_files = selected_files
                    ImageHandler._last_selection_was_all = len(selected_files) == len(files)

                    # 선택된 첫 번째 파일을 로드합니다.
                    # (batch "all" 실행 시 pipeline이 나머지 파일을 순회합니다.)
                    logger.info("입력 이미지 선택: %s", selected_files[0])
                    return [ImageHandler.load(selected_files[0]), prompt]

                # ── 이미지 파일이 없고 서브폴더가 있으면 폴더 선택 모드 ───────────
                subdirs = sorted(
                    [child for child in path.iterdir()
                     if child.is_dir() and not child.name.startswith(".")]
                )

                if subdirs:
                    selected_dirs = ImageHandler._select_entries(path, subdirs, kind="모델 폴더")
                    ImageHandler._last_selected_files = selected_dirs
                    ImageHandler._last_selection_was_all = len(selected_dirs) == len(subdirs)

                    # 선택된 첫 번째 폴더의 이미지를 로드합니다.
                    return ImageHandler._load_dir_images(selected_dirs[0], prompt, max_images)

                logger.info("폴더에 이미지가 없습니다: %s", path)
                return [prompt]

            # ── 단일 파일 ────────────────────────────────────────────────────────
            if path.is_file():
                ImageHandler._last_selected_files = [path]
                image = ImageHandler.load(path)
                return [image, prompt]

        return [prompt]

    @staticmethod
    def build_labeled_parts(labeled_paths: list[tuple[str, Path]], prompt: str) -> list:
        """(라벨, 경로) 목록을 [라벨, 이미지, ..., 프롬프트] 파트로 조립합니다.

        Args:
            labeled_paths: (라벨 문자열, 이미지 경로) 튜플 목록. 목록 순서가 전송 순서입니다.
            prompt: 맨 뒤에 붙일 텍스트 프롬프트.

        Returns:
            Gemini API에 전달할 parts 리스트.
            로드 가능한 이미지가 하나도 없으면 [prompt]만 반환합니다.
        """
        parts: list = []
        index = 1
        for label, path in labeled_paths:
            try:
                image = ImageHandler.load(path)
            except Exception as exc:  # noqa: BLE001
                logger.warning("이미지 로드 실패: %s — %s", path, exc)
                continue
            parts.append(ImageHandler.LABEL_FORMAT.format(index=index, label=label))
            parts.append(image)
            index += 1

        if not parts:
            logger.info("로드된 이미지가 없습니다 — 프롬프트만으로 진행합니다.")
            return [prompt]

        parts.append(prompt)
        return parts

    # ──────────────────────────────────────────────────
    # 내부 헬퍼
    # ──────────────────────────────────────────────────

    @staticmethod
    def _select_entries(base: Path, entries: list[Path], kind: str = "항목") -> list[Path]:
        """콘솔에서 파일 또는 폴더를 선택합니다. 비대화형이면 전체를 반환합니다."""
        import sys

        if len(entries) == 1 or not sys.stdin.isatty():
            return entries

        print(f"\n[{base.name}] 다음 {kind}을(를) 찾았습니다:")
        for i, entry in enumerate(entries, start=1):
            if entry.is_dir():
                # 폴더 안 이미지 수도 함께 표시
                print(f"  {i}) {entry.name}  ({len(ImageHandler.list_image_files(entry))}장)")
            else:
                print(f"  {i}) {entry.name}")

        raw = input(
            f"번호를 입력하세요 (예: 2). 'all' 또는 빈값은 전체 {kind}을(를) 순서대로 실행합니다: "
        ).strip()

        if raw == "" or raw.lower() in ("all", "a"):
            return entries

        try:
            idx = int(raw) - 1
            if 0 <= idx < len(entries):
                return [entries[idx]]
            logger.info("범위를 벗어난 번호 — 첫 번째 %s을(를) 사용합니다.", kind)
            return [entries[0]]
        except ValueError:
            logger.info("올바르지 않은 입력 — 첫 번째 %s을(를) 사용합니다.", kind)
            return [entries[0]]

    @staticmethod
    def _load_dir_images(folder: Path, prompt: str, max_images: int | None = None) -> list:
        """폴더 안의 지원 이미지를 로드해 [*images, prompt]를 반환합니다.

        max_images가 주어지면 정렬 순서 기준 앞에서 그 장수만 사용합니다.
        """
        image_files = ImageHandler.list_image_files(folder)
        if not image_files:
            logger.info("폴더에 이미지 없음: %s — 프롬프트만으로 진행합니다.", folder)
            return [prompt]

        if max_images is not None and len(image_files) > max_images:
            logger.info(
                "폴더 '%s'의 이미지 %d장 중 앞 %d장만 사용합니다: %s",
                folder.name,
                len(image_files),
                max_images,
                ", ".join(f.name for f in image_files[:max_images]),
            )
            image_files = image_files[:max_images]

        # 폴더 방식은 뷰 종류를 알 수 없으므로 파일명을 라벨로 넘겨 모델이 판단하게 합니다.
        parts = ImageHandler.build_labeled_parts(
            [(f"파일명: {f.stem}", f) for f in image_files], prompt
        )
        loaded = (len(parts) - 1) // 2
        logger.info("폴더 '%s'에서 이미지 %d장 로드 완료", folder.name, loaded)
        return parts
