# 서비스 단위 폴더 재구조화 설계

- 날짜: 2026-08-28
- 상태: 승인됨
- 대상: `Shoe-Image-To-Pattern` 저장소 전체 구조
- 근거 문서: `CONTEXT.md`, `docs/source_of_truth.md`
- 선행 커밋: `b6934a7` (Step 3 기본 활성화 및 컬러 패턴 라벨)

## 배경

지금 구조는 스텝 세 개를 하나의 범용 엔진(`core/pipeline.py`, 462줄)이 dict 플래그로 구동한다. 스텝 dict의 키가 14개까지 늘었고 그중 `fresh_session`, `include_prev_texts`, `prev_image_label`, `match_input_aspect_ratio`, `response_modalities`는 전부 "이 스텝만 예외"를 뜻한다. 범용 엔진에게 스텝별 차이를 데이터로 설명하다 보니 쌓인 플래그다.

이 구조가 실제 결함을 만들었다.

1. Step 3의 앞 단계 이미지에 라벨이 붙지 않아 모델이 그것을 프롬프트가 지목하는 '원본'으로 읽지 못했다. 같은 일을 하는 독립 스크립트에는 라벨이 있었다. 경로가 두 벌로 갈라져 한쪽만 고쳐졌기 때문이다. (`b6934a7`에서 수정)
2. `ImageHandler.build_parts`가 폴더 내용을 보고 파일 선택 모드와 폴더 선택 모드를 추측한다. `inputs` 폴더에 사진이 낱개로 놓이면 Step 1이 라벨 없는 한 장으로 조용히 퇴화한다.
3. 2가 발생하면 Step 2의 `reference_views` 사진이 함께 사라진다. `_references_for`가 Step 1의 parts에서 수확한 라벨 쌍을 읽기 때문이다. 경고 로그만 남기고 실행은 "성공"한다.
4. `images/` 폴더가 파일 형식을 이름으로 삼은 탓에 서로 다른 서비스에 들어가는 두 도메인 산출물이 섞였다. 현재 이 폴더의 12개 중 11개가 컬러 패턴이고 신발 사진은 한 장뿐이며 모델 폴더는 하나도 없다. git이 추적하는 유일한 흔적은 삭제된 `images/step1|step2|step3/.gitkeep`으로, 코드가 기대하는 모델 기준 폴더와 어긋난다.
5. `MODEL_NAME`이 전역이다. Step 3 실험을 위해 고른 `gemini-3.1-flash-image`가 Step 1까지 지배한다. Step 1은 그 이미지 모델에게 TEXT + `application/json` + `Survey` 스키마를 요구한다.

1과 3은 같은 뿌리를 가진다. 스텝 간 암묵적 결합을 엔진이 중개하는 구조다.

## 결정 요약

1. 분해 축은 스텝이 아니라 **서비스**다. `services/color_pattern`(현 Step 1·2)과 `services/sketch_pattern`(현 Step 3)으로 나눈다.
2. **서비스 경계가 곧 채팅 세션 경계다.** `color_pattern`의 두 스텝은 세션을 공유하고, `sketch_pattern`은 자기 세션을 새로 연다. `fresh_session`과 `include_prev_texts` 플래그는 구조적 사실로 대체되어 사라진다.
3. 서비스 간 핸드오프는 **파일**이다. `sketch_pattern`은 컬러 패턴 이미지 경로를 받는다. 메모리 전달 경로를 따로 두지 않는다.
4. 스텝은 **함수 하나**다. 베이스 클래스도 훅도 없다. 스텝 dict는 삭제한다.
5. pydantic 스키마는 **검증 전용**이다. 프롬프트에 넣는 텍스트는 모델 응답 원문을 그대로 쓴다.
6. 프롬프트는 서비스마다 `prompts.py`로 분리한다.
7. provider 추상화는 만들지 않는다. 모델 이름은 **서비스 단위 설정**으로 내린다.
8. `images/` → `inputs/`, `output/` → `outputs/`. `inputs/`는 소비하는 서비스 기준으로 나눈다.
9. 재구조화 전에 **골든 parts 테스트**를 만든다. 골든이 지키는 명제는 하나다: 같은 입력 파일에 대해 재구조화 전과 후에 Gemini가 받는 것이 한 바이트도 다르지 않다.

