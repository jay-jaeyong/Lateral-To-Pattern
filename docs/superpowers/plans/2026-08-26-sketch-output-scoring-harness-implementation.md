# Sketch Output Scoring Harness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a deterministic, diagnostic-only harness that scores existing Step 3 sketch outputs without changing images and provides a local Flask/canvas interface for normalized connection and boundary annotations.

**Architecture:** Add a standalone `sketch_scoring` package that owns manifest validation, annotation validation, OpenCV metrics, score orchestration, and immutable run reports. Two thin scripts expose manifest/score commands and the local Flask application; the generation pipeline never imports the package. The browser stores only normalized sidecar annotations through constrained Flask APIs and renders overlays in canvas without producing derived image files.

**Tech Stack:** Python 3.11, Pillow, NumPy, OpenCV headless, Flask, standard-library `argparse`/`json`/`csv`/`hashlib`, HTML5 canvas, existing `unittest` test style

**Spec:** `docs/superpowers/specs/2026-08-26-sketch-output-scoring-harness-design.md`

**PRD:** `/Users/rio/Shoe-Image-To-Pattern/.worktrees/safe-region-selection/docs/superpowers/specs/2026-08-26-sketch-output-scoring-harness-design.md`

## Global Constraints

- The harness is diagnostic-only. Do not import it from `core/`, `services/`, `handlers/`, `config/`, `main.py`, or `scripts/run_step3_on_color_patterns.py`.
- Treat `images/` and `images/output-*/` as read-only. The only writable roots are `annotations/sketch-scoring/` and `reports/sketch-scoring/`.
- Do not call Gemini or any external API. Do not add an AI model, embedding model, Streamlit, SciPy, scikit-image, React, or Vue dependency.
- Do not align by translation, rotation, reflection, perspective correction, elastic warp, or medial/lateral symmetry. Compare normalized coordinates exactly as supplied.
- Do not create a total score. Every metric returns `pass`, `warn`, `fail`, or `not_scored` independently with a numeric confidence and a reason when unscored.
- Do not threshold, reconnect, fill, resize, or otherwise save a modified sketch. Temporary masks and normalized comparison arrays stay in memory.
- Red-box JPEGs are annotation sources only. If no clean output exists, pixel metrics are `not_scored`; never erase red pixels and claim the image was restored.
- Persist report history under `reports/sketch-scoring/<run-id>/`; never overwrite an earlier run. Only `latest.json` may be replaced atomically.
- Decode image bytes rather than trusting file extensions because existing `.png` paths may contain JPEG bytes.
- Normalize item display names to NFC while preserving exact filesystem paths, including NFD Korean filenames.
- Use the shortest implementation that satisfies this plan. Do not add extension points or abstractions for unrequested future metrics.
- Do not commit or push unless the user explicitly asks.

## File Structure

- Create `sketch_scoring/__init__.py`: public version and diagnostic-only marker.
- Create `sketch_scoring/manifest.py`: manifest discovery, validation, NFC display names, and safe read-only path resolution.
- Create `sketch_scoring/annotations.py`: annotation schema validation, atomic sidecar persistence, red-box detection, and connection endpoint suggestions.
- Create `sketch_scoring/metrics.py`: image decoding, mask extraction, global image metrics, and annotation-local metrics.
- Create `sketch_scoring/scoring.py`: one-output and one-dataset orchestration, provenance hashes, and per-metric failure isolation.
- Create `sketch_scoring/reporting.py`: immutable run directories, detailed JSON, comparison CSV, and `latest.json`.
- Create `scripts/score_sketch_outputs.py`: `manifest` and `score` CLI entry points.
- Create `scripts/annotate_sketches.py`: Flask app factory and local server entry point.
- Create `templates/annotate.html`: self-contained canvas annotation UI.
- Create `annotations/sketch-scoring/dataset.json`: confirmed source/output-5 manifest, marking the two red-box JPEGs as annotation-only.
- Create `annotations/sketch-scoring/items/.gitkeep`: sidecar directory placeholder.
- Create `reports/sketch-scoring/.gitkeep`: report root placeholder.
- Modify `pyproject.toml`: add Flask, NumPy, and OpenCV headless.
- Modify `uv.lock`: resolve the three approved dependencies.
- Create `tests/test_sketch_manifest.py`, `tests/test_sketch_annotations.py`, `tests/test_sketch_metrics.py`, `tests/test_sketch_scoring.py`, `tests/test_score_sketch_outputs.py`, and `tests/test_annotate_sketches.py`.

---

### Task 1: Dependencies, Manifest Schema, and Safe Paths

**Files:**
- Create: `sketch_scoring/__init__.py`
- Create: `sketch_scoring/manifest.py`
- Create: `tests/test_sketch_manifest.py`
- Modify: `pyproject.toml:6-10`
- Modify: `uv.lock`

**Interfaces:**
- Produces: `ManifestError(ValueError)`.
- Produces: `canonical_display_name(name: str) -> str`.
- Produces: `load_manifest(path: Path, *, project_root: Path | None = None) -> dict`.
- Produces: `discover_manifest(images_dir: Path, existing: dict | None = None) -> dict`.
- Produces: `write_manifest(path: Path, manifest: dict) -> None` using atomic replacement.
- Produces: `resolve_read_path(project_root: Path, value: str, *, allowed_roots: Sequence[Path]) -> Path`.
- Manifest output values accept either a clean path string or `{"path": str, "kind": "clean" | "annotated_only"}`. `load_manifest` canonicalizes both forms to output records.

- [ ] **Step 1: Add the three approved runtime dependencies**

Change only the dependency list:

```toml
dependencies = [
    "google-genai>=1.0.0",
    "python-dotenv>=1.0.0",
    "Pillow>=10.0.0",
    "Flask>=3.0.0",
    "numpy>=1.26.0",
    "opencv-python-headless>=4.10.0.0",
]
```

Run:

```bash
uv lock
```

Expected: `uv.lock` resolves successfully without adding Streamlit, SciPy, scikit-image, React, or Vue.

