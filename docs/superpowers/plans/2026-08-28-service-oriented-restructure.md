# 서비스 단위 폴더 재구조화 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**PRD:** `/Users/rio/Shoe-Image-To-Pattern/.worktrees/safe-region-selection/docs/superpowers/specs/2026-08-28-service-oriented-restructure-design.md`

**Spec:** `docs/superpowers/specs/2026-08-28-service-oriented-restructure-design.md`

**Goal:** 스텝 dict 플래그로 구동되는 범용 파이프라인을 도메인 산출물 기준 두 서비스(`color_pattern`, `sketch_pattern`)로 분해하고, 그 과정에서 Gemini로 나가는 요청이 한 바이트도 변하지 않았음을 골든 테스트로 증명한다.

**Architecture:** 서비스 경계가 채팅 세션 경계와 일치한다. `color_pattern`은 세션 하나를 열어 스텝 두 개를 순서대로 돌리고, `sketch_pattern`은 자기 세션을 새로 연다. 스텝은 베이스 클래스 없는 함수 하나이며 자신이 직접 `session.send()`를 부른다. 공용 엔진은 세션 생성·재시도·저장·히스토리 아카이브만 제공한다. 서비스 간 핸드오프는 파일 경로다.

**Tech Stack:** Python 3, `google-genai`, `pydantic`, `Pillow`, `unittest`(pytest 아님), `uv`

## Global Constraints

- 테스트 실행 명령은 `uv run python -m unittest discover -s tests -q`이다. pytest를 쓰지 않는다.
- 작업 디렉터리는 `/Users/rio/Shoe-Image-To-Pattern/.worktrees/safe-region-selection`이다. 이곳은 git worktree이므로 원본 저장소 루트로 `cd` 하지 않는다.
- 브랜치는 `safe-region-selection`이다. 새 브랜치를 만들지 않는다.
- 절대 `git stash` / `git stash pop`을 쓰지 않는다. stash 스택이 다른 worktree와 공유된다.
- **프롬프트 문자열을 한 글자도 바꾸지 않는다.** `PART_SURVEY_PROMPT`, `PATTERN_UNFOLD_PROMPT`, `LINE_ART_PROMPT`는 잘라 붙이기로만 이동한다. 파일을 다시 타이핑하거나 포매터를 돌리지 않는다.
- 라벨 문자열 `"[{label}]"`과 뷰 라벨(`"바깥쪽 측면(lateral)"`, `"안쪽 측면(medial)"`, `"앞쪽에서 본 모습(front)"`, `"뒤쪽에서 본 모습(heel)"`, `"위에서 본 모습(top)"`, `"바닥(bottom)"`)은 프롬프트가 그대로 지칭한다. 값을 바꾸지 않는다.
- 라벨 상수 `ORIGINAL_PATTERN_LABEL = "원본 컬러 패턴"`의 값을 바꾸지 않는다.
- 모델 이름 값은 두 서비스 모두 `"gemini-3.1-flash-image"`로 지금과 동일하게 둔다.
- Gemini API를 실제로 호출하지 않는다. 모든 테스트는 스텁 클라이언트를 쓴다.
- 생성 이미지의 내용이나 시각 품질을 판정하지 않는다.
- 각 태스크는 전체 테스트 통과 후 커밋한다.

## File Structure

| 파일 | 책임 |
|---|---|
| `tests/golden_parts.py` | 파트·config를 골든 레코드로 직렬화하는 헬퍼와 기록용 스텁 클라이언트 |
| `tests/golden/*.json` | 스텝별 골든 데이터. **Task 1 이후 절대 변경되지 않는다.** |
| `tests/test_golden_parts.py` | 골든 대조 테스트. 재구조화 중 이 파일은 다시 쓰이지만 골든 데이터는 그대로여야 한다 |
| `services/utils/images.py` | 저수준 이미지 유틸: `load`, `list_image_files`, `find_guideline`, `is_guideline_file`, `LABEL_FORMAT`, `SUPPORTED_EXTENSIONS` |
| `config/gemini.py` | 연결·생성 설정. 모델 이름은 없다 |
| `services/engine.py` | `new_session(model)`, 재시도 `send`, 결과 저장, 히스토리 아카이브 |
| `services/color_pattern/photo_input.py` | 신발 폴더 해석, 뷰 라벨, parts 조립. 모드 추측 없음 |
| `services/color_pattern/prompts.py` | Step 1·2 프롬프트 상수 |
| `services/color_pattern/schema.py` | `Survey`, `Part`, `Marking`, `Symmetry` |
| `services/color_pattern/step_1_part_survey.py` | 부품 명세서 생성 + `Survey` 검증 |
| `services/color_pattern/step_2_pattern_unfold.py` | 컬러 패턴 생성 |
| `services/color_pattern/service.py` | `MODEL` 선언, 세션 하나로 두 스텝 실행 |
| `services/sketch_pattern/prompts.py` | `LINE_ART_PROMPT`, `ORIGINAL_PATTERN_LABEL` |
| `services/sketch_pattern/step_1_line_art.py` | 스케치 패턴 생성 |
| `services/sketch_pattern/service.py` | `MODEL` 선언, 자기 세션으로 한 스텝 실행 |
| `scripts/run_service.py` | 서비스 하나 실행 |
| `scripts/run_all.py` | 두 서비스 순차 실행, 파일 핸드오프 |
| `scripts/run_parallel.sh` | `inputs/photos/*/`를 훑어 `run_service.py`를 병렬 호출 |

---

### Task 1: 골든 parts 하네스와 골든 데이터

재구조화 이전 코드로 골든을 뜬다. 이 태스크가 끝나기 전에는 프로덕션 코드를 한 줄도 건드리지 않는다.

**Files:**
- Create: `tests/golden_parts.py`
- Create: `tests/test_golden_parts.py`
- Create: `tests/golden/color_pattern__step_1_part_survey.json` (생성됨)
- Create: `tests/golden/color_pattern__step_2_pattern_unfold.json` (생성됨)
- Create: `tests/golden/sketch_pattern__step_1_line_art.json` (생성됨)

**Interfaces:**
- Consumes: 없음
- Produces:
  - `tests/golden_parts.py`의 `describe_part(part) -> dict`
  - `describe_config(config) -> dict | None`
  - `RecordingClient(responses)` — `.calls: list[dict]`, `.start_chat_call_count: int`
  - `assert_golden(testcase, name: str, calls: list[dict]) -> None`
  - `make_fixture_photos(dir: Path) -> list[tuple[str, Path]]`
  - `make_fixture_guide(dir: Path) -> Path`
  - `make_fixture_color_pattern(dir: Path) -> Path`

- [ ] **Step 1: 골든 헬퍼를 작성한다**

`tests/golden_parts.py`:

```python
"""골든 parts 하네스.

Gemini로 나가는 요청을 재구조화 전후로 비교하기 위한 직렬화 도구.
생성된 이미지는 비교하지 않는다 — 이미지 모델은 temperature 0에서도
실행마다 다른 픽셀을 내놓으므로 골든으로 잡을 수 있는 값이 아니다.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from PIL import Image as PILImage

GOLDEN_DIR = Path(__file__).parent / "golden"

# 골든을 다시 쓰려면 GOLDEN_UPDATE=1로 실행한다.
# 재구조화 중에는 절대 켜지 않는다. 켜면 회귀가 조용히 골든으로 덮인다.
UPDATE = os.environ.get("GOLDEN_UPDATE") == "1"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def describe_part(part) -> dict:
    """파트 하나를 골든 레코드로 만든다.

    이미지는 경로가 아니라 픽셀을 해시한다. load()가 convert("RGB")를
    수행하므로, 이동 중 그것이 빠지거나 리사이즈가 끼어들면 SDK가
    인코딩하는 바이트가 달라진다. 경로만 기록하면 그걸 통과시킨다.
    """
    if isinstance(part, str):
        return {"kind": "text", "len": len(part), "sha256": _sha(part.encode("utf-8"))}

    if isinstance(part, PILImage.Image):
        return {
            "kind": "pil",
            "mode": part.mode,
            "size": list(part.size),
            "sha256": _sha(part.tobytes()),
        }

    inline = getattr(part, "inline_data", None)
    data = getattr(inline, "data", None) if inline is not None else None
    mime = getattr(inline, "mime_type", None) if inline is not None else None
    if data is None:
        data = getattr(part, "image_bytes", None)
        mime = getattr(part, "mime_type", None)
    if data is not None:
        return {"kind": "bytes", "mime_type": mime, "sha256": _sha(data)}

    raise TypeError(f"골든에 기록할 수 없는 파트 타입입니다: {type(part).__name__}")


def describe_config(config) -> dict | None:
    """GenerateContentConfig를 골든 레코드로 만든다. None이면 None."""
    if config is None:
        return None
    image_config = getattr(config, "image_config", None)
    schema = getattr(config, "response_schema", None)
    thinking = getattr(config, "thinking_config", None)
    modalities = getattr(config, "response_modalities", None)
    return {
        "response_modalities": list(modalities) if modalities else None,
        "response_mime_type": getattr(config, "response_mime_type", None),
        "response_schema": getattr(schema, "__name__", None),
        "temperature": getattr(config, "temperature", None),
        "thinking_level": getattr(thinking, "thinking_level", None),
        "image_config": None if image_config is None else {
            "image_size": image_config.image_size,
            "aspect_ratio": image_config.aspect_ratio,
        },
    }


class RecordingClient:
    """send()가 받은 것을 골든 레코드로 남기는 스텁 클라이언트."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls: list[dict] = []
        self.start_chat_call_count = 0
        self._history: list = []

    def start_chat(self):
        self.start_chat_call_count += 1
        self._history = []

    @property
    def chat_history(self):
        return self._history

    def _format_parts_for_log(self, parts):
        return ""

    def _format_chat_history_for_log(self):
        return ""

    def send(self, parts, config=None):
        self.calls.append({
            "parts": [describe_part(p) for p in parts],
            "config": describe_config(config),
        })
        response = self._responses.pop(0)
        self._history.append(f"turn:{response.text}")
        return response


def assert_golden(testcase, name: str, call: dict) -> None:
    """골든 파일과 대조한다. GOLDEN_UPDATE=1이면 파일을 쓴다."""
    GOLDEN_DIR.mkdir(exist_ok=True)
    path = GOLDEN_DIR / f"{name}.json"
    serialized = json.dumps(call, ensure_ascii=False, indent=2, sort_keys=True)

    if UPDATE:
        path.write_text(serialized + "\n", encoding="utf-8")
        return

    testcase.assertTrue(
        path.exists(),
        f"골든 파일이 없습니다: {path}. GOLDEN_UPDATE=1로 한 번 생성하세요.",
    )
    expected = json.loads(path.read_text(encoding="utf-8"))
    testcase.assertEqual(
        expected, call,
        f"\n{name}의 API 요청이 골든과 다릅니다.\n"
        f"재구조화가 Gemini로 나가는 바이트를 바꿨습니다. 여기서 멈추세요.",
    )


# ── fixture ────────────────────────────────────────────────────────────────
# 실제 신발 사진에 의존하지 않는 결정적인 작은 이미지.
# PNG RGB 왕복은 무손실이므로 매 실행 같은 픽셀이 나온다.

_VIEW_LABELS = (
    ("lateral", "바깥쪽 측면(lateral)"),
    ("medial", "안쪽 측면(medial)"),
    ("front", "앞쪽에서 본 모습(front)"),
    ("heel", "뒤쪽에서 본 모습(heel)"),
    ("top", "위에서 본 모습(top)"),
)


def make_fixture_photos(directory: Path) -> list[tuple[str, Path]]:
    """(라벨, 경로) 쌍을 뷰 순서대로 만든다."""
    directory.mkdir(parents=True, exist_ok=True)
    pairs = []
    for index, (name, label) in enumerate(_VIEW_LABELS):
        path = directory / f"{name}.png"
        PILImage.new("RGB", (6, 6), (index * 31, index * 17, index * 43)).save(path)
        pairs.append((label, path))
    return pairs


def make_fixture_guide(directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "가이드라인_fixture.png"
    PILImage.new("RGB", (8, 8), (250, 250, 250)).save(path)
    return path


def make_fixture_color_pattern(directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "fixture_color.png"
    PILImage.new("RGB", (10, 15), (200, 30, 30)).save(path)
    return path
```

