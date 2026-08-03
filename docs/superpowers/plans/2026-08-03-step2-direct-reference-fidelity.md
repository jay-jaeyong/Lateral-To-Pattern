# Step 2 Direct Reference Fidelity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development to implement this plan task-by-task. The orchestrator executes all three tasks with one worker, then runs one whole-change review.

**Goal:** Re-send the exact Step 1 shoe reference parts in the Step 2 `gemini-3-pro-image` request, replace product-specific prompt assumptions with a dynamic generic specification, and apply image-generation settings suited to the portrait pattern task.

**Architecture:** `Pipeline` captures the label and `PIL.Image` parts from the actual Step 1 request and passes them to `build_step_parts` only for steps declaring `reuse_initial_references`. The parts builder places those references before a newly labelled guide image, then inserts the prior text specification and current prompt. Prompt configuration remains data-driven; no shoe-specific features are hardcoded.

**Tech Stack:** Python 3.11+, `unittest`, Pillow, `google-genai` 2.15.0.

## Global Constraints

- Use only `gemini-3-pro-image`; do not introduce another generation or vision model.
- Do not add dependencies.
- Keep folder input, CLI view flags, batch execution, and single-image input working.
- Do not implement the Gemini QA or automatic regeneration stage.
- Preserve the user's unrelated `.gitignore` modification; never stage or revert it.
- Follow strict red-green TDD for every production behavior change.

---

### Task 1: Assemble Step 2 reference and guide parts in a deterministic order

**Files:**
- Modify: `core/_parts_builder.py:25-154`
- Test: `tests/test_labeled_parts.py:82-115`

**Interfaces:**
- Consumes: `initial_reference_parts: list | None`, containing the exact label strings and `PIL.Image` objects used by Step 1.
- Produces: `build_step_parts(..., initial_reference_parts=None) -> list`.
- Ordering contract: initial references → `[가이드라인]` → guide image → previous text → current prompt.

- [ ] **Step 1: Write failing tests for reference and guide ordering**

Add tests equivalent to:

```python
def test_initial_references_precede_guide_and_previous_text(self):
    reference = Image.new("RGB", (4, 4), "red")
    guide = make_png(self.tmp / "guide.png")

    parts = build_step_parts(
        step_num=2,
        prompt="PROMPT",
        image_path=None,
        prev_images=[],
        prev_texts=["SPEC"],
        guide_image_path=guide,
        initial_reference_parts=["[사진 1] 바깥쪽 측면(lateral)", reference],
    )

    self.assertEqual(parts[0], "[사진 1] 바깥쪽 측면(lateral)")
    self.assertIs(parts[1], reference)
    self.assertEqual(parts[2], "[가이드라인]")
    self.assertIsInstance(parts[3], Image.Image)
    self.assertEqual(parts[4], "[Previous Step 1 Output]\nSPEC")
    self.assertEqual(parts[5], "PROMPT")
```

Add a second test proving that mutating the returned list does not mutate the caller-owned `initial_reference_parts` list.

- [ ] **Step 2: Run the focused tests and confirm RED**

Run:

```bash
rtk test .venv/bin/python -m unittest tests.test_labeled_parts.BuildStepPartsTest -v
```

Expected: failure because `build_step_parts` does not accept `initial_reference_parts` and the guide has no label.

- [ ] **Step 3: Implement the minimum parts-builder change**

Extend `build_step_parts` with:

```python
initial_reference_parts: list | None = None,
```

Copy and prepend those parts before guide insertion:

```python
if initial_reference_parts:
    parts = [*initial_reference_parts, *parts]
```

Change guide insertion to insert:

```python
["[가이드라인]", *guides]
```

Do not add a new abstraction unless the existing `_insert_before_prompt` helper cannot express the ordering.

- [ ] **Step 4: Run focused tests and confirm GREEN**

Run:

```bash
rtk test .venv/bin/python -m unittest tests.test_labeled_parts -v
```

Expected: all tests in `tests.test_labeled_parts` pass.

- [ ] **Step 5: Commit Task 1**

```bash
rtk git add core/_parts_builder.py tests/test_labeled_parts.py
rtk git commit -m "feat: assemble Step 2 reference parts"
```

---

### Task 2: Capture Step 1 references and require them in Step 2

**Files:**
- Modify: `core/pipeline.py:41-67,293-330`
- Test: `tests/test_pipeline_wiring.py:21-157`

