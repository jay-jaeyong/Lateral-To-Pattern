# Sketch Pattern V2 Implementation Plan

> **Superseded:** 이 계획의 래스터 후처리와 `images/new_patterns/v2/` 재생성 방안은 폐기되었다. 최신 실행 계획은 `docs/superpowers/plans/2026-08-21-sketch-pattern-v3-implementation.md`를 따른다.

> **For agentic workers:** Execute all three tasks with one Codex worker using `model: gpt-5.6-luna`, `reasoningEffort: xhigh`. After all tasks pass, review the entire change with one Codex reviewer using `model: gpt-5.6-terra`, `reasoningEffort: high`. Use at most three fix/review rounds. Follow TDD for every production change.

**Goal:** Generate twelve v2 sketch-pattern images whose prompt preserves observable cutting-line topology and whose deterministic postprocessor removes broad black, gray, and colored fills while retaining crisp black cutting lines on white.

**Architecture:** Keep semantic classification in the Step 3 Gemini prompt and add one Pillow-only raster postprocessor for the deterministic black/white invariant. The pipeline and the standalone batch script call the same pure postprocessor before saving. Existing sketches remain untouched; future sample output goes to `images/new_patterns/v2/`, and agents verify only command success and file existence—not image content.

**Tech Stack:** Python 3.11+, Pillow, `unittest`/pytest-compatible tests, existing Gemini client and pipeline

**Spec:** `docs/superpowers/specs/2026-08-21-sketch-pattern-cut-line-extraction-design.md`

## Execution Mode

- Task count: **3**
- Mode: **single-worker mode**
- Implementation owner: one Codex worker, `gpt-5.6-luna`, `xhigh`
- Review owner: one Codex reviewer over Tasks 1–3 together, `gpt-5.6-terra`, `high`
- Review cap: three fix/review rounds; unresolved findings after round three are reported instead of opening round four

## Global Constraints

- The worker is not alone in the repository. Preserve all existing user and agent edits; do not revert unrelated changes.
- Build on the current uncommitted changes in `config/prompts.py`, `tests/test_prompts_structure.py`, `CONTEXT.md`, `docs/source_of_truth.md`, the design spec, and `scripts/run_step3_on_color_patterns.py`.
- Use `rtk`-prefixed shell commands by default. Use CodeGraph before repository code search or code reading while `.codegraph/` exists.
- Use tests first: add a failing test, run it and confirm the expected failure, implement the smallest change, then rerun the focused test and full suite.
- Do not add dependencies. Use Pillow, which is already installed.
- Keep Step 3 `enabled=False`, `include_prev_texts=False`, and `fresh_session=True`.
- Do not add a quality gate, rejection path, or automatic Gemini retry for visual quality.
- Preserve the input canvas dimensions. Do not crop, resize, rotate, reflect, or move parts.
- At `3392×5056`, use a nominal 5px line width and 5px fill-detection erosion radius. Scale with the short side and round the line width to the nearest usable odd filter size so Pillow can center the stroke.
- The final postprocessed image may contain only exact white `#FFFFFF` and exact black `#000000` pixels.
- A broad fill includes black, gray, and chromatic fills. Hollow the interior and keep its boundary.
- Preserve observable topology: the outside cutting line is closed; an internal cutting line is closed or ends at another observed cutting line. Do not invent a genuinely hidden or unobservable segment.
- Preserve mesh-material pattern-part boundaries; remove only the repeated mesh texture inside the part.
- Preserve clearly identifiable circular and elliptical punching cut lines.
- Save regenerated files under `images/new_patterns/v2/`; never overwrite existing files directly under `images/new_patterns/`.
- Generate all twelve `_color` inputs only after code and tests pass.
- No agent may open, inspect, compare, score, or visually review generated v2 images. The user alone reviews image content.
- Agent verification of generation is limited to process exit status, count of output files, filenames, and filesystem metadata.

## File Map

| File | Responsibility |
|---|---|
| `config/prompts.py` | Step 3 semantic rules and `postprocess_sketch=True` opt-in |
| `tests/test_prompts_structure.py` | Regression coverage for the Step 3 prompt contract |
| `utils/sketch_postprocessor.py` | Pure Pillow conversion from generated image to binary line-only image |
| `tests/test_sketch_postprocessor.py` | Synthetic raster tests for fill removal, binary palette, topology, and geometry |
| `core/pipeline.py` | Apply the shared postprocessor to opted-in step responses before saving/forwarding |
| `tests/test_pipeline_wiring.py` | Verify the Step 3 response is postprocessed before storage and result propagation |
| `scripts/run_step3_on_color_patterns.py` | Read twelve source images, call Gemini, postprocess, and save under `v2/` |
| `tests/test_run_step3_on_color_patterns.py` | Batch discovery, output routing, and postprocessor wiring tests without API access |