- [ ] **Step 2: Write failing manifest and path-safety tests**

Cover these exact cases in `tests/test_sketch_manifest.py` with `tempfile.TemporaryDirectory`:

**ManifestDiscoveryTest**
- `test_discovers_color_sources_and_all_output_directories`: implement the setup and assertion stated by this test name and the surrounding step requirements.
- `test_preserves_existing_confirmed_source_and_output_mapping`: implement the setup and assertion stated by this test name and the surrounding step requirements.
- `test_marks_irregular_nike_name_for_review`: implement the setup and assertion stated by this test name and the surrounding step requirements.
- `test_nfc_display_name_keeps_nfd_filesystem_path`: implement the setup and assertion stated by this test name and the surrounding step requirements.
**ManifestValidationTest**
- `test_rejects_absolute_image_path`: implement the setup and assertion stated by this test name and the surrounding step requirements.
- `test_rejects_parent_traversal`: create a manifest path containing `../outside.png` and assert `ManifestError`.
- `test_rejects_symlink_escape`: place a symlink under `images/` that targets a file outside the project and assert `ManifestError` after real-path resolution.
- `test_rejects_missing_source`: point a source at a nonexistent in-root file and assert `ManifestError`.
- `test_accepts_clean_and_annotated_only_output_records`: implement the setup and assertion stated by this test name and the surrounding step requirements.
- `test_rejects_unknown_output_kind`: implement the setup and assertion stated by this test name and the surrounding step requirements.
- `test_rejects_medial_lateral_symmetry_fields`: implement the setup and assertion stated by this test name and the surrounding step requirements.
**AtomicManifestWriteTest**
- `test_write_manifest_preserves_existing_file_if_replace_fails`: implement the setup and assertion stated by this test name and the surrounding step requirements.

The symmetry-field test must reject keys matching `mirror`, `symmetry`, `opposite_side`, or `medial_lateral_similarity` anywhere in an item.

- [ ] **Step 3: Run the manifest tests and verify they fail**

Run:

```bash
uv run python -m unittest tests.test_sketch_manifest -v
```

Expected: FAIL because `sketch_scoring.manifest` does not exist.

- [ ] **Step 4: Implement the minimal manifest module**

Use plain dictionaries at the JSON boundary and canonicalize to this in-memory form:

```python
{
    "schema_version": 1,
    "items": {
        "item-id": {
            "display_name": "푸마2",
            "source": "images/푸마2_color.png",
            "expected_canvas_ratio": "2:3",
            "needs_review": False,
            "outputs": {
                "output-5": {
                    "path": "images/output-5/푸마2_sketch.jpeg",
                    "kind": "annotated_only"
                }
            }
        }
    }
}
```

Implementation rules:

```python
FORBIDDEN_COMPARISON_KEYS = {
    "mirror", "symmetry", "opposite_side", "medial_lateral_similarity"
}
SUPPORTED_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


def canonical_display_name(name: str) -> str:
    return unicodedata.normalize("NFC", name)


def resolve_read_path(project_root, value, *, allowed_roots):
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts:
        raise ManifestError("manifest path is outside the allowed image roots")
    resolved = (project_root / relative).resolve()
    if not any(resolved.is_relative_to(root.resolve()) for root in allowed_roots):
        raise ManifestError("manifest path is outside the allowed image roots")
    if not resolved.is_file():
        raise ManifestError("manifest path is outside the allowed image roots")
    return resolved
```

`discover_manifest` must:

1. Find top-level source files ending in `_color`.
2. Find `output-*` directories and `_sketch` files.
3. Compare candidate stems after NFC normalization.
4. Preserve every existing item field and confirmed path.
5. Add new output candidates without replacing existing mappings.
6. Add irregular unmatched source/output candidates with `needs_review: true` instead of guessing.

Use a sibling temporary file plus `Path.replace()` for atomic JSON writes.

- [ ] **Step 5: Run manifest tests and dependency import checks**

Run:

```bash
uv run python -m unittest tests.test_sketch_manifest -v
uv run python -c "import flask, cv2, numpy; print(flask.__version__ if hasattr(flask, '__version__') else 'ok', cv2.__version__, numpy.__version__)"
```

Expected: tests PASS; imports succeed.

- [ ] **Step 6: Inspect the task diff without committing**

Run:

```bash
rtk git diff -- pyproject.toml uv.lock sketch_scoring/manifest.py tests/test_sketch_manifest.py
rtk git diff --check
```

Expected: only the approved dependencies and manifest implementation are present; no whitespace errors.

---

### Task 2: Annotation Schema, Red-Box Import, and Endpoint Suggestions

**Files:**
- Create: `sketch_scoring/annotations.py`
- Create: `tests/test_sketch_annotations.py`

**Interfaces:**
- Consumes: `load_rgb(path: Path) -> np.ndarray` from Task 3 only at runtime; avoid an import cycle by accepting arrays in detection functions.
- Produces: `AnnotationError(ValueError)`.
- Produces: `validate_annotation_document(document: dict) -> dict`.
- Produces: `annotation_path(annotation_root: Path, item_id: str) -> Path`.
- Produces: `load_annotations(annotation_root: Path, item_id: str) -> dict`.
- Produces: `save_annotations(annotation_root: Path, item_id: str, document: dict) -> Path`.
- Produces: `detect_red_boxes(rgb: np.ndarray) -> list[list[float]]`.
- Produces: `suggest_connection_anchors(rgb: np.ndarray, target_box: list[float]) -> list[list[float]]`.

- [ ] **Step 1: Write failing schema tests**

Use exact document shapes:

```python
EMPTY_DOCUMENT = {"schema_version": 1, "annotations": []}

CONNECTION = {
    "id": "quarter-seam-1",
    "type": "connection",
    "target_box": [0.31, 0.42, 0.39, 0.49],
    "anchors": {
        "start_region": [0.32, 0.45, 0.33, 0.47],
        "end_region": [0.37, 0.44, 0.38, 0.46],
    },
}
```

Tests:

