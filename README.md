# Lateral-To-Pattern

신발 실물 사진을 입력받아 Gemini AI로 재단 패턴(Pattern)을 자동 생성하는 도구입니다.
관찰 → 펼치기 → 라인 아트 3스텝을 같은 채팅 세션에서 순차 실행합니다.

---

## 개요

```
[신발 실물 사진(여러 각도)]
    → Gemini API (부품 관찰)      → 부품 명세서 텍스트
    → Gemini API (패턴 펼치기)    → 2D 전개 패턴 이미지
    → Gemini API (라인 아트 변환) → 라인 아트 이미지
    → output/ 저장
```

`config/prompts.py`의 `PIPELINE_STEPS`에 단계를 추가하면 동일한 Gemini **채팅 세션**에서
순차 실행되어 이전 대화 맥락이 유지됩니다.

---

## 폴더 구조

```
Lateral-To-Pattern/
├── run.sh                   # ★ 한 번에 환경 구성 + 실행 (uv 사용)
├── pyproject.toml           # 의존성 정의
├── uv.lock                  # 잠긴 의존성 버전 (커밋 대상)
├── main.py                  # 진입점
│
├── config/                  # 설정 (수정 빈도 높음)
│   ├── prompts.py           # ★ 프롬프트와 이미지 경로 정의
│   ├── gemini_config.py     # 모델명, 생성 파라미터, 재시도 설정
│   ├── api_config.py        # API 키 로드 로직
│   └── APIkey               # Gemini API 키 파일 (Git 제외)
│
├── core/                    # 파이프라인 핵심 로직
│   ├── pipeline.py          # 멀티스텝 실행 오케스트레이터
│   └── models.py            # 데이터 클래스 (StepResult, PipelineResult 등)
│
├── services/                # 외부 API 통신
│   └── gemini_client.py     # Gemini API 클라이언트 (채팅 세션, 재시도)
│
├── handlers/                # 입출력 처리
│   ├── image_handler.py     # 이미지 로드, 사용자 선택 인터랙션
│   └── output_handler.py    # 결과 Markdown·JSON 파일 저장
│
├── utils/                   # 공통 유틸리티
│   ├── cli.py               # CLI 인자 파서, 이미지 경로 오버라이드
│   └── logging_utils.py     # Step 컨텍스트 로그 필터
│
├── images/                  # 입력 이미지
│   ├── 가이드라인.jpg        # 파일명에 '가이드라인' 포함 → 펼칠 틀로 자동 인식
│   ├── 나이키_탄준/          # 모델 폴더. 안의 사진이 전부 함께 전달됩니다
│   │   ├── lateral.webp
│   │   └── medial.webp
│   └── 뉴발란스_992/
│
└── output/                  # 생성 결과
    └── {선택한 이미지 이름}/
        ├── step_01_pattern_unfold.md
        ├── step_02_line_art_conversion.md
        ├── final_output.md
        └── chat_history.json
```

실행하면 모델 폴더 목록이 번호와 함께 뜹니다. 번호로 하나를 고르거나 `all`을 입력하면
전부 순서대로 실행되고, 출력 폴더는 각 폴더명으로 만들어집니다.

`images/` 바로 아래에 가이드라인이 아닌 낱개 이미지가 있으면 "파일 하나 고르기" 모드로
동작해 멀티뷰가 켜지지 않습니다. 신발 사진은 반드시 모델 폴더 안에 넣으세요.

가이드라인 판별 키워드는 `가이드라인`, `가이드`, `guideline`, `guide` 입니다
([handlers/image_handler.py](handlers/image_handler.py)의 `GUIDELINE_KEYWORDS`).

---

## 데이터 흐름

### Step 1 — 부품 관찰

| 항목 | 내용 |
|------|------|
| **입력 이미지** | 뷰 플래그로 준 사진들, 또는 선택한 모델 폴더 안의 사진 전부 |
| **라벨** | 각 사진 앞에 `[사진 N] 바깥쪽 측면(lateral)` 형태의 텍스트를 붙여 전달 |
| **프롬프트** | Upper를 재단 부품 단위로 읽어 명세서 작성. 확인 못 한 부위는 '미확인'으로 명시 |
| **API 입력** | `[라벨, 사진, 라벨, 사진, ..., 프롬프트]` |
| **응답 모달리티** | 이 스텝만 `["TEXT"]` |
| **출력** | 부품 명세서 텍스트 |

### Step 2 — 패턴 펼치기

| 항목 | 내용 |
|------|------|
| **입력** | 가이드라인 이미지 + Step 1 명세서 (신발 사진은 채팅 히스토리에 남아 있음) |
| **프롬프트** | 실물 우선 4단계 규칙에 따라 Upper를 3D→2D로 전개 |
| **API 입력** | `[가이드라인_이미지, Step1_명세서, 프롬프트]` |
| **출력** | 2D 전개 패턴 이미지 |

