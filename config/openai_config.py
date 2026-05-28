"""
OpenAI (GPT) Responses API Configuration
-----------------------------------------
client.responses.create() + image_generation 도구로 멀티턴 이미지 생성을 수행합니다.

사용 SDK: openai (>=1.40)
사용 모델: gpt-5.5 (Responses API)
이미지 생성: 내장 image_generation 도구 (내부적으로 gpt-image-2 사용)

참고:
  - https://developers.openai.com/api/docs/quickstart
  - https://developers.openai.com/api/docs/guides/latest-model
  - https://developers.openai.com/api/docs/guides/tools-image-generation
"""

# ─────────────────────────────────────────────
# 사용할 모델 (Responses API)
# ─────────────────────────────────────────────
MODEL_NAME = "gpt-5.5"

# ─────────────────────────────────────────────
# 추론 깊이 (Gemini의 thinking_level 대응)
#   "low" | "medium"(기본) | "high" | "xhigh"
# ─────────────────────────────────────────────
REASONING_EFFORT = "high"

# ─────────────────────────────────────────────
# 텍스트 응답의 장황도 — 이미지 작업이므로 짧게
#   "low" | "medium"(기본)
# ─────────────────────────────────────────────
TEXT_VERBOSITY = "low"

# ─────────────────────────────────────────────
# 입력 이미지 디테일 보존 수준
#   "auto" | "high" | "low" | "original"
#   정밀 라인아트 작업이므로 high
# ─────────────────────────────────────────────
IMAGE_DETAIL = "high"

# ─────────────────────────────────────────────
# image_generation 도구의 출력 사이즈 제약 (gpt-image-2 기반)
#   - 가장 긴 변 ≤ 3840px
#   - 16의 배수
#   - 가로:세로 비율 ≤ 3:1
#   - 총 픽셀 수: 655,360 ~ 8,294,400
#
# Step 1: 21:9 → 3360 x 1440 (정확한 21:9, 16의 배수)
# 그 외:  "auto" (도구가 자동 결정)
# ─────────────────────────────────────────────
SIZE_STEP1 = "3360x1440"
SIZE_DEFAULT = "auto"

# ─────────────────────────────────────────────
# 이미지 품질 (도구 옵션)
#   "low" | "medium" | "high" | "auto"
# ─────────────────────────────────────────────
QUALITY = "high"

# ─────────────────────────────────────────────
# 출력 포맷 (도구 옵션): "png" | "jpeg" | "webp"
# ─────────────────────────────────────────────
OUTPUT_FORMAT = "png"

# ─────────────────────────────────────────────
# 재시도 설정
# ─────────────────────────────────────────────
MAX_RETRIES = 3
RETRY_DELAY = 2.0