---

### Task 1: Correct the Step 3 prompt contract

**Files:**

- Modify: `config/prompts.py:474-568`
- Modify: `tests/test_prompts_structure.py` in `SketchPatternContractTest`

**Interfaces:**

- Consumes: `PIPELINE_STEPS[2]`, the existing `line_art_conversion` step
- Produces: a Step 3 configuration whose prompt contains the finalized semantic rules and whose config contains `postprocess_sketch: True`

- [ ] **Step 1: Add failing prompt tests for the new feedback**

Add focused methods to `SketchPatternContractTest`:

```python
def test_preserves_observed_cut_line_topology(self):
    sketch = self.sketch()
    self.assertIn("전체 외곽 재단선은 완전히 닫힌", sketch)
    self.assertIn("내부 재단선은 닫힌 루프", sketch)
    self.assertIn("다른 식별된 재단선에 정확히 닿아", sketch)
    self.assertIn("생성 과정에서 생긴 틈", sketch)
    self.assertNotIn("끊어진 선을 잇거나 가려진 부분을 완성하지 마", sketch)

def test_keeps_mesh_part_boundaries_but_removes_mesh_texture(self):
    sketch = self.sketch()
    self.assertIn("메시 패턴 파트의 재단선", sketch)
    self.assertIn("다른 패턴 파트와 맞닿는지와 관계없이", sketch)
    self.assertIn("메시 조직의 반복 무늬만 제거", sketch)
    self.assertIn("발목", sketch)

def test_keeps_circular_and_elliptical_punching(self):
    sketch = self.sketch()
    self.assertIn("원형 또는 타원형", sketch)
    self.assertIn("닫힌 펀칭 재단선", sketch)

def test_forbids_every_color_fill_and_faint_cut_lines(self):
    sketch = self.sketch()
    self.assertIn("검정·회색·유채색 채움", sketch)
    self.assertIn("순백(#FFFFFF)", sketch)
    self.assertIn("순검정(#000000)", sketch)
    self.assertIn("흐릿", sketch)

def test_enables_shared_sketch_postprocessing(self):
    self.assertIs(PIPELINE_STEPS[2].get("postprocess_sketch"), True)
```

- [ ] **Step 2: Run the focused tests and confirm RED**

Run:

```bash
rtk pytest tests/test_prompts_structure.py -q
```

Expected: the new tests fail because the current prompt removes mesh too broadly, recognizes only a generic closed hole, forbids joining all broken lines without preserving observed topology, and does not opt into postprocessing.

- [ ] **Step 3: Replace contradictory prompt clauses with the approved rules**

Make these minimal edits inside Step 3:

1. Change the priority block to six ordered rules:

```text
1순위 — 입력과 같은 해상도와 화면 비율로, 입력과 같은 캔버스 범위와 좌표계에 그린다
2순위 — 확실하게 식별되는 재단선만 남긴다
3순위 — 입력에서 관찰되는 재단선 연결 관계와 닫힌 외곽선을 보존한다
4순위 — 불확실하거나 실제로 가려진 선은 제거하고 추론해서 복원하지 않는다
5순위 — 재단선이 아닌 모든 요소를 제거한다
6순위 — 남은 재단선을 순백(#FFFFFF) 배경 위의 선명한 순검정(#000000) 실선으로 그린다
```

2. Replace `"끊어진 선을 잇거나 가려진 부분을 완성하지 마"` with all four clauses:

```text
컬러 패턴에서 서로 맞닿은 재단선은 스케치 패턴에서도 같은 위치에서 정확히 맞닿게 유지해
전체 패턴의 외곽 재단선은 완전히 닫힌 선이어야 해
내부 재단선은 닫힌 루프이거나 다른 식별된 재단선에 정확히 닿아 끝나야 해. 허공에서 끝내지 마
생성 과정에서 생긴 틈이나 끊김은 남기지 마. 다만 입력에서 실제로 가려졌거나 식별되지 않는 구간을 추론해 만들지는 마
```

3. Add to `keep_rule`:

