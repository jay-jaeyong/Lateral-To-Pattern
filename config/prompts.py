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
        "name": "level_1_style_change",
        "description": "Step 1 - 이미지 스타일 바꾸기",
        "prompt": (
            """[
                원본 사진을 보고 정확하게 신발의 모든 선을 구분해서 라인 아트로 내부 색을 흰색으로 칠하고, 글자까지 실물과 똑같이 그려.
            ]"""
        ),
        "image_path": IMAGES_BASE / "step1",
        "save_output": True,
    },
    {
        "step": 2,
        "name": "level_2_pattern_generation",
        "description": "Step 2 - 이미지 펼치기",
        "prompt": (
            """{
                "task": [
                    "Upper만 3D 모양이라고 생각했을때, 2D 도면으로 로 펼쳐야해.",
                    "MIDSOLE 라인 위로 모든 시각적으로 보이는 부분은 삭제없이 그려줘"
                ],
                "task_rule": [
                    "라인에 맞게 이어지도록 *비율을 맞춰서* 펼쳐줘",
                    "**발등 부위는 가이드라인 라인 중앙에 밀착되게 펼쳐줘**",
                    "**MIDSOLE, TONGUE, LACE는 없애고 그 아래 부분 채워**",
                    "**신발 패턴이 겹쳐면 오른쪽이 위에 가도록 그려줘**",
                    "**가이드라인과 패턴 사이 '빈틈이 없이' 밀착해서 채워줘**",
                    "모든 선은 가이드라인에 티가 안나게 ***끊김없이 자연스럽게 채워***",
                    "**그림에서 모든 라인과 특징을 *추가/삭제 없이 명확하게* 펼쳐야해**",
                    "**라인을 넘어가면 패턴을 잘라**"
                ]
            }"""   
        ),
        "image_path": IMAGES_BASE / "step2",
        "save_output": True,
    },
    {
        "step": 3,
        "name": "level_3_guideline_addition",
        "description": "Step 3 - 여분 가이드라인 추가",
        "prompt": (
            """
                {
                    "persona": "실제 제조를 위해서 얼마나 자재의 여분이 있어야하는지 가이드라인이 제공됨.",
                    "task": [
                        "**추가로 제공**된 라인 끝까지 끊기지 않고 가이드에 밀착해서 채워줘",
                        "펼친 그림에서 **점선(재봉선)은 지우고 실선만 유지해줘**"
                    ],
                    "caution": "가이드 라인 밖으로는 패턴이 넘어가지 않도록 주의해줘"
                }
            """
        ),
        "image_path": IMAGES_BASE / "step3",
        "save_output": True,
    },
]