### Step 3 — 라인 아트 변환

| 항목 | 내용 |
|------|------|
| **입력** | Step 2가 생성한 패턴 이미지 + Step 1 명세서 |
| **프롬프트** | 모든 선을 구분해 라인 아트로. 아일릿 개수와 무늬 배치를 명세서와 대조 |
| **API 입력** | `[Step2_생성_이미지, Step1_명세서, 프롬프트]` |
| **출력** | 라인 아트 패턴 이미지 |

---

## 빠른 시작

```bash
git clone <repo>
cd Lateral-To-Pattern
./run.sh
```

`run.sh`가 uv로 가상환경(`.venv`)과 의존성을 자동 구성한 뒤 파이프라인을 실행합니다.
uv가 없으면 설치 여부를 물어봅니다. API 키나 입력 이미지가 없으면 실행 전에 알려줍니다.
`main.py` 인자는 그대로 전달됩니다 — 예: `./run.sh --verbose`

---

## 설치 및 실행 (수동)

### 1. 의존성 설치

```bash
uv sync            # 권장 (pyproject.toml + uv.lock 기준)
# 또는
pip install -r requirements.txt
```

### 2. API 키 설정

아래 중 하나를 선택합니다.

```bash
# 방법 A: 파일로 저장 (권장)
echo "your_api_key" > config/APIkey

# 방법 B: 레포 밖 키 파일 경로 지정
export GEMINI_API_KEY_FILE=~/Documents/geminiapi.txt

# 방법 C: 환경변수
export GEMINI_API_KEY=your_api_key

# 방법 D: 프로젝트 루트에 .env 파일
echo "GEMINI_API_KEY=your_api_key" > .env
```

위 설정이 하나도 없으면 `config/api_config.py`의 `EXTERNAL_KEY_FILES`에 적힌
기본 경로(`~/Documents/geminiapi.txt`)에서 키를 읽습니다. 키 값은 로그에 남지 않고,
어느 경로에서 읽었는지만 출력됩니다.

### 3. 이미지 배치

```
images/가이드라인.jpg          ← 2D 펼침 가이드라인(틀). 파일명에 '가이드라인' 포함
images/나이키_탄준/            ← 모델 폴더. 안에 각도별 사진을 넣습니다
    ├── lateral.webp
    ├── medial.webp
    └── top.webp
images/뉴발란스_992/
    ├── lateral.webp
    └── front.webp
```

### 4. 실행

```bash
# 기본 실행 (콘솔에서 모델 폴더 선택)
./run.sh
# 또는
uv run python main.py

# 각도별로 직접 지정 (한 켤레 멀티뷰). 준 것만 쓰이고, 빠진 각도가 있어도 됩니다.
./run.sh --lateral shoes/v2k/lat.webp --medial shoes/v2k/med.webp --top shoes/v2k/top.webp

# 뷰 플래그는 항상 lateral → medial → front → heel → top → bottom 순으로 전달됩니다.
# 플래그를 하나라도 주면 --shoe-image와 폴더 선택은 무시됩니다.

# 이미지 직접 지정 (선택 과정 건너뛰기)
./run.sh --shoe-image "images/나이키_탄준/lateral.webp" --guide-image "images/가이드라인.jpg"

# 신발 이미지 여러 장 지정 — 이미지마다 파이프라인을 따로 실행하고
# output/{이미지 이름}/ 폴더에 각각 저장합니다.
./run.sh --shoe-image "images/나이키_탄준/lateral.webp" "images/뉴발란스_992/lateral.webp" --guide-image "images/가이드라인.jpg"

# 출력 폴더명 지정
python main.py --run-label my_run

# 상세 로그
python main.py --verbose
```

---

## 출력 결과

```
output/{모델명}/
├── step_01_part_survey.md              # Step 1: 부품 명세서 텍스트
├── step_02_pattern_unfold_generated_01.png  # Step 2: 2D 패턴 이미지
├── step_03_line_art_conversion_generated_01.png  # Step 3: 라인 아트 이미지
├── final_output.md                     # 최종 결과 요약
└── chat_history.json                   # 전체 채팅 히스토리 (JSON)
```

생성된 이미지는 동일한 폴더에 저장됩니다.

---

## 설정 변경

프롬프트·이미지 경로 변경은 **`config/prompts.py`** 만 수정합니다.  
모델·파라미터 변경은 **`config/gemini_config.py`** 를 수정합니다.

---

## 요구사항

- Python 3.11+
- `google-genai >= 1.0.0`
- `Pillow >= 10.0.0`
- `python-dotenv >= 1.0.0`
