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
MODEL_NAME = "gemini-3-pro-image-preview"

# ─────────────────────────────────────────────
# 응답 모달리티 (이미지만 요청)
# ─────────────────────────────────────────────
RESPONSE_MODALITIES = ["IMAGE"]

# ─────────────────────────────────────────────
# 출력 이미지 설정 (4K 해상도 + 자동 비율 적용)
# ─────────────────────────────────────────────
# image_size: "512", "1K", "2K", "4K" 중 선택 가능
# aspect_ratio를 설정하지 않으면 모델이 최적의 비율을 자동으로 선택합니다.
IMAGE_CONFIG = types.ImageConfig(
    image_size="4K",
    aspect_ratio=None  # 또는 아예 이 라인을 삭제해도 무방합니다.
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
# Step 1 전용 이미지 설정 (21:9 가로 비율)
# ─────────────────────────────────────────────
STEP1_IMAGE_CONFIG = types.ImageConfig(
    aspect_ratio="21:9"
)

# ─────────────────────────────────────────────
# 채팅 세션 GenerateContentConfig
# ─────────────────────────────────────────────
CHAT_CONFIG = types.GenerateContentConfig(
    response_modalities=RESPONSE_MODALITIES,
    image_config=IMAGE_CONFIG,
    safety_settings=SAFETY_SETTINGS,
    temperature=0,
)

# Step 1 전용 GenerateContentConfig (1:4 비율, 나머지 설정 동일)
STEP1_CHAT_CONFIG = types.GenerateContentConfig(
    response_modalities=RESPONSE_MODALITIES,
    image_config=STEP1_IMAGE_CONFIG,
    safety_settings=SAFETY_SETTINGS,
    temperature=0,
)

# ─────────────────────────────────────────────
# 재시도 설정
# ─────────────────────────────────────────────
MAX_RETRIES = 3       # API 호출 실패 시 최대 재시도 횟수
RETRY_DELAY = 2.0     # 재시도 간격 (초)