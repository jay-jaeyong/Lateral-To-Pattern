# Lateral-To-Pattern

신발 실물 사진을 입력받아 Gemini AI로 재단 패턴(Pattern)을 자동 생성하는 도구입니다.
서비스 두 개가 순차 실행됩니다: `color_pattern`(관찰 → 펼치기, 세션 공유)과
`sketch_pattern`(라인 아트, 독립 세션).

---

## 개요

```
[신발 실물 사진(여러 각도)]
    → color_pattern 서비스
        → Gemini API (부품 관찰)   → 부품 명세서 텍스트
        → Gemini API (패턴 펼치기) → 2D 컬러 패턴 이미지
    → sketch_pattern 서비스
        → Gemini API (라인 아트 변환) → 라인 아트 이미지
    → outputs/ 저장
```

프롬프트는 `services/color_pattern/prompts.py`와 `services/sketch_pattern/prompts.py`에 있습니다.

---

## 폴더 구조

```
Lateral-To-Pattern/
├── run.sh                        # ★ 한 번에 환경 구성 + 실행 (uv 사용)
├── pyproject.toml                # 의존성 정의
├── uv.lock                       # 잠긴 의존성 버전 (커밋 대상)
│
├── config/                       # 설정
│   ├── gemini.py                 # 연결·생성 파라미터, 재시도 설정 (모델명은 없음)
│   └── api_config.py             # API 키 로드 로직
│
├── services/
│   ├── engine.py                 # new_session, 재시도 send, 결과 저장, 히스토리 아카이브
│   ├── utils/images.py           # 이미지 로드·라벨링 저수준 유틸
│   ├── color_pattern/
│   │   ├── photo_input.py        # 신발 폴더 해석, 뷰 라벨, parts 조립
│   │   ├── prompts.py            # Step 1·2 프롬프트
│   │   ├── schema.py             # Survey/Part/Marking/Symmetry
│   │   ├── step_1_part_survey.py
│   │   ├── step_2_pattern_unfold.py
│   │   └── service.py            # MODEL 선언, 세션 하나로 두 스텝 실행
│   └── sketch_pattern/
│       ├── prompts.py            # LINE_ART_PROMPT, ORIGINAL_PATTERN_LABEL
│       ├── step_1_line_art.py
│       └── service.py            # MODEL 선언, 자기 세션으로 한 스텝 실행
│
├── scripts/
│   ├── run_service.py            # 서비스 하나 실행
│   ├── run_all.py                # 두 서비스 순차 실행, 파일 핸드오프
│   └── run_parallel.sh           # inputs/photos/*/를 훑어 병렬 실행
│
├── utils/
│   └── logging_utils.py          # Step 컨텍스트 로그 필터
│
├── inputs/                       # 입력 자산 (사람이 배치)
│   ├── guides/                   # 2D 펼침 가이드라인(틀). Git 추적
│   │   └── 가이드라인_회전5도_여백표시.png
│   ├── photos/                   # 신발 폴더별 각도 사진. Git 제외
│   │   └── 나이키_탄준/
│   │       ├── lateral.webp
│   │       └── medial.webp
│   └── color_patterns/           # sketch_pattern 단독 실행용 컬러 패턴. Git 제외
│
└── outputs/                       # 생성 결과 (Git 제외)
    └── {label}/
        ├── color_pattern/
        │   ├── step_1_part_survey.md
        │   ├── step_2_pattern_unfold.md
        │   └── step_2_pattern_unfold_generated_01.png
        ├── sketch_pattern/
        │   ├── step_1_line_art.md
        │   └── step_1_line_art_generated_01.png
        └── chat_history.json
```

가이드라인 판별 키워드는 `가이드라인`, `가이드`, `guideline`, `guide`입니다
(`services/utils/images.py`의 `GUIDELINE_KEYWORDS`).

---

## 데이터 흐름

### color_pattern 서비스 — Step 1: 부품 관찰

