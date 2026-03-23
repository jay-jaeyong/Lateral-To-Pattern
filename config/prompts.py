"""
Pipeline Step Prompts
----------------------
각 단계(Step)별 프롬프트와 이미지 경로를 관리합니다.
파이프라인의 동작을 변경하고 싶다면 이 파일만 수정하세요.

구조:
    PIPELINE_STEPS: 순서대로 실행될 단계 목록
        - step       : 단계 번호 (1부터 시작)
        - name       : 단계 식별자 (영문, 공백 없음)
        - description: 단계 설명
        - prompt     : Gemini에 전달할 프롬프트 텍스트
        - image_path : 이 단계에서 사용할 이미지 경로 (None이면 이미지 없이 진행)
        - save_output: True이면 이 단계의 결과를 output/ 에 저장
"""

from pathlib import Path

# 프로젝트 루트 기준 이미지 폴더
IMAGES_BASE = Path("images")

# ─────────────────────────────────────────────────────────────────────────────
# 파이프라인 단계 정의
# 각 단계는 이전 단계의 응답을 채팅 히스토리로 유지한 채 실행됩니다.
# ─────────────────────────────────────────────────────────────────────────────
PIPELINE_STEPS: list[dict] = [
    {
        "step": 1,
        "name": "initial_analysis",
        "description": "Step 1 - 초기 이미지 분석",
        "prompt": (
            "제공된 이미지를 주의 깊게 분석해 주세요.\n"
            "다음 항목을 중심으로 설명하세요:\n"
            "1. 이미지의 주요 시각적 요소와 구성\n"
            "2. 색상 팔레트 및 명암 특성\n"
            "3. 반복되거나 눈에 띄는 패턴 또는 구조\n"
            "4. 전체적인 스타일 및 분위기"
        ),
        "image_path": IMAGES_BASE / "step1" / "input.png",
        "save_output": True,
    },
    {
        "step": 2,
        "name": "lateral_pattern_extraction",
        "description": "Step 2 - 측면 패턴 추출",
        "prompt": (
            "이전 분석 결과를 바탕으로, 이번 두 번째 이미지를 살펴보세요.\n"
            "다음을 분석하세요:\n"
            "1. 첫 번째 이미지와 공통적으로 나타나는 패턴 또는 구조\n"
            "2. 두 이미지 간의 시각적 차이점과 전환 방식\n"
            "3. 두 이미지를 관통하는 '측면적(lateral)' 패턴의 핵심 요소"
        ),
        "image_path": IMAGES_BASE / "step2" / "input.png",
        "save_output": True,
    },
    {
        "step": 3,
        "name": "final_synthesis",
        "description": "Step 3 - 최종 패턴 합성",
        "prompt": (
            "앞선 두 단계의 분석을 종합하여, 이 세 번째 이미지까지 포함한 "
            "최종 패턴 합성 결과를 작성해 주세요.\n"
            "결과물에 다음을 포함하세요:\n"
            "1. 세 이미지를 관통하는 통합 패턴 기술\n"
            "2. 패턴의 변화 흐름(Step 1 → Step 2 → Step 3)\n"
            "3. 최종 도출된 핵심 패턴의 구조적 정의\n"
            "4. 이 패턴을 활용할 수 있는 응용 방향 제안"
        ),
        "image_path": IMAGES_BASE / "step3" / "input.png",
        "save_output": True,
    },
]
