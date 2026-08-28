# Sketch Pattern v3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **Repository execution override:** This three-task plan must use `superpowers:executing-plans` with one worker for the entire plan. The worker must not dispatch per-task subagents; `superpowers:subagent-driven-development` is not permitted for this plan.

**Goal:** Make Step 3 preserve the input color pattern's aspect ratio and cutting-line geometry, remove destructive raster postprocessing, and generate twelve untouched v3 sketch outputs for human review.

**Architecture:** Keep the existing global `4K / 2:3` image configuration for Step 1–2, but add a call-level Step 3 configuration that requests `4K` without an explicit aspect ratio. Encode cutting-line classification, normalized-coordinate preservation, and closed mesh-part perimeter rules in the Step 3 prompt. Pass generated image objects unchanged through the pipeline and batch runner; do not resize, threshold, redraw, clean, or otherwise mutate pixels.

**Tech Stack:** Python 3.12, google-genai, Pillow for fixture creation and metadata-only tests, unittest/pytest, existing pipeline and batch runner.

**Spec:** `docs/superpowers/specs/2026-08-21-sketch-pattern-cut-line-extraction-design.md`

## Global Constraints

- Do not regenerate or modify any existing `*_color` image.
- Do not add a visual quality gate, image-content classifier, or content-based Gemini regeneration. The existing low-level retry for API transport failures remains unchanged and is not a visual regeneration path.
- Do not resize generated sketches to the color input's pixel dimensions.
- Do not apply thresholding, binarization, erosion, dilation, skeletonization, line redrawing, line repair, fill removal, speck cleanup, or antialiasing changes.
- Do not save a separate raw image: with no postprocessing, the generated image is already the final image.
- Preserve Step 3 `enabled=False`, `fresh_session=True`, and `include_prev_texts=False`.
- Save future batch outputs only under `images/new_patterns/v3/`; preserve v2 and older results.
- Agents must not open, display, screenshot, overlay, zoom, or visually judge any v3 output. Automated checks stop at tests, exit status, filenames, count, and nonvisual metadata. The user performs visual review.
- Do not add a dependency or abstraction beyond the one call-level image configuration needed by Step 3.
- Do not commit code, tests, docs, or generated images unless the user separately authorizes a commit.

## Execution Mode

This plan has exactly **3 tasks**, so execute it in **single-worker mode** under the repository instructions.

1. Dispatch all three tasks together to one Codex worker with `model: gpt-5.6-luna` and `reasoningEffort: xhigh`.
2. Tell the worker it is not alone in the codebase, must preserve unrelated edits, and must not inspect generated image contents.
3. After all tasks are complete, dispatch one whole-change reviewer with `model: gpt-5.6-terra` and `reasoningEffort: high`.
4. Send Critical and Important findings back to the same worker. Allow at most three review/fix rounds.
5. If a load-bearing finding remains after round three, stop and report it as blocked instead of opening a fourth round.

## File Responsibility Map

| File | Responsibility | Planned change |
|---|---|---|
| `config/gemini_config.py` | Shared Gemini request configuration | Add the minimal input-aspect image config and a call-level selector while preserving all existing defaults. |
| `config/prompts.py` | Step definitions and prompt contracts | Replace exact-pixel-size wording with aspect/framing/normalized-coordinate rules; add mesh perimeter closure; remove the postprocess flag; enable input-aspect request selection. |
| `core/pipeline.py` | Step request wiring and result propagation | Forward the Step 3 selector to request construction and remove all image mutation. |
| `scripts/run_step3_on_color_patterns.py` | Twelve-image Step 3 batch execution | Use the Step 3 request config, save the returned image directly, and route to `v3/`. |
| `utils/sketch_postprocessor.py` | Obsolete raster mutation | Delete. |
| `tests/test_survey_schema.py` | Request-config regression tests | Cover default behavior and Step 3 input-aspect behavior. |
| `tests/test_prompts_structure.py` | Prompt/step contract tests | Cover normalized geometry, mesh closure, rendering constraints, and removal of postprocessing. |
| `tests/test_pipeline_wiring.py` | Pipeline call and object-flow tests | Prove Step 3 receives the special config and the returned image object is not replaced. |
| `tests/test_run_step3_on_color_patterns.py` | Batch runner tests | Cover `v3/`, config forwarding, direct save, and skip-existing behavior. |
| `tests/test_sketch_postprocessor.py` | Tests for rejected behavior | Delete with the implementation. |
| `images/new_patterns/v3/` | Runtime outputs | Create during Task 3 and write twelve sketches; do not add them to a commit. |

