"""
OpenAI (GPT) API Client
------------------------
gpt-image-2 모델로 이미지 생성/편집을 수행하는 클라이언트.
GeminiClient와 동일한 인터페이스(start_chat / send / chat_history)를 제공해
파이프라인 코드 변경 없이 교체할 수 있습니다.

내부 동작:
- send(parts)로 들어온 parts에서 텍스트는 합쳐 prompt로, PIL 이미지들은
  reference 이미지로 넘겨 images.edit를 호출합니다.
- 이미지가 하나도 없으면 images.generate를 사용합니다.
- 채팅 히스토리는 로깅용으로만 보관합니다 (실제 멀티턴 컨텍스트는 파이프라인이
  매 호출마다 prev_images / prev_texts를 parts에 누적해 넘겨주므로 별도 유지가 불필요).
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
# 채팅 히스토리 호환 객체 (GeminiClient의 history와 동일한 attribute 형태로 노출)
# output_handler._serialize_history와 _format_chat_history_for_log_inner는
# turn.role / turn.parts / part.text / part.inline_data.mime_type 만 사용합니다.
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
    """OpenAI 이미지 생성 클라이언트 (GeminiClient와 동일한 인터페이스)."""

    def __init__(self) -> None:
        self._client = OpenAI(api_key=get_openai_api_key())
        self._history: list[_Turn] = []
        self._chat_started = False
        logger.info("OpenAIClient 초기화 완료 (모델: %s)", MODEL_NAME)

    # ──────────────────────────────────────────────────
    # 채팅 세션 관리
    # ──────────────────────────────────────────────────

    def start_chat(self) -> None:
        """새 세션을 시작합니다. 히스토리(로깅용)를 초기화합니다."""
        self._history = []
        self._chat_started = True
        logger.info("새 채팅 세션 시작 (OpenAI)")

    @property
    def chat_history(self) -> list:
        return list(self._history)

    # ──────────────────────────────────────────────────
    # 메시지 전송
    # ──────────────────────────────────────────────────

    def send(self, parts: list, step_num: int | None = None, config_override=None) -> StepResponse:
        """parts(텍스트+이미지)를 OpenAI 이미지 API로 전송합니다.

        Args:
            parts: 텍스트 문자열과 PIL 이미지가 섞인 리스트.
            step_num: 현재 단계 번호. step_num==1이면 21:9에 가장 가까운
                      landscape 사이즈(1536x1024)를 사용합니다.
            config_override: GeminiClient와의 인터페이스 호환을 위해 받음 (미사용).
        """
        if not self._chat_started:
            raise RuntimeError(
                "채팅 세션이 시작되지 않았습니다. start_chat()을 먼저 호출하세요."
            )

        parts = self._flatten_parts(parts)

        # 텍스트 / 이미지 분리
        text_parts: list[str] = []
        image_parts: list[PILImage.Image] = []
        for p in parts:
            if isinstance(p, str):
                text_parts.append(p)
            elif isinstance(p, PILImage.Image):
                image_parts.append(p)
            else:
                # 알 수 없는 타입 → repr로 텍스트화
                text_parts.append(repr(p)[:1000])

        prompt = "\n\n".join(t for t in text_parts if t).strip()
        if not prompt:
            prompt = "Generate an image."

        size = SIZE_STEP1 if step_num == 1 else SIZE_DEFAULT

        # 공통 파라미터: size가 None이면 보내지 않음(모델 기본 사이즈 사용)
        common: dict = {
            "model": MODEL_NAME,
            "prompt": prompt,
            "quality": QUALITY,
            "output_format": OUTPUT_FORMAT,
            "n": 1,
        }
        if size:
            common["size"] = size

        # 요청/히스토리 로깅
        sep_parts = self._format_parts_for_log(parts)
        logger.debug("=== OpenAI API Request Parts ===\n%s", sep_parts)
        logger.debug(
            "=== OpenAI API Call ===\nmodel=%s size=%s quality=%s format=%s images=%d prompt_len=%d",
            MODEL_NAME, size, QUALITY, OUTPUT_FORMAT, len(image_parts), len(prompt),
        )

        # API 호출 (재시도)
        last_error: Exception | None = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                logger.debug("API 호출 시도 %d/%d", attempt, MAX_RETRIES)
                if image_parts:
                    files = [self._pil_to_upload(img, idx) for idx, img in enumerate(image_parts, start=1)]
                    response = self._client.images.edit(image=files, **common)
                else:
                    response = self._client.images.generate(**common)

                generated = self._parse_response(response)

                # 히스토리 누적 (로깅용)
                self._record_turn("user", parts)
                self._record_turn("assistant", [*generated.images, generated.text] if generated.text else list(generated.images))

                logger.debug(
                    "API 응답 수신 완료 (텍스트: %d자, 이미지: %d장)",
                    len(generated.text), len(generated.images),
                )
                return generated
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                logger.warning("API 호출 실패 (시도 %d/%d): %s", attempt, MAX_RETRIES, exc)
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_DELAY)

        raise RuntimeError(
            f"OpenAI API 호출이 {MAX_RETRIES}회 실패했습니다."
        ) from last_error

    # ──────────────────────────────────────────────────
    # 내부 헬퍼
    # ──────────────────────────────────────────────────

    @staticmethod
    def _pil_to_upload(img: PILImage.Image, idx: int) -> tuple:
        """PIL 이미지를 OpenAI SDK가 받는 (filename, bytes, content_type) 튜플로 변환."""
        buf = BytesIO()
        # PNG로 직렬화 (RGBA 허용 — gpt-image-2는 PNG/JPEG/WEBP 지원)
        save_img = img if img.mode in ("RGB", "RGBA") else img.convert("RGB")
        save_img.save(buf, format="PNG")
        buf.seek(0)
        return (f"image_{idx}.png", buf.getvalue(), "image/png")

    @staticmethod
    def _parse_response(response) -> StepResponse:
        """gpt-image-2 응답에서 이미지를 추출합니다."""
        images: list[PILImage.Image] = []
        for item in getattr(response, "data", []) or []:
            b64 = getattr(item, "b64_json", None)
            if b64:
                try:
                    img_bytes = base64.b64decode(b64)
                    images.append(PILImage.open(BytesIO(img_bytes)))
                except Exception:
                    logger.exception("base64 이미지 디코드 실패")
                continue
            url = getattr(item, "url", None)
            if url:
                # URL 응답은 사용하지 않지만, 호환을 위해 기록만 남김
                logger.warning("OpenAI 응답이 URL 형태로 반환됨 — b64_json만 처리됩니다: %s", url)

        return StepResponse(text="", images=images)

    def _record_turn(self, role: str, parts: list) -> None:
        """parts를 단순화한 형태로 히스토리에 기록합니다 (로깅용)."""
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
    # 로깅 포매터 (Pipeline에서 호출되는 인터페이스)
    # ──────────────────────────────────────────────────

    def _format_parts_for_log(self, parts: list) -> str:
        lines: list[str] = []
        for idx, part in enumerate(parts):
            try:
                if isinstance(part, PILImage.Image):
                    filename = getattr(part, "filename", None)
                    size = getattr(part, "size", None)
                    mode = getattr(part, "mode", None)
                    lines.append(
                        f"part[{idx}]: Image filename={filename!r} size={size} mode={mode}"
                    )
                elif isinstance(part, str):
                    preview = " ".join(part.splitlines())[:200]
                    lines.append(f"part[{idx}]: Text(len={len(part)}) preview={preview!r}")
                else:
                    lines.append(f"part[{idx}]: {type(part).__name__} repr={repr(part)[:200]}")
            except Exception:
                lines.append(f"part[{idx}]: <failed to inspect part>")
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
