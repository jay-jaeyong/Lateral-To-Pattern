"""진단 하네스 CLI 테스트.

서브프로세스를 띄우지 않고 `main()`을 직접 부릅니다. 모든 경로는 임시
프로젝트 안이며 실제 `images/`, `annotations/`, `reports/`를 건드리지 않습니다.
"""

import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np

from scripts import score_sketch_outputs as cli
from sketch_scoring.reporting import LATEST_NAME, RESULTS_NAME, SUMMARY_NAME


def _save(path: Path, rgb: np.ndarray, suffix: str = ".png") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ok, encoded = cv2.imencode(suffix, cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
    assert ok
    path.write_bytes(encoded.tobytes())


ANNOTATION_ROOT = "annotations/sketch-scoring"
REPORTS_ROOT = "reports/sketch-scoring"


def _project(tmp: str, *, sketch_suffix: str = ".png") -> Path:
    root = Path(tmp)
    (root / ANNOTATION_ROOT / "items").mkdir(parents=True, exist_ok=True)
    source = np.full((300, 200, 3), 255, dtype=np.uint8)
    cv2.rectangle(source, (40, 60), (160, 240), (30, 60, 200), -1)
    _save(root / "images" / "shoe_color.png", source)
    sketch = np.full((300, 200, 3), 255, dtype=np.uint8)
    cv2.rectangle(sketch, (40, 60), (160, 240), (0, 0, 0), 2)
    _save(root / "images" / "output-5" / f"shoe_sketch{sketch_suffix}", sketch, sketch_suffix)
    return root


@contextlib.contextmanager
def _inside(root: Path):
    previous = os.getcwd()
    os.chdir(root)
    try:
        yield
    finally:
        os.chdir(previous)


def _run(argv: list[str]) -> tuple[int, str]:
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream), contextlib.redirect_stderr(stream):
        code = cli.main(argv)
    return code, stream.getvalue()


