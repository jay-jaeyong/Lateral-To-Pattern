"""
Output Handler
---------------
각 파이프라인 단계의 결과를 output/ 디렉터리에 파일로 저장합니다.

저장 구조:
    output/
    └── {run_label}/              ← 실행별 폴더 (타임스탬프 또는 사용자 지정)
        ├── step_01_initial_analysis.md
        ├── step_02_lateral_pattern_extraction.md
        ├── step_03_final_synthesis.md
        └── final_output.md       ← 전체 결과 + 채팅 히스토리 요약
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


class OutputHandler:
    """파이프라인 실행 결과를 파일로 저장합니다."""

    def __init__(
        self,
        output_dir: Path = Path("output"),
        run_label: str | None = None,
    ) -> None:
        """
        Args:
            output_dir: 결과 파일을 저장할 최상위 디렉터리.
            run_label: 실행 식별자. None이면 실행 시각 기반의 레이블 자동 생성.
        """
        self._run_label = run_label or datetime.now().strftime("%Y%m%d_%H%M%S")
        self._run_dir = output_dir / self._run_label
        # run dir is created lazily to allow image selection and other setup
        # to happen before filesystem side-effects. Actual directory creation
        # and logging occurs in `_ensure_run_dir()` when saving.
        self._run_dir_created = False

    @property
    def run_dir(self) -> Path:
        """현재 실행의 출력 디렉터리 경로."""
        self._ensure_run_dir()
        return self._run_dir

    # ──────────────────────────────────────────────────
    # 단계별 결과 저장
    # ──────────────────────────────────────────────────

    def save_step(
        self,
        step: int,
        name: str,
        description: str,
        prompt: str,
        image_path: Path | str | None,
        response: str,
        generated_images: list | None = None,
    ) -> Path:
        """단계별 결과를 Markdown 파일로 저장하고 생성된 이미지도 저장합니다.

        Returns:
            저장된 Markdown 파일의 경로.
        """
        # Ensure output directory exists before writing files
        self._ensure_run_dir()

        # 생성된 이미지 저장 (파일명 안전화 및 예외 처리)
        saved_image_paths: list[Path] = []
        safe_name = self._sanitize_filename(name)
        for idx, img in enumerate(generated_images or [], start=1):
            img_filename = f"step_{step:02d}_{safe_name}_generated_{idx:02d}.png"
            img_path = self._run_dir / img_filename
            try:
                img.save(img_path)
                saved_image_paths.append(img_path)
                logger.info("Step %d 생성 이미지 저장: %s", step, img_path)
            except Exception:
                logger.exception("이미지 저장 실패: %s", img_path)

        # Markdown 저장
        filename = f"step_{step:02d}_{safe_name}.md"
        file_path = self._run_dir / filename

        content = self._format_step_markdown(
            step=step,
            description=description,
            prompt=prompt,
            image_path=image_path,
            response=response,
            saved_image_paths=saved_image_paths,
        )

        try:
            file_path.write_text(content, encoding="utf-8")
            logger.info("Step %d 결과 저장: %s", step, file_path)
        except Exception:
            logger.exception("Markdown 파일 저장 실패: %s", file_path)
        return file_path

    # ──────────────────────────────────────────────────
    # 최종 결과 저장
    # ──────────────────────────────────────────────────

    def save_final(self, text: str, generated_images: list | None = None, chat_history: list | None = None) -> Path:
        """최종 응답과 전체 채팅 히스토리를 저장합니다.

        Returns:
            저장된 파일의 경로.
        """
        # Ensure output directory exists before writing files
        self._ensure_run_dir()

        # 최종 생성 이미지 저장 (예외 처리)
        for idx, img in enumerate(generated_images or [], start=1):
            img_path = self._run_dir / f"final_generated_{idx:02d}.png"
            try:
                img.save(img_path)
                logger.info("최종 생성 이미지 저장: %s", img_path)
            except Exception:
                logger.exception("최종 이미지 저장 실패: %s", img_path)

        # 최종 응답 Markdown
        final_md_path = self._run_dir / "final_output.md"
        try:
            final_md_path.write_text(
                self._format_final_markdown(text),
                encoding="utf-8",
            )
            logger.info("최종 결과 저장: %s", final_md_path)
        except Exception:
            logger.exception("최종 Markdown 파일 저장 실패: %s", final_md_path)

        # 채팅 히스토리 JSON
        history_path = self._run_dir / "chat_history.json"
        history_data = self._serialize_history(chat_history or [])
        try:
            history_path.write_text(
                json.dumps(history_data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            logger.info("채팅 히스토리 저장: %s", history_path)
        except Exception:
            logger.exception("채팅 히스토리 저장 실패: %s", history_path)

        return final_md_path

    def _ensure_run_dir(self) -> None:
        """Create the run directory if it doesn't exist and log creation once."""
        if getattr(self, "_run_dir_created", False):
            return
        try:
            if not self._run_dir.exists():
                self._run_dir.mkdir(parents=True, exist_ok=True)
                logger.info("출력 디렉터리 생성: %s", self._run_dir)
        except Exception:
            logger.exception("출력 디렉터리 생성 실패: %s", self._run_dir)
        finally:
            self._run_dir_created = True

    # ──────────────────────────────────────────────────
    # 포맷터
    # ──────────────────────────────────────────────────

    @staticmethod
    def _format_step_markdown(
        step: int,
        description: str,
        prompt: str,
        image_path: Path | str | None,
        response: str,
        saved_image_paths: list | None = None,
    ) -> str:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        image_str = str(image_path) if image_path else "없음"

        # 생성된 이미지 링크 목록
        if saved_image_paths:
            img_links = "\n".join(
                f"- ![생성이미지_{i}]({p.name})" for i, p in enumerate(saved_image_paths, 1)
            )
            generated_section = f"\n**생성된 이미지:**\n\n{img_links}\n"
        else:
            generated_section = "\n**생성된 이미지:** 없음\n"

        return (
            f"# Step {step}: {description}\n\n"
            f"> 생성 시각: {timestamp}\n\n"
            f"---\n\n"
            f"## 입력\n\n"
            f"**입력 이미지 경로:** `{image_str}`\n\n"
            f"**프롬프트:**\n\n"
            f"```\n{prompt}\n```\n\n"
            f"---\n\n"
            f"## Gemini 응답\n\n"
            f"### 텍스트\n\n"
            f"{response}\n"
            f"{generated_section}"
        )

    @staticmethod
    def _format_final_markdown(response: str) -> str:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return (
            f"# 최종 출력 (Final Output)\n\n"
            f"> 생성 시각: {timestamp}\n\n"
            f"---\n\n"
            f"{response}\n"
        )

    @staticmethod
    def _serialize_history(history: list) -> list[dict]:
        """채팅 히스토리(Gemini/OpenAI 양쪽)를 JSON 직렬화 가능한 형태로 변환합니다."""
        serialized = []
        for turn in history:
            parts_data = []
            for part in getattr(turn, "parts", []) or []:
                if getattr(part, "text", None):
                    parts_data.append({"type": "text", "content": part.text})
                elif getattr(part, "inline_data", None):
                    mime = getattr(part.inline_data, "mime_type", "unknown")
                    parts_data.append({
                        "type": "image",
                        "content": f"[이미지 데이터 mime_type={mime}]",
                    })
                else:
                    parts_data.append({"type": "unknown", "content": str(part)})
            serialized.append({"role": getattr(turn, "role", "unknown"), "parts": parts_data})
        return serialized

    @staticmethod
    def _sanitize_filename(value: str) -> str:
        """파일명으로 안전하게 변환합니다: 위험 문자 제거, 연속 구분자 축소."""
        if not value:
            return "untitled"
        # 위험한 문자들을 '_'로 대체
        s = re.sub(r'[\\/*?<>|:"\n\r]+', "_", value)
        # 공백을 언더스코어로
        s = re.sub(r"\s+", "_", s)
        # 여러 '_' 연속을 하나로
        s = re.sub(r"_+", "_", s)
        # 앞뒤 '_' 제거 및 길이 제한
        s = s.strip("_")[:100]
        return s or "untitled"
