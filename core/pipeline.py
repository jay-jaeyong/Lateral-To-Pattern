"""
Pipeline
---------
멀티스텝 채팅 파이프라인.

관찰 → 펼치기 → 라인 아트 3스텝을 순차 실행합니다.
  Step 1: [라벨, 신발 사진, ..., 프롬프트] → 텍스트 명세서
  Step 2: [가이드라인, Step 1 명세서, 프롬프트] → 2D 패턴 이미지
  Step 3: [Step 2 이미지, 프롬프트] (명세서 미포함) → 라인 아트 이미지

Step 1·2는 같은 채팅 세션을 공유해 이전 단계 응답을 히스토리로 유지합니다.
Step 3는 fresh_session=True로 표시되어 있어 자신의 차례 직전에 채팅 세션이
새로 열립니다. Step 1 명세서가 히스토리를 통해 Step 3에 전달되는 것을 막기
위함입니다(config/prompts.py 참고). 끊긴 히스토리는 Pipeline._history_archive에
보관되어 최종 chat_history.json에서는 그대로 이어져 보입니다.
"""

from __future__ import annotations

import logging
from pathlib import Path

from config.prompts import PIPELINE_STEPS
from config.gemini_config import build_response_config
from core.models import StepResult, PipelineResult, StepResponse
from core._parts_builder import build_step_parts
from services.gemini_client import GeminiClient
from handlers.image_handler import ImageHandler
from handlers.output_handler import OutputHandler
from utils.logging_utils import step_context
from utils.cli import VIEW_FLAGS, label_image_files, resolve_run_label_from_path
from PIL import Image as PILImage

logger = logging.getLogger(__name__)