- [ ] **Step 2: 현재 코드로 세 스텝을 돌려 골든을 대조하는 테스트를 작성한다**

`tests/test_golden_parts.py`:

```python
"""재구조화 전후로 Gemini가 받는 것이 동일한지 검증한다.

이 파일 자체는 재구조화 때 다시 쓰인다. 호출 진입점이 Pipeline에서
서비스 함수로 바뀌기 때문이다. 그러나 tests/golden/*.json은
한 바이트도 바뀌면 안 된다.
"""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from PIL import Image

import core.pipeline as pipeline_module
from config.prompts import PIPELINE_STEPS
from core.models import StepResponse
from core.pipeline import Pipeline
from tests.golden_parts import (
    RecordingClient,
    assert_golden,
    make_fixture_color_pattern,
    make_fixture_guide,
    make_fixture_photos,
)


class GoldenPartsTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.out = self.tmp / "out"

    def _run_pipeline(self, color_pattern_image):
        photos = make_fixture_photos(self.tmp / "photos")
        guide = make_fixture_guide(self.tmp / "guides")

        steps = [dict(s) for s in PIPELINE_STEPS]
        steps[0]["image_path"] = None
        steps[0]["view_images"] = photos
        steps[1]["guide_image_path"] = guide

        client = RecordingClient([
            StepResponse(text='{"분석대상짝": "왼발"}', images=[]),
            StepResponse(text="", images=[color_pattern_image]),
            StepResponse(text="", images=[Image.new("RGB", (4, 4))]),
        ])
        with patch.object(pipeline_module, "GeminiClient", lambda *a, **k: client), \
             patch.object(pipeline_module.OutputHandler, "save_step"), \
             patch.object(pipeline_module.OutputHandler, "save_final"):
            Pipeline(steps=steps, output_dir=self.out, run_label="golden").run(
                skip_initial_selection=True
            )
        return client.calls

    def test_golden_color_pattern_step_1(self):
        calls = self._run_pipeline(Image.new("RGB", (10, 15), (200, 30, 30)))
        assert_golden(self, "color_pattern__step_1_part_survey", calls[0])

    def test_golden_color_pattern_step_2(self):
        calls = self._run_pipeline(Image.new("RGB", (10, 15), (200, 30, 30)))
        assert_golden(self, "color_pattern__step_2_pattern_unfold", calls[1])

    def test_golden_sketch_pattern_step_1(self):
        color = Image.open(make_fixture_color_pattern(self.tmp / "patterns")).convert("RGB")
        calls = self._run_pipeline(color)
        assert_golden(self, "sketch_pattern__step_1_line_art", calls[2])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: 골든이 없으므로 실패하는 것을 확인한다**

Run: `uv run python -m unittest tests.test_golden_parts -v`
Expected: 세 테스트 모두 FAIL, 메시지에 "골든 파일이 없습니다"

- [ ] **Step 4: 골든을 생성한다**

Run: `GOLDEN_UPDATE=1 uv run python -m unittest tests.test_golden_parts -q`
그 다음 `cat tests/golden/color_pattern__step_1_part_survey.json`으로 내용을 눈으로 확인한다.

기대값 확인 포인트 — 아래와 다르면 fixture 배선이 잘못된 것이므로 멈춘다:
- `color_pattern__step_1_part_survey`: 파트 11개(라벨 텍스트 5 + 이미지 5 + 프롬프트 1), 마지막 텍스트 파트 `len`이 11777, config의 `response_modalities`가 `["TEXT"]`, `response_mime_type`이 `"application/json"`, `response_schema`가 `"Survey"`
- `color_pattern__step_2_pattern_unfold`: 파트 8개, 마지막 텍스트 파트 `len`이 15216, config가 `null`
- `sketch_pattern__step_1_line_art`: 파트 3개 — 첫 파트가 `"[원본 컬러 패턴]"`의 해시(len 10), 두 번째가 이미지, 세 번째가 프롬프트. config가 `null`

- [ ] **Step 5: 골든 없이 다시 돌려 통과를 확인한다**

Run: `uv run python -m unittest discover -s tests -q`
Expected: OK, 167 tests

- [ ] **Step 6: 골든이 실제로 회귀를 잡는지 확인한다 (뮤테이션)**

`config/prompts.py`의 `ORIGINAL_PATTERN_LABEL` 값을 `"원본 컬러 패턴 "`(끝에 공백)으로 잠시 바꾼다.

Run: `uv run python -m unittest tests.test_golden_parts -q`
Expected: `test_golden_sketch_pattern_step_1`이 FAIL

값을 원래대로 되돌리고 다시 돌려 OK를 확인한다. 되돌리는 것을 잊지 않는다.

- [ ] **Step 7: 커밋**

```bash
git add tests/golden_parts.py tests/test_golden_parts.py tests/golden/
git commit -m "test: 재구조화 전 API 요청 골든 캡처

Gemini로 나가는 parts와 config를 스텝별로 직렬화해 커밋한다.
생성 이미지는 비교하지 않는다 - 이미지 모델은 temperature 0에서도
실행마다 다른 픽셀을 내놓는다.

입력 이미지는 경로가 아니라 픽셀을 해시한다. load()의 convert(RGB)가
서비스 재구조화 중 이동하는데, 그 과정에서 빠지거나 리사이즈가
끼어들면 SDK가 인코딩하는 바이트가 달라진다."
```

---

### Task 2: `services/utils/images.py` 추출

`ImageHandler`에서 두 서비스가 실제로 공유하는 저수준 함수만 뽑는다. 근거: `scripts/run_step3_on_color_patterns.py`가 `list_image_files`·`load`·`LABEL_FORMAT` 세 개만 쓴다.

**Files:**
- Create: `services/utils/__init__.py`
- Create: `services/utils/images.py`
- Create: `tests/test_services_utils_images.py`
- Modify: `handlers/image_handler.py` — 옮긴 함수를 `services.utils.images`로 위임

**Interfaces:**
- Consumes: 없음
- Produces:
  - `services.utils.images.LABEL_FORMAT: str = "[{label}]"`
  - `SUPPORTED_EXTENSIONS: set[str]`
  - `GUIDELINE_KEYWORDS: tuple[str, ...]`
  - `load(image_path: Path | str) -> PIL.Image.Image`
  - `is_guideline_file(path: Path) -> bool`
  - `list_image_files(folder: Path, exclude_guideline: bool = False) -> list[Path]`
  - `find_guideline(folder: Path) -> Path | None`
  - `label(text: str) -> str` — `LABEL_FORMAT.format(label=text)`의 축약

- [ ] **Step 1: 실패하는 테스트를 작성한다**

`tests/test_services_utils_images.py`:

```python
"""services/utils/images.py 저수준 이미지 유틸 테스트."""

import tempfile
import unittest
from pathlib import Path

from PIL import Image

from services.utils import images


class ImagesUtilTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)

    def test_load_converts_to_rgb(self):
        """load()는 반드시 RGB로 변환한다. 이게 빠지면 SDK가 인코딩하는
        바이트가 달라지고 골든이 깨진다."""
        path = self.tmp / "gray.png"
        Image.new("L", (4, 4), 128).save(path)
        self.assertEqual(images.load(path).mode, "RGB")

    def test_load_does_not_resize(self):
        path = self.tmp / "a.png"
        Image.new("RGB", (7, 11), (1, 2, 3)).save(path)
        self.assertEqual(images.load(path).size, (7, 11))

    def test_load_missing_file_raises(self):
        with self.assertRaises(FileNotFoundError):
            images.load(self.tmp / "없음.png")

    def test_load_unsupported_extension_raises(self):
        path = self.tmp / "a.txt"
        path.write_text("x")
        with self.assertRaises(ValueError):
            images.load(path)

    def test_is_guideline_file_matches_korean_and_english(self):
        self.assertTrue(images.is_guideline_file(Path("가이드라인_회전5도.png")))
        self.assertTrue(images.is_guideline_file(Path("GUIDELINE.png")))
        self.assertFalse(images.is_guideline_file(Path("lateral.png")))

    def test_list_image_files_can_exclude_guideline(self):
        for name in ("lateral.png", "medial.png", "가이드라인.png"):
            Image.new("RGB", (2, 2)).save(self.tmp / name)
        (self.tmp / "notes.txt").write_text("x")

        every = images.list_image_files(self.tmp)
        without = images.list_image_files(self.tmp, exclude_guideline=True)

        self.assertEqual(len(every), 3)
        self.assertEqual([p.name for p in without], ["lateral.png", "medial.png"])

    def test_find_guideline_returns_the_guideline_file(self):
        for name in ("lateral.png", "가이드라인.png"):
            Image.new("RGB", (2, 2)).save(self.tmp / name)
        found = images.find_guideline(self.tmp)
        self.assertIsNotNone(found)
        self.assertEqual(found.name, "가이드라인.png")

    def test_label_wraps_in_brackets(self):
        self.assertEqual(images.label("바깥쪽 측면(lateral)"), "[바깥쪽 측면(lateral)]")
        self.assertEqual(images.LABEL_FORMAT, "[{label}]")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 실패를 확인한다**

Run: `uv run python -m unittest tests.test_services_utils_images -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'services.utils'`

- [ ] **Step 3: 함수를 옮긴다**

`services/utils/__init__.py`는 빈 파일로 만든다.

`services/utils/images.py`에 `handlers/image_handler.py`의 다음 멤버를 **잘라내어** 모듈 수준 함수·상수로 옮긴다. 본문은 그대로 두고 `ImageHandler.` 접두사만 제거한다.

- `SUPPORTED_EXTENSIONS`, `GUIDELINE_KEYWORDS`, `LABEL_FORMAT` (주석 포함)
- `is_guideline_file`, `list_image_files`, `find_guideline`, `load`

추가로 `label` 축약 함수를 만든다:

```python
def label(text: str) -> str:
    """이미지 앞에 붙는 라벨 텍스트 파트를 만든다."""
    return LABEL_FORMAT.format(label=text)
```

`handlers/image_handler.py`는 이 태스크에서 삭제하지 않는다. 남은 메서드가 계속 동작하도록 클래스 속성을 새 모듈로 위임한다:

```python
from services.utils import images as _images

class ImageHandler:
    SUPPORTED_EXTENSIONS = _images.SUPPORTED_EXTENSIONS
    GUIDELINE_KEYWORDS = _images.GUIDELINE_KEYWORDS
    LABEL_FORMAT = _images.LABEL_FORMAT

    is_guideline_file = staticmethod(_images.is_guideline_file)
    list_image_files = staticmethod(_images.list_image_files)
    find_guideline = staticmethod(_images.find_guideline)
    load = staticmethod(_images.load)
```

