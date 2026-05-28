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
    image_size="4K",
    aspect_ratio="21:9",
)

# ─────────────────────────────────────────────
# 사고 수준 (모든 단계 동일) — Gemini 3 Pro의 최대값은 "high"
#   "low" | "medium" | "high"
# ─────────────────────────────────────────────
THINKING_CONFIG = types.ThinkingConfig(
    thinking_level="high",
    include_thoughts=False,
)

# ─────────────────────────────────────────────
# 채팅 세션 GenerateContentConfig
# ─────────────────────────────────────────────
CHAT_CONFIG = types.GenerateContentConfig(
    response_modalities=RESPONSE_MODALITIES,
    image_config=IMAGE_CONFIG,
    safety_settings=SAFETY_SETTINGS,
    temperature=0,
    thinking_config=THINKING_CONFIG,
)

# Step 1 전용 GenerateContentConfig (21:9 비율, 나머지 설정 동일)
STEP1_CHAT_CONFIG = types.GenerateContentConfig(
    response_modalities=RESPONSE_MODALITIES,
    image_config=STEP1_IMAGE_CONFIG,
    safety_settings=SAFETY_SETTINGS,
    temperature=0,
    thinking_config=THINKING_CONFIG,
)

# ─────────────────────────────────────────────
# 동적 비율 선택용 헬퍼
# (가이드라인 이미지의 실제 비율에 가장 가까운 Gemini 지원 비율을 고름)
# ─────────────────────────────────────────────
SUPPORTED_ASPECT_RATIOS: list[tuple[str, float]] = [
    ("1:1", 1.0),
    ("3:4", 3 / 4), ("4:3", 4 / 3),
    ("4:5", 4 / 5), ("5:4", 5 / 4),
    ("2:3", 2 / 3), ("3:2", 3 / 2),
    ("9:16", 9 / 16), ("16:9", 16 / 9),
    ("21:9", 21 / 9),
    ("1:4", 1 / 4), ("4:1", 4.0),
    ("1:8", 1 / 8), ("8:1", 8.0),
]


def closest_aspect_ratio(width: int, height: int) -> str:
    """가로/세로 크기에 가장 가까운 Gemini 지원 비율 문자열을 반환합니다."""
    if height <= 0:
        return "1:1"
    target = width / height
    return min(SUPPORTED_ASPECT_RATIOS, key=lambda x: abs(x[1] - target))[0]


def make_chat_config(aspect_ratio: str | None = None) -> types.GenerateContentConfig:
    """주어진 aspect_ratio로 GenerateContentConfig를 동적으로 생성합니다.

    image_size, safety_settings, temperature는 기본 CHAT_CONFIG와 동일.
    """
    img_cfg = types.ImageConfig(image_size="4K", aspect_ratio=aspect_ratio)
    return types.GenerateContentConfig(
        response_modalities=RESPONSE_MODALITIES,
        image_config=img_cfg,
        safety_settings=SAFETY_SETTINGS,
        temperature=0,
    )


# ─────────────────────────────────────────────
# 재시도 설정
# ─────────────────────────────────────────────
MAX_RETRIES = 3       # API 호출 실패 시 최대 재시도 횟수
RETRY_DELAY = 2.0     # 재시도 간격 (초)