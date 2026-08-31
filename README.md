# Shoe-Image-To-Pattern

신발 실물 사진을 입력받아 Gemini로 재단 패턴(Pattern)을 생성합니다.
서비스 두 개가 순차 실행됩니다: `color_pattern`(부품 관찰 → 패턴 펼치기, 한 세션 공유)과
`sketch_pattern`(라인 아트 변환, 독립 세션).

```
inputs/photos/<신발>/            (신발 사진 여러 각도)
  → color_pattern 서비스
      Gemini (부품 관찰)     → 부품 명세서 텍스트
      Gemini (패턴 펼치기)   → 2D 컬러 패턴 이미지
  → sketch_pattern 서비스
      Gemini (라인 아트 변환) → 라인 아트 패턴 이미지
  → outputs/<레이블>/
```

두 서비스는 세션을 공유하지 않습니다. `sketch_pattern`이 신발 사진과 부품 명세서를 보면
평면 패턴을 트레이싱하는 대신 3D 신발을 다시 그리기 때문에, 서비스 경계가 곧 세션 경계입니다.
서비스 사이의 핸드오프는 파일 하나(컬러 패턴 PNG)입니다.

---

## 빠른 시작

```bash
git clone git@github.com:jay-jaeyong/Shoe-Image-To-Pattern.git
cd Shoe-Image-To-Pattern

echo "your_api_key" > config/APIkey          # API 키
mkdir -p inputs/photos/나이키_탄준           # 사진 배치
cp ~/사진/측면.webp inputs/photos/나이키_탄준/lateral.webp

./run.sh --input inputs/photos/나이키_탄준
```

`run.sh`가 uv로 `.venv`와 의존성을 구성한 뒤 `scripts/run_all.py`를 실행합니다.
uv가 없으면 설치 여부를 물어봅니다. API 키, `--input`, 기본 가이드라인 파일이
없으면 API를 호출하기 전에 알려줍니다.

---

## inputs — 입력 폴더

사람이 채우는 폴더입니다. 가이드라인만 Git으로 추적하고 사진과 컬러 패턴은 추적하지 않습니다.

```
inputs/
├── guides/                                  # Git 추적
│   └── 가이드라인_회전5도_여백표시.png       # 기본 가이드라인 (2D 펼침 틀)
├── photos/                                  # Git 제외 — color_pattern 입력
│   ├── 나이키_탄준/
│   │   ├── lateral.webp
│   │   ├── medial.webp
│   │   └── top.webp
│   └── 뉴발란스_992/
│       └── lateral.jpg
└── color_patterns/                          # Git 제외 — sketch_pattern 단독 실행 입력
    ├── 나이키_탄준_color.png
    └── 뉴발란스_992_color.png
```

### photos — 파일명이 곧 뷰 라벨입니다

`inputs/photos/<신발>/` 안의 **파일명으로 각도를 판별합니다.** 정해진 이름이 아니면 무시됩니다.

| 파일명 | 프롬프트에 붙는 라벨 |
|--------|---------------------|
| `lateral.*` | 바깥쪽 측면(lateral) |
| `medial.*` | 안쪽 측면(medial) |
| `front.*` | 앞쪽에서 본 모습(front) |
| `heel.*` | 뒤쪽에서 본 모습(heel) |
| `top.*` | 위에서 본 모습(top) |
| `bottom.*` | 바닥(bottom) |

- 확장자는 `webp`, `jpg`, `jpeg`, `png` 중 하나입니다. 같은 뷰에 여러 확장자가 있으면 이 순서로 하나만 고릅니다.
- 여섯 개를 다 넣을 필요는 없습니다. 하나라도 인식되면 실행됩니다. 하나도 못 찾으면 기대 파일명을 알려주고 멈춥니다.
- **Step 1(부품 관찰)은 찾은 사진을 전부** 위 표 순서대로 보냅니다. **Step 2(패턴 펼치기)는 `lateral`과 `medial`만** 직접 받고, 나머지 각도는 같은 세션의 대화 히스토리로만 닿습니다. 그러니 `lateral`은 사실상 필수이고, `medial`이 있으면 결과가 좋아집니다.
- 폴더 이름이 기본 출력 레이블이 됩니다.

