# Lateral-To-Pattern

신발 측면(Lateral) 사진을 입력받아 Gemini AI를 이용해 **3단계 파이프라인**으로 재단 패턴(Pattern)을 자동 생성하는 도구입니다.

---

## 개요

```
신발 측면 사진
    → [Step 1] 라인 아트 변환       (흑백 선화)
    → [Step 2] 2D 패턴 전개         (어퍼를 평면으로 펼치기)
    → [Step 3] 시접 가이드라인 추가  (제조용 여분 확장)
    → output/ 저장
```

각 단계는 동일한 Gemini **채팅 세션**에서 실행되어 이전 대화 맥락이 유지됩니다.

---

## 폴더 구조

```
Lateral-To-Pattern/
├── main.py                  # 진입점
│
├── config/                  # 설정 (수정 빈도 높음)
│   ├── prompts.py           # ★ 각 Step의 프롬프트와 이미지 경로 정의
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
├── images/                  # 입력 이미지 (단계별 하위 폴더)
│   ├── step1/               # 신발 측면 원본 사진
│   ├── step2/               # Step 2 가이드라인 이미지 (어퍼 실루엣)
│   │   └── {모델명}/
│   └── step3/               # Step 3 가이드라인 이미지 (시접 라인)
│       └── {모델명}/
│
└── output/                  # 생성 결과
    └── {모델명}/
        ├── step_01_level_1_style_change.md
        ├── step_02_level_2_pattern_generation.md
        ├── step_03_level_3_guideline_addition.md
        ├── final_output.md
        └── chat_history.json
```

---

## 파이프라인 단계별 데이터 흐름

### Step 1 — 라인 아트 변환

| 항목 | 내용 |
|------|------|
| **입력 이미지** | `images/step1/` 내 신발 측면 원본 사진 |
| **선택 방식** | 실행 시 콘솔에서 번호 입력 선택 (단일·복수·`all` 지원) |
| **프롬프트** | 원본 사진을 정밀하게 라인 아트로 재현 (흰 내부, 검은 윤곽선, 글자 포함) |
| **API 입력** | `[원본_이미지, 프롬프트]` |
| **출력** | 흑백 선화 이미지 + 텍스트 응답 |
| **부가 효과** | 선택한 파일명 → `run_label` (출력 폴더명) 및 `model_name` 자동 결정 |

### Step 2 — 2D 패턴 전개

| 항목 | 내용 |
|------|------|
| **입력 이미지** | `images/step2/{model_name}/` 내 어퍼 실루엣 가이드라인 이미지 |
| **이전 이미지** | ⚠️ Step 1 생성 이미지는 **포함하지 않음** (가이드라인 이미지만 사용) |
| **이전 텍스트** | ⚠️ **포함하지 않음** |
| **채팅 맥락** | Step 1 대화 히스토리는 세션에 유지됨 |
| **프롬프트** | 어퍼를 3D→2D로 전개, 가이드라인 실루엣에 밀착, 흑백, 재봉선 점선 표현 |
| **API 입력** | `[가이드라인_이미지, 프롬프트]` |
| **출력** | 2D 전개 패턴 이미지 + 텍스트 응답 |

### Step 3 — 시접 가이드라인 추가

| 항목 | 내용 |
|------|------|
| **입력 이미지** | `images/step3/{model_name}/` 내 시접 여분 가이드라인 이미지 |
| **이전 이미지** | ✅ Step 2에서 생성된 패턴 이미지 **포함** |
| **이전 텍스트** | ✅ Step 1·2 텍스트 응답 **포함** |
| **프롬프트** | 패턴을 가이드라인(시접 라인) 끝까지 확장, 흑백 |
| **API 입력** | `[Step2_생성_이미지, 가이드라인_이미지, 이전_텍스트_응답, 프롬프트]` |
| **출력** | 시접 포함 최종 패턴 이미지 + 텍스트 응답 |

---

## 설치 및 실행

### 1. 의존성 설치

```bash
pip install -r requirements.txt
```

### 2. API 키 설정

아래 중 하나를 선택합니다.

```bash
# 방법 A: 파일로 저장 (권장)
echo "your_api_key" > config/APIkey

# 방법 B: 환경변수
export GEMINI_API_KEY=your_api_key

# 방법 C: 프로젝트 루트에 .env 파일
echo "GEMINI_API_KEY=your_api_key" > .env
```

### 3. 이미지 배치

```
images/step1/            ← 신발 측면 사진 (PNG/JPG 등)
images/step2/{모델명}/   ← 어퍼 실루엣 가이드라인
images/step3/{모델명}/   ← 시접 가이드라인
```

