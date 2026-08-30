"""
Pipeline Step Prompts
----------------------
각 단계(Step)별 프롬프트와 이미지 경로를 관리합니다.
파이프라인의 동작을 변경하고 싶다면 이 파일만 수정하세요.

구조:
    PIPELINE_STEPS: 순서대로 실행될 단계 목록
        - step            : 단계 번호 (1부터 시작)
        - name            : 단계 식별자 (영문, 공백 없음)
        - description     : 단계 설명
        - prompt          : Gemini에 전달할 프롬프트 텍스트
        - image_path      : 이 단계의 주 입력 이미지 경로 (None이면 이미지 없이 진행)
        - guide_image_path: 가이드라인(틀) 이미지 경로. 주 입력 이미지 뒤, 프롬프트 앞에 들어갑니다.
        - max_images      : 폴더에서 불러올 이미지 최대 장수 (None이면 전부)
        - save_output     : True이면 이 단계의 결과를 output/ 에 저장

스텝 정의에 쓸 수 있는 선택 키:
        - response_modalities: 이 스텝만 다른 응답 모달리티로 호출 (예: ["TEXT"])
        - response_schema    : 응답을 특정 Pydantic 스키마로 검증 (예: Survey)
        - view_images        : (라벨, 경로) 목록. CLI 뷰 플래그가 런타임에 주입합니다
        - include_prev_texts : False면 이전 단계 텍스트(명세서 등)를 이 스텝의 parts에 넣지 않음 (기본 True)
        - prev_image_label   : 앞 단계에서 생성된 이미지에 붙일 라벨. 없으면 라벨 없이 들어감
        - fresh_session      : True면 이 스텝 실행 직전에 채팅 세션을 새로 시작해 이전 단계
                                텍스트가 채팅 히스토리로 전달되는 경로를 끊음 (기본 False)

API에 전달되는 순서:
    Step 1  [라벨, 신발 사진, 라벨, 신발 사진, ..., 프롬프트]        → 텍스트 명세서
    Step 2  [가이드라인, 앞 단계 명세서, 프롬프트]                   → 펼친 패턴 이미지
    Step 3  [원본 컬러 패턴 라벨, 앞 단계 생성 이미지, 프롬프트]      → 스케치 패턴 이미지
            (명세서 미포함)
"""

from pathlib import Path
from services.color_pattern.schema import Survey
from services.color_pattern.prompts import PART_SURVEY_PROMPT, PATTERN_UNFOLD_PROMPT
from services.sketch_pattern.prompts import LINE_ART_PROMPT, ORIGINAL_PATTERN_LABEL

# 프로젝트 루트 기준 이미지 폴더
#
# images/
#   ├── 가이드라인.jpg          ← 이름에 '가이드라인'이 들어간 파일 = 펼칠 틀
#   ├── 나이키_탄준/            ← 모델 폴더. 안에 각도별 사진을 넣습니다
#   │     ├── lateral.webp
#   │     └── medial.webp
#   └── 뉴발란스_992/
#
# 실행하면 모델 폴더 목록이 뜨고, 번호로 하나를 고르거나 'all'을 입력해
# 전부 순서대로 돌릴 수 있습니다. 폴더 안 사진은 전부 함께 전달됩니다.
#
# CLI 뷰 플래그(--lateral, --medial, --front, --heel, --top, --bottom)를
# 하나라도 주면 이 폴더 탐색을 건너뛰고 그 사진들만 씁니다.
IMAGES_BASE = Path("images")

# 신발 실물 사진(사이드뷰)을 찾을 폴더
SHOE_PHOTO_BASE = IMAGES_BASE

