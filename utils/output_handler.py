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
from datetime import datetime
from pathlib import Path
from PIL import Image as PILImage

from src.image_handler import ImageHandler

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
        self._run_dir.mkdir(parents=True, exist_ok=True)
        logger.info("출력 디렉터리 생성: %s", self._run_dir)

    @property
    def run_dir(self) -> Path:
        """현재 실행의 출력 디렉터리 경로."""
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
        chat_history_before: list | None = None,
    ) -> Path:
        """단계별 결과를 Markdown 파일로 저장하고 생성된 이미지도 저장합니다.

        Returns:
            저장된 Markdown 파일의 경로.
        """
        # 단계별 하위 디렉터리 생성 (예: output/{run_label}/step1)
        step_dir = self._run_dir / f"step{step}"
        step_dir.mkdir(parents=True, exist_ok=True)

        # 입력 이미지 정보 수집 (이름, 상대경로, 크기)
        input_image_infos: list[dict] = []
        if image_path:
            p = Path(image_path)
            if p.is_dir():
                for child in sorted(p.iterdir()):
                    if child.is_file() and child.suffix.lower() in ImageHandler.SUPPORTED_EXTENSIONS:
                        try:
                            with PILImage.open(child) as im:
                                size = im.size
                        except Exception:
                            size = None
                        input_image_infos.append({
                            "name": child.name,
                            "path": child.name,
                            "size": size,
                        })
            elif p.is_file():
                try:
                    with PILImage.open(p) as im:
                        size = im.size
                except Exception:
                    size = None
                input_image_infos.append({
                    "name": p.name,
                    "path": p.name,
                    "size": size,
                })

        # 생성된 이미지 저장 (단계별 폴더에 저장) 및 정보 수집
        saved_image_paths: list[Path] = []
        generated_image_infos: list[dict] = []
        for idx, img in enumerate(generated_images or [], start=1):
            # 가능한 경우 입력 이미지명으로 생성 이미지 파일명을 정해 덮어쓰기 가능하게 합니다.
            if input_image_infos:
                # 대응되는 입력 이미지가 있으면 그 이름을 사용
                if len(input_image_infos) >= idx:
                    base_name = Path(input_image_infos[idx - 1]["name"]).stem
                else:
                    # 입력이 하나뿐이면 모두 그 이름으로 덮어쓰기
                    base_name = Path(input_image_infos[0]["name"]).stem
                img_filename = f"{base_name}.png"
            else:
                img_filename = f"generated_{idx:02d}.png"
            img_path = step_dir / img_filename
            img.save(img_path)
            saved_image_paths.append(img_path)
            try:
                size = getattr(img, "size", None)
            except Exception:
                size = None
            generated_image_infos.append({
                "name": img_filename,
                "path": img_path.name,
                "size": size,
            })
            logger.info("Step %d 생성 이미지 저장: %s", step, img_path)

        # Markdown 저장 (단계별 폴더에 저장)
        filename = f"step_{step:02d}_{name}.md"
        file_path = step_dir / filename

        # 누적 채팅 히스토리(단계 시작 전)를 간단한 텍스트로 요약
        accumulated_text = ""
        if chat_history_before:
            serialized = self._serialize_history(chat_history_before)
            parts: list[str] = []
            for turn in serialized:
                role = turn.get("role", "unknown")
                texts = [p["content"] for p in turn.get("parts", []) if p.get("type") == "text"]
                if texts:
                    parts.append(f"- {role}: {' '.join(texts)}")
            accumulated_text = "\n".join(parts)

        content = self._format_step_markdown(
            step=step,
            description=description,
            prompt=prompt,
            image_path=image_path,
            response=response,
            input_images=input_image_infos,
            generated_images=generated_image_infos,
            step_dir=step_dir.name,
            run_label=self._run_label,
            accumulated_context=accumulated_text,
        )

        file_path.write_text(content, encoding="utf-8")
        logger.info("Step %d 결과 저장: %s", step, file_path)
        return file_path

    # ──────────────────────────────────────────────────
    # 최종 결과 저장
    # ──────────────────────────────────────────────────

    def save_final(self, text: str, generated_images: list | None = None, chat_history: list | None = None) -> Path:
        """최종 응답과 전체 채팅 히스토리를 저장합니다.

        Returns:
            저장된 파일의 경로.
        """
        # 최종 생성 이미지 저장
        for idx, img in enumerate(generated_images or [], start=1):
            img_path = self._run_dir / f"final_generated_{idx:02d}.png"
            img.save(img_path)
            logger.info("최종 생성 이미지 저장: %s", img_path)

        # 최종 응답 Markdown
        final_md_path = self._run_dir / "final_output.md"
        final_md_path.write_text(
            self._format_final_markdown(text),
            encoding="utf-8",
        )
        logger.info("최종 결과 저장: %s", final_md_path)

        # 채팅 히스토리 JSON
        history_path = self._run_dir / "chat_history.json"
        history_data = self._serialize_history(chat_history or [])
        history_path.write_text(
            json.dumps(history_data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info("채팅 히스토리 저장: %s", history_path)

        return final_md_path

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
        input_images: list[dict] | None = None,
        generated_images: list[dict] | None = None,
        step_dir: str | None = None,
        run_label: str | None = None,
        accumulated_context: str | None = None,
    ) -> str:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        image_str = str(image_path) if image_path else "없음"

        # 입력 이미지 섹션
        if input_images:
            input_lines = []
            for info in input_images:
                size_str = f" ({info['size'][0]}x{info['size'][1]})" if info.get("size") else ""
                input_lines.append(f"- {info['name']}{size_str}")
            input_section = "\n".join(input_lines)
        else:
            input_section = "없음"

        # 생성된 이미지 링크 및 정보
        if generated_images:
            gen_lines = []
            for i, info in enumerate(generated_images, 1):
                size = info.get("size")
                size_str = f" ({size[0]}x{size[1]})" if size else ""
                gen_lines.append(f"- ![generated_{i}]({info['path']}) {info['name']}{size_str}")
            generated_section = "\n".join(gen_lines)
        else:
            generated_section = "없음"

        metadata = f"Run: {run_label or 'unknown'} | Step dir: {step_dir or 'N/A'}"

        # 누적 컨텍스트(단계 시작 전에 Gemini가 가진 정보)
        acc_section = accumulated_context or "(없음)"

        return (
            "# Step "
            + str(step)
            + ": "
            + description
            + "\n\n"
            + "> 생성 시각: "
            + timestamp
            + "\n\n"
            + "---\n\n"
            + "**메타데이터:** "
            + metadata
            + "\n\n"
            + "## 입력 이미지\n\n"
            + input_section
            + "\n\n"
            + "---\n\n"
            + "## 프롬프트\n\n"
            + "```\n"
            + prompt
            + "\n```\n\n"
            + "---\n\n"
            + "## 누적 컨텍스트 (단계 시작 전)\n\n"
            + acc_section
            + "\n\n"
            + "---\n\n"
            + "## Gemini 응답\n\n"
            + "### 텍스트\n\n"
            + response
            + "\n\n"
            + "---\n\n"
            + "## 생성된 이미지\n\n"
            + generated_section
            + "\n"
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
        """Gemini 채팅 히스토리를 JSON 직렬화 가능한 형태로 변환합니다."""
        serialized = []
        for turn in history:
            parts_data = []
            for part in turn.parts:
                if getattr(part, "text", None):
                    parts_data.append({"type": "text", "content": part.text})
                elif getattr(part, "inline_data", None):
                    parts_data.append({
                        "type": "image",
                        "content": f"[이미지 데이터 mime_type={part.inline_data.mime_type}]",
                    })
                else:
                    parts_data.append({"type": "unknown", "content": str(part)})
            serialized.append({"role": turn.role, "parts": parts_data})
        return serialized