**AnnotationValidationTest**
- `test_accepts_connection_required_path_and_complete_roi`: implement the setup and assertion stated by this test name and the surrounding step requirements.
- `test_rejects_coordinates_outside_zero_one`: implement the setup and assertion stated by this test name and the surrounding step requirements.
- `test_rejects_reversed_box_coordinates`: implement the setup and assertion stated by this test name and the surrounding step requirements.
- `test_connection_requires_exactly_two_anchor_regions`: implement the setup and assertion stated by this test name and the surrounding step requirements.
- `test_required_path_requires_at_least_two_points`: implement the setup and assertion stated by this test name and the surrounding step requirements.
- `test_complete_roi_requires_nonempty_paths`: implement the setup and assertion stated by this test name and the surrounding step requirements.
- `test_rejects_duplicate_annotation_ids`: implement the setup and assertion stated by this test name and the surrounding step requirements.
- `test_rejects_symmetry_and_opposite_side_fields`: implement the setup and assertion stated by this test name and the surrounding step requirements.
- `test_item_id_cannot_escape_annotation_root`: implement the setup and assertion stated by this test name and the surrounding step requirements.

- [ ] **Step 2: Write failing red-box and anchor-suggestion tests**

Create arrays in memory, not image files:

```python
rgb = np.full((100, 200, 3), 255, dtype=np.uint8)
cv2.rectangle(rgb, (40, 20), (120, 70), (255, 0, 0), 3)
```

Assert one normalized box approximately equals `[0.20, 0.20, 0.60, 0.70]` within the stroke tolerance.

For anchor suggestions, draw two black line fragments ending inside a target box. Assert:

- exactly two endpoint regions are returned for an unambiguous two-end fragment;
- zero regions are returned when there are zero, one, or more than two plausible endpoints;
- every returned box stays within `[0, 1]`.

- [ ] **Step 3: Run annotation tests and verify they fail**

Run:

```bash
uv run python -m unittest tests.test_sketch_annotations -v
```

Expected: FAIL because `sketch_scoring.annotations` does not exist.

- [ ] **Step 4: Implement annotation validation and atomic persistence**

Validation must allow only these annotation types:

```python
ANNOTATION_TYPES = {"connection", "required_path", "complete_roi"}
```

Rules:

- A box is four finite numbers with `0 <= x1 < x2 <= 1` and `0 <= y1 < y2 <= 1`.
- A polyline has at least two finite normalized `[x, y]` points.
- `connection` requires `target_box`, `anchors.start_region`, and `anchors.end_region`.
- `required_path` and `complete_roi` require `target_box` and one or more paths.
- Duplicate IDs are rejected.
- Unknown keys are allowed only for `label`; comparison keys involving reflection, symmetry, opposite sides, medial, or lateral are rejected recursively.
- `item_id` must match `^[A-Za-z0-9_.가-힣-]+$` after NFC normalization and cannot contain slashes.
- Saves write UTF-8 JSON with `ensure_ascii=False`, two-space indentation, and atomic replace.

- [ ] **Step 5: Implement deterministic red-box detection**

Use HSV or RGB channel dominance, then connected components:

```python
red = (
    (rgb[:, :, 0] >= 180)
    & (rgb[:, :, 0] >= rgb[:, :, 1] + 60)
    & (rgb[:, :, 0] >= rgb[:, :, 2] + 60)
).astype(np.uint8)
```

For each connected component:

1. Reject components covering less than `0.01%` of the image.
2. Use the component bounding rectangle.
3. Require red pixels along at least three sides so isolated logos are not treated as boxes.
4. Merge components whose bounding rectangles overlap because JPEG compression can split a box.
5. Return normalized boxes sorted top-to-bottom, then left-to-right.

The detector returns candidates only. It does not save annotations automatically. Add a persistence test that imports red-box candidates, reloads the item sidecar, and proves it is byte-for-byte unchanged until a separate confirmed annotation save request is made.

- [ ] **Step 6: Implement conservative endpoint suggestions**

Within `target_box`:

1. Convert to grayscale and mark dark ink with a fixed diagnostic threshold.
2. Apply no closing, dilation, reconnection, or saved transformation.
3. Skeletonize is out of scope; use contour pixels and local 8-neighbor counts to identify endpoint candidates.
4. Cluster candidates that are within `2%` of the ROI diagonal.
5. Exclude candidates touching the ROI boundary unless the visible line itself enters through that boundary.
6. Return two small normalized boxes only when exactly two clusters remain; otherwise return `[]` so the UI asks for clicks.

- [ ] **Step 7: Run annotation tests and inspect the diff**

Run:

```bash
uv run python -m unittest tests.test_sketch_annotations -v
rtk git diff --check
```

Expected: all annotation tests PASS; no image file is created by tests.

---

### Task 3: Image Decoding and Global Diagnostic Metrics

**Files:**
- Create: `sketch_scoring/metrics.py`
- Create: `tests/test_sketch_metrics.py`

**Interfaces:**
- Produces: immutable `MetricResult` dataclass with fields `score: bool | float | dict | None`, `status: str`, `confidence: float`, `reason: str | None`, and `details: dict`.
- Produces: immutable `ScoringConfig` dataclass containing canvas size and thresholds.
- Produces: `load_rgb(path: Path) -> np.ndarray` using `Path.read_bytes()` plus `cv2.imdecode`.
- Produces: `score_aspect_ratio(output_rgb: np.ndarray, expected_ratio: str, config: ScoringConfig) -> MetricResult`.
- Produces: `score_silhouette(source_rgb: np.ndarray, output_rgb: np.ndarray, config: ScoringConfig) -> MetricResult`.
- Produces: `score_colored_pixels(output_rgb: np.ndarray, config: ScoringConfig) -> MetricResult`.
- Produces: `score_black_fill(output_rgb: np.ndarray, config: ScoringConfig) -> MetricResult`.
- Produces: `score_faint_strokes(output_rgb: np.ndarray, config: ScoringConfig) -> MetricResult`.
- Produces: `score_global_metrics(source_rgb, output_rgb, expected_ratio, config) -> dict[str, MetricResult]`.

