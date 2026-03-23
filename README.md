# Lateral-To-Pattern

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
