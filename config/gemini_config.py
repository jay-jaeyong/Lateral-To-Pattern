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
# 출력 이미지 설정 (4K 해상도 + 세로 비율 고정)
# ─────────────────────────────────────────────
# image_size: "512", "1K", "2K", "4K" 중 선택 가능
#
# aspect_ratio를 비워두면 모델이 매 실행마다 비율을 새로 고릅니다. 가로로
# 고르면 Toe가 아래·Heel이 위라는 방향 규칙이 깨지고 나비 모양으로 나옵니다.
# 펼친 패턴은 세로로 긴 형태이므로 2:3으로 고정합니다.
IMAGE_CONFIG = types.ImageConfig(
    image_size="4K",
    aspect_ratio="2:3",
)

INPUT_ASPECT_IMAGE_CONFIG = types.ImageConfig(image_size="4K")

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
    safety_settings=SAFETY_SETTINGS,
    temperature=0,
)

# ─────────────────────────────────────────────
# 스텝별 응답 모달리티 오버라이드
# ─────────────────────────────────────────────
def build_response_config(
    modalities: list[str] | None,
    response_schema=None,
    match_input_aspect_ratio: bool = False,
) -> types.GenerateContentConfig | None:
    """스텝 하나만 다른 모달리티로 부를 때 쓸 config를 만듭니다.

    관찰 스텝처럼 텍스트 응답이 필요한 경우에 씁니다.
    None이나 빈 목록이면 None을 반환해 세션 기본값(CHAT_CONFIG)을 그대로 쓰게 합니다.

    Args:
        modalities: 응답 모달리티 (예: ["TEXT"], ["IMAGE"], None)
        response_schema: Pydantic 모델. 지정하면 응답이 해당 모델의 JSON 스키마로 강제됩니다.
    """
    if not modalities and not match_input_aspect_ratio:
        return None

    kwargs = {
        "response_modalities": list(modalities or RESPONSE_MODALITIES),
        "safety_settings": SAFETY_SETTINGS,
        "temperature": 0,
    }
    if "IMAGE" in kwargs["response_modalities"]:
        kwargs["image_config"] = (
            INPUT_ASPECT_IMAGE_CONFIG
            if match_input_aspect_ratio
            else IMAGE_CONFIG
        )
    if response_schema is not None:
        kwargs["response_mime_type"] = "application/json"
        kwargs["response_schema"] = response_schema

    return types.GenerateContentConfig(**kwargs)

# ─────────────────────────────────────────────
# 재시도 설정
# ─────────────────────────────────────────────
MAX_RETRIES = 3       # API 호출 실패 시 최대 재시도 횟수
RETRY_DELAY = 2.0     # 재시도 간격 (초)
