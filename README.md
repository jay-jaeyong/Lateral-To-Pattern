# Lateral-To-Pattern

신발 실물 사진을 입력받아 Gemini AI로 재단 패턴(Pattern)을 자동 생성하는 도구입니다.
관찰 → 펼치기 → 라인 아트 3스텝을 순차 실행합니다. Step 1·2는 같은 채팅 세션을 공유하고, Step 3는 별도 세션에서 실행됩니다.

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

## 스케치 출력 주석 웹페이지

이 웹페이지는 컬러 원본과 스케치 출력을 나란히 확인하면서 재단선 오류 영역을
반자동으로 표시하는 로컬 도구입니다. 이미지 파일은 읽기만 하며, 저장 버튼을
눌렀을 때 `annotations/sketch-scoring/items/` 아래의 JSON 주석만 변경합니다.
Gemini나 다른 외부 API를 호출하지 않으며 API 키도 필요하지 않습니다.

### 실행 방법

프로젝트 루트에서 의존성을 설치한 뒤 서버를 실행합니다.

```bash
uv sync
uv run python scripts/annotate_sketches.py
```

브라우저에서 다음 주소를 엽니다.

```text
http://127.0.0.1:5000
```

서버는 기본적으로 현재 컴퓨터에서만 접속할 수 있는 `127.0.0.1`에 바인딩되고
디버그 모드는 꺼져 있습니다. 종료하려면 서버를 실행한 터미널에서 `Ctrl+C`를
누릅니다. 포트를 바꾸려면 다음과 같이 실행합니다.

```bash
uv run python scripts/annotate_sketches.py --port 5050
```

기본 데이터 위치는 다음과 같습니다.

```text
annotations/sketch-scoring/dataset.json   # 원본과 출력 판본을 연결하는 manifest
annotations/sketch-scoring/items/         # 웹페이지에서 저장한 항목별 주석 JSON
```

`images/`에 새 원본이나 출력 판본을 추가했다면 manifest 후보를 다시 탐색할 수
있습니다.

```bash
uv run python scripts/score_sketch_outputs.py manifest \
  --images-dir images \
  --manifest annotations/sketch-scoring/dataset.json
```

같은 항목과 판본에 해당하는 출력 후보가 여러 개면 임의로 선택하지 않고
`dataset.json`에 검토 대상으로 남습니다. 이 경우 실제로 사용할 `path`와
`kind`를 manifest에서 확정한 뒤 웹페이지를 새로 고칩니다.

### 화면 선택

왼쪽 **대상** 영역에서 다음 순서로 선택합니다.

1. **항목**에서 신발 모델을 선택합니다.
2. **판본**에서 `output-5`처럼 검사할 출력 판본을 선택합니다.
3. **이미지**에서 주석을 그릴 이미지를 선택합니다.
   - **컬러 원본**: 정상 재단선의 위치와 형상을 확인할 때 사용합니다.
   - **스케치 출력**: 끊김이나 누락이 발생한 실제 출력 위에 주석을 그릴 때 사용합니다.

주석 좌표는 이미지 너비와 높이를 기준으로 한 `[0, 1]` 정규화 좌표로
저장됩니다. 확대·축소하거나 화면을 이동해도 저장 좌표는 바뀌지 않습니다.

### 공통 조작

- **이동**: 캔버스를 드래그해 화면을 이동합니다.
- **선택**: 기존 주석을 클릭해 선택합니다. 선택한 박스 내부를 드래그하면
  주석 전체가 이동하고, 모서리 핸들을 드래그하면 검사 박스의 크기가 바뀝니다.
- **박스 드래그**: 새 검사 영역을 만듭니다. 먼저 **주석 종류**를 선택한 뒤
  이미지 안에서 드래그합니다.
- **확대·축소**: 마우스 휠 또는 **확대**, **축소** 버튼을 사용합니다.
- **원래대로**: 이미지를 화면에 다시 맞춥니다.
- **선택 삭제**: 선택한 주석을 메모리에서 제거합니다. JSON에 반영하려면
  마지막에 **주석 저장**을 눌러야 합니다.

이미지 바깥의 회색 여백에 그린 점이나 박스는 주석으로 저장되지 않습니다.

### `connection`: 끊긴 재단선 표시

하나의 재단선이어야 하지만 중간이 끊긴 위치를 검사할 때 사용합니다.

1. **주석 종류**에서 `connection (끊긴 재단선)`을 선택합니다.
2. **박스 드래그**를 누르고 끊긴 부분과 선의 양쪽 끝을 포함하도록 박스를 그립니다.
3. 생성된 `connection` 주석이 선택된 상태에서 다음 방법 중 하나로 앵커 두 개를
   지정합니다.
   - **앵커 자동 제안**: 선 끝이 정확히 두 개로 명확할 때만 후보를 적용합니다.
   - **앵커 두 번 클릭**: 끊긴 동일 재단선의 한쪽 끝과 반대쪽 끝을 차례로
     클릭합니다.
4. 파란 앵커 박스 두 개가 의도한 선 끝을 감싸는지 확인합니다.
5. **주석 저장**을 누릅니다.