## 목표

1. 스텝 dict의 플래그 14개를 없애고 각 스텝의 동작을 그 스텝 파일의 코드로 만든다.
2. 파이프라인 경로와 개별 실행 경로를 하나로 합쳐, 한쪽만 고쳐지는 종류의 결함을 구조적으로 막는다.
3. `inputs/` 배치를 강제해 입력 모드 추측 로직을 제거한다. 입력이 규약과 다르면 API 호출 전에 소리 내어 실패한다.
4. 신발 사진 서비스와 컬러 패턴 서비스가 서로 다른 모델을 쓸 수 있게 한다.
5. Step 1 응답이 `Survey` 스키마를 지켰는지 그 자리에서 검증한다.
6. 서비스 단위 개별 실행, 전체 순차 실행, 여러 입력 병렬 실행을 하나의 인자 어휘로 제공한다.
7. 재구조화가 API 요청을 바꾸지 않았음을 자동으로 증명한다.

## 비목표

- 프롬프트 문구 수정. `LINE_ART_PROMPT`를 포함한 모든 프롬프트 텍스트는 한 글자도 바꾸지 않는다.
- 생성 이미지의 내용이나 시각 품질 판정.
- provider 추상화 계층.
- 두 번째 AI provider 지원.
- 스텝 단위 개별 실행. 개별 실행의 단위는 서비스다.
- Step 1과 Step 2를 서로 다른 모델로 돌리는 것. 세션 공유가 이를 막는다.
- 기존 `output/` 아래 14개 실행 결과의 이전 또는 변환.
- 브랜치 분리. 작업은 `safe-region-selection`에서 계속하고 PR #1에 이어 붙인다.

## 도메인 언어

`CONTEXT.md`에 **컬러 패턴**을 추가했다(`cbb35a5`). 서비스 이름이 도메인 용어를 그대로 쓴다.

- `color_pattern` 서비스는 **컬러 패턴**을 만든다.
- `sketch_pattern` 서비스는 **스케치 패턴**을 만든다.

코드 식별자에서 "모델"의 중의성을 없앤다. 신발 제품은 `shoe`, AI 모델만 `model`이다. `_derive_model_name`, `_resolve_model_subdir`의 `model_name`은 `shoe_name`으로 바꾼다.

## 폴더 구조

```
config/
  api_config.py            키 로딩 (변경 없음)
  gemini.py                연결 설정, 안전 설정, temperature, 재시도
services/
  engine.py                세션 생성·재시도·저장·히스토리 아카이브
  utils/
    images.py              load, list_image_files, LABEL_FORMAT, find_guideline, is_guideline_file
  color_pattern/
    service.py             MODEL 선언, 세션 열고 step 1 → step 2
    step_1_part_survey.py
    step_2_pattern_unfold.py
    prompts.py             PART_SURVEY_PROMPT, PATTERN_UNFOLD_PROMPT
    schema.py              Survey, Part, Marking, Symmetry
    photo_input.py         뷰 라벨, 신발 폴더 해석, 참조 사진 선택
  sketch_pattern/
    service.py             MODEL 선언, 자기 세션을 열고 step 1
    step_1_line_art.py
    prompts.py             LINE_ART_PROMPT, ORIGINAL_PATTERN_LABEL
inputs/
  photos/<신발>/            신발 사진. color_pattern 입력
  color_patterns/           컬러 패턴. sketch_pattern 입력
  guides/                   가이드라인 이미지. color_pattern이 사용
outputs/
scripts/
  run_all.py
  run_service.py
  run_parallel.sh
tests/
```

`core/`는 사라진다. `main.py`도 사라지고 `scripts/run_all.py`가 그 자리를 대신한다.

## 스텝 계약

스텝은 모듈 하나이고 그 안에 `run` 함수 하나를 노출한다. 베이스 클래스, 추상 메서드, 등록 데코레이터를 두지 않는다.

