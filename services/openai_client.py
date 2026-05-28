"""
OpenAI (GPT) Responses API Client
----------------------------------
client.responses.create() + image_generation 도구로 멀티턴 이미지 생성.

핵심 아이디어:
- start_chat(): previous_response_id를 None으로 초기화 → 새 대화 시작
- send(parts, step_num): 현재 단계 입력만 보냄. previous_response_id로 서버가
  이전 단계 컨텍스트를 자동으로 이어줌. 이전 이미지/텍스트를 재전송할 필요 없음.
- chat_history: 로깅용 (저장 등). 실제 대화 상태는 OpenAI 서버 + previous_response_id로 관리.
"""

from __future__ import annotations

import base64
import logging
import time
from io import BytesIO

from PIL import Image as PILImage
from openai import OpenAI

from config.api_config import get_openai_api_key
from config.openai_config import (
    MODEL_NAME,
    REASONING_EFFORT,
    TEXT_VERBOSITY,
    IMAGE_DETAIL,
    SIZE_STEP1,
    SIZE_DEFAULT,
    QUALITY,
    OUTPUT_FORMAT,
    MAX_RETRIES,
    RETRY_DELAY,
)
from core.models import StepResponse

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# 채팅 히스토리 호환 객체 (output_handler가 turn.role / turn.parts / part.text /
# part.inline_data.mime_type 만 사용하므로 그 attribute만 노출)
# ──────────────────────────────────────────────────────────────────────────────

class _InlineData:
    def __init__(self, mime_type: str) -> None:
        self.mime_type = mime_type


class _Part:
    def __init__(self, text: str | None = None, inline_data: _InlineData | None = None) -> None:
        self.text = text
        self.inline_data = inline_data


class _Turn:
    def __init__(self, role: str, parts: list[_Part]) -> None:
        self.role = role
        self.parts = parts