class Pipeline:
    """순차적 멀티스텝 Gemini 채팅 파이프라인.

    config/prompts.py에 정의된 PIPELINE_STEPS를 순서대로 실행합니다.
    Step 1·2는 같은 채팅 세션을 공유해 컨텍스트가 유지되지만, fresh_session=True로
    표시된 스텝(Step 3)은 실행 직전에 채팅 세션이 새로 시작되어 그 전 단계들의
    컨텍스트를 이어받지 않습니다.
    """

    def __init__(
        self,
        steps: list[dict] | None = None,
        output_dir: Path | str = Path("output"),
        run_label: str | None = None,
        batch_targets: list[Path] | None = None,
    ) -> None:
        """
        Args:
            steps: 파이프라인 단계 정의 목록.
                   None이면 config/prompts.py의 PIPELINE_STEPS 사용.
            output_dir: 결과 파일을 저장할 디렉터리.
            run_label: 실행 식별자 (출력 파일명에 사용). None이면 타임스탬프 자동 생성.
            batch_targets: 신발 이미지(또는 모델 폴더) 목록. 주어지면 각 항목마다
                           파이프라인을 개별 실행합니다.
        """
        # enabled=False로 꺼둔 스텝은 아예 실행 목록에서 뺍니다.
        self._steps = [s for s in (steps or PIPELINE_STEPS) if s.get("enabled", True)]
        self._batch_targets = batch_targets
        self._client = GeminiClient()
        self._output_handler = OutputHandler(
            output_dir=Path(output_dir),
            run_label=run_label,
        )
        # 초기 입력 이미지(단계별)를 보관합니다. key: step number -> list[PIL.Image]
        self._initial_images: dict[int, list] = {}
        # 첫 스텝에 넣은 실물 사진을 (라벨, 이미지)로 보관합니다. 뒤 스텝이
        # 채팅 히스토리 대신 직접 다시 참조할 때 씁니다.
        self._reference_images: list[tuple[str, object]] = []
        # 사용자가 명시적으로 run_label을 제공했는지 여부
        self._run_label_forced = run_label is not None
        # fresh_session으로 채팅 세션을 다시 열기 전에, 그때까지 쌓인 히스토리를
        # 여기 이어 붙여둡니다. save_final에 넘길 때 현재 세션 히스토리와 합쳐
        # chat_history.json에서 턴이 유실되지 않게 합니다.
        self._history_archive: list = []

    # ──────────────────────────────────────────────────
    # 실행
    # ──────────────────────────────────────────────────

    @staticmethod
    def _resolve_model_subdir(base_path: Path, model_name: str, fallback_to_first: bool = True) -> Path:
        """base_path 내에서 model_name과 일치하는 서브폴더를 반환합니다.

        일치하는 폴더가 없으면 fallback_to_first에 따라 첫 번째 서브폴더 또는
        base_path를 그대로 반환합니다.
        """
        if not base_path.is_dir():
            return base_path
        # 1) 정확히 일치
        target = base_path / model_name
        if target.is_dir():
            logger.info("모델 서브폴더 발견: %s", target)
            return target
        # 2) 공백 → 언더스코어 변환 후 재시도
        target_under = base_path / model_name.replace(" ", "_")
        if target_under.is_dir():
            logger.info("모델 서브폴더 발견 (공백→_): %s", target_under)
            return target_under
        # 3) 언더스코어 → 공백 변환 후 재시도
        target_space = base_path / model_name.replace("_", " ")
        if target_space.is_dir():
            logger.info("모델 서브폴더 발견 (_→공백): %s", target_space)
            return target_space
        if fallback_to_first:
            subdirs = sorted([d for d in base_path.iterdir() if d.is_dir()])
            if subdirs:
                logger.warning(
                    "모델명(%s)과 일치하는 폴더 없음 → 첫 번째 폴더 사용: %s",
                    model_name,
                    subdirs[0],
                )
                return subdirs[0]
        return base_path

    @staticmethod
    def _derive_model_name(image_path: Path | str | None) -> str | None:
        """입력 이미지 경로에서 신발 모델명을 추론합니다.

        모델 폴더들을 담고 있는 상위 폴더라면(아직 모델이 정해지지 않은 상태)
        None을 반환합니다.
        """
        if image_path is None:
            return None
        path = Path(image_path)
        if path.is_dir():
            has_subdirs = any(
                child.is_dir() and not child.name.startswith(".")
                for child in path.iterdir()
            )
            return None if has_subdirs else path.name
        if path.is_file():
            return path.stem
        return None

    def _resolve_step_images(self, config: dict, model_name: str | None, is_first: bool) -> dict:
        """모델명이 정해졌다면 이미지 경로를 해당 모델 서브폴더로 좁힙니다.

        첫 스텝의 image_path는 이미 선택이 끝났으므로 건드리지 않습니다.
        가이드라인 경로는 런타임에 변경되지 않습니다 (미리 해석되어 있음).
        """
        if not model_name:
            return config

        resolved = dict(config)

        if not is_first and config.get("image_path") is not None:
            resolved["image_path"] = self._resolve_model_subdir(Path(config["image_path"]), model_name)

        return resolved

    @staticmethod
    def _pair_labels_with_images(parts: list) -> list[tuple[str, object]]:
        """[라벨, 이미지, 라벨, 이미지, ...] 형태의 parts에서 쌍을 뽑습니다."""
        pairs: list[tuple[str, object]] = []
        for index, part in enumerate(parts[:-1]):
            if isinstance(part, str) and isinstance(parts[index + 1], PILImage.Image):
                pairs.append((part, parts[index + 1]))
        return pairs

    def _references_for(self, wanted: list[str]) -> list[tuple[str, object]]:
        """스텝이 요청한 뷰의 (라벨, 이미지)를 첫 스텝 입력에서 골라옵니다.

        wanted는 뷰 플래그 이름 목록입니다(예: ["lateral"]). 해당 뷰가 없으면
        경고만 남기고 건너뜁니다. 사진이 없는 실행에서도 죽지 않아야 합니다.
        """
        if not wanted or not self._reference_images:
            return []

        labels = dict(VIEW_FLAGS)
        picked: list[tuple[str, object]] = []
        for name in wanted:
            canonical = labels.get(name)
            if canonical is None:
                continue
            match = next(
                (pair for pair in self._reference_images if canonical in pair[0]), None
            )
            if match is None:
                logger.warning("참조로 요청한 '%s' 사진이 첫 스텝 입력에 없습니다.", canonical)
                continue
            picked.append(match)
        return picked

    def _run_for_each(self, targets: list[Path], pipeline_result: PipelineResult) -> PipelineResult:
        """선택된 모델 폴더마다 파이프라인을 개별 실행합니다('all' 선택 또는 --shoe-image 배치)."""
        base_output_dir = self._output_handler._run_dir.parent
        labels_seen: set[str] = set()

        for target in targets:
            target_path = Path(target)
            per_steps = [dict(s) for s in self._steps]

            # 대상이 디렉터리면 그 안의 모든 이미지를 view_images로 설정합니다.
            if target_path.is_dir():
                image_files = ImageHandler.list_image_files(target_path, exclude_guideline=True)
                if not image_files:
                    # 여기서 넘어가지 않고 진행하면 image_path가 기본 폴더로 남아
                    # 이 폴더 이름을 단 출력에 다른 신발 사진이 들어갑니다.
                    logger.warning("사용할 이미지가 없어 건너뜁니다: %s", target_path)
                    continue
                per_steps[0]["view_images"] = label_image_files(image_files)
                per_steps[0]["image_path"] = None
            else:
                # 파일 타겟은 기존 방식 (image_path 설정)
                per_steps[0]["image_path"] = target_path

            # 경로 stem이 뷰 플래그 이름이면 부모 폴더명을 사용합니다.
            label = resolve_run_label_from_path(target_path)

            # 라벨이 겹치면 출력 폴더가 서로를 덮어쓰므로 유일해질 때까지 바꿉니다.
            final_label = label
            if final_label in labels_seen:
                # 먼저 stem을 붙여보고(예: "adidas_adiracer_medial"),
                # 그래도 겹치면 번호를 올립니다.
                final_label = f"{label}_{target_path.stem}"
                suffix = 2
                while final_label in labels_seen:
                    final_label = f"{label}_{target_path.stem}_{suffix}"
                    suffix += 1
                logger.warning("라벨 충돌 '%s' → '%s'로 바꿉니다", label, final_label)
            labels_seen.add(final_label)

            per_pipeline = Pipeline(
                steps=per_steps,
                output_dir=base_output_dir,
                run_label=final_label,
            )
            try:
                sub_result = per_pipeline.run(skip_initial_selection=True)
                pipeline_result.steps.extend(sub_result.steps)
            except Exception:
                logger.exception("모델별 파이프라인 실행 실패: %s", target)

        logger.info("배치 실행 완료")
        return pipeline_result

    def run(self, skip_initial_selection: bool = False) -> PipelineResult:
        """파이프라인 전체를 실행합니다.

        Returns:
            각 단계의 결과를 담은 PipelineResult 객체.
        """
        logger.info("파이프라인 시작 (총 %d 단계)", len(self._steps))
        self._client.start_chat()

        pipeline_result = PipelineResult()

        # --- 신발 이미지를 여러 개 받았다면 하나씩 개별 실행 ---
        if self._batch_targets and not skip_initial_selection:
            logger.info("신발 이미지 %d개를 개별 실행합니다", len(self._batch_targets))
            return self._run_for_each(self._batch_targets, pipeline_result)

        # 누적된 이전 단계의 텍스트 응답 및 생성 이미지를 보관합니다
        previous_texts: list[str] = []
        previous_images: list = []
        # 첫 단계에서 선택된 신발 모델명을 보관합니다
        model_name: str | None = None
        # 첫 단계의 이미지 선택 결과(이미 로드된 parts)
        prebuilt_parts: list | None = None

        # --- 첫 스텝 입력(신발 실물 사진) 선택 ---
        if not skip_initial_selection and self._steps:
            first_cfg = self._steps[0]
            first_img_path = first_cfg.get("image_path")
            try:
                if first_img_path is not None and Path(first_img_path).is_dir():
                    # 사용자에게 폴더 선택(또는 'all')을 묻되, 아직 API 호출은 하지 않습니다.
                    prebuilt_parts = ImageHandler.build_parts(
                        first_cfg["prompt"],
                        first_img_path,
                        max_images=first_cfg.get("max_images"),
                    )
                    selected_files = getattr(ImageHandler, "_last_selected_files", None) or []
                    selection_all = getattr(ImageHandler, "_last_selection_was_all", False)

                    # 'all'을 선택했다면 모델 폴더마다 전체 파이프라인을 별도 실행합니다.
                    if selection_all and len(selected_files) > 1:
                        return self._run_for_each(selected_files, pipeline_result)

                    if selected_files:
                        model_name = selected_files[0].stem
                        logger.info("신발 모델명 인식: %s", model_name)
            except Exception:
                logger.exception("초기 선택 처리 중 오류 발생 — 기본 순차 실행으로 전환합니다")
                prebuilt_parts = None

        # --- 단계 순차 실행 ---
        for index, step_config in enumerate(self._steps):
            if model_name is None:
                model_name = self._derive_model_name(step_config.get("image_path"))
                if model_name:
                    logger.info("신발 모델명 인식: %s", model_name)

            step_config = self._resolve_step_images(step_config, model_name, is_first=(index == 0))

            if step_config.get("fresh_session"):
                # 히스토리 경로로 이전 단계 텍스트가 전달되지 않도록 세션을 끊습니다.
                # 끊기 전 히스토리는 archive에 보관해 chat_history.json에서 유실되지 않게 합니다.
                self._history_archive.extend(self._client.chat_history)
                self._client.start_chat()
                logger.info("Step %d: fresh_session=True — 채팅 세션을 새로 시작합니다", step_config["step"])

            step_result = self._run_step(
                step_config,
                previous_texts,
                previous_images,
                prebuilt_parts=prebuilt_parts if index == 0 else None,
            )

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
            chat_history=self._history_archive + self._client.chat_history,
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
        guide_image_path = config.get("guide_image_path")
        view_images = config.get("view_images")
        reference_views = config.get("reference_views")
        should_save = config.get("save_output", True)

        with step_context(step_num):
            logger.info("─── Step %d: %s ───", step_num, description)

            # ── parts 조립 (core/_parts_builder.py) ──────────────────────────
            try:
                parts = build_step_parts(
                    step_num=step_num,
                    prompt=prompt,
                    image_path=image_path,
                    prev_images=previous_images or [],
                    prev_texts=previous_texts or [],
                    prebuilt_parts=prebuilt_parts,
                    guide_image_path=guide_image_path,
                    max_images=config.get("max_images"),
                    view_images=view_images,
                    reference_images=self._references_for(reference_views or []),
                    include_prev_texts=config.get("include_prev_texts", True),
                    prev_image_label=config.get("prev_image_label"),
                )
            except Exception:
                logger.exception("parts 조립 실패 — 프롬프트만으로 진행합니다.")
                parts = [prompt]

            # ── 입력 이미지 캡처 (이후 단계 재사용용) ──────────────────────
            try:
                imgs_in_parts = [p for p in parts if isinstance(p, PILImage.Image)]
                if imgs_in_parts:
                    self._initial_images[step_num] = imgs_in_parts
                if not self._reference_images:
                    self._reference_images = self._pair_labels_with_images(parts)
            except Exception:
                logger.debug("입력 이미지 캡처 실패 (무시)")

            # 이미지 선택이 발생했고, 사용자가 run_label을 명시하지 않았다면
            # 출력 레이블을 선택한 이미지 이름으로 설정합니다 (실제 디렉터리 생성 전).
            try:
                selected_files = getattr(ImageHandler, "_last_selected_files", None)
                if selected_files and not self._run_label_forced and not self._output_handler._run_dir_created:
                    new_label = self._output_handler._sanitize_filename(resolve_run_label_from_path(selected_files[0]))
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
            # 관찰 스텝처럼 텍스트 응답이 필요한 단계만 모달리티를 바꿔 부릅니다.
            response_modalities = config.get("response_modalities")
            response_schema = config.get("response_schema")
            step_response: StepResponse = self._client.send(
                parts,
                config=build_response_config(
                    response_modalities,
                    response_schema=response_schema,
                    match_input_aspect_ratio=config.get(
                        "match_input_aspect_ratio", False
                    ),
                ),
            )

            if response_modalities and "TEXT" in response_modalities and not step_response.text:
                logger.warning(
                    "Step %d: TEXT 응답을 요청했지만 텍스트가 비어 있습니다. "
                    "다음 단계로 넘길 명세서가 없습니다.",
                    step_num,
                )

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