```python
# services/color_pattern/step_1_part_survey.py
def run(session, photos) -> str:
    parts = photo_input.build_labeled_parts(photos, PART_SURVEY_PROMPT)
    text = session.send(parts, config=SURVEY_CONFIG).text
    Survey.model_validate_json(text)   # 검증만. 반환값은 원문 그대로.
    return text
```

```python
# services/color_pattern/service.py
MODEL = "gemini-3.1-flash-image"

def run(photos_dir, out) -> Path:
    session = engine.new_session(MODEL)
    survey_text = step_1_part_survey.run(session, photo_input.resolve(photos_dir))
    return step_2_pattern_unfold.run(session, photo_input.resolve(photos_dir), survey_text, out)
```

규칙:

- 스텝 함수가 직접 `session.send()`를 부른다. 엔진이 스텝을 대신 호출하지 않는다.
- 스텝 함수의 반환값이 다음 스텝의 인자다. 공유 상태 객체를 두지 않는다.
- 스텝별 분기 플래그를 새로 만들지 않는다. 차이는 그 스텝 파일의 코드로 표현한다.
- pydantic 모델로 검증은 하되, 검증 결과를 다시 직렬화해 프롬프트에 넣지 않는다. 키 순서와 공백이 달라지면 다음 스텝이 보는 토큰이 달라진다.

### 엔진의 책임

`services/engine.py`가 제공하는 것은 네 가지뿐이다.

- `new_session(model)` — 채팅 세션 생성. `chats.create(model=..., config=...)`.
- `send(parts, config)` 재시도 — `MAX_RETRIES`, `RETRY_DELAY`.
- 실행 결과 저장 — 현 `OutputHandler.save_step`, `save_final`.
- 채팅 히스토리 아카이브 — 세션이 여러 개이므로 서비스마다의 히스토리를 모아 `chat_history.json` 하나로 남긴다.

입력 준비는 엔진의 책임이 아니다.

## 입력 배치

```
inputs/
  photos/<신발>/lateral.png  medial.png  front.png  heel.png  top.png  bottom.png
  color_patterns/*.png
  guides/가이드라인_회전5도_여백표시.png
```

- 확장자는 현 스크립트와 같이 `webp`, `jpg`, `jpeg`, `png`를 순서대로 탐색한다.
- 뷰 파일명은 `utils/cli.py:VIEW_FLAGS`의 플래그 이름을 그대로 쓴다. 프롬프트에 붙는 한글 라벨 문자열은 프롬프트가 그대로 지칭하므로 바뀌면 안 되며 `color_pattern/photo_input.py`로 옮긴다.
- `photo_input`은 `inputs/photos/<신발>/`을 **요구**한다. 폴더가 없거나 인식 가능한 뷰 파일이 하나도 없으면 API 호출 전에 예외를 던진다. 파일 선택 모드로의 대체 경로를 두지 않는다. `ImageHandler._select_entries`의 대화형 선택도 제거한다.
- `inputs/`는 gitignore를 유지한다. 단 `inputs/photos/.gitkeep`, `inputs/color_patterns/.gitkeep`을 두어 폴더 모양을 남기고, 삭제된 `images/step1|step2|step3/.gitkeep` 흔적은 정리한다.
- `inputs/guides/`의 가이드라인 이미지는 git에 추적한다. 손으로 만든 자산이고 모든 실행이 같은 것을 쓴다.

## 출력 배치

```
outputs/
  <label>/
    color_pattern/
      step_1_part_survey.md
      step_2_pattern_unfold.md
      step_2_pattern_unfold_generated_01.png
    sketch_pattern/
      step_1_line_art.md
      step_1_line_art_generated_01.png
    final_generated_01.png
    final_output.md
    chat_history.json
  _runlogs/<label>.log
```

스텝 번호는 서비스 폴더 안에서 1부터 다시 매긴다. 폴더 이름이 그 번호가 어느 서비스의 순서인지 말한다.

## 스크립트 계약