class ManifestCommandTest(unittest.TestCase):
    def test_manifest_command_creates_candidate_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _project(tmp)
            manifest = root / ANNOTATION_ROOT / "dataset.json"

            with _inside(root):
                code, _ = _run(
                    ["manifest", "--images-dir", "images", "--manifest", str(manifest)]
                )

            self.assertEqual(code, 0)
            document = json.loads(manifest.read_text(encoding="utf-8"))
            self.assertEqual(document["schema_version"], 1)
            item = document["items"]["shoe"]
            self.assertEqual(item["source"], "images/shoe_color.png")
            self.assertEqual(
                item["outputs"]["output-5"]["path"], "images/output-5/shoe_sketch.png"
            )

    def test_manifest_command_preserves_existing_confirmed_mapping(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _project(tmp)
            _save(root / "images" / "confirmed.png", np.full((4, 4, 3), 255, np.uint8))
            manifest = root / ANNOTATION_ROOT / "dataset.json"
            manifest.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "items": {
                            "shoe": {
                                "display_name": "shoe",
                                "source": "images/confirmed.png",
                                "expected_canvas_ratio": "3:4",
                                "needs_review": False,
                                "outputs": {},
                            }
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            with _inside(root):
                code, _ = _run(["manifest", "--manifest", str(manifest)])

            self.assertEqual(code, 0)
            item = json.loads(manifest.read_text(encoding="utf-8"))["items"]["shoe"]
            self.assertEqual(item["source"], "images/confirmed.png")
            self.assertEqual(item["expected_canvas_ratio"], "3:4")
            self.assertEqual(
                item["outputs"]["output-5"]["path"], "images/output-5/shoe_sketch.png"
            )

    def test_manifest_command_reports_broken_json_as_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _project(tmp)
            manifest = root / ANNOTATION_ROOT / "dataset.json"
            manifest.write_text("{ not json", encoding="utf-8")

            with _inside(root):
                code, output = _run(["manifest", "--manifest", str(manifest)])

            self.assertEqual(code, 1)
            self.assertIn("오류", output)


class ScoreCommandTest(unittest.TestCase):
    def _manifest(self, root: Path, *, kind: str = "clean", name: str = "shoe_sketch.png"):
        manifest = root / ANNOTATION_ROOT / "dataset.json"
        manifest.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "items": {
                        "shoe": {
                            "display_name": "shoe",
                            "source": "images/shoe_color.png",
                            "expected_canvas_ratio": "2:3",
                            "needs_review": False,
                            "outputs": {
                                "output-5": {
                                    "path": f"images/output-5/{name}",
                                    "kind": kind,
                                }
                            },
                        }
                    },
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return manifest

    def test_score_command_writes_run_reports(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _project(tmp)
            manifest = self._manifest(root)
            reports = root / REPORTS_ROOT

            with _inside(root):
                code, _ = _run(
                    [
                        "score",
                        "--manifest",
                        str(manifest),
                        "--annotation-root",
                        str(root / ANNOTATION_ROOT / "items"),
                        "--reports-root",
                        str(reports),
                        "--label",
                        "test-run",
                    ]
                )

            self.assertEqual(code, 0)
            latest = json.loads((reports / LATEST_NAME).read_text(encoding="utf-8"))
            run_dir = reports / latest["run_id"]
            self.assertTrue((run_dir / RESULTS_NAME).is_file())
            self.assertTrue((run_dir / SUMMARY_NAME).is_file())
            self.assertEqual(
                sorted(path.name for path in run_dir.iterdir()),
                [RESULTS_NAME, SUMMARY_NAME],
            )
            stored = json.loads((run_dir / RESULTS_NAME).read_text(encoding="utf-8"))
            self.assertTrue(stored["diagnostic_only"])
            self.assertIn("output-5", stored["items"]["shoe"])

    def test_schema_error_returns_nonzero(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _project(tmp)
            manifest = root / ANNOTATION_ROOT / "dataset.json"
            manifest.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "items": {"shoe": {"source": "/etc/passwd", "outputs": {}}},
                    }
                ),
                encoding="utf-8",
            )

            with _inside(root):
                code, output = _run(
                    [
                        "score",
                        "--manifest",
                        str(manifest),
                        "--annotation-root",
                        str(root / ANNOTATION_ROOT / "items"),
                        "--reports-root",
                        str(root / REPORTS_ROOT),
                        "--label",
                        "bad",
                    ]
                )

            self.assertEqual(code, 1)
            self.assertIn("오류", output)
            self.assertFalse((root / REPORTS_ROOT).exists())

    def test_individual_not_scored_metric_still_returns_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _project(tmp, sketch_suffix=".jpeg")
            manifest = self._manifest(root, kind="annotated_only", name="shoe_sketch.jpeg")
            reports = root / REPORTS_ROOT

            with _inside(root):
                code, _ = _run(
                    [
                        "score",
                        "--manifest",
                        str(manifest),
                        "--annotation-root",
                        str(root / ANNOTATION_ROOT / "items"),
                        "--reports-root",
                        str(reports),
                        "--label",
                        "annotated-only",
                    ]
                )

            self.assertEqual(code, 0)
            latest = json.loads((reports / LATEST_NAME).read_text(encoding="utf-8"))
            stored = json.loads(
                (reports / latest["run_id"] / RESULTS_NAME).read_text(encoding="utf-8")
            )
            metrics = stored["items"]["shoe"]["output-5"]["metrics"]
            self.assertTrue(
                all(metric["status"] == "not_scored" for metric in metrics.values())
            )


class RequiredSourceTest(unittest.TestCase):
    """필수 원본을 읽거나 디코드할 수 없으면 출력 종류와 무관하게 비정상 종료합니다."""

    def _run_score(self, root: Path, manifest: Path) -> tuple[int, str]:
        with _inside(root):
            return _run(
                [
                    "score",
                    "--manifest",
                    str(manifest),
                    "--annotation-root",
                    str(root / ANNOTATION_ROOT / "items"),
                    "--reports-root",
                    str(root / REPORTS_ROOT),
                    "--label",
                    "broken-source",
                ]
            )

    def test_undecodable_source_with_annotated_only_output_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _project(tmp, sketch_suffix=".jpeg")
            manifest = ScoreCommandTest()._manifest(
                root, kind="annotated_only", name="shoe_sketch.jpeg"
            )
            (root / "images" / "shoe_color.png").write_bytes(b"not an image at all")

            code, output = self._run_score(root, manifest)

            self.assertEqual(code, 1)
            self.assertIn("오류", output)
            self.assertIn("디코드", output)
            self.assertFalse((root / REPORTS_ROOT).exists())

    def test_undecodable_source_with_missing_output_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _project(tmp)
            manifest = ScoreCommandTest()._manifest(root, name="absent_sketch.png")
            (root / "images" / "shoe_color.png").write_bytes(b"not an image at all")

            code, output = self._run_score(root, manifest)

            self.assertEqual(code, 1)
            self.assertIn("오류", output)
            self.assertFalse((root / REPORTS_ROOT).exists())

    def test_missing_source_file_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _project(tmp)
            manifest = ScoreCommandTest()._manifest(root)
            (root / "images" / "shoe_color.png").unlink()

            code, output = self._run_score(root, manifest)

            self.assertEqual(code, 1)
            self.assertIn("오류", output)

    def test_undecodable_clean_output_fails_and_writes_no_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _project(tmp)
            manifest = ScoreCommandTest()._manifest(root)
            (root / "images" / "output-5" / "shoe_sketch.png").write_bytes(b"broken png")

            code, output = self._run_score(root, manifest)

            self.assertEqual(code, 1)
            self.assertIn("오류", output)
            self.assertIn("디코드", output)
            self.assertFalse((root / REPORTS_ROOT).exists())

    def test_failure_preserves_existing_latest_pointer_and_run_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _project(tmp)
            manifest = ScoreCommandTest()._manifest(root)

            # 먼저 정상 실행으로 이력을 만듭니다.
            first_code, _ = self._run_score(root, manifest)
            self.assertEqual(first_code, 0)
            reports = root / REPORTS_ROOT
            latest_before = (reports / LATEST_NAME).read_bytes()
            run_id = json.loads(latest_before.decode("utf-8"))["run_id"]
            history_before = {
                path.relative_to(reports).as_posix(): path.read_bytes()
                for path in sorted(reports.rglob("*"))
                if path.is_file()
            }

            # 그 다음 출력을 깨뜨리고 다시 실행합니다.
            (root / "images" / "output-5" / "shoe_sketch.png").write_bytes(b"broken png")
            code, output = self._run_score(root, manifest)

            self.assertEqual(code, 1)
            self.assertIn("오류", output)
            # 이전 실행 이력과 최신 포인터가 그대로 남아 있습니다.
            self.assertEqual((reports / LATEST_NAME).read_bytes(), latest_before)
            history_after = {
                path.relative_to(reports).as_posix(): path.read_bytes()
                for path in sorted(reports.rglob("*"))
                if path.is_file()
            }
            self.assertEqual(history_after, history_before)
            # 새 실행 디렉터리는 만들어지지 않았습니다.
            self.assertEqual(
                sorted(p.name for p in reports.iterdir() if p.is_dir()), [run_id]
            )

    def test_valid_source_with_annotated_only_output_still_succeeds(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _project(tmp, sketch_suffix=".jpeg")
            manifest = ScoreCommandTest()._manifest(
                root, kind="annotated_only", name="shoe_sketch.jpeg"
            )

            code, _ = self._run_score(root, manifest)

            self.assertEqual(code, 0)
            self.assertTrue((root / REPORTS_ROOT / LATEST_NAME).is_file())

    def test_valid_source_with_missing_output_still_succeeds(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _project(tmp)
            manifest = ScoreCommandTest()._manifest(root, name="absent_sketch.png")

            code, _ = self._run_score(root, manifest)

            self.assertEqual(code, 0)
            latest = json.loads(
                (root / REPORTS_ROOT / LATEST_NAME).read_text(encoding="utf-8")
            )
            stored = json.loads(
                (root / REPORTS_ROOT / latest["run_id"] / RESULTS_NAME).read_text(
                    encoding="utf-8"
                )
            )
            metrics = stored["items"]["shoe"]["output-5"]["metrics"]
            self.assertTrue(
                all(metric["status"] == "not_scored" for metric in metrics.values())
            )
            self.assertIsNone(stored["items"]["shoe"]["output-5"]["output_sha256"])


class WriteBoundaryTest(unittest.TestCase):
    """쓰기 목적지는 허용된 두 루트 안이어야 합니다(심볼릭 링크 포함)."""

    def _snapshot(self, path: Path) -> bytes:
        return path.read_bytes()

    def test_manifest_command_refuses_to_target_an_image_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _project(tmp)
            target = root / "images" / "shoe_color.png"
            before = self._snapshot(target)

            with _inside(root):
                code, output = _run(["manifest", "--manifest", "images/shoe_color.png"])

            self.assertEqual(code, 1)
            self.assertIn("오류", output)
            self.assertEqual(self._snapshot(target), before)

    def test_manifest_command_refuses_repository_file_outside_annotation_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _project(tmp)
            target = root / "keepme.json"
            target.write_text("original", encoding="utf-8")

            with _inside(root):
                code, _ = _run(["manifest", "--manifest", "keepme.json"])

            self.assertEqual(code, 1)
            self.assertEqual(target.read_text(encoding="utf-8"), "original")

    def test_manifest_command_refuses_symlink_escape_to_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _project(tmp)
            target = root / "images" / "shoe_color.png"
            before = self._snapshot(target)
            link = root / ANNOTATION_ROOT / "escape.json"
            os.symlink(target, link)

            with _inside(root):
                code, output = _run(
                    ["manifest", "--manifest", f"{ANNOTATION_ROOT}/escape.json"]
                )

            self.assertEqual(code, 1)
            self.assertIn("오류", output)
            self.assertEqual(self._snapshot(target), before)
            self.assertTrue(link.is_symlink())

    def test_manifest_command_refuses_symlinked_directory_escape(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as outside:
            root = _project(tmp)
            os.symlink(Path(outside), root / ANNOTATION_ROOT / "linked")

            with _inside(root):
                code, _ = _run(
                    ["manifest", "--manifest", f"{ANNOTATION_ROOT}/linked/dataset.json"]
                )

            self.assertEqual(code, 1)
            self.assertEqual(list(Path(outside).iterdir()), [])

    def test_score_command_refuses_external_reports_root(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as outside:
            root = _project(tmp)
            manifest = ScoreCommandTest()._manifest(root)

            with _inside(root):
                code, output = _run(
                    [
                        "score",
                        "--manifest",
                        str(manifest),
                        "--annotation-root",
                        str(root / ANNOTATION_ROOT / "items"),
                        "--reports-root",
                        outside,
                        "--label",
                        "escape",
                    ]
                )

            self.assertEqual(code, 1)
            self.assertIn("오류", output)
            self.assertEqual(list(Path(outside).iterdir()), [])

    def test_score_command_refuses_symlinked_reports_root(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as outside:
            root = _project(tmp)
            manifest = ScoreCommandTest()._manifest(root)
            (root / REPORTS_ROOT).mkdir(parents=True, exist_ok=True)
            os.symlink(Path(outside), root / REPORTS_ROOT / "linked")

            with _inside(root):
                code, _ = _run(
                    [
                        "score",
                        "--manifest",
                        str(manifest),
                        "--annotation-root",
                        str(root / ANNOTATION_ROOT / "items"),
                        "--reports-root",
                        f"{REPORTS_ROOT}/linked",
                        "--label",
                        "escape",
                    ]
                )

            self.assertEqual(code, 1)
            self.assertEqual(list(Path(outside).iterdir()), [])

    def test_score_command_refuses_annotation_root_outside(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _project(tmp)
            manifest = ScoreCommandTest()._manifest(root)

            with _inside(root):
                code, _ = _run(
                    [
                        "score",
                        "--manifest",
                        str(manifest),
                        "--annotation-root",
                        "images",
                        "--reports-root",
                        str(root / REPORTS_ROOT),
                        "--label",
                        "escape",
                    ]
                )

            self.assertEqual(code, 1)
            self.assertFalse((root / REPORTS_ROOT).exists())


class ParserTest(unittest.TestCase):
    def test_command_is_required(self):
        with self.assertRaises(SystemExit):
            cli.build_parser().parse_args([])

    def test_score_requires_label(self):
        with self.assertRaises(SystemExit):
            cli.build_parser().parse_args(["score"])

    def test_defaults_match_the_documented_layout(self):
        args = cli.build_parser().parse_args(["score", "--label", "x"])
        self.assertEqual(args.manifest, Path("annotations/sketch-scoring/dataset.json"))
        self.assertEqual(args.annotation_root, Path("annotations/sketch-scoring/items"))
        self.assertEqual(args.reports_root, Path("reports/sketch-scoring"))
        self.assertIsNone(args.versions)

        manifest_args = cli.build_parser().parse_args(["manifest"])
        self.assertEqual(manifest_args.images_dir, Path("images"))


if __name__ == "__main__":
    unittest.main()