- [ ] **Step 1: Write failing decoding and status tests**

Include a JPEG byte stream saved to a `.png` path and assert `load_rgb` decodes it from content. Test that `MetricResult.not_scored(reason, confidence)` has `score is None` and a nonempty reason, and that confidence is clamped or rejected outside `[0, 1]`.

- [ ] **Step 2: Write failing aspect, color, fill, and faint-stroke tests**

Synthetic fixtures must cover:

**AspectMetricTest**
- `test_two_to_three_is_pass`: implement the setup and assertion stated by this test name and the surrounding step requirements.
- `test_three_percent_error_is_warn`: implement the setup and assertion stated by this test name and the surrounding step requirements.
- `test_landscape_for_portrait_expectation_is_fail`: implement the setup and assertion stated by this test name and the surrounding step requirements.
**ColorMetricTest**
- `test_black_gray_white_image_passes`: implement the setup and assertion stated by this test name and the surrounding step requirements.
- `test_colored_region_fails`: implement the setup and assertion stated by this test name and the surrounding step requirements.
- `test_small_jpeg_chroma_noise_does_not_fail`: implement the setup and assertion stated by this test name and the surrounding step requirements.
**BlackFillMetricTest**
- `test_thin_black_lines_are_not_fill`: implement the setup and assertion stated by this test name and the surrounding step requirements.
- `test_wide_solid_black_region_is_fill`: implement the setup and assertion stated by this test name and the surrounding step requirements.
**FaintStrokeMetricTest**
- `test_antialiasing_next_to_dark_core_is_excluded`: implement the setup and assertion stated by this test name and the surrounding step requirements.
- `test_gray_line_without_dark_core_is_counted`: implement the setup and assertion stated by this test name and the surrounding step requirements.

- [ ] **Step 3: Write failing silhouette confidence tests**

Create one high-contrast colored foreground on white and one nearly white foreground on white. Assert:

- the high-contrast pair returns numeric IoU and confidence above the scoring floor;
- the low-contrast source returns `not_scored` with a background/foreground separation reason;
- translating the output lowers IoU because no registration is performed;
- horizontally flipping an asymmetric output lowers IoU because no reflection is performed.

- [ ] **Step 4: Run metric tests and verify they fail**

Run:

```bash
uv run python -m unittest tests.test_sketch_metrics -v
```

Expected: FAIL because the metric interfaces do not exist.

- [ ] **Step 5: Implement decoding and common metric structures**

Use this baseline configuration:

```python
@dataclass(frozen=True)
class ScoringConfig:
    canvas_width: int = 512
    canvas_height: int = 768
    aspect_pass_relative_error: float = 0.02
    aspect_warn_relative_error: float = 0.05
    chroma_threshold: int = 18
    chroma_pass_ratio: float = 0.0005
    chroma_warn_ratio: float = 0.002
    dark_threshold: int = 72
    fill_half_width_px: float = 4.0
    fill_pass_ratio: float = 0.0005
    fill_warn_ratio: float = 0.002
    faint_low: int = 80
    faint_high: int = 220
    faint_dark_core: int = 80
    silhouette_min_confidence: float = 0.55
    path_tolerance_px: int = 5
```

`load_rgb` must decode actual bytes:

```python
data = np.frombuffer(path.read_bytes(), dtype=np.uint8)
bgr = cv2.imdecode(data, cv2.IMREAD_COLOR)
if bgr is None:
    raise ImageDecodeError(f"이미지를 디코드할 수 없음: {path}")
return cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
```

- [ ] **Step 6: Implement immediately classifiable metrics**

- Aspect ratio: parse `"2:3"`, compare width/height relative error, and fail orientation mismatch.
- Colored pixels: `max(rgb) - min(rgb) > chroma_threshold`, excluding near-white JPEG noise through the threshold only; ratio is over all pixels.
- Black fill: make a dark-pixel mask, run `cv2.distanceTransform`, and count dark pixels farther than `fill_half_width_px` from white. Thin lines have no deep interior.
- Faint strokes: count nonwhite gray ink whose local `5x5` minimum remains above `faint_dark_core`; gray antialiasing next to a dark center is excluded. Return raw ratio and confidence, with `status="not_scored"` and reason `"정상 사례 기반 문턱 미확정"` until calibration exists.

Do not expose a combined score.

- [ ] **Step 7: Implement silhouette extraction with confidence gating**

For source images:

1. Convert to Lab.
2. Estimate background from a border band using channel medians.
3. Compute border dispersion and each pixel's Lab distance from background.
4. Select foreground with a fixed distance threshold derived only from `ScoringConfig`, not from the output.
5. Keep all meaningful connected components; do not keep only the largest because the pattern contains multiple pieces.
6. Confidence combines border stability, foreground/background separation, and plausible foreground-area range.

For sketches, foreground is nonwhite ink; fill external contours to obtain piece silhouettes for this metric only. Resize masks in memory to the fixed normalized canvas using nearest-neighbor interpolation. Return `not_scored` when source separation confidence is below the floor. For scored masks, return IoU and confidence but `status="not_scored"`, reason `"정상 사례 기반 문턱 미확정"`, and preserve the numeric IoU in `details["raw_score"]` until calibration exists.

- [ ] **Step 8: Run metric tests and inspect the diff**

Run:

```bash
uv run python -m unittest tests.test_sketch_metrics -v
rtk git diff --check
```

Expected: all global metric tests PASS; no files are written by metric functions.

---

### Task 4: Connection, Required-Path, and Complete-ROI Metrics

**Files:**
- Modify: `sketch_scoring/metrics.py`
- Modify: `tests/test_sketch_metrics.py`