앵커는 서로 다른 선의 끝이 아니라 **동일한 재단선이 이어져야 하는 두 끝**을
표시해야 합니다. 빨간 박스가 합성된 `annotated_only` 출력에서는 빨간 선을
재단선으로 오인할 수 있으므로 자동 제안을 사용하지 않고 직접 두 끝을
클릭하도록 안내됩니다.

### `required_path`: 반드시 있어야 하는 경계 표시

특정 재단선의 누락 여부와 위치 오차만 검사할 때 사용합니다. 같은 박스 안의
다른 선은 추가 오류로 계산하지 않습니다.

1. **주석 종류**에서 `required_path (필수 경계)`를 선택합니다.
2. **박스 드래그**로 검사할 경계를 포함하는 영역을 만듭니다.
3. 생성된 주석을 선택하고 **폴리라인 클릭**을 누릅니다.
4. 컬러 원본에서 기대하는 재단선을 따라 순서대로 점을 찍습니다.
5. 점을 두 개 이상 찍은 뒤 **폴리라인 완료**를 누릅니다. 더 분리된 경계가
   필요하면 폴리라인 클릭과 완료를 반복합니다.
6. **주석 저장**을 누릅니다.

점은 경계의 흐름을 나타내므로 시작점부터 끝점까지 순서대로 찍어야 합니다.
너무 많은 점을 촘촘하게 찍기보다는 곡률이 바뀌는 지점과 양 끝을 중심으로
표시합니다.

### `complete_roi`: 영역 안의 모든 정상 재단선 표시

한 영역 안에서 누락된 선과 불필요하게 추가된 선을 모두 검사할 때 사용합니다.

1. **주석 종류**에서 `complete_roi (완전 영역)`를 선택합니다.
2. **박스 드래그**로 완전하게 주석할 영역을 지정합니다.
3. **폴리라인 클릭**으로 박스 안에 있어야 하는 모든 정상 재단선을 표시하고,
   각 선마다 **폴리라인 완료**를 누릅니다.
4. 박스 안의 정상 선을 빠뜨리지 않았는지 확인한 뒤 **주석 저장**을 누릅니다.

`complete_roi`는 표시한 기대 경계의 누락 비율과 기대 경계 주변 허용 범위 밖에
생긴 추가 잉크 비율을 함께 측정합니다. 박스 안의 정상 선을 일부만 표시하면
정상 출력선도 추가 선으로 계산될 수 있으므로, 영역을 작게 잡더라도 내부의
정상 재단선은 전부 표시해야 합니다.

### 빨간 바운딩박스 가져오기

이미 빨간 박스가 그려진 참고 출력은 다음 순서로 후보를 가져올 수 있습니다.

1. **이미지**를 **스케치 출력**으로 바꿉니다.
2. 만들 주석의 종류를 먼저 선택합니다.
3. **빨간 박스 가져오기**를 누릅니다.
4. 캔버스에 표시된 점선 후보를 확인합니다.
5. 올바르면 **후보 확정**, 잘못 검출됐으면 **후보 버리기**를 누릅니다.
6. `connection` 후보라면 각 박스에 앵커 두 개를 직접 지정합니다.
7. 모든 주석을 확인한 뒤 **주석 저장**을 누릅니다.

**후보 확정**은 브라우저 메모리에 주석을 추가할 뿐이며 JSON 파일을 저장하지
않습니다. 반드시 별도로 **주석 저장**을 눌러야 합니다. 빨간 픽셀을 지워서
깨끗한 출력으로 복원하지도 않습니다.

### 저장과 채점 확인

- **주석 저장**은 현재 항목의 전체 주석을 다음 위치에 저장합니다.

  ```text
  annotations/sketch-scoring/items/{항목 ID}.json
  ```

- 미완성 `connection`이나 폴리라인이 없는 `required_path`·`complete_roi`가 있으면
  저장하지 않고 해당 주석 ID를 알려줍니다.
- **이 이미지 채점**은 현재 선택한 판본을 메모리에서만 채점해 왼쪽 지표 표에
  표시합니다. 이 버튼은 실행 보고서를 만들지 않습니다.
- 결과는 `pass`, `warn`, `fail`, `not_scored`와 신뢰도·사유로 나뉘며 단일 총점이나
  전체 순위는 만들지 않습니다.
- `not_scored`는 오류를 숨긴 점수가 아니라, 입력 신뢰도가 낮거나 정상 사례로
  판정 문턱을 아직 확정하지 않은 지표입니다.

전체 manifest를 실행 이력으로 남기며 채점하려면 웹 서버와 별도로 다음 명령을
사용합니다.

```bash
uv run python scripts/score_sketch_outputs.py score \
  --manifest annotations/sketch-scoring/dataset.json \
  --label my-annotation-run
```

결과는 새 실행 디렉터리에 저장되며 이전 실행을 덮어쓰지 않습니다.

```text
reports/sketch-scoring/{실행 ID}/results.json
reports/sketch-scoring/{실행 ID}/summary.csv
reports/sketch-scoring/latest.json
```

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