---

### Task 1: Add the Step 3 input-aspect request contract and sharpen the prompt

**Files:**

- Modify: `config/gemini_config.py:24-34,71-98`
- Modify: `config/prompts.py` Step 3 `line_art_conversion`
- Modify: `tests/test_survey_schema.py:191-217`
- Modify: `tests/test_prompts_structure.py` Step 3 contract tests near the end of the file

**Interfaces:**

- Add: `INPUT_ASPECT_IMAGE_CONFIG = types.ImageConfig(image_size="4K")`
- Change: `build_response_config(modalities, response_schema=None, match_input_aspect_ratio=False)`
- Add to Step 3: `"match_input_aspect_ratio": True`
- Remove from Step 3: `"postprocess_sketch": True`

- [ ] **Step 1: Write failing request-configuration tests**

Extend the import in `tests/test_survey_schema.py`:

```python
from config.gemini_config import IMAGE_CONFIG, build_response_config
```

Add these tests to `BuildResponseConfigWithSchemaTest`:

```python
def test_input_aspect_request_uses_4k_without_explicit_ratio(self):
    config = build_response_config(None, match_input_aspect_ratio=True)

    self.assertIsNotNone(config)
    self.assertEqual(list(config.response_modalities), ["IMAGE"])
    self.assertEqual(config.image_config.image_size, "4K")
    self.assertIsNone(config.image_config.aspect_ratio)

def test_default_image_config_remains_four_k_two_by_three(self):
    self.assertEqual(IMAGE_CONFIG.image_size, "4K")
    self.assertEqual(IMAGE_CONFIG.aspect_ratio, "2:3")

def test_default_none_modalities_behavior_is_unchanged(self):
    self.assertIsNone(build_response_config(None))
    self.assertIsNone(build_response_config(None, response_schema=Survey))
```

- [ ] **Step 2: Replace obsolete Step 3 prompt tests with failing v3 contract tests**

In `tests/test_prompts_structure.py`, remove or rewrite tests that require exact equal pixel resolution, pure two-color raster output, or `postprocess_sketch=True`. Add the following assertions in the existing Step 3 test class:

```python
def test_step3_matches_input_aspect_without_requesting_postprocessing(self):
    step = PIPELINE_STEPS[2]
    self.assertIs(step.get("match_input_aspect_ratio"), True)
    self.assertNotIn("postprocess_sketch", step)
    self.assertIs(step.get("enabled"), False)
    self.assertIs(step.get("fresh_session"), True)
    self.assertIs(step.get("include_prev_texts"), False)

def test_step3_preserves_normalized_geometry_not_exact_pixel_dimensions(self):
    prompt = PIPELINE_STEPS[2]["prompt"]
    for phrase in (
        "입력과 같은 화면 비율",
        "프레이밍",
        "정규화 좌표",
        "x/width",
        "y/height",
        "곡률",
        "개별 부품을 이동하지 마",
    ):
        self.assertIn(phrase, prompt)
    self.assertNotIn("입력과 동일한 해상도", prompt)
    self.assertNotIn("같은 픽셀 위치", prompt)

def test_step3_requires_closed_mesh_part_perimeters(self):
    prompt = PIPELINE_STEPS[2]["prompt"]
    for phrase in (
        "메시 패턴 파트의 둘레",
        "닫힌 순환 경계",
        "정확한 접점",
        "공유 구간",
        "평행한 중복선",
        "메시 조직만 제거",
    ):
        self.assertIn(phrase, prompt)

def test_step3_keeps_round_and_elliptical_punching(self):
    prompt = PIPELINE_STEPS[2]["prompt"]
    self.assertIn("원형 또는 타원형", prompt)
    self.assertIn("닫힌 펀칭 재단선", prompt)

def test_step3_rendering_allows_only_edge_antialias_gray(self):
    prompt = PIPELINE_STEPS[2]["prompt"]
    self.assertIn("순백", prompt)
    self.assertIn("순검정", prompt)
    self.assertIn("검은 선 가장자리", prompt)
    self.assertIn("중립 회색 안티앨리어싱", prompt)
    for forbidden in ("유채색 픽셀", "회색 채움", "음영", "재질 표현"):
        self.assertIn(forbidden, prompt)
```