# 2D로 펼칠 가이드라인(틀). 명시적 파일 경로입니다.
# Step 2 (pattern_unfold)는 이 파일을 그대로 사용합니다. 런타임에 폴더를 검색하거나
# 가이드라인을 찾아내지 않습니다. 그 검색은 CLI 계층에서 미리 끝나야 합니다.
# 과거에는 폴더에서 가이드라인을 찾아 사용했는데, 한 번은 신발 사진이 가이드라인으로
# 선택되어 Step 2에 들어간 적이 있습니다. 폴더 검색을 제거해 이를 방지합니다.
#
# 절개면과 좌우 면을 문자로 표시한 판본입니다. 원본 가이드라인은 외곽 형태만
# 주기 때문에, 절개선 양옆이 실물에서 맞닿아 있던 한 자리라는 정보와 두 반쪽이
# 서로 다른 면이라는 정보가 이미지에 없었습니다. 표시의 뜻은 Step 2의
# heel_rule(절개면)과 reconstruct_rule(좌우 면)이 설명합니다.
#
# 라벨은 패턴 내부가 아니라 캔버스를 넓혀 만든 바깥 여백에 있어야 합니다.
# 내부에 적었던 판본(가이드라인_절개표시.png)에서 SONOMA의 아식스 교차
# 스트라이프가 소실되고 외곽이 달걀처럼 둥글어지는 퇴행이 나왔습니다.
# Step 1 명세서를 고정한 단일 변수 실험에서 내부 라벨 2/2 퇴행, 여백 라벨
# 2/2 복원으로 위치가 원인임이 확인됐습니다. 글자가 패턴 안에 있으면 모델이
# 이 이미지를 '따라 그릴 재단 틀'이 아니라 '주석 달린 도해'로 읽습니다.
#
# 외곽은 좌우 비대칭 판본을 씁니다. 원본 가이드라인은 채운 마스크 미러 IoU가
# 0.94로 거의 대칭인데, 5순위가 "바깥 재단선을 가이드라인에 맞춘다"이므로
# 대칭인 외곽(이미지 조건)이 "두 반쪽은 서로 다른 면"(텍스트 조건)을 눌렀습니다.
# 그래서 한쪽에만 있는 로고가 양쪽에 복제됐습니다. 외곽을 비대칭(IoU 0.86)으로
# 바꾸자 AM95 스우시, KAYANO 워드마크, liteblaze 삼선, GEL-NYC 좌우 로고가
# 모두 한쪽에만 그려졌습니다. 두 면이 실제로 닮은 SONOMA와 양면에 스우시가
# 있는 Vomero 5는 그대로 대칭으로 나오므로 회귀가 아닙니다.
#
# 비대칭 판본은 외곽만 좌우를 다르게 만들었을 뿐, 안쪽 절개선(목선)은 그대로
# 좌우 대칭이라 lateral·medial 경계에서 두 반쪽이 여전히 같은 선을 공유하고
# 있었습니다. 이를 없애기 위해 좌우 반쪽을 (453, 1164) 중심으로 5도 강체
# 회전시켰습니다. 강체 회전이므로 외곽선과 안쪽 선 사이 재료 폭(패턴 두께)은
# 그대로 보존됩니다. 다만 회전만으로는 안쪽 곡선의 교차가 사라지지 않았고,
# 오히려 회전으로 안쪽 선 두 곳이 끊기고 한쪽 반쪽에 반대쪽 특징의 선
# 조각이 남았습니다. 끊긴 두 곳을 다시 그려 잇고, 남은 선 조각을 지운 뒤
# 좌우로 반전해 다시 붙이는 후처리를 거쳐 지금 판본을 만들었습니다.
GUIDELINE_BASE = Path("guides/가이드라인_회전5도_여백표시.png")
# GUIDELINE_BASE = Path("guides/가이드라인_비대칭_여백표시.png")  # 5도 회전 판본 이전

# ─────────────────────────────────────────────────────────────────────────────
# 파이프라인 단계 정의
# 각 단계는 이전 단계의 응답을 채팅 히스토리로 유지한 채 실행됩니다.
# ─────────────────────────────────────────────────────────────────────────────
PIPELINE_STEPS: list[dict] = [
    {
        "step": 1,
        "name": "part_survey",
        "description": "부품 관찰 - 멀티뷰 실물 사진 → 부품 명세서",
        "prompt": PART_SURVEY_PROMPT,
        "image_path": SHOE_PHOTO_BASE,
        "guide_image_path": None,
        "max_images": None,
        "response_modalities": ["TEXT"],
        "response_schema": Survey,
        "save_output": True,
    },
    {
        "step": 2,
        "name": "pattern_unfold",
        "description": "패턴 펼치기 - 실물 사진 → 2D 전개 패턴",
        "prompt": PATTERN_UNFOLD_PROMPT,
        "image_path": None,
        "guide_image_path": GUIDELINE_BASE,
        # 기준 사진을 채팅 히스토리에만 맡기지 않고 이번 요청에 다시 넣습니다.
        #
        # 앞선 실험(v3~v5)에서 이게 형태를 흐트러뜨린다고 봤지만, 같은 설정
        # 3회 반복에서 실루엣 IoU가 57~62%로 갈리는 것을 확인했습니다. 즉
        # 그 비교는 실행 편차를 원인으로 오독했을 수 있습니다. 이번에는
        # 3회씩 돌려 중앙값으로 판단합니다.
        "reference_views": ["lateral", "medial"],
        "save_output": True,
    },
    {
        "step": 3,
        "name": "line_art_conversion",
        "description": "스케치 패턴 변환 - 컬러 패턴 → 재단선만 남긴 스케치 패턴",
        "prompt": LINE_ART_PROMPT,
        # 앞 단계에서 생성된 컬러 패턴이 입력에 들어갑니다. 라벨을 붙여야
        # 모델이 이 이미지를 프롬프트가 말하는 '원본'으로 읽습니다. 라벨 없이
        # 넣으면 그냥 참고 사진 한 장으로 흘려봅니다.
        "image_path": None,
        "prev_image_label": ORIGINAL_PATTERN_LABEL,
        "save_output": True,
        # Step 1 명세서는 측면 사진 기준 3D 서술이라, 이걸 Step 3 입력에 넣으면
        # 모델이 평면 패턴을 트레이싱하는 대신 3D 신발을 다시 그려버립니다.
        # 5개 모델 × 2회 통제 실험으로 확인해서 껐습니다.
        # 명세서가 Step 3에 전달되는 경로는 둘입니다. include_prev_texts=False는
        # 이번 요청의 parts에 명세서 텍스트가 다시 삽입되는 것을 막고,
        # fresh_session=True는 Step 1·2가 쌓아온 채팅 히스토리 자체를 끊어
        # 세션 재전송으로 명세서가 실리는 것을 막습니다. 둘 다 있어야 합니다.
        "include_prev_texts": False,
        "fresh_session": True,

    },
]