`handlers/image_handler.py`가 `services.gemini_client`를 import 하지 않으므로 순환참조는 생기지 않는다. 확인만 하고 넘어간다.

- [ ] **Step 4: 새 테스트와 전체 테스트를 돌린다**

Run: `uv run python -m unittest discover -s tests -q`
Expected: OK. 골든 세 개가 그대로 통과해야 한다 — `load`의 `convert("RGB")`가 유지됐다는 증거다.

- [ ] **Step 5: 커밋**

```bash
git add services/utils/ handlers/image_handler.py tests/test_services_utils_images.py
git commit -m "refactor: 저수준 이미지 유틸을 services/utils/images.py로 추출

두 서비스가 실제로 공유하는 것만 뽑았다. run_step3_on_color_patterns.py가
list_image_files, load, LABEL_FORMAT 세 개만 쓰는 것이 근거다.
build_parts 계열의 모드 추측 로직은 신발 사진 전용이므로 남겨둔다."
```

---

### Task 3: `config/gemini.py`와 모델 이름 제거

**Files:**
- Create: `config/gemini.py` (`config/gemini_config.py`의 내용에서 `MODEL_NAME` 제외)
- Modify: `config/gemini_config.py` — `config.gemini`를 재수출하는 얇은 shim으로 축소 (`MODEL_NAME`은 유지)
- Create: `tests/test_gemini_config_module.py`

**Interfaces:**
- Consumes: 없음
- Produces: `config.gemini`의 `SAFETY_SETTINGS`, `IMAGE_CONFIG`, `INPUT_ASPECT_IMAGE_CONFIG`, `THINKING_CONFIG`, `RESPONSE_MODALITIES`, `CHAT_CONFIG`, `MAX_RETRIES`, `RETRY_DELAY`, `build_response_config(modalities, response_schema=None, match_input_aspect_ratio=False)`

- [ ] **Step 1: 실패하는 테스트를 작성한다**

`tests/test_gemini_config_module.py`:

```python
"""config/gemini.py가 모델 이름을 담지 않는지 확인한다."""

import unittest

from config import gemini


class GeminiConfigModuleTest(unittest.TestCase):
    def test_module_has_no_model_name(self):
        """모델 선택은 서비스 단위 설정이다. 전역 상수로 두면 스케치 실험이
        color_pattern까지 끌고 간다."""
        self.assertFalse(hasattr(gemini, "MODEL_NAME"))

    def test_chat_config_keeps_current_values(self):
        self.assertEqual(list(gemini.CHAT_CONFIG.response_modalities), ["IMAGE"])
        self.assertEqual(gemini.CHAT_CONFIG.image_config.image_size, "4K")
        self.assertEqual(gemini.CHAT_CONFIG.image_config.aspect_ratio, "2:3")
        self.assertEqual(gemini.CHAT_CONFIG.temperature, 0)
        self.assertEqual(gemini.CHAT_CONFIG.thinking_config.thinking_level, "HIGH")

    def test_build_response_config_returns_none_without_overrides(self):
        self.assertIsNone(gemini.build_response_config(None))

    def test_retry_settings_present(self):
        self.assertEqual(gemini.MAX_RETRIES, 3)
        self.assertEqual(gemini.RETRY_DELAY, 2.0)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 실패를 확인한다**

Run: `uv run python -m unittest tests.test_gemini_config_module -v`
Expected: FAIL — `ImportError: cannot import name 'gemini'`

- [ ] **Step 3: 파일을 나눈다**

`config/gemini_config.py`의 내용을 `config/gemini.py`로 통째로 옮기되 `MODEL_NAME` 상수와 그 주석 블록만 제외한다.

`config/gemini_config.py`는 아직 `services/gemini_client.py`가 참조하므로 shim으로 남긴다:

```python
"""config/gemini.py로 이동 중인 shim. Task 9에서 삭제된다."""

from config.gemini import *  # noqa: F401,F403
from config.gemini import (  # noqa: F401
    CHAT_CONFIG,
    IMAGE_CONFIG,
    INPUT_ASPECT_IMAGE_CONFIG,
    MAX_RETRIES,
    RESPONSE_MODALITIES,
    RETRY_DELAY,
    SAFETY_SETTINGS,
    THINKING_CONFIG,
    build_response_config,
)

MODEL_NAME = "gemini-3.1-flash-image"
```

- [ ] **Step 4: 전체 테스트를 돌린다**

Run: `uv run python -m unittest discover -s tests -q`
Expected: OK. 골든이 그대로여야 한다 — config 값이 하나도 변하지 않았다는 증거다.

- [ ] **Step 5: 커밋**

```bash
git add config/gemini.py config/gemini_config.py tests/test_gemini_config_module.py
git commit -m "refactor: config/gemini.py를 분리하고 MODEL_NAME을 뺀다