Retain the existing tests that reject the old instructions to draw mesh texture, stitching, letters, and material details.

- [ ] **Step 3: Run focused tests and confirm RED**

Run:

```bash
rtk pytest tests/test_survey_schema.py tests/test_prompts_structure.py -q
```

Expected: new tests fail because `build_response_config` has no `match_input_aspect_ratio` parameter, Step 3 still opts into postprocessing, and the v3 geometry/mesh wording is absent.

- [ ] **Step 4: Implement the minimal call-level image config**

In `config/gemini_config.py`, keep `IMAGE_CONFIG` and `CHAT_CONFIG` unchanged and add:

```python
INPUT_ASPECT_IMAGE_CONFIG = types.ImageConfig(image_size="4K")
```

Replace `build_response_config` with:

```python
def build_response_config(
    modalities: list[str] | None,
    response_schema=None,
    match_input_aspect_ratio: bool = False,
) -> types.GenerateContentConfig | None:
    """Build a per-step response config without changing chat defaults."""
    if not modalities and not match_input_aspect_ratio:
        return None

    effective_modalities = list(modalities or RESPONSE_MODALITIES)
    kwargs = {
        "response_modalities": effective_modalities,
        "safety_settings": SAFETY_SETTINGS,
        "temperature": 0,
    }
    if "IMAGE" in effective_modalities:
        kwargs["image_config"] = (
            INPUT_ASPECT_IMAGE_CONFIG
            if match_input_aspect_ratio
            else IMAGE_CONFIG
        )
    if response_schema is not None:
        kwargs["response_mime_type"] = "application/json"
        kwargs["response_schema"] = response_schema

    return types.GenerateContentConfig(**kwargs)
```

Do not modify `CHAT_CONFIG`; Step 2 must continue to use the existing `4K / 2:3` default.

- [ ] **Step 5: Apply the approved Step 3 prompt contract**

Keep the current JSON-like prompt structure, but make these rules explicit and remove contradictory exact-resolution wording:

```text
입력 컬러 패턴과 같은 화면 비율, 프레이밍과 캔버스 범위를 유지해.
각 재단선 점의 정규화 좌표(x/width, y/height), 곡률, 상대 길이와 부품 간 배치를 유지해.
크롭, 회전, 반전, 재배치하거나 개별 부품을 이동하지 마.

메시 조직을 제거하기 전에 메시 패턴 파트의 둘레를 하나의 닫힌 순환 경계로 식별해.
경계 끝이 전체 외곽선, 발목 부근 경계 또는 인접 파트 재단선에 닿으면 관찰된 정확한 접점까지 이어.
둘레 일부가 다른 재단선과 겹치는 공유 구간이면 그 공유 구간을 둘레의 일부로 사용하고 평행한 중복선을 만들지 마.
메시 조직만 제거하고 메시 패턴 파트 자체의 재단 경계는 제거하지 마.
실제로 가려져 관찰되지 않는 구간은 폐합을 위해 추론하지 마.

고체 패널에 독립된 원형 또는 타원형의 닫힌 펀칭 재단선은 남겨.

배경은 순백이고 재단선 중심은 순검정의 선명한 실선이어야 해.
검은 선 가장자리의 중립 회색 안티앨리어싱만 허용해.
유채색 픽셀, 회색 채움, 음영, 그림자와 재질 표현은 남기지 마.
```

Update the Step 3 self-check to verify the same conditions. Add:

```python
"match_input_aspect_ratio": True,
```

Remove:

```python
"postprocess_sketch": True,
```

Do not change `enabled`, `fresh_session`, or `include_prev_texts`.

- [ ] **Step 6: Run focused tests and confirm GREEN**

Run:

```bash
rtk pytest tests/test_survey_schema.py tests/test_prompts_structure.py -q
```

Expected: all focused tests pass without network access.

---

### Task 2: Remove raster postprocessing and preserve generated image objects unchanged

**Files:**

- Modify: `core/pipeline.py:23-33,417-428`
- Modify: `tests/test_pipeline_wiring.py:1-13,364-439`
- Delete: `utils/sketch_postprocessor.py`
- Delete: `tests/test_sketch_postprocessor.py`