```text
메시 패턴 파트의 재단선 — 메시 조직의 반복 무늬만 제거하고, 메시 원단이 위치할 영역의 경계는 다른 패턴 파트와 맞닿는지와 관계없이 남겨
발목 부근에 닿는 메시 패턴 파트 경계 — 발목 재단선과의 관찰된 접점을 끊지 마
원형 또는 타원형의 닫힌 펀칭 재단선 — 형태가 원이 아니어도 타원이면 남겨
```

4. Narrow the mesh removal rule to:

```text
메시 패턴 파트 내부의 촘촘한 메시 조직, 니트, 격자, 엠보싱, 원단결 같은 반복 표면 무늬와 질감만 제거해. 메시 패턴 파트 자체의 재단 경계는 제거하지 마
```

5. Add to `render_rule` and `self_check`:

```text
순백(#FFFFFF)과 순검정(#000000) 이외의 색상 픽셀을 남기지 마
재단선은 흐릿한 회색이나 반투명 선이 아니라 선명한 검은 실선이어야 해
전체 외곽선이 닫혀 있고 모든 내부 재단선이 닫힌 루프 또는 다른 재단선과의 접점에서 끝나는가
메시 조직만 사라지고 메시 패턴 파트의 재단선과 발목 경계의 접점은 남아 있는가
원형과 타원형 펀칭이 모두 닫힌 재단선으로 남아 있는가
```

6. Add the step-level flag without changing `enabled`, `include_prev_texts`, or `fresh_session`:

```python
"postprocess_sketch": True,
```

- [ ] **Step 4: Run focused and structural tests and confirm GREEN**

Run:

```bash
rtk pytest tests/test_prompts_structure.py -q
```

Expected: all prompt structure tests pass.

- [ ] **Step 5: Commit Task 1**

```bash
rtk git add config/prompts.py tests/test_prompts_structure.py
rtk git commit -m "fix: preserve sketch pattern cutting boundaries"
```

---

### Task 2: Add the deterministic sketch postprocessor

**Files:**

- Create: `utils/sketch_postprocessor.py`
- Create: `tests/test_sketch_postprocessor.py`

**Interfaces:**

- Consumes: `PIL.Image.Image`
- Produces: `scaled_line_width(size: tuple[int, int]) -> int`, always a positive odd integer
- Produces: `postprocess_sketch(image: Image.Image, line_width: int | None = None) -> Image.Image`
- Guarantee: output size equals input size; output mode is `RGB`; every output channel value is either `0` or `255`

- [ ] **Step 1: Write synthetic failing tests**

Create `tests/test_sketch_postprocessor.py` with small, deterministic images. Use `line_width=3` so tests do not depend on 4K fixtures and Pillow receives an odd filter size.

```python
import unittest

from PIL import Image, ImageDraw

from utils.sketch_postprocessor import postprocess_sketch, scaled_line_width


class SketchPostprocessorTest(unittest.TestCase):
    def test_scales_five_pixels_from_reference_short_side(self):
        self.assertEqual(scaled_line_width((3392, 5056)), 5)
        self.assertEqual(scaled_line_width((6784, 10112)), 11)

    def test_hollows_black_gray_and_colored_fills(self):
        image = Image.new("RGB", (80, 40), "white")
        draw = ImageDraw.Draw(image)
        draw.rectangle((5, 5, 24, 34), fill="black")
        draw.rectangle((30, 5, 49, 34), fill=(120, 120, 120))
        draw.rectangle((55, 5, 74, 34), fill=(20, 80, 220))

        result = postprocess_sketch(image, line_width=3)

        for point in ((14, 20), (39, 20), (64, 20)):
            self.assertEqual(result.getpixel(point), (255, 255, 255))
        for point in ((5, 20), (30, 20), (55, 20)):
            self.assertEqual(result.getpixel(point), (0, 0, 0))

    def test_preserves_thin_connected_lines(self):
        image = Image.new("RGB", (50, 50), "white")
        draw = ImageDraw.Draw(image)
        draw.line((5, 25, 45, 25), fill=(100, 100, 100), width=1)
        draw.line((25, 5, 25, 45), fill=(10, 10, 10), width=1)

        result = postprocess_sketch(image, line_width=3)

        self.assertEqual(result.getpixel((25, 25)), (0, 0, 0))
        self.assertEqual(result.getpixel((5, 25)), (0, 0, 0))
        self.assertEqual(result.getpixel((25, 5)), (0, 0, 0))

    def test_preserves_closed_circle_and_ellipse(self):
        image = Image.new("RGB", (80, 50), "white")
        draw = ImageDraw.Draw(image)
        draw.ellipse((5, 10, 25, 30), outline="black", width=1)
        draw.ellipse((35, 10, 70, 30), outline="black", width=1)

        result = postprocess_sketch(image, line_width=3)

        self.assertEqual(result.getpixel((5, 20)), (0, 0, 0))
        self.assertEqual(result.getpixel((15, 10)), (0, 0, 0))
        self.assertEqual(result.getpixel((35, 20)), (0, 0, 0))
        self.assertEqual(result.getpixel((52, 10)), (0, 0, 0))

    def test_output_is_binary_rgb_with_unchanged_canvas(self):
        image = Image.new("RGB", (31, 47), (240, 200, 120))
        result = postprocess_sketch(image, line_width=3)

        self.assertEqual(result.size, image.size)
        self.assertEqual(result.mode, "RGB")
        self.assertLessEqual(set(result.getdata()), {(0, 0, 0), (255, 255, 255)})


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the new test and confirm RED**

Run:

```bash
rtk pytest tests/test_sketch_postprocessor.py -q
```

Expected: collection fails because `utils.sketch_postprocessor` does not exist.

- [ ] **Step 3: Implement the Pillow-only postprocessor**

Create `utils/sketch_postprocessor.py` with these constants and signatures:

```python
from __future__ import annotations