### guides — 2D 펼침 틀

`--guide`를 주지 않으면 `inputs/guides/가이드라인_회전5도_여백표시.png`를 씁니다.
이 파일은 저장소에 포함돼 있어 클론 직후 바로 동작합니다. 다른 틀을 쓰려면
`--guide inputs/guides/다른_가이드.png`처럼 경로를 직접 지정하세요.

가이드라인은 Step 2에서만 쓰이지만 **서비스 시작 시점에 미리 열어 확인합니다.**
경로가 틀렸을 때 Step 1의 유료 호출을 태우고 나서야 실패하지 않게 하기 위해서입니다.

### color_patterns — 스케치만 다시 뽑을 때

이미 만들어둔 컬러 패턴에서 라인 아트만 다시 뽑고 싶을 때 여기에 넣고
`run_service.py sketch_pattern`으로 실행합니다. 파일 하나든 폴더 전체든 받습니다.

---

## outputs — 출력 폴더

전부 Git 제외입니다. 실행 한 번이 `outputs/<레이블>/` 하나를 만듭니다.

```
outputs/
├── 나이키_탄준/
│   ├── color_pattern/
│   │   ├── step_1_part_survey.md                    # 부품 명세서 텍스트
│   │   ├── step_2_pattern_unfold.md
│   │   └── step_2_pattern_unfold_generated_01.png   # ★ 컬러 패턴
│   ├── sketch_pattern/
│   │   ├── step_1_line_art.md
│   │   └── step_1_line_art_generated_01.png         # ★ 라인 아트 패턴
│   └── chat_history.json                            # 두 세션의 턴을 모두 담은 히스토리
└── _runlogs/                                        # run_parallel.sh 실행 로그
    └── 나이키_탄준.log
```

`.md` 파일에는 그 스텝에 보낸 프롬프트와 받은 텍스트 응답이 들어갑니다.

### 레이블 정하는 규칙

| 상황 | 레이블 |
|------|--------|
| `--label`을 주면 | 그 값 |
| 입력이 폴더면 | 폴더 이름 (`나이키_탄준`) |
| 입력이 파일이면 | 확장자 뗀 파일명 (`나이키_탄준_color`) |
| 그것도 없으면 | 실행 시각 (`20260831_142530`) |

`--repeat N`을 주면 `<레이블>-1`, `<레이블>-2`처럼 번호가 붙습니다. `--repeat 1`(기본값)이면
접미사가 붙지 않습니다. **같은 레이블로 다시 실행하면 이전 결과를 덮어씁니다.**

---

## 스크립트 사용법

`scripts/` 아래 세 개가 전부입니다. 모두 저장소 루트에서 실행합니다.

### run_all.py — 두 서비스를 순서대로

```bash
./run.sh --input inputs/photos/나이키_탄준
uv run python scripts/run_all.py --input inputs/photos/나이키_탄준
```

`color_pattern`이 만든 컬러 패턴 파일을 그대로 `sketch_pattern`에 넘깁니다.
`run.sh`는 여기에 환경 구성과 사전 확인을 얹은 래퍼이고 인자를 그대로 전달합니다.

| 인자 | 기본값 | 설명 |
|------|--------|------|
| `--input` | (필수) | `inputs/photos/<신발>/` 폴더 |
| `--out` | `outputs` | 출력 루트 |
| `--label` | 입력에서 유도 | 출력 폴더 이름 |
| `--repeat` | `1` | 같은 입력을 N번 실행 |
| `--guide` | `inputs/guides/가이드라인_회전5도_여백표시.png` | 2D 펼침 틀 |
| `--verbose`, `-v` | 꺼짐 | SDK 디버그 로그까지 출력 |