**Interface:** `Pipeline._run_step` must pass `match_input_aspect_ratio` into `build_response_config` and return the same image objects supplied by `GeminiClient.send`.

- [ ] **Step 1: Replace postprocessor tests with failing pipeline contract tests**

Remove `_as_pil_image`, `postprocess_sketch`, and their tests/imports from `tests/test_pipeline_wiring.py`. Delete `tests/test_sketch_postprocessor.py` because the behavior it specifies is rejected.

Add this request-config test to `PipelineWiringTest`:

```python
def test_step3_passes_input_aspect_config_to_client(self):
    raw = MagicMock()
    step = {
        "step": 3,
        "name": "line_art_conversion",
        "description": "sketch",
        "prompt": "prompt",
        "image_path": None,
        "save_output": False,
        "match_input_aspect_ratio": True,
    }

    with patch("core.pipeline.GeminiClient") as MockClient:
        MockClient.return_value.send.return_value = StepResponse(images=[raw])
        result = Pipeline(steps=[step], output_dir=self.tmp)._run_step(step)

    config = MockClient.return_value.send.call_args.kwargs["config"]
    self.assertEqual(config.image_config.image_size, "4K")
    self.assertIsNone(config.image_config.aspect_ratio)
    self.assertIs(result.generated_images[0], raw)
```

Add this unchanged-object save test:

```python
def test_generated_image_reaches_save_and_result_unchanged(self):
    raw = MagicMock()
    step = {
        "step": 3,
        "name": "line_art_conversion",
        "description": "sketch",
        "prompt": "prompt",
        "image_path": None,
    }

    with patch("core.pipeline.GeminiClient") as MockClient:
        MockClient.return_value.send.return_value = StepResponse(images=[raw])
        pipeline = Pipeline(steps=[step], output_dir=self.tmp)
        pipeline._output_handler.save_step = MagicMock(
            return_value=Path(self.tmp) / "step.md"
        )
        result = pipeline._run_step(step)

    saved = pipeline._output_handler.save_step.call_args.kwargs["generated_images"]
    self.assertIs(saved[0], raw)
    self.assertIs(result.generated_images[0], raw)
```

- [ ] **Step 2: Run the focused test and confirm RED**

Run:

```bash
rtk pytest tests/test_pipeline_wiring.py -q
```

Expected: the config test fails because the selector is not forwarded. If the old postprocessor tests were not removed, collection or patch targets also show the obsolete dependency.

- [ ] **Step 3: Remove the postprocessor from the pipeline**

Delete this import from `core/pipeline.py`:

```python
from utils.sketch_postprocessor import postprocess_sketch, _as_pil_image
```

Change the Step 3 request construction to:

```python
step_response: StepResponse = self._client.send(
    parts,
    config=build_response_config(
        response_modalities,
        response_schema=response_schema,
        match_input_aspect_ratio=config.get(
            "match_input_aspect_ratio", False
        ),
    ),
)
```

Delete the entire mutation block:

```python
if config.get("postprocess_sketch"):
    step_response.images = [
        postprocess_sketch(_as_pil_image(image)) for image in step_response.images
    ]
```

Delete `utils/sketch_postprocessor.py`. Do not replace it with a no-op wrapper; direct object flow is the smaller and testable contract.

- [ ] **Step 4: Prove no stale postprocessing references remain**

Run:

```bash
rtk grep -n "sketch_postprocessor\|postprocess_sketch\|_as_pil_image" config core scripts tests utils
```

Expected: no matches after Task 3's runner edits are also applied. During Task 2, matches may remain only in `scripts/run_step3_on_color_patterns.py` and its test; record them as the explicit Task 3 worklist rather than adding compatibility code.

- [ ] **Step 5: Run focused tests and confirm GREEN**

Run:

```bash
rtk pytest tests/test_pipeline_wiring.py tests/test_survey_schema.py -q
```

Expected: all focused tests pass with generated image identity preserved.

---

### Task 3: Update the v3 batch runner, run regression tests, and generate twelve outputs

**Files:**

- Modify: `scripts/run_step3_on_color_patterns.py`
- Modify: `tests/test_run_step3_on_color_patterns.py`
- Runtime output only: `images/new_patterns/v3/*_sketch.png`