```
scripts/run_service.py  <서비스> --input <경로> [--repeat N] [--label L] [--out outputs]
scripts/run_all.py                --input <경로> [--repeat N] [--label L] [--out outputs]
scripts/run_parallel.sh <서비스...> [--jobs N] [--repeat N]
```

- `--input`의 의미는 서비스가 정한다. `color_pattern`이면 `inputs/photos/<신발>/`, `sketch_pattern`이면 컬러 패턴 파일 하나 또는 그것들이 든 폴더.
- `run_all.py`는 `color_pattern`을 실행해 결과를 저장하고, 저장된 파일 경로를 `sketch_pattern`에 넘긴다.
- `--repeat N`은 현 `RUNS`/`VER` 조합을 대체한다. `--repeat 3 --label adidas_ORKETRO_v7`이면 `outputs/adidas_ORKETRO_v7-1..3/`이 생긴다. `--repeat 1`이면 접미사를 붙이지 않는다.
- `--label` 미지정 시 현 `derive_run_label` 규칙(타임스탬프)을 유지한다.
- `run_parallel.sh`는 bash로 남긴다. 실행마다 별도 프로세스라 채팅 세션과 출력 폴더가 격리되고, `logging.basicConfig`가 전역이라 스레드로 돌리면 로그가 뒤섞인다. `inputs/photos/*/`를 훑어 `run_service.py`를 부르기만 하며, 현 `run_model()`의 뷰 × 확장자 탐색 12줄은 `photo_input`으로 옮겨가므로 삭제한다.
- `utils/cli.py`의 뷰 플래그 6개(`--lateral` 등)와 `--shoe-image`, `--guide-image`는 제거한다. 입력 위치는 규약이 정한다.
- `scripts/run_all_views.sh`, `scripts/run_parallel.sh`(현재본), `scripts/run_step3_on_color_patterns.py`는 위 세 스크립트로 대체하고 삭제한다.
- `scripts/mark_guideline.py`, `mark_guideline_margin.py`, `warp_guideline_asym.py`, `prototypes/`는 파이프라인 밖의 도구다. 그대로 둔다.

## 모델 설정

`MODEL_NAME` 전역 상수를 제거하고 각 서비스의 `service.py`가 자기 모델을 선언한다.

```python
# services/color_pattern/service.py
MODEL = "gemini-3.1-flash-image"

# services/sketch_pattern/service.py
MODEL = "gemini-3.1-flash-image"
```

두 값은 지금과 동일하다. 재구조화 시점에 모델을 바꾸지 않는다. 얻는 것은 이후 실험에서 한쪽만 바꿀 수 있다는 점이다.

`chats.create(model=...)`가 세션 생성 시점에 모델을 고정하고 `send_message(config=...)`로는 바꿀 수 없으므로, 세션을 공유하는 Step 1과 Step 2는 같은 모델을 쓴다. 이는 결정 2의 직접적 귀결이다.

`config/gemini.py`에 남는 것: `SAFETY_SETTINGS`, `temperature=0`, `THINKING_CONFIG`, `IMAGE_CONFIG`, `INPUT_ASPECT_IMAGE_CONFIG`, `MAX_RETRIES`, `RETRY_DELAY`, `build_response_config`.

## 골든 parts 테스트

`tests/test_golden_parts.py`와 `tests/golden/` 아래 스텝별 골든 파일.

측정 대상은 `send()`가 받은 `parts`와 `config`다. 생성된 이미지는 비교하지 않는다. 이미지 모델은 temperature 0에서도 실행마다 다른 픽셀을 내놓으므로 골든으로 잡을 수 있는 값이 아니다.

기록 형식:

