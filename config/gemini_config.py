"""config/gemini.py로 이동 중인 shim. Task 9에서 삭제된다."""

from config.gemini import *  # noqa: F401,F403
from config.gemini import (  # noqa: F401
    CHAT_CONFIG,
    IMAGE_CONFIG,
    INPUT_ASPECT_IMAGE_CONFIG,
    MAX_RETRIES,
    RESPONSE_MODALITIES,
    RETRY_DELAY,
    SAFETY_SETTINGS,
    THINKING_CONFIG,
    build_response_config,
)

MODEL_NAME = "gemini-3.1-flash-image"
