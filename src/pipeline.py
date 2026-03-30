"""
Pipeline
---------
멀티스텝 채팅 파이프라인.

이미지 + 프롬프트 → Gemini API → 이미지 + 프롬프트 → Gemini API → ... → output 저장

각 단계는 이전 단계의 응답을 채팅 히스토리로 유지한 채 실행되므로,
Gemini는 전체 대화 맥락을 가지고 각 단계에 응답합니다.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from config.prompts import PIPELINE_STEPS
from src.gemini_client import GeminiClient, StepResponse
from src.image_handler import ImageHandler
from utils.output_handler import OutputHandler
from src.logging_utils import step_context

logger = logging.getLogger(__name__)


@dataclass
class StepResult:
    """단계별 실행 결과."""

    step: int
    name: str
    description: str
    prompt: str
    image_path: Path | None
    response: str                              # Gemini 텍스트 응답
    generated_images: list = field(default_factory=list)  # Gemini 생성 이미지
    output_file: Path | None = None


@dataclass
class PipelineResult:
    """전체 파이프라인 실행 결과."""

    steps: list[StepResult] = field(default_factory=list)

    @property
    def final_output(self) -> str:
        """마지막 단계의 응답을 반환합니다."""
        if not self.steps:
            return ""
        return self.steps[-1].response

    def summary(self) -> str:
        """각 단계 결과의 요약 문자열을 반환합니다."""
        lines = ["=" * 60, "파이프라인 실행 요약", "=" * 60]
        for result in self.steps:
            lines.append(f"\n[Step {result.step}] {result.description}")
            lines.append(f"  입력 이미지: {result.image_path or '없음'}")
            lines.append(f"  생성 이미지: {len(result.generated_images)}장")
            lines.append(f"  저장 위치:   {result.output_file or '저장 안 함'}")
            lines.append(f"  응답 길이:   {len(result.response)}자")
        lines.append("\n" + "=" * 60)
        return "\n".join(lines)


class Pipeline:
    """순차적 멀티스텝 Gemini 채팅 파이프라인.

    config/prompts.py에 정의된 PIPELINE_STEPS를 순서대로 실행합니다.
    각 단계는 동일한 채팅 세션 안에서 실행되어 컨텍스트가 유지됩니다.
    """

    def __init__(
        self,
        steps: list[dict] | None = None,
        output_dir: Path | str = Path("output"),
        run_label: str | None = None,
    ) -> None:
        """
        Args:
            steps: 파이프라인 단계 정의 목록.
                   None이면 config/prompts.py의 PIPELINE_STEPS 사용.
            output_dir: 결과 파일을 저장할 디렉터리.
            run_label: 실행 식별자 (출력 파일명에 사용). None이면 타임스탬프 자동 생성.
        """
        self._steps = steps or PIPELINE_STEPS
        self._client = GeminiClient()
        self._output_handler = OutputHandler(
            output_dir=Path(output_dir),
            run_label=run_label,
        )
        # 사용자가 명시적으로 run_label을 제공했는지 여부를 보관합니다.
        self._run_label_forced = run_label is not None

    # ──────────────────────────────────────────────────
    # 실행
    # ──────────────────────────────────────────────────

    def run(self) -> PipelineResult:
        """파이프라인 전체를 실행합니다.

        Returns:
            각 단계의 결과를 담은 PipelineResult 객체.
        """
        logger.info("파이프라인 시작 (총 %d 단계)", len(self._steps))
        self._client.start_chat()

        pipeline_result = PipelineResult()
        # 누적된 이전 단계의 텍스트 응답 및 생성 이미지를 보관합니다
        previous_texts: list[str] = []
        previous_images: list = []

        for step_config in self._steps:
            step_result = self._run_step(step_config, previous_texts, previous_images)
            pipeline_result.steps.append(step_result)
            if step_result.response:
                previous_texts.append(step_result.response)
            if step_result.generated_images:
                previous_images.extend(step_result.generated_images)

        # 최종 결과 저장
        last = pipeline_result.steps[-1] if pipeline_result.steps else None
        self._output_handler.save_final(
            text=pipeline_result.final_output,
            generated_images=last.generated_images if last else [],
            chat_history=self._client.chat_history,
        )

        logger.info("파이프라인 완료")
        return pipeline_result

    # ──────────────────────────────────────────────────
    # 단계 실행
    # ──────────────────────────────────────────────────

    def _run_step(self, config: dict, previous_texts: list[str] | None = None, previous_images: list | None = None) -> StepResult:
        """단일 파이프라인 단계를 실행합니다."""
        step_num = config["step"]
        name = config["name"]
        description = config["description"]
        prompt = config["prompt"]
        image_path = config.get("image_path")
        should_save = config.get("save_output", True)

        with step_context(step_num):
            logger.info("─── Step %d: %s ───", step_num, description)

            # 이미지 + 프롬프트 → parts 구성
            parts = ImageHandler.build_parts(prompt, image_path)

            # 이전 단계에서 생성된 이미지가 있으면 parts 앞에 포함시킵니다.
            # 단, 2단계에서는 이전 단계 결과물을 포함하지 않음
            if previous_images and step_num != 2:
                try:
                    parts = [*previous_images, *parts]
                    logger.info("이전 단계 생성 이미지(%d개)를 현재 요청에 포함했습니다.", len(previous_images))
                except Exception:
                    logger.info("이전 단계 생성 이미지를 요청에 포함하지 못했습니다.")

            # 이전 단계의 응답 텍스트가 있으면 parts에 포함시킵니다.
            # 단, 2단계에서는 이전 단계 결과물을 포함하지 않음
            if previous_texts and step_num != 2:
                try:
                    prev_combined = "\n\n".join(
                        f"[Previous Step {i+1} Output]\n{txt}" for i, txt in enumerate(previous_texts) if txt
                    )
                    if parts and isinstance(parts[-1], str):
                        parts.insert(len(parts) - 1, prev_combined)
                    else:
                        parts.append(prev_combined)
                    logger.info("이전 단계 출력(%d개)을 현재 요청에 포함했습니다.", len(previous_texts))
                except Exception:
                    logger.info("이전 단계 출력을 요청에 포함하지 못했습니다.")

            # 이미지 선택이 발생했고, 사용자가 run_label을 명시하지 않았다면
            # 출력 레이블을 선택한 이미지 이름으로 설정합니다 (실제 디렉터리 생성 전).
            try:
                selected_files = getattr(ImageHandler, "_last_selected_files", None)
                if selected_files and not self._run_label_forced and not self._output_handler._run_dir_created:
                    new_label = self._output_handler._sanitize_filename(selected_files[0].stem)
                    base_dir = self._output_handler._run_dir.parent
                    self._output_handler._run_label = new_label
                    self._output_handler._run_dir = base_dir / new_label
                    logger.info("출력 디렉터리 레이블을 선택한 이미지로 설정: %s", new_label)
            except Exception:
                logger.exception("선택 이미지로 출력 레이블을 설정하는 중 오류 발생")

            # INFO-level: 실제로 API에 전달되는 `parts`와 현재 채팅 히스토리를 구분선으로 보기 좋게 출력합니다.
            sep = "\n" + ("─" * 60)
            try:
                logger.info(
                    "%s\n[ API REQUEST PARTS ]\n\n%s\n%s",
                    sep,
                    self._client._format_parts_for_log(parts),
                    sep,
                )
            except Exception:
                logger.info("%s\n[ API REQUEST PARTS ]\n<failed to format parts>\n%s", sep, sep)

            try:
                logger.info(
                    "%s\n[ CHAT HISTORY BEFORE SEND ]\n\n%s\n%s",
                    sep,
                    self._client._format_chat_history_for_log(),
                    sep,
                )
            except Exception:
                logger.info("%s\n[ CHAT HISTORY BEFORE SEND ]\n<failed to format history>\n%s", sep, sep)

            # Gemini API 호출 → 텍스트 + 생성 이미지
            step_response: StepResponse = self._client.send(parts)

            # 결과 저장
            output_file: Path | None = None
            if should_save:
                output_file = self._output_handler.save_step(
                    step=step_num,
                    name=name,
                    description=description,
                    prompt=prompt,
                    image_path=image_path,
                    response=step_response.text,
                    generated_images=step_response.images,
                )
                logger.info("Step %d 완료: %s", step_num, output_file or '저장 안 함')

        return StepResult(
            step=step_num,
            name=name,
            description=description,
            prompt=prompt,
            image_path=Path(image_path) if image_path else None,
            response=step_response.text,
            generated_images=step_response.images,
            output_file=output_file,
        )