- 텍스트 파트: 길이와 SHA-256. 해시만 있으면 깨졌을 때 무엇이 달라졌는지 안 보이고, 15,216자를 통째로 커밋하면 프롬프트 수정 때마다 골든 diff가 프롬프트 diff와 중복된다.
- PIL 이미지 파트: `mode`, `size`, `tobytes()`의 SHA-256. **경로가 아니라 픽셀을 해시한다.** `ImageHandler.load`가 `Image.open(path).convert("RGB")`를 수행하고 이 함수가 `services/utils/images.py`로 이동하므로, 이동 중 `convert("RGB")`가 빠지거나 리사이즈가 끼어들면 SDK가 인코딩하는 바이트가 달라진다. 경로만 기록한 골든은 이를 통과시킨다.
- genai `Part` 파트: `mime_type`과 `image_bytes`의 SHA-256. 앞 서비스 생성 이미지는 `Part.from_bytes`로 재인코딩 없이 감싸지며, 재인코딩이 없다는 것 자체가 지켜야 할 성질이다.
- config: `response_modalities`, `response_mime_type`, `response_schema` 이름, `temperature`, `thinking_level`, `image_config`의 `image_size`와 `aspect_ratio`. config가 `None`이면 `None`으로 기록한다.

fixture는 `tests/fixtures/` 아래 결정적인 작은 이미지로 만든다. 실제 신발 사진에 의존하지 않는다.

골든은 재구조화 **전에**, 커밋 `cbb35a5` 시점의 코드로 생성해 커밋한다. 재구조화 후 같은 fixture가 동일한 골든을 만들어야 한다. 골든이 깨지면 그 자리에서 멈춘다.

## 코드 이동 대응표

| 현재 | 이후 |
|---|---|
| `core/pipeline.py` 세션·재시도·히스토리 | `services/engine.py` |
| `core/pipeline.py` `_resolve_model_subdir`, `_derive_model_name`, `_run_for_each`, `_pair_labels_with_images`, `_references_for` | `services/color_pattern/photo_input.py` (`shoe` 명명으로 변경) |
| `core/pipeline.py` `_run_step` 플래그 분기 | 각 스텝 파일의 `run` 함수 |
| `core/_parts_builder.py` | 각 스텝 파일의 parts 조립 |
| `core/_parts_builder.py`의 `GUIDE_LABEL` | `color_pattern/photo_input.py` (값 불변) |
| `core/models.py` `StepResponse` | `services/engine.py` |
| `core/models.py` `StepResult`, `PipelineResult` | 삭제 |
| `services/gemini_client.py` | `services/engine.py` |
| `handlers/output_handler.py` | `services/engine.py` |
| `handlers/image_handler.py` `load`, `list_image_files`, `LABEL_FORMAT`, `find_guideline`, `is_guideline_file` | `services/utils/images.py` |
| `handlers/image_handler.py` `build_parts`, `build_labeled_parts`, `_select_entries`, `_load_dir_images` | `services/color_pattern/photo_input.py` (모드 추측 제거) |
| `config/gemini_config.py` `MODEL_NAME` | 각 `service.py`의 `MODEL` |
| `config/gemini_config.py` 나머지 | `config/gemini.py` |
| `config/prompts.py` `PART_SURVEY_PROMPT`, `PATTERN_UNFOLD_PROMPT` | `services/color_pattern/prompts.py` |
| `config/prompts.py` `LINE_ART_PROMPT`, `ORIGINAL_PATTERN_LABEL` | `services/sketch_pattern/prompts.py` |
| `config/prompts.py` `PIPELINE_STEPS` | 삭제 |
| `config/survey_schema.py` | `services/color_pattern/schema.py` |
| `utils/cli.py` `VIEW_FLAGS` | `services/color_pattern/photo_input.py` |
| `utils/cli.py` 뷰·이미지 플래그 파싱 | 삭제 |
| `utils/cli.py` `derive_run_label`, `resolve_run_label_from_path` | `scripts/` 공용 |
| `utils/logging_utils.py` | 유지 |
| `main.py` | `scripts/run_all.py` |

## 검증 경계

- 에이전트는 Gemini API를 호출하지 않는다. 모든 테스트는 스텁 클라이언트를 쓴다.
- 에이전트는 생성 이미지의 내용이나 시각 품질을 판정하지 않는다.
- 프롬프트 텍스트가 바뀌지 않았음은 골든의 길이·해시로 확인한다. 사람이 읽어 판정하지 않는다.
- 실제 API를 호출하는 최종 확인은 사람이 한다.

## 수용 기준

