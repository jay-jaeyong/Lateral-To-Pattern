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
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image as PILImage
from google import genai

from config.api_config import get_api_key
from config.gemini_config import (
    MODEL_NAME,
    CHAT_CONFIG,
    MAX_RETRIES,
    RETRY_DELAY,
)

logger = logging.getLogger(__name__)


@dataclass
class StepResponse:
    """단일 API 호출의 결과 (텍스트 + 생성 이미지 목록)."""

    text: str = ""
    images: list[PILImage.Image] = field(default_factory=list)

    def has_image(self) -> bool:
        return len(self.images) > 0


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
