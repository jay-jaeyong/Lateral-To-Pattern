"""
Gemini Model Configuration
---------------------------
Gemini API 모델 및 생성 파라미터 설정.
모델 변경이나 생성 파라미터 조정은 이 파일에서만 수행하세요.

사용 SDK: google-genai (신규 SDK)
"""

from google.genai import types

# ─────────────────────────────────────────────
# 사용할 Gemini 모델
# ─────────────────────────────────────────────
# gemini-3-pro-image-preview: 이미지 생성/편집 지원 (Nano Banana Pro)
MODEL_NAME = "gemini-3-pro-image"

# ─────────────────────────────────────────────
# 응답 모달리티 (이미지만 요청)
# ─────────────────────────────────────────────
RESPONSE_MODALITIES = ["IMAGE"]

# ─────────────────────────────────────────────
# 출력 이미지 설정 (4K 해상도 + 세로 패턴 비율)
# ─────────────────────────────────────────────
# image_size: "512", "1K", "2K", "4K" 중 선택 가능
IMAGE_CONFIG = types.ImageConfig(
    image_size="4K",
    aspect_ratio="2:3",
)

# ─────────────────────────────────────────────
# 안전 설정
# ─────────────────────────────────────────────
SAFETY_SETTINGS = [
    types.SafetySetting(
        category="HARM_CATEGORY_HARASSMENT",
        threshold="BLOCK_MEDIUM_AND_ABOVE",
    ),
    types.SafetySetting(
        category="HARM_CATEGORY_HATE_SPEECH",
        threshold="BLOCK_MEDIUM_AND_ABOVE",
    ),
    types.SafetySetting(
        category="HARM_CATEGORY_SEXUALLY_EXPLICIT",
        threshold="BLOCK_MEDIUM_AND_ABOVE",
    ),
    types.SafetySetting(
        category="HARM_CATEGORY_DANGEROUS_CONTENT",
        threshold="BLOCK_MEDIUM_AND_ABOVE",
    ),
]

# ─────────────────────────────────────────────
# 채팅 세션 GenerateContentConfig
# ─────────────────────────────────────────────
CHAT_CONFIG = types.GenerateContentConfig(
    response_modalities=RESPONSE_MODALITIES,
    image_config=IMAGE_CONFIG,
    media_resolution=types.MediaResolution.MEDIA_RESOLUTION_HIGH,
    safety_settings=SAFETY_SETTINGS,
)

# ─────────────────────────────────────────────
# 스텝별 응답 모달리티 오버라이드
# ─────────────────────────────────────────────
def build_response_config(
    modalities: list[str] | None,
) -> types.GenerateContentConfig | None:
    """스텝 하나만 다른 모달리티로 부를 때 쓸 config를 만듭니다.

    관찰 스텝처럼 텍스트 응답이 필요한 경우에 씁니다.
    None이나 빈 목록이면 None을 반환해 세션 기본값(CHAT_CONFIG)을 그대로 쓰게 합니다.
    """
    if not modalities:
        return None

    kwargs = {
        "response_modalities": list(modalities),
        "media_resolution": types.MediaResolution.MEDIA_RESOLUTION_HIGH,
        "safety_settings": SAFETY_SETTINGS,
    }
    if "IMAGE" in modalities:
        kwargs["image_config"] = IMAGE_CONFIG

    return types.GenerateContentConfig(**kwargs)

# ─────────────────────────────────────────────
# 재시도 설정
# ─────────────────────────────────────────────
MAX_RETRIES = 3       # API 호출 실패 시 최대 재시도 횟수
RETRY_DELAY = 2.0     # 재시도 간격 (초)