1. `uv run python -m unittest discover -s tests -q`가 통과한다.
2. `tests/test_golden_parts.py`가 재구조화 전후로 동일한 골든을 만든다. 골든 파일은 재구조화 커밋에서 변경되지 않는다.
3. `config/prompts.py`의 세 프롬프트 문자열이 이동 후에도 바이트 단위로 동일하다. 골든의 텍스트 해시로 확인한다.
4. `PIPELINE_STEPS` dict와 그 14개 키가 저장소에서 사라진다.
5. `core/` 디렉터리와 `main.py`가 사라진다.
6. `grep -rn "MODEL_NAME" config services`가 결과를 내지 않는다.
7. `scripts/run_service.py color_pattern --input <신발 폴더>`가 스텁 클라이언트로 두 스텝을 순서대로 실행한다.
8. `scripts/run_service.py sketch_pattern --input <컬러 패턴 파일>`이 스텁 클라이언트로 한 스텝을 실행하며, 신발 사진을 전혀 요구하지 않는다.
9. `inputs/photos/<신발>/`이 없거나 인식 가능한 뷰 파일이 없으면 `color_pattern`이 API 호출 전에 예외를 던진다. 이를 검증하는 테스트가 있다.
10. Step 1 응답이 `Survey` 스키마를 위반하면 그 자리에서 예외가 난다. 이를 검증하는 테스트가 있다.
11. `color_pattern`과 `sketch_pattern`이 서로 다른 채팅 세션을 쓴다. 이를 검증하는 테스트가 있다.
12. 스텝 이름이 박힌 테스트 파일명(`test_no_prev_texts_in_step3.py`, `test_run_step3_on_color_patterns.py`)이 서비스 이름으로 바뀐다.

## 위험과 대응

### 프롬프트 이동 중 문자열이 변형됨

가장 큰 위험이다. 27,000자가 넘는 문자열 두 개를 파일 사이로 옮긴다. 편집기나 스크립트가 줄바꿈이나 공백을 건드리면 모델 출력이 달라지고 원인 추적이 어렵다.

대응: 골든의 텍스트 길이와 해시가 이를 잡는다. 이동은 파일 재작성이 아니라 잘라 붙이기로 수행한다.

### 세션이 두 개가 되면서 히스토리 저장이 누락됨

현재 `Pipeline.run`이 `fresh_session` 시점에 `_history_archive`로 이전 세션의 턴을 보관한다. 서비스가 각자 세션을 열면 이 로직의 소유자가 바뀐다.

대응: `tests/test_pipeline_wiring.py::test_save_final_history_includes_turns_before_and_after_fresh_session`이 이미 이를 검증한다. 이 테스트를 새 구조로 옮겨 유지한다.

### `photo_input`이 엄격해지면서 기존 실행 방식이 깨짐

`inputs/photos/<신발>/`을 요구하면 지금처럼 낱개 파일을 놓고 돌리던 방식이 실패한다.

대응: 의도한 변경이다. 실패 메시지가 기대하는 폴더 경로와 인식 가능한 뷰 파일명을 그대로 알려준다.

### Step 1이 이미지 모델에서 TEXT + JSON을 반환하지 못함

`gemini-3.1-flash-image`에 `Survey` 스키마를 요구하는 조합은 아직 실제로 성공한 적이 없다. 재구조화가 이 위험을 만들지는 않았지만 해소하지도 않는다.

대응: 결정 5의 `Survey` 검증이 빈 응답과 깨진 JSON을 그 자리에서 드러낸다. 실제로 실패하면 `color_pattern`의 `MODEL`만 바꾸면 되고 `sketch_pattern`은 영향받지 않는다. 그 판단과 실행은 사람이 한다.

### 재구조화 규모가 커서 중간에 저장소가 깨진 상태로 남음

`core/` 삭제와 `main.py` 삭제를 포함한다.

대응: 골든 테스트를 먼저 커밋하고, 이후 각 이동 단위마다 전체 테스트를 돌린다. 브랜치는 분리하지 않고 `safe-region-selection`에서 계속한다.