class OpenAIClient:
    """OpenAI Responses API 기반 멀티턴 이미지 생성 클라이언트."""

    def __init__(self) -> None:
        self._client = OpenAI(api_key=get_openai_api_key())
        self._previous_response_id: str | None = None
        self._history: list[_Turn] = []
        self._chat_started = False
        logger.info(
            "OpenAIClient 초기화 (모델: %s, reasoning=%s, image_detail=%s)",
            MODEL_NAME, REASONING_EFFORT, IMAGE_DETAIL,
        )

    # ──────────────────────────────────────────────────
    # 세션 관리
    # ──────────────────────────────────────────────────

    def start_chat(self) -> None:
        """새 대화 세션 시작: previous_response_id와 히스토리를 초기화."""
        self._previous_response_id = None
        self._history = []
        self._chat_started = True
        logger.info("새 채팅 세션 시작 (Responses API, previous_response_id=None)")

    @property
    def chat_history(self) -> list:
        return list(self._history)

    # ──────────────────────────────────────────────────
    # 메시지 전송
    # ──────────────────────────────────────────────────

    def send(self, parts: list, step_num: int | None = None, config_override=None) -> StepResponse:
        """parts(텍스트+이미지)를 Responses API로 보냅니다.

        previous_response_id 체이닝으로 이전 단계 맥락이 자동 누적되므로,
        parts에는 **현재 단계의 새 입력만** 들어가야 합니다.
        """
        if not self._chat_started:
            raise RuntimeError("채팅 세션이 시작되지 않았습니다. start_chat()을 먼저 호출하세요.")

        parts = self._flatten_parts(parts)

        # 텍스트와 이미지 분리
        text_parts: list[str] = []
        image_parts: list[PILImage.Image] = []
        for p in parts:
            if isinstance(p, str):
                text_parts.append(p)
            elif isinstance(p, PILImage.Image):
                image_parts.append(p)
            else:
                text_parts.append(repr(p)[:1000])

        prompt = "\n\n".join(t for t in text_parts if t).strip() or "Generate an image."

        # 메시지 콘텐츠 구성: 이미지 먼저, 텍스트 마지막
        content: list[dict] = []
        for img in image_parts:
            data_uri = self._pil_to_data_uri(img)
            content.append({
                "type": "input_image",
                "image_url": data_uri,
                "detail": IMAGE_DETAIL,
            })
        content.append({"type": "input_text", "text": prompt})

        # image_generation 도구 설정 (Step1만 21:9)
        size = SIZE_STEP1 if step_num == 1 else SIZE_DEFAULT
        tool_config: dict = {
            "type": "image_generation",
            "quality": QUALITY,
            "output_format": OUTPUT_FORMAT,
        }
        if size and size != "auto":
            tool_config["size"] = size

        # API 요청 페이로드
        request: dict = {
            "model": MODEL_NAME,
            "input": [{"role": "user", "content": content}],
            "tools": [tool_config],
            "reasoning": {"effort": REASONING_EFFORT},
            "text": {"verbosity": TEXT_VERBOSITY},
        }
        if self._previous_response_id:
            request["previous_response_id"] = self._previous_response_id

        logger.debug(
            "=== Responses API Call ===\nmodel=%s step=%s size=%s images=%d prompt_len=%d prev_id=%s",
            MODEL_NAME, step_num, size, len(image_parts), len(prompt), self._previous_response_id,
        )

        # 재시도 호출
        last_error: Exception | None = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = self._client.responses.create(**request)
                generated = self._parse_response(response)

                # 다음 호출을 위해 response.id 보관
                self._previous_response_id = getattr(response, "id", None)

                # 히스토리(로깅용) 누적
                self._record_turn("user", parts)
                self._record_turn("assistant", list(generated.images) + ([generated.text] if generated.text else []))

                logger.debug(
                    "응답 수신 완료 (텍스트: %d자, 이미지: %d장, new prev_id=%s)",
                    len(generated.text), len(generated.images), self._previous_response_id,
                )
                return generated
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                logger.warning("API 호출 실패 (시도 %d/%d): %s", attempt, MAX_RETRIES, exc)
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_DELAY)

        raise RuntimeError(
            f"OpenAI Responses API 호출이 {MAX_RETRIES}회 실패했습니다."
        ) from last_error

    # ──────────────────────────────────────────────────
    # 내부 헬퍼
    # ──────────────────────────────────────────────────

    @staticmethod
    def _pil_to_data_uri(img: PILImage.Image) -> str:
        """PIL 이미지를 data URI(base64 PNG)로 변환."""
        buf = BytesIO()
        save_img = img if img.mode in ("RGB", "RGBA") else img.convert("RGB")
        save_img.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        return f"data:image/png;base64,{b64}"

    @staticmethod
    def _parse_response(response) -> StepResponse:
        """Responses API 응답에서 생성 이미지와 텍스트를 추출."""
        images: list[PILImage.Image] = []
        text_chunks: list[str] = []

        outputs = getattr(response, "output", None) or []
        for item in outputs:
            item_type = getattr(item, "type", None)

            # image_generation_call: result에 base64 문자열
            if item_type == "image_generation_call":
                b64 = getattr(item, "result", None)
                if b64:
                    try:
                        img_bytes = base64.b64decode(b64)
                        images.append(PILImage.open(BytesIO(img_bytes)))
                    except Exception:
                        logger.exception("생성 이미지 디코드 실패")
                continue

            # message: content 안에 output_text가 있을 수 있음
            if item_type == "message":
                for c in getattr(item, "content", None) or []:
                    txt = getattr(c, "text", None)
                    if txt:
                        text_chunks.append(txt)

        # output_text 헬퍼가 있으면 보조로 활용
        if not text_chunks:
            out_text = getattr(response, "output_text", None)
            if out_text:
                text_chunks.append(out_text)

        return StepResponse(text="\n".join(text_chunks).strip(), images=images)

    def _record_turn(self, role: str, parts: list) -> None:
        rendered: list[_Part] = []
        for p in parts:
            if isinstance(p, str):
                rendered.append(_Part(text=p))
            elif isinstance(p, PILImage.Image):
                rendered.append(_Part(inline_data=_InlineData(mime_type="image/png")))
            else:
                rendered.append(_Part(text=repr(p)[:500]))
        self._history.append(_Turn(role=role, parts=rendered))

    @staticmethod
    def _flatten_parts(parts: list) -> list:
        flat: list = []

        def _rec(item):
            if isinstance(item, str):
                flat.append(item)
                return
            if isinstance(item, (list, tuple)):
                for sub in item:
                    _rec(sub)
                return
            flat.append(item)

        _rec(parts)
        return flat

    # ──────────────────────────────────────────────────
    # 로깅 포매터 (Pipeline에서 호출)
    # ──────────────────────────────────────────────────

    def _format_parts_for_log(self, parts: list) -> str:
        lines: list[str] = []
        for idx, part in enumerate(parts):
            try:
                if isinstance(part, PILImage.Image):
                    filename = getattr(part, "filename", None)
                    size = getattr(part, "size", None)
                    mode = getattr(part, "mode", None)
                    lines.append(f"part[{idx}]: Image filename={filename!r} size={size} mode={mode}")
                elif isinstance(part, str):
                    preview = " ".join(part.splitlines())[:200]
                    lines.append(f"part[{idx}]: Text(len={len(part)}) preview={preview!r}")
                else:
                    lines.append(f"part[{idx}]: {type(part).__name__} repr={repr(part)[:200]}")
            except Exception:
                lines.append(f"part[{idx}]: <failed to inspect>")
        return "\n".join(lines) if lines else "<no parts>"

    def _format_chat_history_for_log(self) -> str:
        if not self._history:
            return "<empty chat history>"
        lines: list[str] = []
        label_map = {"user": "You", "assistant": "Peer"}
        for turn in self._history:
            label = label_map.get(turn.role, turn.role)
            for p in turn.parts:
                if p.text:
                    first, *rest = p.text.splitlines() or [""]
                    lines.append(f"{label}: {first}")
                    for cont in rest:
                        lines.append("    " + cont)
                elif p.inline_data is not None:
                    lines.append(f"{label}: [Image mime={p.inline_data.mime_type}]")
        return "\n".join(lines) if lines else "<empty chat history>"