### 4. 실행

```bash
# 기본 실행 (Step 1에서 이미지 선택)
python main.py

# 특정 이미지 지정
python main.py --step1-image images/step1/nike.png

# 특정 단계부터 시작
python main.py --start-step 2

# 출력 폴더명 지정
python main.py --run-label my_run

# 상세 로그
python main.py --verbose
```

---

## 출력 결과

```
output/{모델명}/
├── step_01_level_1_style_change.md      # Step 1 결과 (입력·프롬프트·응답)
├── step_02_level_2_pattern_generation.md
├── step_03_level_3_guideline_addition.md
├── final_output.md                      # 최종 단계 응답 전문
└── chat_history.json                    # 전체 채팅 히스토리 (JSON)
```

생성된 이미지는 각 단계 Markdown 파일과 동일한 폴더에 저장됩니다.

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

멀티스텝 채팅 방식으로 Gemini API를 호출하는 이미지+프롬프트 파이프라인.

```
이미지 + 프롬프트 → Gemini → 이미지 + 프롬프트 → Gemini → 이미지 + 프롬프트 → Gemini → output 저장
                   (채팅 히스토리 유지)          (채팅 히스토리 유지)
```

## 프로젝트 구조

```
Lateral-To-Pattern/
├── main.py                    ← 실행 진입점
├── requirements.txt
├── .env.example               ← API 키 예시 (복사 후 .env로 이름 변경)
│
├── config/                    ← 설정 관리
│   ├── api_config.py          ← API 키 로드 (.env에서 읽음)
│   ├── gemini_config.py       ← 모델명, 생성 파라미터, 안전 설정
│   └── prompts.py             ← 단계별 프롬프트 & 이미지 경로 정의
│
├── src/                       ← 핵심 로직
│   ├── gemini_client.py       ← Gemini API 채팅 클라이언트 (재시도 포함)
│   ├── image_handler.py       ← 이미지 로드 & parts 구성
│   └── pipeline.py            ← 멀티스텝 파이프라인 오케스트레이터
│
├── utils/
│   └── output_handler.py      ← 단계별 결과 & 최종 출력 파일 저장
│
├── images/                    ← 단계별 입력 이미지
│   ├── step1/input.png
│   ├── step2/input.png
│   └── step3/input.png
│
└── output/                    ← 실행 결과 (실행마다 타임스탬프 폴더 생성)
    └── 20240101_120000/
        ├── step_01_initial_analysis.md
        ├── step_02_lateral_pattern_extraction.md
        ├── step_03_final_synthesis.md
        ├── final_output.md
        └── chat_history.json
```

## 시작하기

### 1. 의존성 설치

```bash
pip install -r requirements.txt
```

### 2. API 키 설정

```bash
cp .env.example .env
# .env 파일에서 GEMINI_API_KEY 값을 실제 키로 교체
```

또는 `config/APIkey` 파일에 API 키 문자열만 넣어 저장하면 해당 파일을 우선적으로 사용합니다 (파일은 .gitignore에 등록되어 있습니다).

### 3. 이미지 배치

각 단계에 사용할 이미지를 해당 폴더에 저장:
```
images/step1/input.png
images/step2/input.png
images/step3/input.png
```

### 4. 프롬프트 커스터마이징 (선택)

`config/prompts.py`에서 각 단계의 프롬프트와 이미지 경로를 수정합니다.

### 5. 실행

```bash
# 기본 실행
python main.py

# CLI로 이미지 경로 직접 지정
python main.py --step1-image path/to/img1.png --step2-image path/to/img2.png --step3-image path/to/img3.png

# 실행 레이블 지정 (output 폴더명)
python main.py --run-label experiment_01

# 상세 로그 출력
python main.py --verbose
```

## 설정 파일 설명

| 파일 | 역할 |
|------|------|
| `.env` | API 키 (Git 업로드 금지) |
| `config/api_config.py` | API 키 로드 로직 |
| `config/gemini_config.py` | 모델, 온도, 토큰 수 등 생성 파라미터 |
| `config/prompts.py` | 단계별 프롬프트 & 이미지 경로 |

## 결과물

실행 후 `output/{run_label}/` 폴더에 저장됩니다:

- `step_01_*.md` ~ `step_03_*.md`: 각 단계의 프롬프트 + 응답
- `final_output.md`: 최종(마지막 단계) 응답
- `chat_history.json`: 전체 채팅 히스토리 (JSON)