**Interfaces:**
- Produces: `score_connection(output_rgb: np.ndarray, annotation: dict, config: ScoringConfig) -> MetricResult`.
- Produces: `score_required_path(output_rgb: np.ndarray, annotation: dict, config: ScoringConfig) -> MetricResult`.
- Produces: `score_complete_roi(output_rgb: np.ndarray, annotation: dict, config: ScoringConfig) -> MetricResult`.
- Produces: `score_annotation(output_rgb: np.ndarray, annotation: dict, config: ScoringConfig) -> MetricResult`.

- [ ] **Step 1: Write failing connection tests**

Use a white `256x256` image and draw black fragments. Cover:

**ConnectionMetricTest**
- `test_same_component_touching_both_anchors_passes`: implement the setup and assertion stated by this test name and the surrounding step requirements.
- `test_two_components_fail_and_report_gap`: implement the setup and assertion stated by this test name and the surrounding step requirements.
- `test_missing_ink_in_one_anchor_is_not_scored`: implement the setup and assertion stated by this test name and the surrounding step requirements.
- `test_nearby_unrelated_line_does_not_replace_anchor_component`: implement the setup and assertion stated by this test name and the surrounding step requirements.
- `test_result_has_gap_pixels_and_normalized_gap`: implement the setup and assertion stated by this test name and the surrounding step requirements.

The result details must contain:

```python
{
    "connected": False,
    "gap_pixels": 14.0,
    "gap_normalized": 0.038,
    "start_component": 2,
    "end_component": 5,
}
```

- [ ] **Step 2: Write failing required-path tests**

Rasterize a known expected polyline and create exact, shifted, and missing output lines. Assert `details` contains:

```python
{
    "detection_ratio": 0.84,
    "median_error_px": 1.2,
    "p95_error_px": 4.8,
}
```

The metric must ignore unrelated lines elsewhere in the ROI because `required_path` measures only expected-path presence and location.

- [ ] **Step 3: Write failing complete-ROI tests**

Cover:

- exact expected paths: low missing and extra ratios;
- one absent expected path: higher missing ratio;
- an unannotated extra line: higher extra ratio;
- output ink outside the target box: ignored;
- no output ink: valid numeric missing ratio, not a crash.

- [ ] **Step 4: Run annotation metric tests and verify they fail**

Run:

```bash
uv run python -m unittest tests.test_sketch_metrics.ConnectionMetricTest tests.test_sketch_metrics.RequiredPathMetricTest tests.test_sketch_metrics.CompleteRoiMetricTest -v
```

Expected: FAIL because the annotation metrics are not implemented.

- [ ] **Step 5: Implement shared ROI and ink helpers**

Add private helpers only in `metrics.py`:

```python
`_normalized_box_to_pixels(box, width, height) -> tuple[int, int, int, int]`
`_ink_mask(rgb, config) -> np.ndarray`
`_rasterize_paths(paths, width, height, thickness=1) -> np.ndarray`
`_metric_not_calibrated(raw_score, confidence, **details) -> MetricResult`
```

Use normalized coordinates directly. Annotation metrics map coordinates onto the output's native pixel dimensions and never resize the output; only global source/output metrics may create an in-memory common analysis canvas. Do not translate or warp the ROI to improve alignment.

- [ ] **Step 6: Implement connection scoring**

1. Label 8-connected ink components inside the target box with `cv2.connectedComponents`.
2. Find component IDs touching each anchor region.
3. If either anchor contains no ink, return `not_scored` with the missing-anchor reason.
4. If the anchor component sets intersect, return `pass` and zero gap.
5. Otherwise compute the minimum Euclidean distance between the two anchor components with `cv2.distanceTransform`; report pixels on the fixed ROI raster and normalize by ROI diagonal.
6. Return `fail` for a confident disconnected result.

The distance is a diagnostic estimate of the white break. It must not modify or reconnect the image.

- [ ] **Step 7: Implement required-path and complete-ROI scoring**

For `required_path`:

1. Rasterize expected paths in the normalized target-box canvas.
2. Compute distance to the nearest output ink.
3. Detection ratio is expected-path pixels within `path_tolerance_px` of output ink.
4. Report median and 95th-percentile error.
5. Keep the numeric values but use `not_scored` with reason `"정상 사례 기반 문턱 미확정"`.

For `complete_roi`:

1. Compute required-path missing ratio.
2. Dilate the full expected-path mask only for tolerance measurement.
3. Extra ratio is output ink outside that tolerance band divided by all output ink in the ROI.
4. Keep numeric values but use the same uncalibrated `not_scored` status.

- [ ] **Step 8: Run all metric tests**

Run:

```bash
uv run python -m unittest tests.test_sketch_metrics -v
rtk git diff --check
```

Expected: all global and annotation metric tests PASS.

---

### Task 5: Scoring Orchestration, Provenance, Reports, CLI, and Initial Manifest

**Files:**
- Create: `sketch_scoring/scoring.py`
- Create: `sketch_scoring/reporting.py`
- Create: `scripts/score_sketch_outputs.py`
- Create: `annotations/sketch-scoring/dataset.json`
- Create: `annotations/sketch-scoring/items/.gitkeep`
- Create: `reports/sketch-scoring/.gitkeep`
- Create: `tests/test_sketch_scoring.py`
- Create: `tests/test_score_sketch_outputs.py`

**Interfaces:**
- Consumes: Task 1 manifest functions, Task 2 annotation functions, and Task 3/4 metric functions.
- Produces: `sha256_file(path: Path) -> str`.
- Produces: `score_output(item_id: str, item: dict, version: str, output_record: dict, *, project_root: Path, annotation_root: Path, config: ScoringConfig) -> dict`.
- Produces: `score_dataset(manifest_path: Path, *, versions: set[str] | None = None, annotation_root: Path, config: ScoringConfig | None = None) -> dict`.
- Produces: `write_run_reports(result: dict, reports_root: Path, label: str) -> Path`.
- Produces: `build_parser() -> argparse.ArgumentParser` and `main(argv: list[str] | None = None) -> int`.

- [ ] **Step 1: Write failing orchestration tests**

`tests/test_sketch_scoring.py` must verify:

**ScoreOutputTest**
- `test_clean_output_runs_global_and_annotation_metrics`: implement the setup and assertion stated by this test name and the surrounding step requirements.
- `test_annotated_only_output_marks_pixel_metrics_not_scored`: implement the setup and assertion stated by this test name and the surrounding step requirements.
- `test_missing_clean_output_does_not_decode_annotation_source`: implement the setup and assertion stated by this test name and the surrounding step requirements.
- `test_one_metric_exception_becomes_not_scored_without_aborting_item`: implement the setup and assertion stated by this test name and the surrounding step requirements.
- `test_image_hash_and_mtime_are_unchanged`: implement the setup and assertion stated by this test name and the surrounding step requirements.
- `test_result_contains_no_total_score`: implement the setup and assertion stated by this test name and the surrounding step requirements.
- `test_result_records_manifest_annotation_source_and_output_hashes`: implement the setup and assertion stated by this test name and the surrounding step requirements.

Patch the metric functions to isolate orchestration. Assert no Gemini service is imported.

- [ ] **Step 2: Write failing report tests**

Cover:

- run directory name contains UTC timestamp and sanitized label;
- a second run with the same label creates a different directory instead of overwriting;
- `results.json`, `summary.csv`, and `latest.json` are the only generated files;
- `latest.json` points to the newest run;
- CSV has per-metric medians and improved/same/worsened counts between ordered output versions;
- `not_scored` counts and reason counts are included;
- no `total`, `overall_score`, or rank column exists.

- [ ] **Step 3: Write failing CLI tests**

`tests/test_score_sketch_outputs.py` must call `main(["score", "--manifest", str(manifest), "--label", "test-run"])`, not a subprocess, and verify:

**ManifestCommandTest**
- `test_manifest_command_creates_candidate_file`: implement the setup and assertion stated by this test name and the surrounding step requirements.
- `test_manifest_command_preserves_existing_confirmed_mapping`: implement the setup and assertion stated by this test name and the surrounding step requirements.
**ScoreCommandTest**
- `test_score_command_writes_run_reports`: implement the setup and assertion stated by this test name and the surrounding step requirements.
- `test_schema_error_returns_nonzero`: implement the setup and assertion stated by this test name and the surrounding step requirements.
- `test_individual_not_scored_metric_still_returns_zero`: implement the setup and assertion stated by this test name and the surrounding step requirements.

- [ ] **Step 4: Run orchestration, report, and CLI tests and verify they fail**

Run:

```bash
uv run python -m unittest tests.test_sketch_scoring tests.test_score_sketch_outputs -v
```

Expected: FAIL because orchestration and CLI modules do not exist.

- [ ] **Step 5: Implement scoring orchestration**

Result root shape:

```python
{
    "schema_version": 1,
    "diagnostic_only": True,
    "provenance": {
        "started_at": "2026-08-26T06:30:00Z",
        "manifest_path": "annotations/sketch-scoring/dataset.json",
        "manifest_sha256": "64-character SHA-256 hex",
        "annotation_sha256": {"nike_p6000": "64-character SHA-256 hex"},
        "git_commit": null,
        "harness_version": "1",
        "config": {"canvas_width": 512, "canvas_height": 768},
    },
    "items": {"nike_p6000": {"output-5": {"metrics": {}}}},
}
```

For `kind="annotated_only"`, produce a standard `not_scored` result for every pixel metric with reason `"빨간 표시가 합성된 주석 자료이며 깨끗한 출력이 없음"`. Still load and validate sidecar annotations, but do not decode the annotated JPEG as a clean output and do not attempt red-pixel removal.

Wrap each metric call separately so one algorithm error becomes that metric's `not_scored` result with a diagnostic reason. Manifest errors, invalid annotations, unreadable required source files, and report-write failures remain fatal.

- [ ] **Step 6: Implement immutable JSON/CSV reports**

Use `datetime.now(timezone.utc)` and a filesystem-safe label. If a run directory already exists, append `-2`, `-3`, and so on. Write files atomically.

`summary.csv` rows use this stable schema:

```text
version,metric,median,improved,same,worsened,pass,warn,fail,not_scored,not_scored_reasons
```

Compare only numeric raw scores with known directionality declared in a small constant map, for example lower is better for chroma/fill/gap/error and higher is better for IoU/detection. Do not infer direction from metric names.

- [ ] **Step 7: Implement the thin CLI**

Parser shape:

```python
parser = argparse.ArgumentParser(description="스케치 출력 진단 하네스")
sub = parser.add_subparsers(dest="command", required=True)

manifest = sub.add_parser("manifest")
manifest.add_argument("--images-dir", type=Path, default=Path("images"))
manifest.add_argument("--manifest", type=Path, default=Path("annotations/sketch-scoring/dataset.json"))

score = sub.add_parser("score")
score.add_argument("--manifest", type=Path, default=Path("annotations/sketch-scoring/dataset.json"))
score.add_argument("--annotation-root", type=Path, default=Path("annotations/sketch-scoring/items"))
score.add_argument("--reports-root", type=Path, default=Path("reports/sketch-scoring"))
score.add_argument("--label", required=True)
score.add_argument("--version", action="append", dest="versions")
```

Insert the repository root in `sys.path` using the existing script convention. Return exit code `0` for completed scoring even when metrics are `fail` or `not_scored`; return nonzero for fatal schema, decode, or write errors.

- [ ] **Step 8: Create the confirmed initial dataset manifest**

Include all 12 current source items and output-5 mappings. Use exact on-disk relative paths. In particular:

```json
"nike_p6000": {
  "display_name": "nike_p6000",
  "source": "images/nike_p6000.jpeg",
  "expected_canvas_ratio": "2:3",
  "needs_review": false,
  "outputs": {
    "output-5": "images/output-5/nike_p6000_sketch.png"
  }
}
```

Mark the NFD filenames without renaming them:

```json
"푸마2": {
  "display_name": "푸마2",
  "source": "images/푸마2_color.png",
  "expected_canvas_ratio": "2:3",
  "needs_review": false,
  "outputs": {
    "output-5": {
      "path": "images/output-5/푸마2_sketch.jpeg",
      "kind": "annotated_only"
    }
  }
}
```