chats.create(model=...)가 세션 생성 시점에 모델을 고정하므로 모델은
서비스 단위 설정이다. gemini_config.py는 Task 9까지 shim으로 남긴다."
```

---

### Task 4: `services/engine.py`

세션 생성·재시도·저장·히스토리 아카이브만 담는다. 입력 준비는 여기 없다.

**Files:**
- Create: `services/engine.py`
- Create: `tests/test_engine.py`

**Interfaces:**
- Consumes: `config.gemini` (Task 3)
- Produces:
  - `services.engine.StepResponse` — `core.models.StepResponse`를 그대로 옮긴 dataclass. 필드 `text: str = ""`, `images: list = field(default_factory=list)`
  - `Session` — `.send(parts, config=None) -> StepResponse`, `.history -> list`
  - `new_session(model: str) -> Session`
  - `RunOutput(out_dir: Path, label: str)` — `.save_step(service: str, step: int, name: str, description: str, prompt: str, response: str, generated_images: list) -> Path`, `.save_final(text, generated_images, chat_history) -> Path`, `.service_dir(service: str) -> Path`, `.run_dir -> Path`
  - `HistoryArchive` — `.extend(turns)`, `.all() -> list`

- [ ] **Step 1: 실패하는 테스트를 작성한다**

`tests/test_engine.py`:

```python
"""services/engine.py 세션·저장·히스토리 테스트."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from PIL import Image

from services import engine


class NewSessionTest(unittest.TestCase):
    def test_new_session_passes_the_given_model(self):
        """모델은 서비스가 정한다. 엔진이 고정 상수를 쓰면 안 된다."""
        with patch.object(engine, "genai") as mock_genai:
            engine.new_session("some-model")
        kwargs = mock_genai.Client.return_value.chats.create.call_args.kwargs
        self.assertEqual(kwargs["model"], "some-model")

    def test_send_retries_then_raises(self):
        with patch.object(engine, "genai") as mock_genai, \
             patch.object(engine.time, "sleep"):
            chat = mock_genai.Client.return_value.chats.create.return_value
            chat.send_message.side_effect = RuntimeError("boom")
            session = engine.new_session("m")
            with self.assertRaises(RuntimeError):
                session.send(["hi"])
        self.assertEqual(chat.send_message.call_count, engine.MAX_RETRIES)


class RunOutputTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)

    def test_save_step_writes_under_the_service_folder(self):
        """스텝 번호는 서비스 폴더 안에서 1부터 다시 매긴다."""
        out = engine.RunOutput(self.tmp, "run1")
        path = out.save_step(
            service="sketch_pattern", step=1, name="line_art",
            description="스케치", prompt="p", response="r",
            generated_images=[Image.new("RGB", (2, 2))],
        )
        self.assertEqual(path.parent.name, "sketch_pattern")
        self.assertEqual(path.name, "step_1_line_art.md")
        self.assertTrue(
            (self.tmp / "run1" / "sketch_pattern" / "step_1_line_art_generated_01.png").exists()
        )

    def test_run_dir_is_not_created_until_a_save(self):
        engine.RunOutput(self.tmp, "run2")
        self.assertFalse((self.tmp / "run2").exists())


class HistoryArchiveTest(unittest.TestCase):
    def test_archive_keeps_turns_from_every_session(self):
        """서비스마다 세션이 다르므로, 합쳐두지 않으면 앞 서비스의 턴이
        chat_history.json에서 사라진다."""
        archive = engine.HistoryArchive()
        archive.extend(["a", "b"])
        archive.extend(["c"])
        self.assertEqual(archive.all(), ["a", "b", "c"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 실패를 확인한다**

Run: `uv run python -m unittest tests.test_engine -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'services.engine'`

- [ ] **Step 3: 엔진을 만든다**

`services/gemini_client.py`의 `GeminiClient` 본문을 `services/engine.py`로 옮기고 다음만 바꾼다.

- `__init__`이 모델을 받지 않고, `new_session(model)`이 `genai.Client(api_key=get_api_key())`와 `client.chats.create(model=model, config=CHAT_CONFIG)`를 수행해 `Session`을 반환한다.
- `send`, `_parse_response`, `_flatten_parts`, `_format_parts_for_log`, `_format_chat_history_for_log`, 파트 sanitize 로직(`Part.from_bytes` 감싸기 포함)은 **그대로** 옮긴다. sanitize를 손대면 골든이 깨진다.
- `Session.history` 프로퍼티가 기존 `chat_history`를 대신한다.

`core/models.py`의 `StepResponse` dataclass를 `services/engine.py`로 옮긴다. `StepResult`와 `PipelineResult`는 옮기지 않는다 — Task 9에서 `core/`와 함께 삭제된다.

`handlers/output_handler.py`의 `OutputHandler`를 `RunOutput`으로 옮기며 다음만 바꾼다.

- `save_step`이 `service: str`을 첫 인자로 받고 `self._run_dir / service`에 쓴다. 그 폴더를 만든다.
- 파일명이 `f"step_{step}_{safe_name}.md"`, 이미지가 `f"step_{step}_{safe_name}_generated_{idx:02d}.png"`. **`step:02d`가 아니라 `step`이다** — 서비스 안에서 한 자리로 충분하다.
- `image_path` 인자를 없앤다. 마크다운의 입력 이미지 줄도 함께 없앤다.
- `_run_label`을 실행 중에 바꾸는 로직(`_run_dir_created` 검사와 라벨 재설정)은 옮기지 않는다. 라벨은 스크립트가 정한다.
- `save_final`, `_serialize_history`, `_sanitize_filename`, `_ensure_run_dir`는 그대로 옮긴다.

`HistoryArchive`는 새로 만든다:

```python
class HistoryArchive:
    """서비스마다 세션이 다르므로 턴을 모아둔다."""

    def __init__(self) -> None:
        self._turns: list = []

    def extend(self, turns) -> None:
        self._turns.extend(turns)

    def all(self) -> list:
        return list(self._turns)
```

- [ ] **Step 4: 전체 테스트를 돌린다**

Run: `uv run python -m unittest discover -s tests -q`
Expected: OK. 골든이 그대로여야 한다 — 이 태스크는 아직 프로덕션 경로를 바꾸지 않는다.

- [ ] **Step 5: 커밋**

```bash
git add services/engine.py tests/test_engine.py
git commit -m "feat: services/engine.py - 세션·재시도·저장·히스토리

엔진의 책임은 네 가지뿐이다. 입력 준비는 서비스가 한다.
save_step이 service 인자를 받아 서비스 폴더에 쓰고, 스텝 번호는
서비스 안에서 1부터 다시 매긴다."
```

---

### Task 5: `services/color_pattern` 입력·프롬프트·스키마

**Files:**
- Create: `services/color_pattern/__init__.py`
- Create: `services/color_pattern/prompts.py`
- Create: `services/color_pattern/schema.py`
- Create: `services/color_pattern/photo_input.py`
- Create: `tests/test_color_pattern_photo_input.py`

**Interfaces:**
- Consumes: `services.utils.images` (Task 2)
- Produces:
  - `services.color_pattern.prompts.PART_SURVEY_PROMPT: str`, `PATTERN_UNFOLD_PROMPT: str`
  - `services.color_pattern.schema.Survey`, `Part`, `Marking`, `Symmetry`
  - `services.color_pattern.photo_input.VIEW_LABELS: tuple[tuple[str, str], ...]`
  - `resolve(shoe_dir: Path) -> list[tuple[str, Path]]` — 뷰 순서대로 (라벨, 경로). 없으면 `FileNotFoundError`
  - `build_survey_parts(photos: list[tuple[str, Path]], prompt: str) -> list`
  - `build_unfold_parts(photos, guide_path, survey_text, prompt) -> list`

- [ ] **Step 1: 실패하는 테스트를 작성한다**

`tests/test_color_pattern_photo_input.py`:

```python
"""신발 사진 입력 해석 테스트. 모드 추측 없이 규약을 요구한다."""

import tempfile
import unittest
from pathlib import Path

from PIL import Image

from services.color_pattern import photo_input


class ResolveTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.shoe = Path(self._tmp.name) / "adidas_ORKETRO"
        self.shoe.mkdir()

    def _make(self, name: str):
        Image.new("RGB", (4, 4)).save(self.shoe / name)

    def test_resolve_returns_views_in_declared_order_not_file_order(self):
        """API 전송 순서는 VIEW_LABELS의 순서다. 파일 시스템 순서가 아니다."""
        self._make("top.png")
        self._make("lateral.png")
        self._make("medial.png")
        labels = [label for label, _ in photo_input.resolve(self.shoe)]
        self.assertEqual(labels, [
            "바깥쪽 측면(lateral)",
            "안쪽 측면(medial)",
            "위에서 본 모습(top)",
        ])

    def test_resolve_prefers_extensions_in_order(self):
        for ext in ("png", "webp"):
            Image.new("RGB", (4, 4)).save(self.shoe / f"lateral.{ext}")
        (_, path), = photo_input.resolve(self.shoe)
        self.assertEqual(path.suffix, ".webp")

    def test_missing_folder_raises_before_any_api_call(self):
        with self.assertRaises(FileNotFoundError):
            photo_input.resolve(self.shoe.parent / "없는신발")

    def test_folder_without_recognisable_views_raises(self):
        """낱개 파일을 놓고 돌리던 방식은 이제 실패한다. 예전에는 파일 선택
        모드로 조용히 넘어가 라벨 없는 한 장이 되었고, Step 2의 참조 사진도
        함께 사라졌다."""
        Image.new("RGB", (4, 4)).save(self.shoe / "adidas_ORKETRO_color.png")
        with self.assertRaises(FileNotFoundError) as ctx:
            photo_input.resolve(self.shoe)
        self.assertIn("lateral", str(ctx.exception))


class BuildPartsTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.shoe = self.tmp / "shoe"
        self.shoe.mkdir()
        for name in ("lateral.png", "medial.png"):
            Image.new("RGB", (4, 4)).save(self.shoe / name)
        self.guide = self.tmp / "가이드라인.png"
        Image.new("RGB", (4, 4)).save(self.guide)

    def test_survey_parts_are_label_image_pairs_then_prompt(self):
        parts = photo_input.build_survey_parts(photo_input.resolve(self.shoe), "PROMPT")
        self.assertEqual(parts[0], "[바깥쪽 측면(lateral)]")
        self.assertEqual(parts[2], "[안쪽 측면(medial)]")
        self.assertEqual(parts[-1], "PROMPT")
        self.assertEqual(len(parts), 5)

    def test_unfold_parts_are_exactly_the_eight_parts_in_order(self):
        parts = photo_input.build_unfold_parts(
            photo_input.resolve(self.shoe), self.guide, "명세서 본문", "PROMPT"
        )
        self.assertEqual(len(parts), 8)
        self.assertEqual(parts[0], "[바깥쪽 측면(lateral)]")
        self.assertEqual(parts[2], "[안쪽 측면(medial)]")
        self.assertEqual(parts[4], photo_input.GUIDE_LABEL)
        self.assertEqual(parts[6], "[Previous Step 1 Output]\n명세서 본문")
        self.assertEqual(parts[7], "PROMPT")
        self.assertEqual(sum(1 for p in parts if hasattr(p, "mode")), 3)

    def test_guide_label_value_is_unchanged(self):
        """라벨이 없으면 모델이 이 틀을 신발 사진 중 하나로 읽는다."""
        self.assertEqual(
            photo_input.GUIDE_LABEL,
            "[가이드라인] 2D 펼침 틀 — 신발 사진이 아니야",
        )

    def test_unfold_uses_only_the_two_side_views(self):
        """reference_views가 ['lateral', 'medial']인 현 동작을 유지한다."""
        Image.new("RGB", (4, 4)).save(self.shoe / "top.png")
        parts = photo_input.build_unfold_parts(
            photo_input.resolve(self.shoe), self.guide, "s", "PROMPT"
        )
        self.assertNotIn("[위에서 본 모습(top)]", [p for p in parts if isinstance(p, str)])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 실패를 확인한다**

Run: `uv run python -m unittest tests.test_color_pattern_photo_input -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'services.color_pattern'`

- [ ] **Step 3: 프롬프트와 스키마를 옮긴다**

`services/color_pattern/__init__.py`는 빈 파일로 만든다.

**주의:** 이 두 프롬프트는 아직 이름이 없다. `config/prompts.py`의 `PIPELINE_STEPS[0]["prompt"]`와 `PIPELINE_STEPS[1]["prompt"]`에 인라인 문자열 리터럴로 박혀 있다(각각 11,777자, 15,216자).

그 리터럴을 **잘라내어** `services/color_pattern/prompts.py`에 이름을 붙여 붙인다. 문자열을 다시 타이핑하지 않는다.

```python
# services/color_pattern/prompts.py
PART_SURVEY_PROMPT = """{
    ... PIPELINE_STEPS[0]["prompt"]에서 잘라온 11,777자 그대로 ...
}"""

PATTERN_UNFOLD_PROMPT = """{
    ... PIPELINE_STEPS[1]["prompt"]에서 잘라온 15,216자 그대로 ...
}"""
```

옮긴 뒤 길이를 확인한다. 다르면 잘라내기가 어긋난 것이다:

```bash
uv run python -c "
from services.color_pattern.prompts import PART_SURVEY_PROMPT, PATTERN_UNFOLD_PROMPT
assert len(PART_SURVEY_PROMPT) == 11777, len(PART_SURVEY_PROMPT)
assert len(PATTERN_UNFOLD_PROMPT) == 15216, len(PATTERN_UNFOLD_PROMPT)
print('프롬프트 길이 OK')
"
```

프롬프트를 감싸던 주석 블록도 함께 옮긴다.

`config/survey_schema.py`를 `services/color_pattern/schema.py`로 옮긴다(내용 변경 없음).

- [ ] **Step 4: `photo_input.py`를 만든다**

`utils/cli.py:VIEW_FLAGS`를 `VIEW_LABELS`라는 이름으로 옮기고 값은 그대로 둔다. 순서가 API 전송 순서라는 주석도 옮긴다.

```python
"""신발 사진 입력 해석.