from PIL import Image, ImageChops, ImageFilter

REFERENCE_SHORT_SIDE = 3392
REFERENCE_LINE_WIDTH = 5
WHITE_THRESHOLD = 250


def scaled_line_width(size: tuple[int, int]) -> int:
    width = max(1, round(min(size) * REFERENCE_LINE_WIDTH / REFERENCE_SHORT_SIDE))
    return width if width % 2 else width + 1


def _nonwhite_mask(image: Image.Image) -> Image.Image:
    red, green, blue = image.convert("RGB").split()
    darkest = ImageChops.darker(red, ImageChops.darker(green, blue))
    return darkest.point(lambda value: 255 if value < WHITE_THRESHOLD else 0)


def _skeletonize(mask: Image.Image) -> Image.Image:
    current = mask
    skeleton = Image.new("L", mask.size, 0)
    while current.getbbox() is not None:
        eroded = current.filter(ImageFilter.MinFilter(3))
        opened = eroded.filter(ImageFilter.MaxFilter(3))
        skeleton = ImageChops.lighter(
            skeleton,
            ImageChops.subtract(current, opened),
        )
        current = eroded
    return skeleton


def postprocess_sketch(
    image: Image.Image,
    line_width: int | None = None,
) -> Image.Image:
    width = line_width or scaled_line_width(image.size)
    ink = _nonwhite_mask(image)
    core = ink.filter(ImageFilter.MinFilter(width * 2 + 1))
    retained_lines = ImageChops.subtract(ink, core)
    centerlines = _skeletonize(retained_lines)
    normalized_lines = centerlines.filter(ImageFilter.MaxFilter(width))

    white = Image.new("L", image.size, 255)
    white.paste(0, mask=normalized_lines)
    return Image.merge("RGB", (white, white, white))