Do the same for `필라1`. Do not invent clean `.png` paths for either item.

- [ ] **Step 9: Run tests and a temporary end-to-end CLI smoke test**

Run unit tests first:

```bash
uv run python -m unittest tests.test_sketch_scoring tests.test_score_sketch_outputs -v
```

Then use a temporary manifest/report root in a Python test fixture or temporary shell directory, not the permanent reports directory, and verify exactly JSON/CSV/latest files are created.

Expected: tests PASS; source/output hashes and mtimes are unchanged.

---

### Task 6: Flask APIs and HTML Canvas Annotation UI

**Files:**
- Create: `scripts/annotate_sketches.py`
- Create: `templates/annotate.html`
- Create: `tests/test_annotate_sketches.py`

**Interfaces:**
- Consumes: manifest loading/path safety, annotation loading/saving/detection, `score_output`, and `ScoringConfig`.
- Produces: `create_app(manifest_path: Path, *, project_root: Path | None = None, annotation_root: Path | None = None) -> Flask`.
- Produces routes: `GET /`, `GET /api/images`, `GET /api/image/<item_id>`, `GET /api/annotations/<item_id>`, `POST /api/annotations/<item_id>`, `POST /api/import-red-boxes/<item_id>`, `POST /api/suggest-anchors/<item_id>`, and `POST /api/score/<item_id>`.

- [ ] **Step 1: Write failing Flask API tests**

Use `create_app(manifest_path, project_root=project_root, annotation_root=annotation_root).test_client()` with temporary files. Cover:

**ImageApiTest**
- `test_images_lists_nfc_display_names_and_versions`: implement the setup and assertion stated by this test name and the surrounding step requirements.
- `test_image_serves_only_manifest_source_or_output`: implement the setup and assertion stated by this test name and the surrounding step requirements.
- `test_unknown_item_is_404`: implement the setup and assertion stated by this test name and the surrounding step requirements.
- `test_unknown_version_is_404`: implement the setup and assertion stated by this test name and the surrounding step requirements.
- `test_path_traversal_cannot_escape_manifest`: implement the setup and assertion stated by this test name and the surrounding step requirements.
**AnnotationApiTest**
- `test_get_missing_annotations_returns_empty_document`: implement the setup and assertion stated by this test name and the surrounding step requirements.
- `test_post_validates_saves_and_reloads_document`: implement the setup and assertion stated by this test name and the surrounding step requirements.
- `test_invalid_coordinates_return_400_without_replacing_existing_file`: implement the setup and assertion stated by this test name and the surrounding step requirements.
- `test_red_box_import_returns_candidates_without_saving`: implement the setup and assertion stated by this test name and the surrounding step requirements.
- `test_ambiguous_anchor_suggestion_returns_empty_candidates`: implement the setup and assertion stated by this test name and the surrounding step requirements.
**ScoreApiTest**
- `test_score_returns_diagnostic_result_without_writing_report`: implement the setup and assertion stated by this test name and the surrounding step requirements.
- `test_annotated_only_output_is_not_scored`: implement the setup and assertion stated by this test name and the surrounding step requirements.

- [ ] **Step 2: Write failing UI contract tests**

GET `/` and assert the response includes:

- one `<canvas id="annotation-canvas">`;
- item, version, and image-kind selectors;
- controls for `connection`, `required_path`, and `complete_roi`;
- controls for box drawing, anchor clicks, path completion, delete, save, red-box import, anchor suggestion, and score;
- zoom/pan controls;
- visible `pass`, `warn`, `fail`, and `not_scored` legend text;
- JavaScript functions named `imageToNormalized`, `normalizedToImage`, `drawOverlay`, `saveAnnotations`, and `loadScore`.

- [ ] **Step 3: Run Flask tests and verify they fail**

Run:

```bash
uv run python -m unittest tests.test_annotate_sketches -v
```

Expected: FAIL because the Flask app and template do not exist.

- [ ] **Step 4: Implement the constrained Flask app factory**

Core app setup:

```python
def create_app(manifest_path, *, project_root=None, annotation_root=None):
    app = Flask(__name__, template_folder=str(PROJECT_ROOT / "templates"))
    app.config.update(
        MANIFEST_PATH=Path(manifest_path),
        PROJECT_ROOT=Path(project_root or PROJECT_ROOT),
        ANNOTATION_ROOT=Path(annotation_root or "annotations/sketch-scoring/items"),
        MAX_CONTENT_LENGTH=1_000_000,
    )
    app.config["TESTING"] = False
    return app
```

Rules:

- Bind to `127.0.0.1` by default; require an explicit CLI option to change host.
- Resolve every served image from the loaded manifest, never from a user-supplied path.
- Accept image selectors only as query fields `kind=source` or `kind=output&version=<version>`.
- Return JSON error bodies for invalid items, versions, or annotations.
- `POST /api/score/<item_id>` returns in-memory results and does not create a report run.
- No route writes image bytes.
- Set `Cache-Control: no-store` for image and JSON responses so annotations and local output changes appear immediately.

- [ ] **Step 5: Implement the self-contained canvas UI**

Keep CSS and JavaScript inline because CSP/self-hosting and package management are not needed for this local page.

Required state:

```javascript
const state = {
  items: {}, itemId: null, version: null, imageKind: "source",
  image: new Image(), annotations: [], selectedId: null,
  mode: "pan", draft: null, zoom: 1, panX: 0, panY: 0,
  score: null
};
```

Required behavior:

1. Fetch `/api/images`, select an item/version, and load source or output through `/api/image/<item_id>`.
2. Convert pointer positions through canvas viewport, pan, zoom, and displayed-image bounds into normalized image coordinates.
3. Draw boxes with drag; draw paths with clicks and finish by double-click or Enter.
4. For a connection annotation, collect start and end clicks and generate small normalized anchor boxes around them.
5. Select an existing box/path, drag to move it, show four box resize handles, and delete the selection.
6. Keep normalized coordinates unchanged when zooming or panning.
7. Draw overlays without modifying the loaded image: blue boxes, green/red anchors based on score, orange missing/extra paths, and gray `not_scored` state.
8. Import red-box candidates into a draft list that requires an explicit user confirmation before becoming annotations.
9. Request anchor suggestions and use them only when exactly two candidates are returned; otherwise show instructions for two manual clicks.
10. Save only the annotation JSON with `POST /api/annotations/<item_id>`.
11. Show metric value, status, confidence, and reason individually; never render a total score.

- [ ] **Step 6: Add the local server CLI**

Arguments:

```python
parser.add_argument("--manifest", type=Path, default=Path("annotations/sketch-scoring/dataset.json"))
parser.add_argument("--host", default="127.0.0.1")
parser.add_argument("--port", type=int, default=5000)
parser.add_argument("--debug", action="store_true")
```

Run with `app.run(host=args.host, port=args.port, debug=args.debug)`. Do not enable debug by default.

- [ ] **Step 7: Run Flask tests and syntax checks**

Run:

```bash
uv run python -m unittest tests.test_annotate_sketches -v
uv run python -m py_compile scripts/annotate_sketches.py sketch_scoring/*.py
rtk git diff --check
```

Expected: Flask tests and Python syntax checks PASS.

---

### Task 7: Whole-Harness Safety and Acceptance Verification

**Files:**
- Modify: `tests/test_sketch_scoring.py`
- Modify: `tests/test_score_sketch_outputs.py`
- Modify: `tests/test_annotate_sketches.py`
- Modify if needed: files created in Tasks 1-6 only

**Interfaces:**
- Consumes: the complete harness.
- Produces: no new public runtime interface; this task closes PRD acceptance gaps.

- [ ] **Step 1: Add an import-boundary regression test**

Walk production Python files outside `sketch_scoring/`, `scripts/score_sketch_outputs.py`, and `scripts/annotate_sketches.py`. Parse them with `ast` and assert none import `sketch_scoring`:

```python
for node in ast.walk(ast.parse(path.read_text())):
    if isinstance(node, ast.Import): assert all(alias.name != "sketch_scoring" and not alias.name.startswith("sketch_scoring.") for alias in node.names)
    if isinstance(node, ast.ImportFrom): assert node.module != "sketch_scoring" and not (node.module or "").startswith("sketch_scoring.")
```

This proves the diagnostic harness is not wired into generation.

- [ ] **Step 2: Add a filesystem-write boundary test**

Create a temporary project with `images/`, `annotations/sketch-scoring/`, and `reports/sketch-scoring/`. Snapshot every image's SHA-256, size, and `st_mtime_ns`, then run:

1. manifest discovery;
2. dataset scoring;
3. annotation API load/save;
4. individual score API.

Assert all image snapshots are unchanged and every newly written file is under annotation or report roots. Assert no `.png`, `.jpg`, `.jpeg`, mask, thumbnail, or overlay file exists under reports.

- [ ] **Step 3: Add forbidden-feature regression tests**

Assert:

- result JSON and CSV contain no total score or rank;
- manifest/annotation schema rejects symmetry/reflection/opposite-side fields;
- no call path imports `services.gemini_client` or `google.genai` from `sketch_scoring` or the two new scripts;
- no metric function calls `cv2.imwrite`, `PIL.Image.save`, or opens an image path for writing;
- `annotated_only` outputs never reach `load_rgb` as clean outputs;
- no auto-registration helper exists and the translated/flipped silhouette tests still lose score.

Use AST/source assertions only for explicit forbidden calls; prefer behavior tests for all other contracts.

- [ ] **Step 4: Run all targeted harness tests**

Run:

```bash
uv run python -m unittest \
  tests.test_sketch_manifest \
  tests.test_sketch_annotations \
  tests.test_sketch_metrics \
  tests.test_sketch_scoring \
  tests.test_score_sketch_outputs \
  tests.test_annotate_sketches -v
```

Expected: all harness tests PASS.

- [ ] **Step 5: Run the complete repository test suite**

Run:

```bash
rtk pytest tests/
```

Expected: all existing and new tests PASS. If a pre-existing unrelated failure appears, report it with its exact test name and do not claim completion.

- [ ] **Step 6: Run static and CLI acceptance checks**

Run:

```bash
uv run python -m py_compile sketch_scoring/*.py scripts/score_sketch_outputs.py scripts/annotate_sketches.py
uv run python scripts/score_sketch_outputs.py --help
uv run python scripts/score_sketch_outputs.py manifest --help
uv run python scripts/score_sketch_outputs.py score --help
uv run python scripts/annotate_sketches.py --help
rtk git diff --check
```

Expected: commands exit successfully and no whitespace errors are reported.

- [ ] **Step 7: Perform a read-only smoke score on the real manifest**

Before the run, hash all 12 sources and all output-5 files. Then run:

```bash
uv run python scripts/score_sketch_outputs.py score \
  --manifest annotations/sketch-scoring/dataset.json \
  --label output-5-baseline
```

Verify:

- a new `reports/sketch-scoring/<run-id>/results.json` exists;
- `summary.csv` exists and has no total score;
- `latest.json` points to that run;
- 푸마2 and 필라1 pixel metrics are `not_scored` because their files are annotation-only;
- all pre-run image hashes and mtimes are unchanged;
- no report image, mask, thumbnail, or overlay was created;
- no API request was made.

- [ ] **Step 8: Smoke-test the Flask app without opening or judging images**

Use the Flask test client or start the server only long enough to request `/`, `/api/images`, and one annotation document. Verify HTTP 200 and then stop it. Do not perform visual quality judgment; the user will inspect the UI and generated images.

- [ ] **Step 9: Review the final diff without committing**

Run:

```bash
rtk git status --short
rtk git diff --stat
rtk git diff --check
```

Expected: the PRD, plan, approved dependencies, standalone harness, manifest, UI, and tests are present; unrelated pre-existing changes remain untouched.