**Interfaces:**
- Consumes: `config["reuse_initial_references"]`, defaulting to `False`.
- Produces: `Pipeline._initial_reference_parts: list`.
- Calls: `build_step_parts(..., initial_reference_parts=...)`.
- Failure contract: a step requiring references raises `RuntimeError` before its Gemini `send` call if no `PIL.Image` reference was captured.

- [ ] **Step 1: Write a failing integration test for exact reference replay**

Construct Step 1 with two `view_images`, Step 2 with a guide and
`reuse_initial_references=True`, and a mocked external Gemini client.
After `pipeline.run(skip_initial_selection=True)`, inspect the second
`send` call and assert:

```python
self.assertEqual(parts[0], "[사진 1] 바깥쪽 측면(lateral)")
self.assertIsInstance(parts[1], Image.Image)
self.assertEqual(parts[2], "[사진 2] 안쪽 측면(medial)")
self.assertIsInstance(parts[3], Image.Image)
self.assertEqual(parts[4], "[가이드라인]")
self.assertIsInstance(parts[5], Image.Image)
self.assertIn(step1_text, parts[6])
self.assertEqual(parts[7], "STEP 2 PROMPT")
```

Use real temporary images and mock only `GeminiClient`, the external API boundary.

- [ ] **Step 2: Write a failing test for missing required references**

Create Step 1 with `image_path=None` and Step 2 with
`reuse_initial_references=True`. Assert:

```python
with self.assertRaisesRegex(RuntimeError, "실물 참조 이미지"):
    pipeline.run(skip_initial_selection=True)
self.assertEqual(mock_instance.send.call_count, 1)
```

This proves the expensive Step 2 API call is not made without its source images.

- [ ] **Step 3: Run the focused tests and confirm RED**

Run:

```bash
rtk test .venv/bin/python -m unittest tests.test_pipeline_wiring.PipelineWiringTest -v
```

Expected: the replay test lacks the Step 1 images and the missing-reference test does not raise.

- [ ] **Step 4: Implement reference capture and replay**

Replace the unused label-free `_initial_images` field with:

```python
self._initial_reference_parts: list = []
```

After Step 1 parts are assembled, capture a shallow copy of every part before
the final prompt:

```python
if step_num == 1:
    self._initial_reference_parts = list(parts[:-1])
```

Before assembling a step with `reuse_initial_references=True`, require at least
one `PILImage.Image`:

```python
reuse_initial_references = config.get("reuse_initial_references", False)
initial_reference_parts = (
    self._initial_reference_parts if reuse_initial_references else []
)
if reuse_initial_references and not any(
    isinstance(part, PILImage.Image) for part in initial_reference_parts
):
    raise RuntimeError("Step 2에 재사용할 실물 참조 이미지가 없습니다.")
```

Pass `initial_reference_parts` to `build_step_parts`. Perform this validation
outside the broad parts-assembly fallback so the error cannot be converted to
a prompt-only API request.

- [ ] **Step 5: Run focused and adjacent tests and confirm GREEN**

Run:

```bash
rtk test .venv/bin/python -m unittest \
  tests.test_pipeline_wiring \
  tests.test_folder_labels_and_batch \
  tests.test_cli_view_flags -v
```

Expected: all selected tests pass.

- [ ] **Step 6: Commit Task 2**

```bash
rtk git add core/pipeline.py tests/test_pipeline_wiring.py
rtk git commit -m "feat: replay initial references in Step 2"
```

---

### Task 3: Make prompts generic and apply Gemini 3 image settings

**Files:**
- Modify: `config/prompts.py:1-365`
- Modify: `config/gemini_config.py:13-86`
- Modify: `tests/test_prompts_structure.py:10-250`
- Modify: `tests/test_response_config.py:10-25`

**Interfaces:**
- Produces: `PIPELINE_STEPS[1]["reuse_initial_references"] is True`.
- Produces: Step 1 specification fields `component`, `presence`,
  `lateral_geometry`, `medial_geometry`, `topology`, `count_per_side`,
  `attachment`, `landmarks`, `source_views`, `confidence`, and
  `critical_features`.
- Produces: generic Step 2 priorities where current-turn photos override the
  text specification and the guide controls only outer shape/orientation.
- Produces: `IMAGE_CONFIG.aspect_ratio == "2:3"` and high media resolution
  without an explicit temperature.

- [ ] **Step 1: Replace history-reliance assertions with failing direct-reference assertions**

Update the pipeline shape test to assert:

```python
unfold = PIPELINE_STEPS[1]
self.assertTrue(unfold["reuse_initial_references"])
self.assertIsNone(unfold["image_path"])
self.assertIsNotNone(unfold["guide_image_path"])
```