```

This implementation deliberately stops at the first ponytail rung that satisfies the approved rule: Pillow morphology distinguishes regions with a surviving interior core from thin strokes, reduces retained strokes to their centerlines, then expands them to one odd target width. Hollowing bounds the stroke thickness before skeletonization, so the loop is limited by the nominal line width rather than the diameter of a large filled panel. It adds no OpenCV/NumPy dependency and does not infer semantic geometry.

- [ ] **Step 4: Run the focused test and confirm GREEN**

Run:

```bash
rtk pytest tests/test_sketch_postprocessor.py -q
```

Expected: all postprocessor tests pass.

- [ ] **Step 5: Run the full suite**

Run:

```bash
rtk pytest tests/ -q
```

Expected: all existing and new tests pass.

- [ ] **Step 6: Commit Task 2**

```bash
rtk git add utils/sketch_postprocessor.py tests/test_sketch_postprocessor.py
rtk git commit -m "feat: hollow sketch fills with pillow"
```

---

### Task 3: Wire postprocessing into Step 3 and the twelve-image batch runner

**Files:**

- Modify: `core/pipeline.py:416-453`
- Modify: `scripts/run_step3_on_color_patterns.py`
- Modify: `tests/test_pipeline_wiring.py`
- Create: `tests/test_run_step3_on_color_patterns.py`
- Runtime output only: `images/new_patterns/v2/*_sketch.png`

**Interfaces:**

- Consumes: `postprocess_sketch(image: Image.Image, line_width: int | None = None) -> Image.Image` from Task 2
- Consumes: `PIPELINE_STEPS[2]["postprocess_sketch"] is True` from Task 1
- Produces: postprocessed `StepResponse.images` before `OutputHandler.save_step` and `StepResult`
- Produces: `find_color_patterns(folder: Path) -> list[Path]`
- Produces: `sketch_output_path(color_path: Path, output_dir: Path) -> Path`
- Produces: twelve files under `images/new_patterns/v2/` when the batch command is run

- [ ] **Step 1: Add failing pipeline and batch-routing tests**

In `tests/test_pipeline_wiring.py`, add these two tests to `PipelineWiringTest`:

```python
def test_opted_in_step_postprocesses_before_save_and_result(self):
    raw = Image.new("RGB", (8, 8), "blue")
    processed = Image.new("RGB", (8, 8), "white")
    step = {
        "step": 3,
        "name": "line_art_conversion",
        "description": "sketch",
        "prompt": "prompt",
        "image_path": None,
        "postprocess_sketch": True,
    }

    with patch("core.pipeline.GeminiClient") as MockClient, patch(
        "core.pipeline.postprocess_sketch", return_value=processed
    ) as postprocess:
        MockClient.return_value.send.return_value = StepResponse(images=[raw])
        pipeline = Pipeline(steps=[step], output_dir=self.tmp)
        pipeline._output_handler.save_step = MagicMock(return_value=self.tmp / "step.md")

        result = pipeline._run_step(step)

    postprocess.assert_called_once_with(raw)
    saved = pipeline._output_handler.save_step.call_args.kwargs["generated_images"]
    self.assertIs(saved[0], processed)
    self.assertIs(result.generated_images[0], processed)

def test_unflagged_step_keeps_original_generated_image(self):
    raw = Image.new("RGB", (8, 8), "blue")
    step = {
        "step": 2,
        "name": "pattern_unfold",
        "description": "color",
        "prompt": "prompt",
        "image_path": None,
        "save_output": False,
    }

    with patch("core.pipeline.GeminiClient") as MockClient, patch(
        "core.pipeline.postprocess_sketch"
    ) as postprocess:
        MockClient.return_value.send.return_value = StepResponse(images=[raw])
        pipeline = Pipeline(steps=[step], output_dir=self.tmp)

        result = pipeline._run_step(step)

    postprocess.assert_not_called()
    self.assertIs(result.generated_images[0], raw)
```

Create `tests/test_run_step3_on_color_patterns.py`:

```python
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from scripts import run_step3_on_color_patterns as runner


class Step3BatchRunnerTest(unittest.TestCase):
    def test_discovers_only_color_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            Image.new("RGB", (2, 2), "white").save(folder / "a_color.png")
            Image.new("RGB", (2, 2), "white").save(folder / "a_sketch.png")
            self.assertEqual(
                [path.name for path in runner.find_color_patterns(folder)],
                ["a_color.png"],
            )

    def test_routes_output_to_v2_without_touching_source(self):
        source = Path("images/new_patterns/model_color.png")
        output = runner.sketch_output_path(source, Path("images/new_patterns/v2"))
        self.assertEqual(output, Path("images/new_patterns/v2/model_sketch.png"))

    def test_convert_one_postprocesses_before_save(self):
        raw = Image.new("RGB", (20, 20), "blue")
        processed = Image.new("RGB", (20, 20), "white")

        class FakeClient:
            def start_chat(self):
                pass

            def send(self, parts):
                from core.models import StepResponse
                return StepResponse(images=[raw])

        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            source = folder / "model_color.png"
            output_dir = folder / "v2"
            Image.new("RGB", (20, 20), "white").save(source)
            with patch.object(runner, "GeminiClient", return_value=FakeClient()), patch.object(
                runner, "postprocess_sketch", return_value=processed
            ) as postprocess:
                output = runner.convert_one(source, output_dir)

            self.assertIs(postprocess.call_args.args[0], raw)
            self.assertEqual(output, output_dir / "model_sketch.png")
            self.assertEqual(Image.open(output).getpixel((10, 10)), (255, 255, 255))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run focused tests and confirm RED**

Run:

```bash
rtk pytest tests/test_pipeline_wiring.py tests/test_run_step3_on_color_patterns.py -q
```

Expected: failures show the pipeline does not call the postprocessor, the runner has the wrong function signatures and source directory, and output routing does not create/use `v2/`.

- [ ] **Step 3: Apply postprocessing before pipeline save and propagation**

Import the shared function in `core/pipeline.py`:

```python
from utils.sketch_postprocessor import postprocess_sketch
```

Immediately after `self._client.send(...)` and before `save_step`, add:

```python
if config.get("postprocess_sketch"):
    step_response.images = [postprocess_sketch(image) for image in step_response.images]
```

This placement is load-bearing: the same processed PIL objects must reach step saving, `StepResult.generated_images`, `previous_images`, and final saving.

- [ ] **Step 4: Correct and reuse the standalone runner**

Make these exact runner changes:

```python
from utils.sketch_postprocessor import postprocess_sketch

SRC_DIR = Path("images/new_patterns")
OUT_DIR = SRC_DIR / "v2"


def sketch_output_path(color_path: Path, output_dir: Path = OUT_DIR) -> Path:
    stem = color_path.stem
    new_stem = stem.replace("_color", "_sketch") if "_color" in stem else f"{stem}_sketch"
    return output_dir / f"{new_stem}.png"


def convert_one(color_path: Path, output_dir: Path = OUT_DIR) -> Path | None:
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = sketch_output_path(color_path, output_dir)
    image = ImageHandler.load(color_path)
    client = GeminiClient()
    client.start_chat()
    response = client.send([image, STEP3_PROMPT])
    if not response.images:
        logger.error("실패(이미지 없음): %s — 응답 텍스트: %s", color_path.name, response.text[:300])
        return None
    postprocess_sketch(response.images[0]).save(out_path)
    logger.info("완료: %s", out_path)
    return out_path
```

Keep `MAX_WORKERS = 6`, but pass `OUT_DIR` explicitly from `main()` so tests and later CLI evolution have one routing seam:

```python
OUT_DIR.mkdir(parents=True, exist_ok=True)
future_to_path = {
    pool.submit(convert_one, path, OUT_DIR): path
    for path in targets
}
```

Do not read or transform existing `_sketch` files. Discovery continues to select only stems containing `_color`.

- [ ] **Step 5: Run focused and full tests and confirm GREEN**

Run:

```bash
rtk pytest tests/test_pipeline_wiring.py tests/test_run_step3_on_color_patterns.py -q
rtk pytest tests/ -q
```

Expected: all tests pass with no API calls.

- [ ] **Step 6: Commit Task 3 code and tests**

```bash
rtk git add core/pipeline.py scripts/run_step3_on_color_patterns.py tests/test_pipeline_wiring.py tests/test_run_step3_on_color_patterns.py
rtk git commit -m "feat: postprocess sketch pattern outputs"
```

- [ ] **Step 7: Generate all twelve v2 outputs without visual inspection**

Run:

```bash
rtk proxy uv run python scripts/run_step3_on_color_patterns.py
```

Expected process result: exit status `0`, log summary `완료 12개 / 실패 0개`.

Do not open any generated image. Verify only names and count:

```bash
rtk proxy find images/new_patterns/v2 -maxdepth 1 -type f -name '*_sketch.png' | sort
rtk proxy find images/new_patterns/v2 -maxdepth 1 -type f -name '*_sketch.png' | wc -l
```

Expected count: `12`.

Do not add generated images to a commit unless the user later asks for that explicitly.

- [ ] **Step 8: Run fresh final verification**

Run:

```bash
rtk pytest tests/ -q
rtk git status --short
rtk git diff --check
```

Record the exact test count and exit codes in the worker report. Do not report visual correctness because agents are forbidden from inspecting v2 image content.

---

## Whole-Change Review

After Tasks 1–3 are complete, dispatch one reviewer with the complete diff and these binding checks:

- Prompt preserves observed topology while still forbidding invented hidden lines.
- Mesh texture removal does not remove mesh pattern-part cutting boundaries.
- Circular and elliptical punching rules are explicit.
- Postprocessing is Pillow-only, binary, canvas-preserving, and shared by the pipeline and batch runner.
- Black, gray, and chromatic broad fills are hollowed while synthetic thin/closed line tests remain green.
- Step 3 remains disabled and isolated from previous text/history.
- Existing sketches are not overwritten; outputs route only to `images/new_patterns/v2/`.
- No quality gate or automatic Gemini visual retry was added.
- Neither implementer nor reviewer opens or visually judges generated v2 images.
- Tests use no live API calls.
- No unrelated edits were reverted or swept into commits.

Send all Critical and Important findings to the same implementer. Repeat fix and scoped review at most three times. If findings remain after round three, stop and report them to the user.