inputs/photos/<신발>/ 구조를 요구한다. 폴더 내용을 보고 모드를 추측하지
않는다. 예전 build_parts는 파일이 낱개로 있으면 파일 선택 모드로 넘어가
라벨 없는 한 장을 보냈고, 그때 Step 2의 참조 사진도 함께 사라졌다.
"""

from __future__ import annotations

from pathlib import Path

from services.utils import images

# 이 튜플의 순서가 곧 API 전송 순서다. 파일 시스템 순서와 무관하다.
# 라벨 문자열은 프롬프트가 그대로 지칭하므로 바꾸면 안 된다.
VIEW_LABELS: tuple[tuple[str, str], ...] = (
    ("lateral", "바깥쪽 측면(lateral)"),
    ("medial", "안쪽 측면(medial)"),
    ("front", "앞쪽에서 본 모습(front)"),
    ("heel", "뒤쪽에서 본 모습(heel)"),
    ("top", "위에서 본 모습(top)"),
    ("bottom", "바닥(bottom)"),
)

# 같은 뷰에 여러 확장자가 있으면 이 순서로 고른다.
EXTENSIONS = ("webp", "jpg", "jpeg", "png")

# Step 2가 직접 받는 뷰. 나머지는 채팅 히스토리로만 닿는다.
UNFOLD_VIEWS = ("lateral", "medial")

# 가이드라인 이미지 앞에 붙는 라벨. core/_parts_builder.py의 GUIDE_LABEL을
# 값 그대로 옮긴 것이다. 라벨이 없으면 모델이 이 틀을 신발 사진 중 하나로 읽는다.
GUIDE_LABEL = "[가이드라인] 2D 펼침 틀 — 신발 사진이 아니야"


def resolve(shoe_dir: Path) -> list[tuple[str, Path]]:
    """<신발> 폴더에서 (라벨, 경로) 쌍을 뷰 선언 순서대로 만든다."""
    shoe_dir = Path(shoe_dir)
    if not shoe_dir.is_dir():
        raise FileNotFoundError(
            f"신발 사진 폴더가 없습니다: {shoe_dir}\n"
            f"inputs/photos/<신발>/ 아래에 뷰별 파일을 두세요."
        )

    found: list[tuple[str, Path]] = []
    for name, view_label in VIEW_LABELS:
        for ext in EXTENSIONS:
            candidate = shoe_dir / f"{name}.{ext}"
            if candidate.is_file():
                found.append((view_label, candidate))
                break

    if not found:
        expected = ", ".join(f"{n}.{{{'|'.join(EXTENSIONS)}}}" for n, _ in VIEW_LABELS)
        raise FileNotFoundError(
            f"인식 가능한 뷰 파일이 없습니다: {shoe_dir}\n"
            f"기대하는 파일명: {expected}"
        )
    return found


def build_survey_parts(photos: list[tuple[str, Path]], prompt: str) -> list:
    """[라벨, 이미지] 쌍을 뷰 순서대로 늘어놓고 끝에 프롬프트를 둔다."""
    parts: list = []
    for view_label, path in photos:
        parts.append(images.label(view_label))
        parts.append(images.load(path))
    parts.append(prompt)
    return parts


def build_unfold_parts(
    photos: list[tuple[str, Path]],
    guide_path: Path,
    survey_text: str,
    prompt: str,
) -> list:
    """측면 두 장 + 가이드라인 + 명세서 + 프롬프트, 정확히 이 순서로 8개."""
    wanted = {label for name, label in VIEW_LABELS if name in UNFOLD_VIEWS}
    parts: list = []
    for view_label, path in photos:
        if view_label in wanted:
            parts.append(images.label(view_label))
            parts.append(images.load(path))
    parts.append(GUIDE_LABEL)
    parts.append(images.load(guide_path))
    parts.append(f"[Previous Step 1 Output]\n{survey_text}")
    parts.append(prompt)
    return parts
```

**이 순서는 골든이 검증한다.** 현재 `core/_parts_builder.py`가 만드는 Step 2 파트는 다음 8개이며, 위 함수는 그것을 그대로 재현한 것이다.

| # | 내용 |
|---|---|
| 1 | `"[바깥쪽 측면(lateral)]"` |
| 2 | lateral 이미지 |
| 3 | `"[안쪽 측면(medial)]"` |
| 4 | medial 이미지 |
| 5 | `GUIDE_LABEL` |
| 6 | 가이드라인 이미지 |
| 7 | `"[Previous Step 1 Output]\n<명세서>"` |
| 8 | `PATTERN_UNFOLD_PROMPT` |

옛 코드는 이 순서를 네 단계에 나눠 만들었다. `[프롬프트]`에서 시작해 가이드를 프롬프트 앞에 끼우고, 앞 스텝에서 쓴 실물 사진을 맨 앞에 붙이고, 마지막으로 명세서를 프롬프트 앞에 끼운다. 새 함수는 결과만 같으면 된다.

- [ ] **Step 5: 테스트를 돌린다**

Run: `uv run python -m unittest tests.test_color_pattern_photo_input -v`
Expected: PASS

`config/prompts.py`는 아직 `PIPELINE_STEPS`를 노출해야 하므로(골든 테스트가 Task 6까지 그것으로 돈다) 상단에 import를 추가하고 dict의 값을 이름으로 바꾼다:

```python
from services.color_pattern.prompts import PART_SURVEY_PROMPT, PATTERN_UNFOLD_PROMPT
...
    {
        "step": 1,
        "name": "part_survey",
        ...
        "prompt": PART_SURVEY_PROMPT,
```

Run: `uv run python -m unittest discover -s tests -q`
Expected: OK. 골든은 그대로여야 한다 — 리터럴이 이름 뒤로 옮겨갔을 뿐 값이 같다는 증거다.

- [ ] **Step 6: 커밋**

```bash
git add services/color_pattern/ tests/test_color_pattern_photo_input.py config/prompts.py config/survey_schema.py
git commit -m "feat: color_pattern 서비스의 입력·프롬프트·스키마

photo_input이 inputs/photos/<신발>/ 구조를 요구하고, 없으면 API 호출
전에 실패한다. 폴더 내용으로 모드를 추측하던 로직을 없앴다 - 그것이
Step 1을 라벨 없는 한 장으로 퇴화시키고 Step 2의 참조 사진까지
조용히 날리던 원인이다."
```

---

### Task 6: `color_pattern` 스텝 두 개와 서비스

**Files:**
- Create: `services/color_pattern/step_1_part_survey.py`
- Create: `services/color_pattern/step_2_pattern_unfold.py`
- Create: `services/color_pattern/service.py`
- Create: `tests/test_color_pattern_service.py`
- Modify: `tests/test_golden_parts.py` — Step 1·2를 새 경로로 구동

**Interfaces:**
- Consumes: `services.engine` (Task 4), `services.color_pattern.photo_input`/`prompts`/`schema` (Task 5)
- Produces:
  - `step_1_part_survey.run(session, photos) -> str` — 응답 원문
  - `step_1_part_survey.SURVEY_CONFIG`
  - `step_2_pattern_unfold.run(session, photos, guide_path, survey_text) -> list` — 생성 이미지 목록
  - `services.color_pattern.service.MODEL: str`
  - `services.color_pattern.service.run(shoe_dir, guide_path, out, archive=None) -> Path` — 저장된 컬러 패턴 PNG 경로

- [ ] **Step 1: 실패하는 테스트를 작성한다**

`tests/test_color_pattern_service.py`:

```python
"""color_pattern 서비스 테스트."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image
from pydantic import ValidationError

from services import engine
from services.color_pattern import photo_input, service, step_1_part_survey
from tests.golden_parts import RecordingClient


VALID_SURVEY = (
    '{"분석대상짝": "왼발", "부품": [], "마킹": []}'
)


class SurveyValidationTest(unittest.TestCase):
    def test_broken_json_raises_at_step_1(self):
        """지금은 빈 응답이나 깨진 JSON이 Step 2까지 조용히 흘러간다."""
        client = RecordingClient([engine.StepResponse(text="not json", images=[])])
        with self.assertRaises(ValidationError):
            step_1_part_survey.run(client, [])

    def test_empty_response_raises_at_step_1(self):
        client = RecordingClient([engine.StepResponse(text="", images=[])])
        with self.assertRaises(ValidationError):
            step_1_part_survey.run(client, [])

    def test_valid_survey_returns_the_raw_text_unchanged(self):
        """검증은 하되 재직렬화하지 않는다. 키 순서나 공백이 달라지면
        Step 2가 보는 토큰이 달라진다."""
        client = RecordingClient([engine.StepResponse(text=VALID_SURVEY, images=[])])
        self.assertEqual(step_1_part_survey.run(client, []), VALID_SURVEY)


class ServiceTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.shoe = self.tmp / "photos" / "shoe"
        self.shoe.mkdir(parents=True)
        for name in ("lateral.png", "medial.png"):
            Image.new("RGB", (4, 4)).save(self.shoe / name)
        self.guide = self.tmp / "가이드라인.png"
        Image.new("RGB", (4, 4)).save(self.guide)

    def _run(self):
        client = RecordingClient([
            engine.StepResponse(text=VALID_SURVEY, images=[]),
            engine.StepResponse(text="", images=[Image.new("RGB", (4, 4))]),
        ])
        out = engine.RunOutput(self.tmp / "outputs", "run1")
        with patch.object(service.engine, "new_session", lambda model: client):
            path = service.run(self.shoe, self.guide, out)
        return client, path

    def test_service_opens_exactly_one_session_for_two_steps(self):
        """두 스텝은 세션을 공유한다. 정면·뒤꿈치·위 사진이 히스토리로만
        Step 2에 닿는 현 구조를 유지하기 위해서다."""
        client, _ = self._run()
        self.assertEqual(len(client.calls), 2)

    def test_step_1_survey_text_reaches_step_2_verbatim(self):
        client, _ = self._run()
        step2_texts = [p for p in client.calls[1]["parts"] if p["kind"] == "text"]
        self.assertTrue(any(
            t["len"] == len(f"[Previous Step 1 Output]\n{VALID_SURVEY}")
            for t in step2_texts
        ))

    def test_service_returns_the_saved_color_pattern_path(self):
        """서비스 간 핸드오프는 파일이다."""
        _, path = self._run()
        self.assertTrue(path.exists())
        self.assertEqual(path.suffix, ".png")
        self.assertEqual(path.parent.name, "color_pattern")

    def test_model_is_declared_by_the_service(self):
        self.assertEqual(service.MODEL, "gemini-3.1-flash-image")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 실패를 확인한다**

Run: `uv run python -m unittest tests.test_color_pattern_service -v`
Expected: FAIL — `ImportError: cannot import name 'step_1_part_survey'`

- [ ] **Step 3: 스텝 두 개를 만든다**

`services/color_pattern/step_1_part_survey.py`:

```python
"""Step 1 — 신발 사진에서 부품 명세서를 만든다."""

from __future__ import annotations

from config.gemini import build_response_config
from services.color_pattern import photo_input
from services.color_pattern.prompts import PART_SURVEY_PROMPT
from services.color_pattern.schema import Survey

SURVEY_CONFIG = build_response_config(["TEXT"], response_schema=Survey)


def run(session, photos) -> str:
    """명세서 원문을 반환한다.

    Survey는 검증 전용이다. 파싱 결과를 다시 직렬화해 다음 스텝의
    프롬프트에 넣지 않는다 - 키 순서나 공백이 달라지면 Step 2가 보는
    토큰이 달라진다.
    """
    parts = photo_input.build_survey_parts(photos, PART_SURVEY_PROMPT)
    text = session.send(parts, config=SURVEY_CONFIG).text
    Survey.model_validate_json(text)
    return text
```

`services/color_pattern/step_2_pattern_unfold.py`:

```python
"""Step 2 — 사진과 명세서로 컬러 패턴을 펼친다."""

from __future__ import annotations

from pathlib import Path

from services.color_pattern import photo_input
from services.color_pattern.prompts import PATTERN_UNFOLD_PROMPT


def run(session, photos, guide_path: Path, survey_text: str) -> list:
    """생성된 컬러 패턴 이미지 목록을 반환한다.

    config를 넘기지 않는다. 세션 기본값(CHAT_CONFIG, 4K/2:3)을 그대로 쓴다.
    """
    parts = photo_input.build_unfold_parts(
        photos, guide_path, survey_text, PATTERN_UNFOLD_PROMPT
    )
    return session.send(parts).images
```

`services/color_pattern/service.py`:

```python
"""컬러 패턴 서비스 — 신발 사진에서 컬러 패턴 한 장을 만든다.

두 스텝이 채팅 세션 하나를 공유한다. 정면·뒤꿈치·위 사진은 Step 2의
parts에 직접 들어가지 않고 히스토리로만 닿는다.
"""

from __future__ import annotations

from pathlib import Path

from services import engine
from services.color_pattern import (
    photo_input,
    step_1_part_survey,
    step_2_pattern_unfold,
)
from services.color_pattern.prompts import PART_SURVEY_PROMPT, PATTERN_UNFOLD_PROMPT

# Step 1의 TEXT+JSON과 Step 2의 IMAGE를 한 세션에서 모두 처리해야 한다.
# chats.create(model=...)가 세션 생성 시점에 모델을 고정하므로 두 스텝은
# 같은 모델을 쓸 수밖에 없다.
MODEL = "gemini-3.1-flash-image"

SERVICE = "color_pattern"


def run(shoe_dir: Path, guide_path: Path, out, archive=None) -> Path:
    """저장된 컬러 패턴 PNG 경로를 반환한다."""
    photos = photo_input.resolve(shoe_dir)
    session = engine.new_session(MODEL)

    survey_text = step_1_part_survey.run(session, photos)
    out.save_step(
        service=SERVICE, step=1, name="part_survey",
        description="부품 관찰 - 신발 사진 → 부품 명세서",
        prompt=PART_SURVEY_PROMPT, response=survey_text, generated_images=[],
    )

    generated = step_2_pattern_unfold.run(session, photos, guide_path, survey_text)
    out.save_step(
        service=SERVICE, step=2, name="pattern_unfold",
        description="패턴 펼치기 - 명세서 → 컬러 패턴",
        prompt=PATTERN_UNFOLD_PROMPT, response="", generated_images=generated,
    )

    if archive is not None:
        archive.extend(session.history)

    return out.service_dir(SERVICE) / "step_2_pattern_unfold_generated_01.png"
```

- [ ] **Step 4: 테스트를 돌린다**

Run: `uv run python -m unittest tests.test_color_pattern_service -v`
Expected: PASS

- [ ] **Step 5: 골든 테스트를 새 경로로 옮긴다**

`tests/test_golden_parts.py`의 `test_golden_color_pattern_step_1`과 `test_golden_color_pattern_step_2`를 `Pipeline` 대신 `service.run`으로 구동하도록 고친다. **`tests/golden/*.json`은 건드리지 않는다.** 사진 fixture는 `make_fixture_photos`가 만든 파일을 `photo_input.resolve`가 인식하도록 뷰 이름 파일로 두면 되므로 이미 호환된다.