Add prompt-contract tests that assert the Step 1 fields above are requested,
that bilateral components are not represented as two `한쪽만` components, and
that `critical_features` are generated dynamically.

Add Step 2 prompt tests that assert:

```python
self.assertIn("현재 요청에 첨부된 실물 사진", unfold_prompt)
self.assertIn("명세서가 사진과 충돌", unfold_prompt)
self.assertIn("통합·치환·단순화하지", unfold_prompt)
self.assertIn("바깥 재단선", unfold_prompt)
for product_specific in ("adistar", "파란 케이지", "검정 프레임", "파란 슬롯"):
    self.assertNotIn(product_specific, unfold_prompt.lower())
```

Delete or rewrite brittle tests whose only purpose is to preserve the old
19-block prompt. Keep behaviorally important checks for orientation, exclusions,
flat output, white background, bonding, landmarks, view labels, and pair handling.

- [ ] **Step 2: Add failing configuration tests**

Extend `tests/test_response_config.py`:

```python
from google.genai import types
from config.gemini_config import CHAT_CONFIG

def test_image_output_is_portrait_two_to_three(self):
    self.assertEqual(IMAGE_CONFIG.aspect_ratio, "2:3")

def test_default_chat_uses_high_media_resolution_and_default_temperature(self):
    self.assertEqual(
        CHAT_CONFIG.media_resolution,
        types.MediaResolution.MEDIA_RESOLUTION_HIGH,
    )
    self.assertIsNone(CHAT_CONFIG.temperature)

def test_text_override_keeps_high_media_resolution_and_default_temperature(self):
    config = build_response_config(["TEXT"])
    self.assertEqual(
        config.media_resolution,
        types.MediaResolution.MEDIA_RESOLUTION_HIGH,
    )
    self.assertIsNone(config.temperature)
```

- [ ] **Step 3: Run prompt/config tests and confirm RED**

Run:

```bash
rtk test .venv/bin/python -m unittest \
  tests.test_prompts_structure \
  tests.test_response_config -v
```

Expected: failures for the missing reuse flag, missing generic specification
fields, old product-oriented wording, automatic aspect ratio, missing media
resolution, and explicit zero temperature.

- [ ] **Step 4: Rewrite the prompts and configuration minimally**

In `config/prompts.py`:

- Update the module data-flow comment to show Step 2 receives the labelled
  shoe views again.
- Keep Step 1 text-only and multi-view.
- Require the generic fields and dynamic `critical_features` from the design
  spec.
- Replace the long Step 2 prompt with the six generic priorities in the design
  spec while retaining essential orientation, exclusion, flatness, background,
  pair, bonding, and landmark constraints.
- Add `"reuse_initial_references": True` to `pattern_unfold`.
- Remove the obsolete comments saying Step 2 relies on chat history.

In `config/gemini_config.py`:

```python
IMAGE_CONFIG = types.ImageConfig(
    image_size="4K",
    aspect_ratio="2:3",
)

CHAT_CONFIG = types.GenerateContentConfig(
    response_modalities=RESPONSE_MODALITIES,
    image_config=IMAGE_CONFIG,
    media_resolution=types.MediaResolution.MEDIA_RESOLUTION_HIGH,
    safety_settings=SAFETY_SETTINGS,
)
```

Add the same `media_resolution` to `build_response_config` and omit
`temperature` from its kwargs.

- [ ] **Step 5: Run focused tests and confirm GREEN**

Run:

```bash
rtk test .venv/bin/python -m unittest \
  tests.test_prompts_structure \
  tests.test_response_config -v
```

Expected: all prompt and response-config tests pass.

- [ ] **Step 6: Run the full suite**

Run:

```bash
rtk test .venv/bin/python -m unittest discover -s tests -v
```

Expected: all tests pass with zero failures.

- [ ] **Step 7: Commit Task 3**

```bash
rtk git add \
  config/prompts.py \
  config/gemini_config.py \
  tests/test_prompts_structure.py \
  tests/test_response_config.py
rtk git commit -m "feat: generalize pattern fidelity prompts"
```

## Final verification

Run:

```bash
rtk git diff --check HEAD~3..HEAD
rtk test .venv/bin/python -m unittest discover -s tests -v
rtk git status --short
```

Expected:

- no whitespace errors;
- all tests pass;
- only the user's pre-existing `.gitignore` modification remains unstaged;
- no QA or automatic regeneration code exists.
