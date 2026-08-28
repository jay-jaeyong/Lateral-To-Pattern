"""채점 오케스트레이션, 출처 기록과 실행별 보고서 테스트.

실제 생성 API를 호출하지 않고 임시 디렉터리의 작은 합성 이미지만 씁니다.
"""

import ast
import dataclasses
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np

from sketch_scoring import scoring
from sketch_scoring.annotations import save_annotations
from sketch_scoring.manifest import ManifestError
from sketch_scoring.metrics import ImageDecodeError, ScoringConfig
from sketch_scoring.reporting import (
    LATEST_NAME,
    RESULTS_NAME,
    SUMMARY_NAME,
    build_summary_csv,
    write_run_reports,
)
from sketch_scoring.scoring import (
    ANNOTATED_ONLY_REASON,
    score_dataset,
    score_output,
    sha256_file,
)

CONFIG = ScoringConfig()
FORBIDDEN_RESULT_KEYS = {"total", "total_score", "overall", "overall_score", "rank"}

CONNECTION = {
    "id": "quarter-seam-1",
    "type": "connection",
    "target_box": [0.2, 0.4, 0.8, 0.6],
    "anchors": {
        "start_region": [0.30, 0.45, 0.36, 0.55],
        "end_region": [0.62, 0.45, 0.68, 0.55],
    },
}