```python
    def _run_color_pattern(self):
        shoe = self.tmp / "photos" / "shoe"
        make_fixture_photos(shoe)
        guide = make_fixture_guide(self.tmp / "guides")
        client = RecordingClient([
            engine.StepResponse(text='{"분석대상짝": "왼발", "부품": [], "마킹": []}', images=[]),
            engine.StepResponse(text="", images=[Image.new("RGB", (10, 15))]),
        ])
        out = engine.RunOutput(self.tmp / "outputs", "golden")
        with patch.object(cp_service.engine, "new_session", lambda model: client):
            cp_service.run(shoe, guide, out)
        return client.calls
```

Run: `uv run python -m unittest tests.test_golden_parts -v`
Expected: PASS. 실패하면 `photo_input.build_unfold_parts`의 파트 순서를 골든에 맞춘다. `git diff --exit-code tests/golden/`이 깨끗해야 한다.

- [ ] **Step 6: 전체 테스트와 골든 불변 확인**

```bash
uv run python -m unittest discover -s tests -q
git diff --exit-code tests/golden/ && echo "골든 불변 OK"
```

- [ ] **Step 7: 커밋**

```bash
git add services/color_pattern/ tests/test_color_pattern_service.py tests/test_golden_parts.py
git commit -m "feat: color_pattern 서비스 - 세션 하나로 스텝 둘

스텝은 함수 하나이고 자기가 session.send()를 부른다. Step 1은 Survey로
응답을 검증하되 원문을 그대로 반환한다 - 재직렬화하면 Step 2가 보는
토큰이 달라진다.

골든이 그대로 통과하므로 API로 나가는 바이트는 변하지 않았다."
```

---

### Task 7: `sketch_pattern` 서비스

**Files:**
- Create: `services/sketch_pattern/__init__.py`
- Create: `services/sketch_pattern/prompts.py`
- Create: `services/sketch_pattern/step_1_line_art.py`
- Create: `services/sketch_pattern/service.py`
- Create: `tests/test_sketch_pattern_service.py`
- Modify: `tests/test_golden_parts.py` — Step 3을 새 경로로 구동
- Modify: `config/prompts.py` — `LINE_ART_PROMPT`, `ORIGINAL_PATTERN_LABEL` 제거 후 새 위치에서 import

**Interfaces:**
- Consumes: `services.engine` (Task 4), `services.utils.images` (Task 2)
- Produces:
  - `services.sketch_pattern.prompts.LINE_ART_PROMPT: str`, `ORIGINAL_PATTERN_LABEL: str = "원본 컬러 패턴"`
  - `step_1_line_art.run(session, color_pattern_path: Path) -> list`
  - `services.sketch_pattern.service.MODEL: str`
  - `services.sketch_pattern.service.run(color_pattern_path: Path, out, archive=None) -> Path`

- [ ] **Step 1: 실패하는 테스트를 작성한다**

`tests/test_sketch_pattern_service.py`:

```python
"""sketch_pattern 서비스 테스트."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from services import engine
from services.sketch_pattern import prompts, service
from tests.golden_parts import RecordingClient


class SketchPatternTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.color = self.tmp / "shoe_color.png"
        Image.new("RGB", (10, 15), (200, 30, 30)).save(self.color)

    def _run(self):
        client = RecordingClient([
            engine.StepResponse(text="", images=[Image.new("RGB", (10, 15))]),
        ])
        out = engine.RunOutput(self.tmp / "outputs", "run1")
        with patch.object(service.engine, "new_session", lambda model: client):
            path = service.run(self.color, out)
        return client, path

    def test_parts_are_label_then_image_then_prompt(self):
        """라벨이 없으면 모델이 이 이미지를 프롬프트가 지목하는 '원본'으로
        읽지 못하고 참고 사진 하나로 흘려본다."""
        client, _ = self._run()
        parts = client.calls[0]["parts"]
        self.assertEqual(len(parts), 3)
        self.assertEqual(parts[0]["kind"], "text")
        self.assertEqual(parts[0]["len"], len("[원본 컬러 패턴]"))
        self.assertEqual(parts[1]["kind"], "pil")
        self.assertEqual(parts[2]["len"], len(prompts.LINE_ART_PROMPT))

    def test_service_does_not_require_shoe_photos(self):
        """이 서비스는 컬러 패턴 경로 하나만 받는다. 신발 사진을 모른다."""
        import inspect
        params = list(inspect.signature(service.run).parameters)
        self.assertEqual(params[0], "color_pattern_path")
        self.assertNotIn("shoe_dir", params)

    def test_config_is_none_so_the_session_default_applies(self):
        client, _ = self._run()
        self.assertIsNone(client.calls[0]["config"])

    def test_service_opens_its_own_session(self):
        """서비스 경계가 세션 경계다. fresh_session 플래그를 대신한다."""
        client, _ = self._run()
        self.assertEqual(client.start_chat_call_count, 0)  # new_session이 스텁이므로
        self.assertEqual(len(client.calls), 1)

    def test_saved_under_the_sketch_pattern_folder(self):
        _, path = self._run()
        self.assertTrue(path.exists())
        self.assertEqual(path.parent.name, "sketch_pattern")

    def test_label_value_is_unchanged(self):
        self.assertEqual(prompts.ORIGINAL_PATTERN_LABEL, "원본 컬러 패턴")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 실패를 확인한다**

Run: `uv run python -m unittest tests.test_sketch_pattern_service -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'services.sketch_pattern'`

- [ ] **Step 3: 서비스를 만든다**

`config/prompts.py`의 `LINE_ART_PROMPT`(483자)와 `ORIGINAL_PATTERN_LABEL`(8자)은 이미 이름이 붙어 있다. 두 정의를 **잘라내어** `services/sketch_pattern/prompts.py`로 붙인다. 주변 주석 블록도 함께 옮긴다. 문자열 리터럴을 다시 타이핑하지 않는다.

`services/sketch_pattern/step_1_line_art.py`:

```python
"""Step 1 — 컬러 패턴을 재단선만 남긴 스케치 패턴으로 바꾼다."""

from __future__ import annotations

from pathlib import Path

from services.sketch_pattern.prompts import LINE_ART_PROMPT, ORIGINAL_PATTERN_LABEL
from services.utils import images


def run(session, color_pattern_path: Path) -> list:
    """생성된 스케치 패턴 이미지 목록을 반환한다.

    라벨을 붙여야 모델이 이 이미지를 프롬프트가 말하는 '원본'으로 읽는다.
    라벨 없이 넣으면 그냥 참고 사진 한 장으로 흘려본다.
    """
    parts = [
        images.label(ORIGINAL_PATTERN_LABEL),
        images.load(color_pattern_path),
        LINE_ART_PROMPT,
    ]
    return session.send(parts).images
```

`services/sketch_pattern/service.py`:

```python
"""스케치 패턴 서비스 — 컬러 패턴 한 장에서 스케치 패턴을 만든다.

자기 세션을 새로 연다. Step 1 명세서는 측면 사진 기준 3D 서술이라
그것이 히스토리로 닿으면 모델이 평면 패턴을 트레이싱하는 대신 3D
신발을 다시 그려버린다. 서비스가 분리되어 있으므로 그 경로가 없다.
"""

from __future__ import annotations

from pathlib import Path

from services import engine
from services.sketch_pattern import step_1_line_art
from services.sketch_pattern.prompts import LINE_ART_PROMPT

MODEL = "gemini-3.1-flash-image"

SERVICE = "sketch_pattern"


def run(color_pattern_path: Path, out, archive=None) -> Path:
    """저장된 스케치 패턴 PNG 경로를 반환한다."""
    session = engine.new_session(MODEL)
    generated = step_1_line_art.run(session, color_pattern_path)
    out.save_step(
        service=SERVICE, step=1, name="line_art",
        description="스케치 패턴 변환 - 컬러 패턴 → 재단선만 남긴 스케치 패턴",
        prompt=LINE_ART_PROMPT, response="", generated_images=generated,
    )
    if archive is not None:
        archive.extend(session.history)
    return out.service_dir(SERVICE) / "step_1_line_art_generated_01.png"
```

`config/prompts.py`는 아직 `PIPELINE_STEPS`를 노출하므로 상단에 `from services.sketch_pattern.prompts import LINE_ART_PROMPT, ORIGINAL_PATTERN_LABEL`을 추가한다.

- [ ] **Step 4: 골든 테스트의 Step 3을 새 경로로 옮긴다**

```python
    def test_golden_sketch_pattern_step_1(self):
        color = make_fixture_color_pattern(self.tmp / "patterns")
        client = RecordingClient([engine.StepResponse(text="", images=[Image.new("RGB", (4, 4))])])
        out = engine.RunOutput(self.tmp / "outputs", "golden")
        with patch.object(sp_service.engine, "new_session", lambda model: client):
            sp_service.run(color, out)
        assert_golden(self, "sketch_pattern__step_1_line_art", client.calls[0])
```

**주의:** 골든의 이미지 해시는 Task 1에서 `Image.new("RGB", (10, 15), (200, 30, 30))`을 직접 넘겨 만들었고, 지금은 `make_fixture_color_pattern`이 저장한 PNG를 `images.load`로 읽는다. 픽셀이 같으므로 해시도 같다. 다르면 Task 1의 fixture 생성과 여기의 로드 경로가 어긋난 것이므로 **골든을 고치지 말고 fixture를 맞춘다.**

- [ ] **Step 5: 전체 테스트와 골든 불변 확인**

```bash
uv run python -m unittest discover -s tests -q
git diff --exit-code tests/golden/ && echo "골든 불변 OK"
```

- [ ] **Step 6: 커밋**

```bash
git add services/sketch_pattern/ tests/test_sketch_pattern_service.py tests/test_golden_parts.py config/prompts.py
git commit -m "feat: sketch_pattern 서비스 - 자기 세션으로 스텝 하나

