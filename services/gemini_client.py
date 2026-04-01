"""
Gemini API Client
------------------
Gemini API와의 통신을 담당하는 클라이언트.
채팅 세션(Chat Session)을 유지하여 멀티턴 대화를 관리합니다.

사용 SDK: google-genai (신규 SDK)
모델: gemini-3.1-flash-image-preview (이미지 생성/편집 지원)
"""

from __future__ import annotations

import time
import logging
from pathlib import Path

from PIL import Image as PILImage
from google import genai
from google.genai import types as genai_types

from config.api_config import get_api_key
from config.gemini_config import (
    MODEL_NAME,
    CHAT_CONFIG,
    MAX_RETRIES,
    RETRY_DELAY,
)
from core.models import StepResponse

logger = logging.getLogger(__name__)


class GeminiClient:
    """Gemini API 채팅 클라이언트.

    채팅 히스토리를 유지하며 멀티모달(이미지+텍스트) 입력과
    이미지 생성/편집 출력을 모두 지원합니다.
    """

    def __init__(self) -> None:
        self._client = genai.Client(api_key=get_api_key())
        self._chat = None
        logger.info("GeminiClient 초기화 완료 (모델: %s)", MODEL_NAME)

    # ──────────────────────────────────────────────────
    # 채팅 세션 관리
    # ──────────────────────────────────────────────────

    def start_chat(self) -> None:
        """새 채팅 세션을 시작합니다. 기존 히스토리는 초기화됩니다."""
        self._chat = self._client.chats.create(
            model=MODEL_NAME,
            config=CHAT_CONFIG,
        )
        logger.info("새 채팅 세션 시작")

    @property
    def chat_history(self) -> list:
        """현재 채팅 히스토리를 반환합니다."""
        if self._chat is None:
            return []
        return list(self._chat.get_history())

    # ──────────────────────────────────────────────────
    # 메시지 전송
    # ──────────────────────────────────────────────────

    def send(self, parts: list) -> StepResponse:
        """메시지(텍스트 + 이미지 등)를 채팅 세션으로 전송하고 응답을 반환합니다.

        Args:
            parts: Gemini에 전달할 콘텐츠 리스트.
                   예: [PIL.Image.Image, "프롬프트 텍스트"]

        Returns:
            StepResponse: 텍스트와 생성된 이미지 목록을 담은 결과 객체.

        Raises:
            RuntimeError: 채팅 세션이 시작되지 않은 경우 또는 MAX_RETRIES 초과 시.
        """
        if self._chat is None:
            raise RuntimeError(
                "채팅 세션이 시작되지 않았습니다. start_chat()을 먼저 호출하세요."
            )

        # 안전: parts에 중첩된 리스트가 있으면 평탄화합니다.
        try:
            parts = self._flatten_parts(parts)
        except Exception:
            logger.debug("parts 평탄화 중 오류 발생 — 원본을 그대로 사용합니다.")

        # 추가 안전 검사: 중첩된 리스트/튜플이 남아 있으면 재평탄화
        try:
            while any(isinstance(p, (list, tuple)) for p in parts):
                parts = self._flatten_parts(parts)
        except Exception:
            logger.debug("parts 추가 평탄화 중 오류 발생")

        # 허용되지 않는 파트 타입이 있으면 문자열로 변환해 보냅니다.
        sanitized: list = []
        for idx, p in enumerate(parts):
            # 허용되는 기본 타입: str, PIL.Image, genai File/Part, dict-like PartDict
            if isinstance(p, str) or isinstance(p, PILImage.Image):
                sanitized.append(p)
                continue
            # genai types: File, Part (실제 클래스만 isinstance 체크, TypedDict 제외)
            allowed_classes = tuple(
                t for t in (
                    getattr(genai_types, "File", None),
                    getattr(genai_types, "Part", None),
                )
                if t is not None and isinstance(t, type)
            )
            if allowed_classes and isinstance(p, allowed_classes):
                sanitized.append(p)
                continue
            # dict-like (PartDict / FileDict 는 TypedDict이므로 dict로만 판별)
            if isinstance(p, dict):
                sanitized.append(p)
                continue
            # 마지막 수단: repr로 변환
            logger.info("허용되지 않는 파트 타입 발견(%s) — repr으로 변환하여 전송합니다.", type(p))
            sanitized.append(repr(p)[:1000])

        parts = sanitized

        # Debug: log the outgoing parts and current chat history (if logger is set to DEBUG)
        try:
            logger.debug("=== Gemini API Request Parts ===\n%s", self._format_parts_for_log(parts))
        except Exception:
            logger.debug("=== Gemini API Request Parts: <failed to format parts> ===")

        try:
            logger.debug("=== Chat history BEFORE send ===\n%s", self._format_chat_history_for_log())
        except Exception:
            logger.debug("=== Chat history BEFORE send: <failed to format history> ===")

        last_error: Exception | None = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                logger.debug("API 호출 시도 %d/%d", attempt, MAX_RETRIES)
                response = self._chat.send_message(parts)
                result = self._parse_response(response)

                logger.debug(
                    "API 응답 수신 완료 (텍스트: %d자, 이미지: %d장)",
                    len(result.text),
                    len(result.images),
                )

                # Debug: log a concise response preview and updated history
                try:
                    preview = result.text.replace("\n", " ")[:400]
                    logger.debug("=== Gemini API Response Preview ===\nlen=%d images=%d preview=%s", len(result.text), len(result.images), preview)
                except Exception:
                    logger.debug("=== Gemini API Response Preview: <failed to format> ===")

                try:
                    logger.debug("=== Chat history AFTER send ===\n%s", self._format_chat_history_for_log())
                except Exception:
                    logger.debug("=== Chat history AFTER send: <failed to format history> ===")

                return result
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                logger.warning(
                    "API 호출 실패 (시도 %d/%d): %s", attempt, MAX_RETRIES, exc
                )
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_DELAY)

        raise RuntimeError(
            f"Gemini API 호출이 {MAX_RETRIES}회 실패했습니다."
        ) from last_error

    # ──────────────────────────────────────────────────
    # 응답 파싱
    # ──────────────────────────────────────────────────

    @staticmethod
    def _parse_response(response) -> StepResponse:
        """API 응답에서 텍스트와 이미지를 추출합니다."""
        text_parts: list[str] = []
        images: list[PILImage.Image] = []

        for part in response.parts:
            # 사고(thought) 파트는 건너뜀
            if getattr(part, "thought", False):
                continue

            if part.text:
                text_parts.append(part.text)
            else:
                img = part.as_image()
                if img is not None:
                    images.append(img)

        return StepResponse(
            text="\n".join(text_parts).strip(),
            images=images,
        )

    # ──────────────────────────────────────────────────────────────────
    # Debug helpers
    # ──────────────────────────────────────────────────────────────────

    def _format_parts_for_log(self, parts: list) -> str:
        """Return a human-friendly summary of the `parts` list for logging."""
        lines: list[str] = []
        for idx, part in enumerate(parts):
            try:
                # PIL Image
                if isinstance(part, PILImage.Image):
                    filename = getattr(part, "filename", None)
                    size = getattr(part, "size", None)
                    mode = getattr(part, "mode", None)
                    lines.append(
                        f"part[{idx}]: Image filename={filename!r} size={size} mode={mode}"
                    )
                # Plain text prompt
                elif isinstance(part, str):
                    preview = " ".join(part.splitlines())[:200]
                    lines.append(f"part[{idx}]: Text(len={len(part)}) preview={preview!r}")
                else:
                    lines.append(f"part[{idx}]: {type(part).__name__} repr={repr(part)[:200]}")
            except Exception:
                lines.append(f"part[{idx}]: <failed to inspect part of type {type(part).__name__}>")
        return "\n".join(lines) if lines else "<no parts>"

    def _format_chat_history_for_log(self) -> str:
        """Render the current chat history in a compact chat-like UI style.

        Produces lines like:
        [18:49] You: Hello from the Left!
        [18:49] Peer: It works!

        Adds optional ANSI colors when stdout is a TTY.
        """
        history = self.chat_history
        if not history:
            return "<empty chat history>"

        import sys
        import datetime

        use_color = sys.stdout.isatty()

        # ANSI color codes (used only when a TTY is detected)
        RESET = "\x1b[0m"
        DIM = "\x1b[2m"
        GREEN = "\x1b[32m"
        CYAN = "\x1b[36m"
        MAGENTA = "\x1b[35m"
        GREY = "\x1b[90m"

        def colorize(text: str, code: str) -> str:
            return f"{code}{text}{RESET}" if use_color else text

        def _fmt_ts(ts) -> str:
            if not ts:
                return ""
            try:
                if hasattr(ts, "ToDatetime"):
                    dt = ts.ToDatetime()
                elif isinstance(ts, datetime.datetime):
                    dt = ts
                elif isinstance(ts, (int, float)):
                    dt = datetime.datetime.fromtimestamp(ts)
                else:
                    # Fallback to str
                    return str(ts)
                return dt.strftime("%H:%M")
            except Exception:
                return str(ts)

        label_map = {"user": "You", "assistant": "Peer", "system": "System"}

        out_lines: list[str] = []

        for turn in history:
            role = getattr(turn, "role", "unknown")
            role_key = str(role).lower()
            label = label_map.get(role_key, str(role))

            ts = getattr(turn, "create_time", None) or getattr(turn, "timestamp", None) or getattr(turn, "time", None)
            ts_short = _fmt_ts(ts)
            ts_display = f"[{ts_short}]" if ts_short else ""

            # choose color for role
            if role_key == "user":
                role_color = GREEN
            elif role_key == "assistant":
                role_color = CYAN
            elif role_key == "system":
                role_color = MAGENTA
            else:
                role_color = GREY

            for p in getattr(turn, "parts", []):
                try:
                    if getattr(p, "text", None):
                        text = p.text.rstrip("\n")
                        if not text:
                            continue
                        # Split into lines; first line prints header, rest are indented
                        lines = text.splitlines()
                        first = lines[0]
                        if use_color:
                            ts_col = colorize(ts_display, DIM) + " " if ts_display else ""
                            role_col = colorize(label, role_color)
                            out_lines.append(f"{ts_col}{role_col}: {first}")
                        else:
                            prefix = f"{ts_display + ' ' if ts_display else ''}{label}:"
                            out_lines.append(f"{prefix} {first}")
                        for cont in lines[1:]:
                            out_lines.append("    " + cont)
                    elif getattr(p, "inline_data", None):
                        mime = getattr(p.inline_data, "mime_type", "unknown")
                        if use_color:
                            ts_col = colorize(ts_display, DIM) + " " if ts_display else ""
                            role_col = colorize(label, role_color)
                            out_lines.append(f"{ts_col}{role_col}: [Image mime={mime}]")
                        else:
                            out_lines.append(f"{ts_display + ' ' if ts_display else ''}{label}: [Image mime={mime}]")
                    else:
                        r = repr(p)
                        out_lines.append(f"{ts_display + ' ' if ts_display else ''}{label}: [{type(p).__name__}] {r[:300]}")
                except Exception:
                    out_lines.append(f"{label}: <failed to render part>")

        return "\n".join(out_lines)

    def _flatten_parts(self, parts: list) -> list:
        """Recursively flatten lists/tuples inside parts but keep strings and image objects intact.

        The SDK expects a flat list of parts (or a single part). If callers accidentally
        pass nested lists (e.g. lists of images), flatten them so each element is an
        allowed part type.
        """
        flat: list = []

        def _rec(item):
            # strings are single parts
            if isinstance(item, str):
                flat.append(item)
                return
            # tuples/lists should be flattened
            if isinstance(item, (list, tuple)):
                for sub in item:
                    _rec(sub)
                return
            # otherwise append as-is (PIL images or genai File/Part objects)
            flat.append(item)

        _rec(parts)
        return flat