**Interfaces:**

- `STEP3 = next(step for step in PIPELINE_STEPS if step["name"] == "line_art_conversion")`
- `OUT_DIR = SRC_DIR / "v3"`
- `convert_one` must call Gemini with the Step 3 request config and invoke `.save(out_path)` directly on the returned image.

- [ ] **Step 1: Rewrite runner tests for direct-save v3 behavior**

Keep discovery and skip-existing coverage. Replace v2 and postprocessor assertions with:

```python
def test_routes_output_to_v3_without_touching_source(self):
    source = Path("images/new_patterns/model_color.png")
    output = runner.sketch_output_path(source, Path("images/new_patterns/v3"))
    self.assertEqual(output, Path("images/new_patterns/v3/model_sketch.png"))

def test_convert_one_passes_input_aspect_config_and_saves_raw_image(self):
    raw = Image.new("RGB", (20, 30), "blue")
    sent_configs = []

    class FakeClient:
        def start_chat(self):
            pass

        def send(self, parts, config=None):
            from core.models import StepResponse

            sent_configs.append(config)
            return StepResponse(images=[raw])

    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        source = folder / "model_color.png"
        output_dir = folder / "v3"
        Image.new("RGB", (20, 30), "white").save(source)

        with patch.object(runner, "GeminiClient", return_value=FakeClient()):
            output = runner.convert_one(source, output_dir)

        self.assertEqual(output, output_dir / "model_sketch.png")
        self.assertEqual(sent_configs[0].image_config.image_size, "4K")
        self.assertIsNone(sent_configs[0].image_config.aspect_ratio)
        self.assertEqual(Image.open(output).getpixel((10, 15)), (0, 0, 255))

def test_convert_one_does_not_regenerate_when_response_has_no_image(self):
    class FakeClient:
        def __init__(self):
            self.send_calls = 0

        def start_chat(self):
            pass

        def send(self, parts, config=None):
            from core.models import StepResponse

            self.send_calls += 1
            return StepResponse(text="no image", images=[])

    client = FakeClient()
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        source = folder / "model_color.png"
        output_dir = folder / "v3"
        Image.new("RGB", (20, 30), "white").save(source)

        with patch.object(runner, "GeminiClient", return_value=client):
            output = runner.convert_one(source, output_dir)

        self.assertIsNone(output)
        self.assertEqual(client.send_calls, 1)
        self.assertFalse((output_dir / "model_sketch.png").exists())
```

The blue fixture is deliberate: it proves the runner saves returned pixels unchanged without making a claim that a production sketch may contain color.

The no-image fixture is the content-regeneration guard: the runner records failure after one `send` call. It does not disable or test the existing transport-error retry inside `GeminiClient`.

- [ ] **Step 2: Run runner tests and confirm RED**

Run:

```bash
rtk pytest tests/test_run_step3_on_color_patterns.py -q
```

Expected: tests fail because the runner still targets `v2`, does not pass a request config, and invokes the postprocessor.

- [ ] **Step 3: Implement the minimal direct-save runner**

Replace the postprocessor import with:

```python
from config.gemini_config import build_response_config
```

Replace the constants with:

```python
SRC_DIR = Path("images/new_patterns")
OUT_DIR = SRC_DIR / "v3"
STEP3 = next(
    step for step in PIPELINE_STEPS
    if step["name"] == "line_art_conversion"
)
STEP3_PROMPT = STEP3["prompt"]
MAX_WORKERS = 6
```

Replace the send/save portion of `convert_one` with:

```python
response = client.send(
    [image, STEP3_PROMPT],
    config=build_response_config(
        None,
        match_input_aspect_ratio=STEP3.get(
            "match_input_aspect_ratio", False
        ),
    ),
)

if not response.images:
    logger.error(
        "실패(이미지 없음): %s — 응답 텍스트: %s",
        color_path.name,
        response.text[:300],
    )
    return None

response.images[0].save(out_path)
```

Do not convert the generated image through Pillow before saving, do not resize it, and do not create a `raw/` directory.

Audit the runner and Step 3 pipeline path for any pre-existing content-based quality loop. Remove a loop only if it judges the returned image and calls Gemini again because of image content. Do not remove `GeminiClient`'s existing `MAX_RETRIES` behavior for request/transport failures.

- [ ] **Step 4: Run focused and full regression tests**