### run_service.py — 서비스 하나만

```bash
# 컬러 패턴만
uv run python scripts/run_service.py color_pattern --input inputs/photos/나이키_탄준

# 이미 있는 컬러 패턴에서 라인 아트만
uv run python scripts/run_service.py sketch_pattern --input inputs/color_patterns/나이키_탄준_color.png

# 폴더를 주면 안의 이미지마다 한 번씩
uv run python scripts/run_service.py sketch_pattern --input inputs/color_patterns --label batch
```

인자는 `run_all.py`와 같고 서비스 이름을 첫 인자로 받습니다(`color_pattern` 또는 `sketch_pattern`).
`--guide`는 `color_pattern`에서만 쓰입니다.

`sketch_pattern`에 폴더를 주면 안의 이미지마다 `<레이블>_<파일명>` 레이블로 따로 실행합니다.
확장자만 다른 동명 파일이 섞여 있어도 서로 덮어쓰지 않게 이름을 구분합니다.

### run_parallel.sh — 여러 신발을 동시에

```bash
uv sync                                        # .venv가 먼저 있어야 합니다

scripts/run_parallel.sh                        # 모든 신발, 두 서비스 전부
scripts/run_parallel.sh color_pattern          # 모든 신발, color_pattern만
scripts/run_parallel.sh --jobs 2 --repeat 3
JOBS=6 REPEAT=3 scripts/run_parallel.sh        # 환경변수로도 됩니다
```

`inputs/photos/*/`를 훑어 신발 폴더마다 하나씩 돌립니다. 동시 실행은 기본 4개이고
`--jobs`로 조절합니다. 진행 상황은 `OK`/`FAIL` 한 줄로 나오고, 자세한 출력은
`outputs/_runlogs/<신발>.log`에 쌓입니다.

`run.sh` 대신 `.venv/bin/python`을 직접 부릅니다. `run.sh`는 매번 `uv sync`를 하는데
여러 개가 동시에 돌면 venv 락을 두고 경쟁하기 때문입니다.

**`sketch_pattern`은 이 스크립트로 실행할 수 없습니다.** 이 스크립트가 훑는 건 신발 사진
폴더인데 `sketch_pattern`의 입력은 컬러 패턴 파일이라서, 지정하면 실행 전에 거부합니다.
컬러 패턴 여러 장은 위의 `run_service.py sketch_pattern --input <폴더>`를 쓰세요.

---

## 폴더 구조

```
Shoe-Image-To-Pattern/
├── run.sh                        # ★ 환경 구성 + 전체 실행
├── pyproject.toml / uv.lock      # 의존성 (requirements.txt도 같은 내용)
│
├── config/                       # AI API 연결 설정
│   ├── api_config.py             # API 키 로드
│   └── gemini.py                 # 연결·생성 파라미터, 재시도 (모델명은 여기 없음)
│
├── services/
│   ├── engine.py                 # 세션 생성, 재시도 전송, 결과 저장, 히스토리 아카이브
│   ├── utils/images.py           # 이미지 로드·라벨 유틸
│   ├── color_pattern/
│   │   ├── service.py            # MODEL 선언, 세션 하나로 두 스텝 실행
│   │   ├── photo_input.py        # 신발 폴더 해석, 뷰 라벨, parts 조립
│   │   ├── prompts.py            # Step 1·2 프롬프트
│   │   ├── schema.py             # Survey / Part / Marking / Symmetry
│   │   ├── step_1_part_survey.py
│   │   └── step_2_pattern_unfold.py
│   └── sketch_pattern/
│       ├── service.py            # MODEL 선언, 자기 세션으로 한 스텝 실행
│       ├── prompts.py            # LINE_ART_PROMPT
│       └── step_1_line_art.py
│
├── scripts/
│   ├── run_all.py                # 두 서비스 순차 실행
│   ├── run_service.py            # 서비스 하나 실행
│   ├── run_parallel.sh           # 신발 폴더 병렬 실행
│   └── _common.py                # 레이블·로깅 공용 헬퍼
│
├── utils/logging_utils.py        # Step 컨텍스트 로그 필터
├── tests/                        # unittest (API 호출 없음)
├── docs/                         # 설계 문서
├── inputs/                       # 입력 (위 참조)
└── outputs/                      # 출력 (위 참조)
```