서비스 경계가 세션 경계다. fresh_session=True와
include_prev_texts=False 플래그가 구조적 사실로 대체되어 사라졌다.
이 서비스는 컬러 패턴 경로 하나만 받고 신발 사진을 모른다."
```

---

### Task 8: 스크립트 세 개

**Files:**
- Create: `scripts/run_service.py`
- Create: `scripts/run_all.py`
- Create: `scripts/_common.py`
- Rewrite: `scripts/run_parallel.sh`
- Create: `tests/test_scripts.py`
- Delete: `scripts/run_all_views.sh`

**Interfaces:**
- Consumes: `services.color_pattern.service`, `services.sketch_pattern.service` (Task 6·7), `services.engine` (Task 4)
- Produces:
  - `scripts._common.SERVICES: dict[str, module]`
  - `scripts._common.derive_label(input_path: Path) -> str`
  - `scripts._common.setup_logging(verbose: bool) -> None`
  - `scripts._common.run_labels(label: str, repeat: int) -> list[str]`
  - `scripts.run_service.main(argv: list[str] | None = None) -> int`
  - `scripts.run_all.main(argv: list[str] | None = None) -> int`

- [ ] **Step 1: 실패하는 테스트를 작성한다**

`tests/test_scripts.py`:

```python
"""스크립트 인자 처리 테스트. API는 호출하지 않는다."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from scripts import _common, run_all, run_service


class LabelTest(unittest.TestCase):
    def test_repeat_one_has_no_suffix(self):
        self.assertEqual(_common.run_labels("shoe_v7", 1), ["shoe_v7"])

    def test_repeat_many_gets_numbered_suffixes(self):
        self.assertEqual(
            _common.run_labels("shoe_v7", 3),
            ["shoe_v7-1", "shoe_v7-2", "shoe_v7-3"],
        )

    def test_derive_label_uses_the_folder_name_for_a_directory(self):
        self.assertEqual(_common.derive_label(Path("inputs/photos/adidas_ORKETRO")),
                         "adidas_ORKETRO")

    def test_derive_label_uses_the_stem_for_a_file(self):
        self.assertEqual(_common.derive_label(Path("inputs/color_patterns/a_color.png")),
                         "a_color")


class RunServiceTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.color = self.tmp / "a_color.png"
        Image.new("RGB", (4, 4)).save(self.color)

    def test_unknown_service_name_exits_nonzero(self):
        with self.assertRaises(SystemExit):
            run_service.main(["nope", "--input", str(self.color)])

    def test_sketch_pattern_runs_once_per_repeat(self):
        calls = []
        with patch.object(run_service, "SERVICES", {
            "sketch_pattern": type("M", (), {
                "run": staticmethod(lambda path, out, archive=None: calls.append(out) or path)
            })
        }):
            run_service.main([
                "sketch_pattern", "--input", str(self.color),
                "--out", str(self.tmp / "outputs"), "--repeat", "2",
            ])
        self.assertEqual(len(calls), 2)


class RunAllTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.shoe = self.tmp / "shoe"
        self.shoe.mkdir()
        Image.new("RGB", (4, 4)).save(self.shoe / "lateral.png")

    def test_color_pattern_output_path_is_handed_to_sketch_pattern(self):
        """서비스 간 핸드오프는 파일이다."""
        produced = self.tmp / "produced.png"
        Image.new("RGB", (4, 4)).save(produced)
        received = []

        fake_cp = type("M", (), {"run": staticmethod(
            lambda shoe_dir, guide, out, archive=None: produced)})
        fake_sp = type("M", (), {"run": staticmethod(
            lambda path, out, archive=None: received.append(path) or path)})

        with patch.object(run_all, "color_pattern", fake_cp), \
             patch.object(run_all, "sketch_pattern", fake_sp):
            run_all.main(["--input", str(self.shoe), "--out", str(self.tmp / "outputs")])

        self.assertEqual(received, [produced])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 실패를 확인한다**

Run: `uv run python -m unittest tests.test_scripts -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts._common'`

`scripts/__init__.py`가 없으면 만든다(빈 파일).

- [ ] **Step 3: `scripts/_common.py`를 만든다**

`main.py`의 `setup_logging`을 그대로 옮긴다. `utils/cli.py`의 `derive_run_label`/`resolve_run_label_from_path` 로직을 `derive_label` 하나로 합친다.

```python
"""스크립트 공용 헬퍼."""

from __future__ import annotations

import logging
import sys
from datetime import datetime
from pathlib import Path

from services.color_pattern import service as color_pattern
from services.sketch_pattern import service as sketch_pattern
from utils.logging_utils import StepFilter

SERVICES = {
    "color_pattern": color_pattern,
    "sketch_pattern": sketch_pattern,
}

DEFAULT_GUIDE = Path("inputs/guides/가이드라인_회전5도_여백표시.png")


def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s%(step_label)s] %(name)s - %(message)s",
        datefmt="%H:%M:%S",
    )
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    handler.addFilter(StepFilter())
    logging.basicConfig(level=level, handlers=[handler])
    if not verbose:
        for name in ("google_genai", "google_genai.models", "httpx", "urllib3"):
            logging.getLogger(name).setLevel(logging.WARNING)


def derive_label(input_path: Path) -> str:
    """입력 경로에서 실행 레이블을 만든다."""
    path = Path(input_path)
    return path.name if path.is_dir() else path.stem


def run_labels(label: str, repeat: int) -> list[str]:
    """--repeat 1이면 접미사를 붙이지 않는다."""
    if repeat <= 1:
        return [label]
    return [f"{label}-{n}" for n in range(1, repeat + 1)]


def timestamp_label() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")
```

- [ ] **Step 4: `scripts/run_service.py`와 `scripts/run_all.py`를 만든다**

`scripts/run_service.py`:

```python
"""서비스 하나를 실행한다.

    python scripts/run_service.py color_pattern  --input inputs/photos/adidas_ORKETRO
    python scripts/run_service.py sketch_pattern --input inputs/color_patterns/a_color.png
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts._common import (  # noqa: E402
    DEFAULT_GUIDE, SERVICES, derive_label, run_labels, setup_logging, timestamp_label,
)
from services import engine  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="서비스 하나를 실행합니다.")
    parser.add_argument("service", choices=sorted(SERVICES))
    parser.add_argument("--input", required=True,
                        help="color_pattern이면 inputs/photos/<신발>/, "
                             "sketch_pattern이면 컬러 패턴 파일 또는 폴더")
    parser.add_argument("--out", default="outputs")
    parser.add_argument("--label", default=None)
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--guide", default=str(DEFAULT_GUIDE))
    parser.add_argument("--verbose", "-v", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    setup_logging(args.verbose)

    module = SERVICES[args.service]
    source = Path(args.input)
    base = args.label or derive_label(source) or timestamp_label()

    for label in run_labels(base, args.repeat):
        out = engine.RunOutput(Path(args.out), label)
        archive = engine.HistoryArchive()
        if args.service == "color_pattern":
            module.run(source, Path(args.guide), out, archive)
        else:
            module.run(source, out, archive)
        out.save_final(text="", generated_images=[], chat_history=archive.all())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

`scripts/run_all.py`:

```python
"""두 서비스를 순서대로 실행한다.

    python scripts/run_all.py --input inputs/photos/adidas_ORKETRO
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts._common import (  # noqa: E402
    DEFAULT_GUIDE, derive_label, run_labels, setup_logging, timestamp_label,
)
from services import engine  # noqa: E402
from services.color_pattern import service as color_pattern  # noqa: E402
from services.sketch_pattern import service as sketch_pattern  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="모든 서비스를 순서대로 실행합니다.")
    parser.add_argument("--input", required=True, help="inputs/photos/<신발>/")
    parser.add_argument("--out", default="outputs")
    parser.add_argument("--label", default=None)
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--guide", default=str(DEFAULT_GUIDE))
    parser.add_argument("--verbose", "-v", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    setup_logging(args.verbose)

    shoe_dir = Path(args.input)
    base = args.label or derive_label(shoe_dir) or timestamp_label()

    for label in run_labels(base, args.repeat):
        out = engine.RunOutput(Path(args.out), label)
        archive = engine.HistoryArchive()
        color_path = color_pattern.run(shoe_dir, Path(args.guide), out, archive)
        sketch_pattern.run(color_path, out, archive)
        out.save_final(text="", generated_images=[], chat_history=archive.all())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: `scripts/run_parallel.sh`를 다시 쓴다**

뷰 × 확장자 탐색 12줄은 `photo_input`으로 옮겨갔으므로 삭제한다.

```bash
#!/usr/bin/env bash
# inputs/photos/ 아래 신발 폴더들을 병렬로 실행합니다.
#
# 사용법:
#   scripts/run_parallel.sh                        # 모든 신발, 모든 서비스
#   scripts/run_parallel.sh sketch_pattern         # 스케치만
#   JOBS=6 REPEAT=3 scripts/run_parallel.sh
#
# run.sh를 쓰지 않고 venv 파이썬을 직접 부릅니다. run.sh는 매번 uv sync를
# 하는데, 동시에 여러 개가 돌면 venv 락을 두고 경쟁합니다.
set -uo pipefail

cd "$(dirname "$0")/.."

PY=.venv/bin/python
JOBS=${JOBS:-4}
REPEAT=${REPEAT:-1}
LOG_DIR=outputs/_runlogs
mkdir -p "$LOG_DIR"

services=("$@")

run_one() {
    local shoe_dir=$1
    local label
    label=$(basename "$shoe_dir")

    if [ ${#services[@]} -eq 0 ]; then
        $PY scripts/run_all.py --input "$shoe_dir" --repeat "$REPEAT" \
            > "$LOG_DIR/${label}.log" 2>&1 \
            && echo "OK   $label" || echo "FAIL $label"
        return
    fi

    local svc
    for svc in "${services[@]}"; do
        $PY scripts/run_service.py "$svc" --input "$shoe_dir" --repeat "$REPEAT" \
            > "$LOG_DIR/${label}_${svc}.log" 2>&1 \
            && echo "OK   $label $svc" || echo "FAIL $label $svc"
    done
}

shopt -s nullglob
targets=(inputs/photos/*/)
if [ ${#targets[@]} -eq 0 ]; then
    echo "inputs/photos/ 아래에 신발 폴더가 없습니다."
    exit 1
fi

echo "START ${#targets[@]}개 신발, 동시 ${JOBS}개, 반복 ${REPEAT}회"
for shoe_dir in "${targets[@]}"; do
    while [ "$(jobs -rp | wc -l)" -ge "$JOBS" ]; do
        wait -n 2>/dev/null || sleep 1
    done
    run_one "${shoe_dir%/}" &
done
wait
echo "DONE"
```

`chmod +x scripts/run_parallel.sh`를 잊지 않는다. `scripts/run_all_views.sh`를 삭제한다.

- [ ] **Step 6: 테스트를 돌린다**

```bash
uv run python -m unittest discover -s tests -q
bash -n scripts/run_parallel.sh && echo "bash 문법 OK"
git diff --exit-code tests/golden/ && echo "골든 불변 OK"
```

- [ ] **Step 7: 커밋**

```bash
git add scripts/ tests/test_scripts.py
git rm -f scripts/run_all_views.sh
git commit -m "feat: 서비스 단위 실행 스크립트 세 개

run_service.py, run_all.py, run_parallel.sh. 병렬 러너는 bash로 남긴다 -
실행마다 별도 프로세스라 세션과 출력 폴더가 격리되고, 전역
logging.basicConfig가 스레드에서 뒤섞이지 않는다.

뷰 x 확장자를 훑어 플래그를 조립하던 12줄은 photo_input으로
옮겨갔으므로 삭제했다."
```

---

### Task 9: 옛 구조 삭제와 `inputs/` 배치

**Files:**
- Delete: `core/` 전체, `main.py`, `handlers/` 전체, `config/prompts.py`, `config/survey_schema.py`, `config/gemini_config.py`, `scripts/run_step3_on_color_patterns.py`
- Modify: `utils/cli.py` — 뷰·이미지 플래그 파싱 제거, 남는 것이 없으면 파일 삭제
- Rename: `tests/test_no_prev_texts_in_step3.py` → `tests/test_sketch_pattern_isolation.py`
- Rename: `tests/test_run_step3_on_color_patterns.py` → 내용 흡수 후 삭제
- Modify: `tests/test_pipeline_wiring.py` → `tests/test_service_wiring.py`로 재작성
- Modify: `tests/test_cli_view_flags.py`, `test_folder_labels_and_batch.py`, `test_guide_path.py`, `test_labeled_parts.py`, `test_prompts_structure.py`, `test_generated_image_passthrough.py`, `test_response_config.py`, `test_survey_schema.py` — 새 경로로 갱신
- Create: `inputs/photos/.gitkeep`, `inputs/color_patterns/.gitkeep`
- Move: `guides/가이드라인_회전5도_여백표시.png` → `inputs/guides/`
- Modify: `.gitignore`, `README.md`, `run.sh`

**Interfaces:**
- Consumes: Task 2~8의 모든 산출물
- Produces: 없음 (정리 태스크)

- [ ] **Step 1: 세션 격리와 히스토리 보존 테스트를 새 구조로 옮긴다**

`tests/test_service_wiring.py`를 만든다. `tests/test_pipeline_wiring.py`에서 다음 두 테스트의 **의도**를 이어받는다.

```python
"""서비스 사이의 배선 테스트."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from services import engine
from services.color_pattern import service as color_pattern
from services.sketch_pattern import service as sketch_pattern
from tests.golden_parts import RecordingClient

VALID_SURVEY = '{"분석대상짝": "왼발", "부품": [], "마킹": []}'


class ServiceWiringTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.shoe = self.tmp / "shoe"
        self.shoe.mkdir()
        for name in ("lateral.png", "medial.png"):
            Image.new("RGB", (4, 4)).save(self.shoe / name)
        self.guide = self.tmp / "가이드라인.png"
        Image.new("RGB", (4, 4)).save(self.guide)

    def test_the_two_services_use_different_sessions(self):
        """서비스 경계가 세션 경계다. sketch_pattern이 color_pattern의
        히스토리를 이어받으면, Step 1 명세서(측면 사진 기준 3D 서술) 때문에
        모델이 평면 패턴을 트레이싱하는 대신 3D 신발을 다시 그린다."""
        created = []

        def fake_new_session(model):
            client = RecordingClient([
                engine.StepResponse(text=VALID_SURVEY, images=[]),
                engine.StepResponse(text="", images=[Image.new("RGB", (4, 4))]),
                engine.StepResponse(text="", images=[Image.new("RGB", (4, 4))]),
            ])
            created.append(client)
            return client

        out = engine.RunOutput(self.tmp / "outputs", "run1")
        archive = engine.HistoryArchive()
        with patch.object(engine, "new_session", fake_new_session):
            color_path = color_pattern.run(self.shoe, self.guide, out, archive)
            sketch_pattern.run(color_path, out, archive)

        self.assertEqual(len(created), 2)
        self.assertIsNot(created[0], created[1])

    def test_sketch_pattern_never_sees_the_survey_text(self):
        created = []

        def fake_new_session(model):
            client = RecordingClient([
                engine.StepResponse(text=VALID_SURVEY, images=[]),
                engine.StepResponse(text="", images=[Image.new("RGB", (4, 4))]),
                engine.StepResponse(text="", images=[Image.new("RGB", (4, 4))]),
            ])
            created.append(client)
            return client

        out = engine.RunOutput(self.tmp / "outputs", "run2")
        with patch.object(engine, "new_session", fake_new_session):
            color_path = color_pattern.run(self.shoe, self.guide, out)
            sketch_pattern.run(color_path, out)

        sketch_texts = [p for p in created[1].calls[0]["parts"] if p["kind"] == "text"]
        survey_len = len(f"[Previous Step 1 Output]\n{VALID_SURVEY}")
        self.assertFalse(any(t["len"] == survey_len for t in sketch_texts))

    def test_archive_keeps_turns_from_both_services(self):
        """세션이 둘이므로 합쳐두지 않으면 앞 서비스의 턴이
        chat_history.json에서 사라진다."""
        def fake_new_session(model):
            return RecordingClient([
                engine.StepResponse(text=VALID_SURVEY, images=[]),
                engine.StepResponse(text="", images=[Image.new("RGB", (4, 4))]),
                engine.StepResponse(text="", images=[Image.new("RGB", (4, 4))]),
            ])

        out = engine.RunOutput(self.tmp / "outputs", "run3")
        archive = engine.HistoryArchive()
        with patch.object(engine, "new_session", fake_new_session):
            color_path = color_pattern.run(self.shoe, self.guide, out, archive)
            sketch_pattern.run(color_path, out, archive)

        self.assertEqual(len(archive.all()), 3)


if __name__ == "__main__":
    unittest.main()
```

Run: `uv run python -m unittest tests.test_service_wiring -v`
Expected: PASS

- [ ] **Step 2: 옛 파일을 삭제한다**

```bash
git rm -r core/ handlers/
git rm main.py config/prompts.py config/survey_schema.py config/gemini_config.py
git rm scripts/run_step3_on_color_patterns.py
git rm tests/test_pipeline_wiring.py tests/test_no_prev_texts_in_step3.py \
       tests/test_run_step3_on_color_patterns.py tests/test_cli_view_flags.py \
       tests/test_folder_labels_and_batch.py tests/test_labeled_parts.py
```

`tests/test_guide_path.py`, `test_prompts_structure.py`, `test_generated_image_passthrough.py`, `test_response_config.py`, `test_survey_schema.py`는 삭제하지 않는다. import 경로만 새 위치로 고친다.

- `test_prompts_structure.py`: `config.prompts` → `services.color_pattern.prompts`, `services.sketch_pattern.prompts`. `PIPELINE_STEPS`를 검사하는 테스트는 지우고, 대신 세 프롬프트가 비어 있지 않은지와 `ORIGINAL_PATTERN_LABEL` 값을 검사한다.
- `test_response_config.py`: `config.gemini_config` → `config.gemini`.
- `test_survey_schema.py`: `config.survey_schema` → `services.color_pattern.schema`.
- `test_generated_image_passthrough.py`: `services.gemini_client` → `services.engine`.
- `test_guide_path.py`: 가이드 경로 검증을 `scripts/_common.DEFAULT_GUIDE` 기준으로 고친다.

`utils/cli.py`에서 뷰 플래그와 `--shoe-image`, `--guide-image` 파싱을 제거한다. 남는 함수가 없으면 `utils/cli.py`를 삭제한다. `utils/logging_utils.py`는 유지한다.

`services/gemini_client.py`를 삭제한다(내용은 Task 4에서 `engine.py`로 옮겨졌다).

- [ ] **Step 3: `inputs/` 배치를 만든다**

```bash
mkdir -p inputs/photos inputs/color_patterns inputs/guides
touch inputs/photos/.gitkeep inputs/color_patterns/.gitkeep
git mv guides/가이드라인_회전5도_여백표시.png inputs/guides/
rmdir guides
```

`.gitignore`를 고친다: `images/`와 `output/` 항목을 `inputs/`와 `outputs/`로 바꾸되, `!inputs/guides/`, `!inputs/photos/.gitkeep`, `!inputs/color_patterns/.gitkeep`을 예외로 둔다.

기존 `images/`와 `output/`은 추적되지 않으므로 git 명령이 필요 없다. 삭제하지 않는다 — 사용자의 작업물이다. 사용자가 직접 옮기도록 남긴다.

- [ ] **Step 4: `run.sh`와 `README.md`를 고친다**

`run.sh`가 `main.py`를 부르고 있으면 `scripts/run_all.py`로 바꾼다.
`README.md`의 실행 예시와 폴더 설명을 새 구조로 갱신한다.

- [ ] **Step 5: 전체 테스트와 수용 기준을 확인한다**

```bash
uv run python -m unittest discover -s tests -q
git diff --exit-code tests/golden/ && echo "골든 불변 OK"

# 수용 기준 자동 검사
test ! -d core && echo "core/ 삭제 OK"
test ! -f main.py && echo "main.py 삭제 OK"
grep -rn "MODEL_NAME" config services && echo "FAIL: MODEL_NAME 잔존" || echo "MODEL_NAME 제거 OK"
grep -rn "PIPELINE_STEPS" . --include=*.py && echo "FAIL: PIPELINE_STEPS 잔존" || echo "PIPELINE_STEPS 제거 OK"
grep -rn "fresh_session\|include_prev_texts\|prev_image_label" --include=*.py . && echo "FAIL: 플래그 잔존" || echo "플래그 제거 OK"
bash -n scripts/run_parallel.sh && echo "bash 문법 OK"
```

- [ ] **Step 6: 스텁으로 스크립트 두 개를 실제로 돌려본다**

```bash
mkdir -p /tmp/ptest/shoe && uv run python - <<'PY'
from PIL import Image
from pathlib import Path
d = Path("/tmp/ptest/shoe"); d.mkdir(parents=True, exist_ok=True)
for n in ("lateral", "medial"): Image.new("RGB", (8, 8)).save(d / f"{n}.png")
Image.new("RGB", (8, 8)).save(Path("/tmp/ptest/color.png"))
PY

# 인자 파싱과 배선만 확인한다. API는 부르지 않는다.
uv run python -c "
from unittest.mock import patch
from PIL import Image
from services import engine
from scripts import run_all
from tests.golden_parts import RecordingClient
S = '{\"분석대상짝\": \"왼발\", \"부품\": [], \"마킹\": []}'
def fake(model):
    return RecordingClient([
        engine.StepResponse(text=S, images=[]),
        engine.StepResponse(text='', images=[Image.new('RGB',(8,8))]),
        engine.StepResponse(text='', images=[Image.new('RGB',(8,8))]),
    ])
with patch.object(engine, 'new_session', fake):
    run_all.main(['--input','/tmp/ptest/shoe','--out','/tmp/ptest/outputs',
                  '--guide','/tmp/ptest/color.png'])
print('run_all 배선 OK')
"
find /tmp/ptest/outputs -type f | sort
```

Expected: `outputs/shoe/color_pattern/step_1_part_survey.md`, `step_2_pattern_unfold.md`, `step_2_pattern_unfold_generated_01.png`, `sketch_pattern/step_1_line_art.md`, `step_1_line_art_generated_01.png`, `chat_history.json`

- [ ] **Step 7: 커밋**

```bash
git add -A
git commit -m "refactor: 옛 파이프라인 구조 삭제와 inputs/outputs 배치

core/, main.py, handlers/, config/prompts.py, config/survey_schema.py,
services/gemini_client.py를 삭제한다. PIPELINE_STEPS dict와 그 14개
키가 사라졌고, fresh_session/include_prev_texts/prev_image_label
플래그는 서비스 구조 자체로 대체됐다.

images/ -> inputs/, output/ -> outputs/. inputs/는 소비하는 서비스
기준으로 나눈다. 기존 images/와 output/은 추적되지 않는 작업물이라
그대로 둔다 - 옮기는 것은 사람이 판단한다.

골든 parts가 아홉 태스크 내내 그대로였다. Gemini로 나가는 요청은
한 바이트도 변하지 않았다."
```

---

## 완료 후 사람이 할 일

에이전트가 하지 않는다. 작업 보고에 아래를 그대로 전달한다.

1. `images/` 아래 컬러 패턴 11개를 `inputs/color_patterns/`로 옮긴다.
2. 신발 사진을 `inputs/photos/<신발>/lateral.png` 형태로 배치한다. 현재 저장소에는 `nike_p6000.jpeg` 한 장뿐이라 실제 사진 자산이 필요하다.
3. `output/` 아래 14개 실행 결과를 보관할지 결정한다.
4. 실제 API로 `scripts/run_all.py --input inputs/photos/<신발>`을 한 번 돌려 Step 1이 이미지 모델에서 TEXT+JSON을 반환하는지 확인한다. 실패하면 `services/color_pattern/service.py`의 `MODEL`만 바꾸면 되고 `sketch_pattern`은 영향받지 않는다.