| 항목 | 내용 |
|------|------|
| **입력 이미지** | 신발 폴더 안의 사진 전부 |
| **라벨** | 각 사진 앞에 `[바깥쪽 측면(lateral)]` 형태의 텍스트를 붙여 전달 |
| **프롬프트** | Upper를 재단 부품 단위로 읽어 명세서 작성. 확인 못 한 부위는 '미확인'으로 명시 |
| **응답 모달리티** | 이 스텝만 `["TEXT"]`, `response_schema=Survey`로 JSON 강제 |
| **출력** | 부품 명세서 텍스트 |

### color_pattern 서비스 — Step 2: 패턴 펼치기

| 항목 | 내용 |
|------|------|
| **입력** | 가이드라인 이미지 + Step 1 명세서 (신발 사진은 같은 세션의 히스토리에 남아 있음) |
| **프롬프트** | 실물 우선 규칙에 따라 Upper를 3D→2D로 전개 |
| **출력** | 2D 컬러 패턴 이미지 |

### sketch_pattern 서비스 — 라인 아트 변환

| 항목 | 내용 |
|------|------|
| **입력** | color_pattern이 만든 컬러 패턴 이미지 한 장 (독립 세션, 신발 사진이나 명세서를 보지 않음) |
| **프롬프트** | 컬러 패턴을 정밀 복제해 라인 아트로 변환 |
| **출력** | 라인 아트 패턴 이미지 |

---

## 빠른 시작

```bash
git clone <repo>
cd Lateral-To-Pattern
./run.sh --input inputs/photos/나이키_탄준
```

`run.sh`가 uv로 가상환경(`.venv`)과 의존성을 자동 구성한 뒤 `scripts/run_all.py`를 실행합니다.
uv가 없으면 설치 여부를 물어봅니다. API 키나 `--input`이 없으면 실행 전에 알려줍니다.

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
inputs/guides/가이드라인_회전5도_여백표시.png   ← 이미 저장소에 있음
inputs/photos/나이키_탄준/                     ← 신발 폴더. 안에 각도별 사진을 넣습니다
    ├── lateral.webp
    ├── medial.webp
    └── top.webp
inputs/photos/뉴발란스_992/
    ├── lateral.webp
    └── front.webp
```

### 4. 실행

```bash
# 두 서비스 순차 실행 (color_pattern → sketch_pattern)
./run.sh --input inputs/photos/나이키_탄준
# 또는
uv run python scripts/run_all.py --input inputs/photos/나이키_탄준

# 서비스 하나만 실행
uv run python scripts/run_service.py color_pattern --input inputs/photos/나이키_탄준
uv run python scripts/run_service.py sketch_pattern --input inputs/color_patterns/나이키_탄준_color.png

# 여러 신발을 병렬로
scripts/run_parallel.sh

# 출력 폴더명·반복 횟수·가이드라인 지정
uv run python scripts/run_all.py --input inputs/photos/나이키_탄준 \
    --out outputs --label my_run --repeat 3 --guide inputs/guides/다른_가이드.png

# 상세 로그
uv run python scripts/run_all.py --input inputs/photos/나이키_탄준 --verbose
```

---

## 출력 결과

```
outputs/{label}/
├── color_pattern/
│   ├── step_1_part_survey.md
│   ├── step_2_pattern_unfold.md
│   └── step_2_pattern_unfold_generated_01.png
├── sketch_pattern/
│   ├── step_1_line_art.md
│   └── step_1_line_art_generated_01.png
└── chat_history.json               # 두 서비스 세션의 턴을 모두 담은 히스토리
```

---

## 설정 변경

프롬프트 변경은 **`services/color_pattern/prompts.py`**, **`services/sketch_pattern/prompts.py`**를 수정합니다.
모델·생성 파라미터 변경은 **`config/gemini.py`**(연결·생성 설정)와 각 서비스의 `service.py`의
`MODEL` 상수를 수정합니다.

---

## 요구사항

- Python 3.11+
- `google-genai >= 1.0.0`
- `Pillow >= 10.0.0`
- `python-dotenv >= 1.0.0`