Run:

```bash
rtk pytest tests/test_run_step3_on_color_patterns.py tests/test_pipeline_wiring.py tests/test_prompts_structure.py tests/test_survey_schema.py -q
rtk pytest tests/ -q
rtk git diff --check
```

Expected: all tests pass, no live API calls occur, and `git diff --check` reports no whitespace errors.

- [ ] **Step 5: Confirm the runtime target set without opening images**

Run:

```bash
rtk proxy find images/new_patterns -maxdepth 1 -type f -name '*_color.*' | sort
rtk proxy find images/new_patterns -maxdepth 1 -type f -name '*_color.*' | wc -l
```

Expected count: `12`. If it is not 12, stop before any API call and report the discovered names and count; do not broaden discovery or regenerate colors.

- [ ] **Step 6: Generate all twelve v3 outputs**

Run:

```bash
rtk proxy uv run python scripts/run_step3_on_color_patterns.py
```

Expected process result: exit status `0`, log summary `완료 12개 / 실패 0개`. Existing v3 files are skipped by the runner; if the user requires a clean rerun later, request explicit permission before removing them.

- [ ] **Step 7: Verify only names, count, and metadata**

Run:

```bash
rtk proxy find images/new_patterns/v3 -maxdepth 1 -type f -name '*_sketch.png' | sort
rtk proxy find images/new_patterns/v3 -maxdepth 1 -type f -name '*_sketch.png' | wc -l
rtk proxy file images/new_patterns/v3/*_sketch.png
```

Expected count: `12`; every file is recognized as an image. Do not use `view_image`, Finder Preview, browser display, Pillow pixel analysis, screenshots, overlays, perceptual hashes, or any other content inspection.

- [ ] **Step 8: Run fresh final verification**

Run:

```bash
rtk pytest tests/ -q
rtk grep -n "sketch_postprocessor\|postprocess_sketch\|_as_pil_image\|quality_gate\|visual_retry\|retry_on_quality" config core scripts tests utils
rtk git status --short
rtk git diff --check
```

Expected: tests pass; stale postprocessing and content-quality retry search has no matches; the runner's no-image test proves exactly one direct `send` call; only intended source/test/doc changes and uncommitted v3 runtime outputs appear in status; diff check is clean. Existing transport-failure retry constants and logic may remain because they are intentionally outside this search and scope.

---

## Whole-Change Review

The reviewer must inspect code and tests only, never generated image contents. Review the complete diff against these binding checks:

- Step 1–2 still use the existing global `4K / 2:3` configuration.
- Step 3 explicitly requests `4K` with no `aspect_ratio` field.
- `build_response_config(None, match_input_aspect_ratio=True)` returns an IMAGE config instead of falling back to `CHAT_CONFIG`.
- Default `build_response_config(None)` and schema behavior remain backward compatible.
- Step 3 retains `enabled=False`, `fresh_session=True`, and `include_prev_texts=False`.
- The prompt prioritizes input aspect, framing, normalized coordinates, curvature, part placement, and observed topology over exact pixel dimensions.
- Mesh part boundaries form an observed closed cycle, reach exact observed contacts, and use shared outer/adjacent cutting-line segments without adding duplicate parallel lines.
- Circular and elliptical punching are explicit keep cases.
- Hidden or ambiguous lines are not inferred.
- No raster postprocessor, forced resize, raw/final duplication, visual quality gate, or content-based automatic regeneration remains; transport-error retry is unchanged.
- Pipeline and runner save the generated image object without pixel mutation.
- Batch input remains the twelve existing `_color` files and output routes only to `images/new_patterns/v3/`.
- Tests make no live API calls.
- Implementer and reviewer do not open or visually judge v3 outputs.
- No unrelated user edits are reverted or included.

Send every Critical or Important finding to the same implementer. Repeat the fix and whole-change review no more than three times. After the third round, report any load-bearing remainder as blocked.

## Human Handoff

After automated verification, report only:

- exact test command and pass count;
- generation command exit status and `완료/실패` counts;
- the twelve output filenames and metadata;
- confirmation that no agent inspected image contents;
- the path `images/new_patterns/v3/` for user review.

Do not claim that lines are smooth, colors are absent, mesh boundaries are closed, or pixel alignment is visually correct. Those are human review decisions.