모델명은 전역 설정이 아니라 각 `service.py`의 `MODEL` 상수입니다.
`chats.create(model=...)`가 세션 생성 시점에 모델을 고정하기 때문에, 모델은
세션 단위 = 서비스 단위 값입니다.

---

## 데이터 흐름

### color_pattern — Step 1: 부품 관찰

| 항목 | 내용 |
|------|------|
| **입력** | 신발 폴더에서 인식된 사진 전부 (뷰 선언 순서) |
| **라벨** | 각 사진 앞에 `[바깥쪽 측면(lateral)]` 형태 텍스트를 붙여 전달 |
| **프롬프트** | Upper를 재단 부품 단위로 읽어 명세서 작성. 확인 못 한 부위는 '미확인'으로 명시 |
| **응답 모달리티** | 이 스텝만 `["TEXT"]` + `response_schema=Survey`로 JSON 강제 |
| **출력** | 부품 명세서 텍스트 |

### color_pattern — Step 2: 패턴 펼치기

| 항목 | 내용 |
|------|------|
| **입력** | `lateral` + `medial` + 가이드라인 이미지 + Step 1 명세서 (나머지 각도는 같은 세션 히스토리로만) |
| **프롬프트** | 실물 우선 규칙에 따라 Upper를 3D → 2D로 전개 |
| **출력** | 2D 컬러 패턴 이미지 |

### sketch_pattern — 라인 아트 변환

| 항목 | 내용 |
|------|------|
| **입력** | 컬러 패턴 이미지 한 장 (독립 세션 — 신발 사진도 명세서도 보지 않음) |
| **프롬프트** | 컬러 패턴을 정밀 복제해 라인 아트로 변환 |
| **출력** | 라인 아트 패턴 이미지 |

---

## API 키 설정

아래 중 하나를 고릅니다. 위에서부터 먼저 찾은 것을 씁니다.

```bash
echo "your_api_key" > config/APIkey             # A. 파일 (권장, gitignore 대상)
export GEMINI_API_KEY_FILE=~/Documents/키.txt   # B. 레포 밖 키 파일 경로
export GEMINI_API_KEY=your_api_key              # C. 환경변수
echo "GEMINI_API_KEY=your_api_key" > .env       # D. .env 파일
```

아무것도 없으면 `config/api_config.py`의 `EXTERNAL_KEY_FILES` 기본 경로
(`~/Documents/geminiapi.txt`)를 읽습니다. 키 값은 로그에 남지 않고 어느 경로에서
읽었는지만 출력됩니다.

---

## 수정할 곳

| 바꾸고 싶은 것 | 파일 |
|---------------|------|
| 프롬프트 | `services/color_pattern/prompts.py`, `services/sketch_pattern/prompts.py` |
| 모델 | 각 서비스의 `service.py`의 `MODEL` 상수 |
| 생성 파라미터·재시도 | `config/gemini.py` |
| 뷰 파일명·전송 순서 | `services/color_pattern/photo_input.py` |

---

## 테스트

```bash
uv run python -m unittest discover -s tests -q
```

실제 API를 호출하지 않습니다. API 키가 없어도 전부 통과해야 합니다.
`tests/golden/`은 Gemini에 실제로 보내는 요청 구조를 고정한 기록입니다.
테스트를 통과시키려고 이 파일들을 고치면 안 됩니다.

---

## 요구사항

- Python 3.11+
- `google-genai >= 1.0.0`, `Pillow >= 10.0.0`, `python-dotenv >= 1.0.0`
- [uv](https://docs.astral.sh/uv/) (`run.sh`가 없으면 설치를 제안합니다)
