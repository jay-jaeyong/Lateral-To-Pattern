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
from pathlib import Path

from config.prompts import PIPELINE_STEPS
from core.models import StepResult, PipelineResult, StepResponse
from services.gemini_client import GeminiClient
from handlers.image_handler import ImageHandler
from handlers.output_handler import OutputHandler
from utils.logging_utils import step_context
from PIL import Image as PILImage

logger = logging.getLogger(__name__)


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
        # 초기 입력 이미지(단계별)를 보관합니다. key: step number -> list[PIL.Image]
        self._initial_images: dict[int, list] = {}
        # 사용자가 명시적으로 run_label을 제공했는지 여부
        self._run_label_forced = run_label is not None
        # 사용자가 명시적으로 run_label을 제공했는지 여부를 보관합니다.
        self._run_label_forced = run_label is not None

    # ──────────────────────────────────────────────────
    # 실행
    # ──────────────────────────────────────────────────

    @staticmethod
    def _resolve_model_subdir(base_path: Path, model_name: str) -> Path:
        """base_path 내에서 model_name과 일치하는 서브폴더를 반환합니다.

        일치하는 폴더가 없으면 첫 번째 서브폴더를, 서브폴더가 없으면 base_path를 반환합니다.
        """
        if not base_path.is_dir():
            return base_path
        target = base_path / model_name
        if target.is_dir():
            logger.info("모델 서브폴더 발견: %s", target)
            return target
        subdirs = sorted([d for d in base_path.iterdir() if d.is_dir()])
        if subdirs:
            logger.info(
                "모델명(%s)과 일치하는 폴더 없음 → 첫 번째 폴더 사용: %s",
                model_name,
                subdirs[0],
            )
            return subdirs[0]
        return base_path

    def run(self, skip_initial_selection: bool = False) -> PipelineResult:
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
        # 첫 단계(보통 Step1)에서 선택된 신발 모델명을 보관합니다
        model_name: str | None = None

        # --- 초기 선택(첫 스텝)에서 사용자가 'all'을 선택했는지 확인 ---
        if not skip_initial_selection and self._steps:
            first_cfg = self._steps[0]
            first_img_path = first_cfg.get("image_path")
            try:
                if first_img_path is not None and Path(first_img_path).is_dir():
                    # 사용자에게 파일 선택(또는 'all')을 묻되, 아직 API 호출은 하지 않습니다.
                    prebuilt_parts = ImageHandler.build_parts(first_cfg["prompt"], first_img_path)
                    selected_files = getattr(ImageHandler, "_last_selected_files", None)
                    selection_all = getattr(ImageHandler, "_last_selection_was_all", False)

                    # 사용자가 'all'을 선택했고, 여러 파일이 선택되었다면
                    # 각 파일마다 전체 파이프라인을 별도 실행합니다.
                    if selection_all and selected_files and len(selected_files) > 1:
                        base_output_dir = self._output_handler._run_dir.parent
                        for f in selected_files:
                            per_steps = [dict(s) for s in self._steps]
                            # 첫 스텝의 image_path를 해당 파일로 고정
                            per_steps[0]["image_path"] = Path(f)
                            # 새 Pipeline 인스턴스로 각 파일별 실행 (run_label에 파일명 사용)
                            per_pipeline = Pipeline(
                                steps=per_steps,
                                output_dir=base_output_dir,
                                run_label=Path(f).stem,
                            )
                            try:
                                sub_result = per_pipeline.run(skip_initial_selection=True)
                                pipeline_result.steps.extend(sub_result.steps)
                            except Exception:
                                logger.exception("파일별 파이프라인 실행 실패: %s", f)

                        logger.info("'all' 선택으로 인한 파일별 실행 완료")
                        return pipeline_result
                    else:
                        # 'all'이 아닌 경우(단일 선택 또는 특정 인덱스 선택)
                        # 이미 build_parts를 통해 선택과 이미지 로딩이 끝났으므로,
                        # 해당 prebuilt_parts를 사용해 첫 스텝을 실행합니다.
                        step_result = self._run_step(dict(first_cfg), previous_texts, previous_images, prebuilt_parts=prebuilt_parts)
                        pipeline_result.steps.append(step_result)
                        if step_result.response:
                            previous_texts.append(step_result.response)
                        if step_result.generated_images:
                            previous_images.extend(step_result.generated_images)

                        # 선택된 파일명에서 모델명 추출
                        if getattr(ImageHandler, "_last_selected_files", None):
                            sel = ImageHandler._last_selected_files
                            if sel:
                                model_name = sel[0].stem
                                logger.info("신발 모델명 인식: %s", model_name)

                        # 남은 스텝(첫 스텝 제외)을 계속 실행
                        for step_config in self._steps[1:]:
                            step_num = step_config.get("step", 0)
                            if step_num > 1 and model_name:
                                img_path = step_config.get("image_path")
                                if img_path is not None:
                                    resolved = self._resolve_model_subdir(Path(img_path), model_name)
                                    step_config = dict(step_config)
                                    step_config["image_path"] = resolved

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
            except Exception:
                logger.exception("초기 선택 처리 중 오류 발생 — 기본 순차 실행으로 전환합니다")

        # --- 기본 단일 실행 흐름(또는 skip_initial_selection=True인 경우) ---
        for step_config in self._steps:
            step_num = step_config.get("step", 0)

            # step 1 이후 단계에서 이미지 경로를 모델 서브폴더로 동적으로 교체합니다.
            if step_num > 1 and model_name:
                img_path = step_config.get("image_path")
                if img_path is not None:
                    resolved = self._resolve_model_subdir(Path(img_path), model_name)
                    step_config = dict(step_config)
                    step_config["image_path"] = resolved

            step_result = self._run_step(step_config, previous_texts, previous_images)

            # 첫 스텝(원래 Step1)의 실행 뒤에 모델명을 추출합니다.
            if step_config.get("step", 0) == self._steps[0].get("step", 0) and model_name is None:
                selected_files = getattr(ImageHandler, "_last_selected_files", None)
                if selected_files:
                    model_name = selected_files[0].stem
                    logger.info("신발 모델명 인식: %s", model_name)

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

    def _run_step(self, config: dict, previous_texts: list[str] | None = None, previous_images: list | None = None, prebuilt_parts: list | None = None) -> StepResult:
        """단일 파이프라인 단계를 실행합니다."""
        step_num = config["step"]
        name = config["name"]
        description = config["description"]
        prompt = config["prompt"]
        image_path = config.get("image_path")
        should_save = config.get("save_output", True)

        with step_context(step_num):
            logger.info("─── Step %d: %s ───", step_num, description)

            # 이미지 + 프롬프트 → parts 구성 (prebuilt_parts가 제공되면 재사용)
            parts = prebuilt_parts if prebuilt_parts is not None else ImageHandler.build_parts(prompt, image_path)

            # Include images into parts with special handling per step:
            # - Step 2: do NOT include Step1 original images (and do NOT include previous generated images)
            # - Step 3: include Step1 originals plus previous generated images
            # - Other steps: include previous generated images (if any)
            try:
                prev_imgs = previous_images or []
                if step_num == 2:
                    # Step 2: 이전 단계의 원본/생성 이미지는 포함하지 않고,
                    # 반드시 해당 단계의 가이드라인 이미지 디렉터리(image_path)와
                    # 프롬프트만 사용합니다.
                    try:
                        if image_path is not None:
                            # image_path가 디렉터리(또는 파일)일 경우 내부 이미지를 로드함.
                            parts = ImageHandler.build_parts(prompt, image_path)
                            logger.info("Step %d: 가이드라인 이미지(%s)와 프롬프트만 사용합니다.", step_num, image_path)
                        else:
                            parts = [prompt]
                            logger.info("Step %d: image_path 없음 — 프롬프트만 사용합니다.", step_num)
                    except Exception:
                        logger.exception("Step %d: 가이드라인 이미지 로드 실패 — 프롬프트만 사용합니다.", step_num)
                elif step_num == 3:
                    # step1_imgs = self._initial_images.get(1, [])
                    merged_prev = [ *prev_imgs] if prev_imgs else []
                    if merged_prev:
                        parts = [*merged_prev, *parts]
                        logger.info(
                            "Step %d에 이전 생성 이미지(%d장)를 포함했습니다.",
                            step_num,
                            len(prev_imgs),
                        )
                else:
                    if prev_imgs:
                        parts = [*prev_imgs, *parts]
                        logger.info("이전 단계 생성 이미지(%d개)를 현재 요청에 포함했습니다.", len(prev_imgs))
            except Exception:
                logger.info("이전 단계 생성 이미지를 요청에 포함하지 못했습니다.")

            # 현재 parts에 포함된 입력 이미지를 캡처해 두면 이후 단계에서 재사용할 수 있습니다.
            try:
                imgs_in_parts = [p for p in parts if isinstance(p, PILImage.Image)]
                if imgs_in_parts:
                    self._initial_images[step_num] = imgs_in_parts
            except Exception:
                logger.debug("입력 이미지 캡처 실패 (무시)")

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
