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
# gemini-3.1-flash-image-preview: 이미지 생성/편집 지원 (Nano Banana 2)
MODEL_NAME = "gemini-3.1-flash-image-preview"
# 다른 옵션: "gemini-3-pro-image-preview", "gemini-2.5-flash-image"

# ─────────────────────────────────────────────
# 응답 모달리티 (텍스트 + 이미지 모두 요청)
# ─────────────────────────────────────────────
RESPONSE_MODALITIES = ["TEXT", "IMAGE"]

# ─────────────────────────────────────────────
# 출력 이미지 설정
# ─────────────────────────────────────────────
# aspect_ratio: "1:1","1:4","1:8","2:3","3:2","3:4","4:1","4:3","4:5",
#               "5:4","8:1","9:16","16:9","21:9"
# image_size:   "512", "1K", "2K", "4K"  ← SDK 버전 업 시 IMAGE_CONFIG에 추가
IMAGE_CONFIG = None  # let the model choose image aspect ratio (auto)

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
    thinking_config=types.ThinkingConfig(thinking_budget=0),
    temperature=0,
)

# ─────────────────────────────────────────────
# 재시도 설정
# ─────────────────────────────────────────────
MAX_RETRIES = 3       # API 호출 실패 시 최대 재시도 횟수
RETRY_DELAY = 2.0     # 재시도 간격 (초)