def _save(path: Path, rgb: np.ndarray, suffix: str = ".png") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ok, encoded = cv2.imencode(suffix, cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
    assert ok
    path.write_bytes(encoded.tobytes())


def _source() -> np.ndarray:
    image = np.full((300, 200, 3), 255, dtype=np.uint8)
    cv2.rectangle(image, (40, 60), (160, 240), (30, 60, 200), -1)
    return image


def _sketch() -> np.ndarray:
    image = np.full((300, 200, 3), 255, dtype=np.uint8)
    cv2.rectangle(image, (40, 60), (160, 240), (0, 0, 0), 2)
    cv2.line(image, (60, 150), (140, 150), (0, 0, 0), 3)
    return image


def _project(tmp: str, *, output_name: str = "shoe_sketch.png") -> Path:
    root = Path(tmp)
    _save(root / "images" / "shoe_color.png", _source())
    suffix = ".jpeg" if output_name.endswith(".jpeg") else ".png"
    _save(root / "images" / "output-5" / output_name, _sketch(), suffix)
    return root


def _manifest_file(
    root: Path, *, kind: str = "clean", output_name: str = "shoe_sketch.png"
) -> Path:
    document = {
        "schema_version": 1,
        "items": {
            "shoe": {
                "display_name": "shoe",
                "source": "images/shoe_color.png",
                "expected_canvas_ratio": "2:3",
                "needs_review": False,
                "outputs": {
                    "output-5": {
                        "path": f"images/output-5/{output_name}",
                        "kind": kind,
                    }
                },
            }
        },
    }
    path = root / "dataset.json"
    path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
    return path


def _item(root: Path, *, kind: str = "clean", output_name: str = "shoe_sketch.png"):
    return (
        {
            "display_name": "shoe",
            "source": "images/shoe_color.png",
            "expected_canvas_ratio": "2:3",
            "needs_review": False,
            "outputs": {},
        },
        {"path": f"images/output-5/{output_name}", "kind": kind},
    )


def _snapshot(root: Path) -> dict:
    snapshot = {}
    for path in sorted((root / "images").rglob("*")):
        if path.is_file():
            stat = path.stat()
            snapshot[str(path)] = (sha256_file(path), stat.st_size, stat.st_mtime_ns)
    return snapshot


def _walk_keys(value, found: set) -> set:
    if isinstance(value, dict):
        found.update(value)
        for child in value.values():
            _walk_keys(child, found)
    elif isinstance(value, list):
        for child in value:
            _walk_keys(child, found)
    return found


class ScoreOutputTest(unittest.TestCase):
    def test_clean_output_runs_global_and_annotation_metrics(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _project(tmp)
            annotation_root = root / "annotations"
            save_annotations(
                annotation_root, "shoe", {"schema_version": 1, "annotations": [CONNECTION]}
            )
            item, record = _item(root)

            result = score_output(
                "shoe",
                item,
                "output-5",
                record,
                project_root=root,
                annotation_root=annotation_root,
                config=CONFIG,
            )

            self.assertEqual(
                sorted(result["metrics"]),
                [
                    "aspect_ratio",
                    "black_fill",
                    "colored_pixels",
                    "faint_strokes",
                    "silhouette_iou",
                ],
            )
            self.assertEqual(result["metrics"]["aspect_ratio"]["status"], "pass")
            self.assertEqual(len(result["annotations"]), 1)
            entry = result["annotations"][0]
            self.assertEqual(entry["id"], "quarter-seam-1")
            self.assertEqual(entry["type"], "connection")
            self.assertIn(entry["metric"]["status"], {"pass", "fail", "not_scored"})
            self.assertEqual(result["kind"], "clean")
            self.assertEqual(result["version"], "output-5")

    def test_annotated_only_output_marks_pixel_metrics_not_scored(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _project(tmp, output_name="shoe_sketch.jpeg")
            annotation_root = root / "annotations"
            save_annotations(
                annotation_root, "shoe", {"schema_version": 1, "annotations": [CONNECTION]}
            )
            item, record = _item(root, kind="annotated_only", output_name="shoe_sketch.jpeg")

            with patch(
                "sketch_scoring.scoring.load_rgb", wraps=scoring.load_rgb
            ) as decode:
                result = score_output(
                    "shoe",
                    item,
                    "output-5",
                    record,
                    project_root=root,
                    annotation_root=annotation_root,
                    config=CONFIG,
                )

            # 필수 원본만 디코드하고, 합성 표시가 있는 출력은 디코드하지 않습니다.
            decoded = [call.args[0] for call in decode.call_args_list]
            self.assertEqual(decoded, [(root / "images" / "shoe_color.png").resolve()])
            for name, metric in result["metrics"].items():
                with self.subTest(metric=name):
                    self.assertEqual(metric["status"], "not_scored")
                    self.assertEqual(metric["reason"], ANNOTATED_ONLY_REASON)
                    self.assertIsNone(metric["score"])
            self.assertEqual(
                result["annotations"][0]["metric"]["reason"], ANNOTATED_ONLY_REASON
            )
            # 주석은 여전히 읽고 검증합니다.
            self.assertEqual(result["annotation_count"], 1)
            self.assertTrue(result["output_sha256"])

    def test_missing_clean_output_does_not_decode_annotation_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _project(tmp)
            annotation_root = root / "annotations"
            item, record = _item(root, output_name="absent_sketch.png")

            with patch(
                "sketch_scoring.scoring.load_rgb", wraps=scoring.load_rgb
            ) as decode:
                result = score_output(
                    "shoe",
                    item,
                    "output-5",
                    record,
                    project_root=root,
                    annotation_root=annotation_root,
                    config=CONFIG,
                )

            # 원본만 디코드하고 없는 출력은 디코드하지 않습니다.
            decoded = [call.args[0] for call in decode.call_args_list]
            self.assertEqual(decoded, [(root / "images" / "shoe_color.png").resolve()])
            self.assertIsNone(result["output_sha256"])
            for metric in result["metrics"].values():
                self.assertEqual(metric["status"], "not_scored")
                self.assertIn("출력 파일이 없음", metric["reason"])

    def test_undecodable_source_is_fatal_for_annotated_only_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _project(tmp, output_name="shoe_sketch.jpeg")
            (root / "images" / "shoe_color.png").write_bytes(b"not an image at all")
            item, record = _item(
                root, kind="annotated_only", output_name="shoe_sketch.jpeg"
            )

            with self.assertRaises(ImageDecodeError):
                score_output(
                    "shoe",
                    item,
                    "output-5",
                    record,
                    project_root=root,
                    annotation_root=root / "annotations",
                    config=CONFIG,
                )

    def test_undecodable_source_is_fatal_for_missing_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _project(tmp)
            (root / "images" / "shoe_color.png").write_bytes(b"not an image at all")
            item, record = _item(root, output_name="absent_sketch.png")

            with self.assertRaises(ImageDecodeError):
                score_output(
                    "shoe",
                    item,
                    "output-5",
                    record,
                    project_root=root,
                    annotation_root=root / "annotations",
                    config=CONFIG,
                )

    def test_undecodable_source_is_fatal_for_the_whole_dataset(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _project(tmp, output_name="shoe_sketch.jpeg")
            (root / "images" / "shoe_color.png").write_bytes(b"broken")
            manifest = _manifest_file(
                root, kind="annotated_only", output_name="shoe_sketch.jpeg"
            )

            with self.assertRaises(ImageDecodeError):
                score_dataset(
                    manifest,
                    annotation_root=root / "annotations",
                    project_root=root,
                    config=CONFIG,
                )

    def test_undecodable_existing_clean_output_is_fatal(self):
        """매핑된 깨끗한 출력이 있는데 디코드되지 않으면 미채점으로 덮지 않습니다."""
        with tempfile.TemporaryDirectory() as tmp:
            root = _project(tmp)
            (root / "images" / "output-5" / "shoe_sketch.png").write_bytes(b"broken png")
            item, record = _item(root)

            with self.assertRaises(ImageDecodeError):
                score_output(
                    "shoe",
                    item,
                    "output-5",
                    record,
                    project_root=root,
                    annotation_root=root / "annotations",
                    config=CONFIG,
                )

    def test_undecodable_existing_clean_output_fails_the_dataset(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _project(tmp)
            (root / "images" / "output-5" / "shoe_sketch.png").write_bytes(b"broken png")
            manifest = _manifest_file(root)

            with self.assertRaises(ImageDecodeError):
                score_dataset(
                    manifest,
                    annotation_root=root / "annotations",
                    project_root=root,
                    config=CONFIG,
                )

    def test_missing_output_stays_not_scored_while_corrupt_output_is_fatal(self):
        """없는 출력과 깨진 출력은 다르게 다룹니다."""
        with tempfile.TemporaryDirectory() as tmp:
            root = _project(tmp)
            absent_item, absent_record = _item(root, output_name="absent_sketch.png")
            result = score_output(
                "shoe",
                absent_item,
                "output-5",
                absent_record,
                project_root=root,
                annotation_root=root / "annotations",
                config=CONFIG,
            )
            self.assertTrue(
                all(m["status"] == "not_scored" for m in result["metrics"].values())
            )

            (root / "images" / "output-5" / "shoe_sketch.png").write_bytes(b"broken")
            item, record = _item(root)
            with self.assertRaises(ImageDecodeError):
                score_output(
                    "shoe",
                    item,
                    "output-5",
                    record,
                    project_root=root,
                    annotation_root=root / "annotations",
                    config=CONFIG,
                )

    def test_clean_output_decodes_source_once_and_output_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _project(tmp)
            item, record = _item(root)

            with patch(
                "sketch_scoring.scoring.load_rgb", wraps=scoring.load_rgb
            ) as decode:
                score_output(
                    "shoe",
                    item,
                    "output-5",
                    record,
                    project_root=root,
                    annotation_root=root / "annotations",
                    config=CONFIG,
                )

            decoded = [call.args[0] for call in decode.call_args_list]
            self.assertEqual(
                decoded,
                [
                    (root / "images" / "shoe_color.png").resolve(),
                    (root / "images" / "output-5" / "shoe_sketch.png").resolve(),
                ],
            )

    def test_one_metric_exception_becomes_not_scored_without_aborting_item(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _project(tmp)
            annotation_root = root / "annotations"
            save_annotations(
                annotation_root, "shoe", {"schema_version": 1, "annotations": [CONNECTION]}
            )
            item, record = _item(root)

            with patch(
                "sketch_scoring.metrics.score_silhouette",
                side_effect=RuntimeError("boom"),
            ), patch(
                "sketch_scoring.metrics.score_connection",
                side_effect=RuntimeError("anchor boom"),
            ):
                result = score_output(
                    "shoe",
                    item,
                    "output-5",
                    record,
                    project_root=root,
                    annotation_root=annotation_root,
                    config=CONFIG,
                )

            self.assertEqual(result["metrics"]["silhouette_iou"]["status"], "not_scored")
            self.assertIn("boom", result["metrics"]["silhouette_iou"]["reason"])
            self.assertEqual(result["metrics"]["aspect_ratio"]["status"], "pass")
            annotation_metric = result["annotations"][0]["metric"]
            self.assertEqual(annotation_metric["status"], "not_scored")
            self.assertIn("anchor boom", annotation_metric["reason"])

    def test_image_hash_and_mtime_are_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _project(tmp)
            annotation_root = root / "annotations"
            save_annotations(
                annotation_root, "shoe", {"schema_version": 1, "annotations": [CONNECTION]}
            )
            item, record = _item(root)
            before = _snapshot(root)

            score_output(
                "shoe",
                item,
                "output-5",
                record,
                project_root=root,
                annotation_root=annotation_root,
                config=CONFIG,
            )

            self.assertEqual(_snapshot(root), before)

    def test_result_contains_no_total_score(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _project(tmp)
            manifest = _manifest_file(root)
            result = score_dataset(
                manifest,
                annotation_root=root / "annotations",
                project_root=root,
                config=CONFIG,
            )
            keys = _walk_keys(result, set())
            self.assertEqual(keys & FORBIDDEN_RESULT_KEYS, set())
            self.assertTrue(result["diagnostic_only"])

    def test_result_records_manifest_annotation_source_and_output_hashes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _project(tmp)
            annotation_root = root / "annotations"
            save_annotations(
                annotation_root, "shoe", {"schema_version": 1, "annotations": [CONNECTION]}
            )
            manifest = _manifest_file(root)

            result = score_dataset(
                manifest,
                annotation_root=annotation_root,
                project_root=root,
                config=CONFIG,
            )

            provenance = result["provenance"]
            self.assertEqual(provenance["manifest_sha256"], sha256_file(manifest))
            self.assertEqual(
                provenance["annotation_sha256"]["shoe"],
                sha256_file(annotation_root / "shoe.json"),
            )
            self.assertEqual(provenance["harness_version"], "1")
            self.assertIsNone(provenance["git_commit"])
            self.assertTrue(provenance["started_at"].endswith("Z"))
            self.assertEqual(provenance["config"]["canvas_width"], 512)
            self.assertEqual(provenance["config"]["canvas_height"], 768)
            # 설정 필드를 추가하면 출처 기록에 자동으로 함께 남습니다.
            self.assertEqual(
                sorted(provenance["config"]),
                sorted(dataclasses.asdict(CONFIG)),
            )
            self.assertEqual(
                provenance["config"]["connection_min_confidence"],
                CONFIG.connection_min_confidence,
            )

            output = result["items"]["shoe"]["output-5"]
            self.assertEqual(
                output["source_sha256"], sha256_file(root / "images" / "shoe_color.png")
            )
            self.assertEqual(
                output["output_sha256"],
                sha256_file(root / "images" / "output-5" / "shoe_sketch.png"),
            )

    def test_invalid_manifest_is_fatal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _project(tmp)
            path = root / "dataset.json"
            path.write_text(
                json.dumps({"schema_version": 1, "items": {"shoe": {"outputs": {}}}}),
                encoding="utf-8",
            )
            with self.assertRaises(ManifestError):
                score_dataset(
                    path, annotation_root=root / "annotations", project_root=root
                )

    def test_version_filter_limits_scored_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _project(tmp)
            manifest = _manifest_file(root)
            result = score_dataset(
                manifest,
                versions={"output-4"},
                annotation_root=root / "annotations",
                project_root=root,
            )
            self.assertEqual(result["items"]["shoe"], {})

    def test_scoring_module_does_not_import_generation_services(self):
        modules = set()
        for path in (Path(scoring.__file__),):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if isinstance(node, ast.Import):
                    modules.update(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom):
                    modules.add(node.module or "")
        for name in modules:
            with self.subTest(module=name):
                self.assertFalse(name.startswith("services"))
                self.assertFalse(name.startswith("google"))
                self.assertFalse(name.startswith("core"))
                self.assertFalse(name.startswith("handlers"))


def _metric(status, raw=None, reason=None, **details):
    payload = {} if raw is None else {"raw_score": raw}
    payload.update(details)
    return {
        "score": raw,
        "status": status,
        "confidence": 1.0,
        "reason": reason,
        "details": payload,
    }


def _two_version_result() -> dict:
    def output(colored, iou, missing, extra, status="pass"):
        return {
            "kind": "clean",
            "version": "x",
            "path": "images/output-x/a_sketch.png",
            "source_sha256": "a" * 64,
            "output_sha256": "b" * 64,
            "annotation_count": 1,
            "metrics": {
                "colored_pixels": _metric(status, colored),
                "silhouette_iou": _metric("not_scored", iou, "정상 사례 기반 문턱 미확정"),
            },
            "annotations": [
                {
                    "id": "heel-complete",
                    "type": "complete_roi",
                    "label": "heel",
                    "metric": _metric(
                        "not_scored",
                        missing,
                        "정상 사례 기반 문턱 미확정",
                        missing_ratio=missing,
                        extra_ratio=extra,
                    ),
                }
            ],
        }

    return {
        "schema_version": 1,
        "diagnostic_only": True,
        "provenance": {
            "started_at": "2026-08-26T06:30:00Z",
            "manifest_path": "annotations/sketch-scoring/dataset.json",
            "manifest_sha256": "c" * 64,
            "annotation_sha256": {},
            "git_commit": None,
            "harness_version": "1",
            "config": {"canvas_width": 512, "canvas_height": 768},
        },
        "items": {
            "a": {
                "output-4": output(0.01, 0.50, 0.40, 0.30, "fail"),
                "output-5": output(0.00, 0.80, 0.10, 0.30, "pass"),
            },
            "b": {
                "output-4": output(0.00, 0.70, 0.20, 0.10, "pass"),
                "output-5": output(0.03, 0.60, 0.20, 0.40, "fail"),
            },
            "c": {
                "output-5": {
                    "kind": "annotated_only",
                    "version": "output-5",
                    "path": "images/output-5/c_sketch.jpeg",
                    "source_sha256": "d" * 64,
                    "output_sha256": "e" * 64,
                    "annotation_count": 0,
                    "metrics": {
                        "colored_pixels": _metric(
                            "not_scored", None, ANNOTATED_ONLY_REASON
                        ),
                        "silhouette_iou": _metric(
                            "not_scored", None, ANNOTATED_ONLY_REASON
                        ),
                    },
                    "annotations": [],
                }
            },
        },
    }


def _csv_rows(text: str) -> list[dict]:
    import csv
    import io

    return list(csv.DictReader(io.StringIO(text)))


class SummaryCsvTest(unittest.TestCase):
    def test_header_has_no_total_or_rank_column(self):
        text = build_summary_csv(_two_version_result())
        header = text.splitlines()[0].split(",")
        self.assertEqual(
            header,
            [
                "version",
                "metric",
                "median",
                "improved",
                "same",
                "worsened",
                "pass",
                "warn",
                "fail",
                "not_scored",
                "not_scored_reasons",
            ],
        )
        for column in header:
            self.assertNotIn(column, FORBIDDEN_RESULT_KEYS)

    def test_median_and_status_counts_per_version(self):
        rows = _csv_rows(build_summary_csv(_two_version_result()))
        colored = {row["version"]: row for row in rows if row["metric"] == "colored_pixels"}
        self.assertEqual(float(colored["output-4"]["median"]), 0.005)
        self.assertEqual(colored["output-4"]["pass"], "1")
        self.assertEqual(colored["output-4"]["fail"], "1")
        self.assertEqual(colored["output-5"]["not_scored"], "1")
        self.assertIn(ANNOTATED_ONLY_REASON, colored["output-5"]["not_scored_reasons"])

    def test_improved_same_worsened_between_ordered_versions(self):
        rows = _csv_rows(build_summary_csv(_two_version_result()))
        first = next(
            row
            for row in rows
            if row["metric"] == "colored_pixels" and row["version"] == "output-4"
        )
        self.assertEqual((first["improved"], first["same"], first["worsened"]), ("0", "0", "0"))

        # colored_pixels는 낮을수록 좋음: a 0.01→0.00 개선, b 0.00→0.03 악화.
        colored = next(
            row
            for row in rows
            if row["metric"] == "colored_pixels" and row["version"] == "output-5"
        )
        self.assertEqual(colored["improved"], "1")
        self.assertEqual(colored["worsened"], "1")

        # silhouette_iou는 높을수록 좋음: a 0.50→0.80 개선, b 0.70→0.60 악화.
        iou = next(
            row
            for row in rows
            if row["metric"] == "silhouette_iou" and row["version"] == "output-5"
        )
        self.assertEqual(iou["improved"], "1")
        self.assertEqual(iou["worsened"], "1")

    def test_complete_roi_missing_and_extra_are_separate_rows(self):
        rows = _csv_rows(build_summary_csv(_two_version_result()))
        names = {row["metric"] for row in rows}
        self.assertIn("complete_roi.missing_ratio", names)
        self.assertIn("complete_roi.extra_ratio", names)

        missing = next(
            row
            for row in rows
            if row["metric"] == "complete_roi.missing_ratio"
            and row["version"] == "output-5"
        )
        # a 0.40→0.10 개선, b 0.20→0.20 동일.
        self.assertEqual(missing["improved"], "1")
        self.assertEqual(missing["same"], "1")

        extra = next(
            row
            for row in rows
            if row["metric"] == "complete_roi.extra_ratio"
            and row["version"] == "output-5"
        )
        # a 0.30→0.30 동일, b 0.10→0.40 악화.
        self.assertEqual(extra["same"], "1")
        self.assertEqual(extra["worsened"], "1")


class RunReportTest(unittest.TestCase):
    def test_run_directory_has_utc_timestamp_and_sanitized_label(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = write_run_reports(
                _two_version_result(), Path(tmp), "output 5/baseline!"
            )
            self.assertTrue(run_dir.name.endswith("output-5-baseline"))
            stamp = run_dir.name.split("-")[0]
            self.assertRegex(stamp, r"^\d{8}T\d{6}Z$")

    def test_second_run_with_same_label_does_not_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = write_run_reports(_two_version_result(), root, "same-label")
            second = write_run_reports(_two_version_result(), root, "same-label")
            self.assertNotEqual(first, second)
            self.assertTrue((first / RESULTS_NAME).is_file())
            self.assertTrue((second / RESULTS_NAME).is_file())
            self.assertEqual(
                json.loads((root / LATEST_NAME).read_text(encoding="utf-8"))["run_id"],
                second.name,
            )

    def test_only_json_and_csv_files_are_generated(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = write_run_reports(_two_version_result(), root, "run")
            self.assertEqual(
                sorted(path.name for path in run_dir.iterdir()),
                [RESULTS_NAME, SUMMARY_NAME],
            )
            self.assertEqual(
                sorted(path.name for path in root.iterdir()),
                sorted([LATEST_NAME, run_dir.name]),
            )
            for path in root.rglob("*"):
                self.assertNotIn(
                    path.suffix.lower(), {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".npy"}
                )

    def test_results_json_round_trips_and_keeps_no_total(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = write_run_reports(_two_version_result(), Path(tmp), "run")
            stored = json.loads((run_dir / RESULTS_NAME).read_text(encoding="utf-8"))
            self.assertTrue(stored["diagnostic_only"])
            self.assertEqual(_walk_keys(stored, set()) & FORBIDDEN_RESULT_KEYS, set())


REPO_ROOT = Path(__file__).resolve().parent.parent
HARNESS_SCRIPTS = ("score_sketch_outputs.py", "annotate_sketches.py")
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff", ".npy", ".npz"}


def _imported_modules(path: Path) -> set[str]:
    modules: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            modules.add(node.module or "")
    return modules


def _production_files() -> list[Path]:
    """하네스와 테스트를 뺀 생산 코드 파일."""
    skip_dirs = {".venv", ".git", "__pycache__", "tests", "sketch_scoring", ".worktrees"}
    found = []
    for path in sorted(REPO_ROOT.rglob("*.py")):
        parts = set(path.relative_to(REPO_ROOT).parts)
        if parts & skip_dirs:
            continue
        if path.name in HARNESS_SCRIPTS:
            continue
        found.append(path)
    return found


class ImportBoundaryTest(unittest.TestCase):
    def test_generation_code_never_imports_the_harness(self):
        files = _production_files()
        self.assertGreater(len(files), 5, "생산 코드 파일을 찾지 못했습니다")
        for path in files:
            with self.subTest(file=str(path.relative_to(REPO_ROOT))):
                for module in _imported_modules(path):
                    self.assertFalse(module == "sketch_scoring")
                    self.assertFalse(module.startswith("sketch_scoring."))

    def test_pipeline_entry_points_are_covered_by_the_scan(self):
        scanned = {path.relative_to(REPO_ROOT).as_posix() for path in _production_files()}
        for expected in (
            "main.py",
            "config/prompts.py",
            "services/gemini_client.py",
            "scripts/run_step3_on_color_patterns.py",
        ):
            self.assertIn(expected, scanned)

    def test_harness_never_imports_generation_or_external_sdks(self):
        paths = sorted((REPO_ROOT / "sketch_scoring").glob("*.py")) + [
            REPO_ROOT / "scripts" / name for name in HARNESS_SCRIPTS
        ]
        for path in paths:
            with self.subTest(file=path.name):
                for module in _imported_modules(path):
                    for forbidden in (
                        "services",
                        "google",
                        "core",
                        "handlers",
                        "config",
                        "main",
                        "streamlit",
                        "scipy",
                        "skimage",
                        "torch",
                    ):
                        self.assertFalse(
                            module == forbidden or module.startswith(f"{forbidden}."),
                            f"{path.name}이 {module}을 import합니다",
                        )


class NoImageWriteTest(unittest.TestCase):
    def _harness_sources(self) -> list[Path]:
        return sorted((REPO_ROOT / "sketch_scoring").glob("*.py")) + [
            REPO_ROOT / "scripts" / name for name in HARNESS_SCRIPTS
        ]

    def test_no_image_save_calls_anywhere_in_the_harness(self):
        forbidden = {"imwrite", "imsave", "save", "savefig", "imshow"}
        for path in self._harness_sources():
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    name = None
                    if isinstance(node.func, ast.Attribute):
                        name = node.func.attr
                    elif isinstance(node.func, ast.Name):
                        name = node.func.id
                    if name in forbidden:
                        self.fail(f"{path.name}에 금지된 호출이 있습니다: {name}")

    def test_no_file_is_opened_for_writing_outside_json_and_csv(self):
        for path in self._harness_sources():
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                is_open = (isinstance(node.func, ast.Name) and node.func.id == "open") or (
                    isinstance(node.func, ast.Attribute) and node.func.attr == "open"
                )
                if not is_open:
                    continue
                mode = "r"
                if len(node.args) > 1 and isinstance(node.args[1], ast.Constant):
                    mode = str(node.args[1].value)
                for keyword in node.keywords:
                    if keyword.arg == "mode" and isinstance(keyword.value, ast.Constant):
                        mode = str(keyword.value.value)
                with self.subTest(file=path.name):
                    self.assertNotRegex(mode, r"[wax+]", f"{path.name}이 쓰기 모드로 엽니다")

    def test_no_automatic_registration_or_warp_helper_exists(self):
        forbidden = ("register", "align", "warp", "affine", "homography", "reflect")
        for path in self._harness_sources():
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    lowered = node.name.lower()
                    for token in forbidden:
                        self.assertNotIn(
                            token, lowered, f"{path.name}: {node.name}은 정렬 보조로 보입니다"
                        )


class ForbiddenComparisonFieldTest(unittest.TestCase):
    def test_manifest_rejects_symmetry_fields(self):
        from sketch_scoring.manifest import load_manifest

        with tempfile.TemporaryDirectory() as tmp:
            root = _project(tmp)
            path = root / "dataset.json"
            path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "items": {
                            "shoe": {
                                "source": "images/shoe_color.png",
                                "outputs": {},
                                "medial_lateral_similarity": 0.8,
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaises(ManifestError):
                load_manifest(path, project_root=root)

    def test_annotation_schema_rejects_reflection_fields(self):
        from sketch_scoring.annotations import (
            AnnotationError,
            validate_annotation_document,
        )

        for extra in ({"mirror": True}, {"opposite_side": "medial"}, {"symmetry": 1}):
            with self.subTest(extra=extra):
                annotation = dict(CONNECTION, **extra)
                with self.assertRaises(AnnotationError):
                    validate_annotation_document(
                        {"schema_version": 1, "annotations": [annotation]}
                    )

    def test_no_symmetry_metric_is_exposed(self):
        from sketch_scoring import metrics

        for name in dir(metrics):
            lowered = name.lower()
            for token in ("symmetry", "mirror", "medial", "lateral", "reflect"):
                self.assertNotIn(token, lowered)

    def test_translated_and_flipped_output_still_loses_score(self):
        """정렬·반전을 하지 않으므로 이동·좌우 반전은 점수를 잃습니다."""
        from sketch_scoring.metrics import ImageDecodeError, ScoringConfig, score_silhouette

        config = ScoringConfig()
        # 좌우 대칭이 아닌 같은 삼각형을 원본과 출력에 씁니다.
        source = _asymmetric_source()
        aligned = _asymmetric_sketch()
        shifted = _asymmetric_sketch(offset=40)
        flipped = np.ascontiguousarray(aligned[:, ::-1])

        base = score_silhouette(source, aligned, config).details["raw_score"]
        self.assertGreater(base, 0.9)
        self.assertLess(
            score_silhouette(source, shifted, config).details["raw_score"], base - 0.1
        )
        self.assertLess(
            score_silhouette(source, flipped, config).details["raw_score"], base - 0.1
        )


_TRIANGLE = np.array([[20, 40], [180, 90], [60, 260]], dtype=np.int32)


def _asymmetric_source() -> np.ndarray:
    image = np.full((300, 200, 3), 255, dtype=np.uint8)
    cv2.fillPoly(image, [_TRIANGLE], (30, 60, 200))
    return image


def _asymmetric_sketch(offset: int = 0) -> np.ndarray:
    image = np.full((300, 200, 3), 255, dtype=np.uint8)
    points = _TRIANGLE + np.array([offset, 0], dtype=np.int32)
    cv2.polylines(image, [points], True, (0, 0, 0), 2)
    return image


class FilesystemBoundaryTest(unittest.TestCase):
    """manifest 탐색·채점·주석 저장·개별 채점 전부가 이미지를 건드리지 않습니다."""

    def _full_snapshot(self, root: Path) -> dict:
        snapshot = {}
        for path in sorted((root / "images").rglob("*")):
            if path.is_file():
                stat = path.stat()
                snapshot[path.relative_to(root).as_posix()] = (
                    sha256_file(path),
                    stat.st_size,
                    stat.st_mtime_ns,
                )
        return snapshot

    def test_whole_harness_writes_only_under_annotation_and_report_roots(self):
        from scripts.annotate_sketches import create_app
        from sketch_scoring.manifest import discover_manifest, write_manifest

        with tempfile.TemporaryDirectory() as tmp:
            root = _project(tmp)
            annotation_root = root / "annotations" / "sketch-scoring"
            reports_root = root / "reports" / "sketch-scoring"
            (annotation_root / "items").mkdir(parents=True)
            reports_root.mkdir(parents=True)
            manifest_path = annotation_root / "dataset.json"
            before_images = self._full_snapshot(root)

            # 1. manifest 탐색
            write_manifest(manifest_path, discover_manifest(root / "images"))
            document = json.loads(manifest_path.read_text(encoding="utf-8"))
            document["items"]["shoe"]["expected_canvas_ratio"] = "2:3"
            manifest_path.write_text(
                json.dumps(document, ensure_ascii=False), encoding="utf-8"
            )

            # 2. dataset 채점과 보고서
            result = score_dataset(
                manifest_path,
                annotation_root=annotation_root / "items",
                project_root=root,
                config=CONFIG,
            )
            run_dir = write_run_reports(result, reports_root, "boundary")

            # 3. 주석 API 읽기·쓰기, 4. 개별 채점 API
            client = create_app(
                manifest_path,
                project_root=root,
                annotation_root=annotation_root / "items",
            ).test_client()
            self.assertEqual(client.get("/api/annotations/shoe").status_code, 200)
            self.assertEqual(
                client.post(
                    "/api/annotations/shoe",
                    json={"schema_version": 1, "annotations": [CONNECTION]},
                ).status_code,
                200,
            )
            self.assertEqual(
                client.post("/api/score/shoe", json={"version": "output-5"}).status_code,
                200,
            )

            self.assertEqual(self._full_snapshot(root), before_images)

            written = sorted(
                path.relative_to(root).as_posix()
                for path in root.rglob("*")
                if path.is_file() and not path.relative_to(root).as_posix().startswith("images/")
            )
            self.assertTrue(written)
            for path in written:
                self.assertTrue(
                    path.startswith("annotations/sketch-scoring/")
                    or path.startswith("reports/sketch-scoring/"),
                    f"허용되지 않은 위치에 파일이 생겼습니다: {path}",
                )

            for path in reports_root.rglob("*"):
                self.assertNotIn(path.suffix.lower(), IMAGE_SUFFIXES)
                for token in ("mask", "thumb", "overlay", "preview"):
                    self.assertNotIn(token, path.name.lower())
            self.assertEqual(
                sorted(path.name for path in run_dir.iterdir()),
                [RESULTS_NAME, SUMMARY_NAME],
            )

    def test_sidecar_is_untouched_until_an_explicit_save(self):
        from scripts.annotate_sketches import create_app

        with tempfile.TemporaryDirectory() as tmp:
            root = _project(tmp)
            annotation_root = root / "annotations" / "sketch-scoring" / "items"
            manifest_path = _manifest_file(root)
            path = save_annotations(
                annotation_root, "shoe", {"schema_version": 1, "annotations": []}
            )
            before = path.read_bytes()
            client = create_app(
                manifest_path, project_root=root, annotation_root=annotation_root
            ).test_client()

            client.get("/api/annotations/shoe")
            client.post("/api/import-red-boxes/shoe", json={"version": "output-5"})
            client.post(
                "/api/suggest-anchors/shoe",
                json={"version": "output-5", "target_box": [0.2, 0.4, 0.8, 0.6]},
            )
            client.post("/api/score/shoe", json={"version": "output-5"})
            self.assertEqual(path.read_bytes(), before)

            client.post(
                "/api/annotations/shoe",
                json={"schema_version": 1, "annotations": [CONNECTION]},
            )
            self.assertNotEqual(path.read_bytes(), before)

    def test_annotated_only_output_never_reaches_load_rgb(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _project(tmp, output_name="shoe_sketch.jpeg")
            manifest = _manifest_file(
                root, kind="annotated_only", output_name="shoe_sketch.jpeg"
            )
            with patch(
                "sketch_scoring.scoring.load_rgb", wraps=scoring.load_rgb
            ) as decode:
                result = score_dataset(
                    manifest,
                    annotation_root=root / "annotations",
                    project_root=root,
                    config=CONFIG,
                )
            # 원본만 디코드하고 합성 표시 출력은 디코드하지 않습니다.
            decoded = [call.args[0] for call in decode.call_args_list]
            self.assertEqual(decoded, [(root / "images" / "shoe_color.png").resolve()])
            metrics = result["items"]["shoe"]["output-5"]["metrics"]
            self.assertTrue(
                all(metric["status"] == "not_scored" for metric in metrics.values())
            )

    def test_reports_contain_no_total_or_rank_in_json_or_csv(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _project(tmp)
            manifest = _manifest_file(root)
            result = score_dataset(
                manifest,
                annotation_root=root / "annotations",
                project_root=root,
                config=CONFIG,
            )
            reports_root = root / "reports" / "sketch-scoring"
            run_dir = write_run_reports(result, reports_root, "no-total")

            stored = json.loads((run_dir / RESULTS_NAME).read_text(encoding="utf-8"))
            self.assertEqual(_walk_keys(stored, set()) & FORBIDDEN_RESULT_KEYS, set())
            csv_text = (run_dir / SUMMARY_NAME).read_text(encoding="utf-8")
            header = csv_text.splitlines()[0].split(",")
            for column in header:
                self.assertNotIn(column, FORBIDDEN_RESULT_KEYS)
            for token in ("total", "overall", "rank"):
                self.assertNotIn(token, csv_text.lower())


if __name__ == "__main__":
    unittest.main()
