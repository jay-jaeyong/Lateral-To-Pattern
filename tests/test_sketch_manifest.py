"""sketch_scoring.manifest의 후보 탐색, 스키마 검증과 경로 안전성 테스트."""

import json
import os
import tempfile
import unicodedata
import unittest
from pathlib import Path
from unittest.mock import patch

from sketch_scoring import manifest as manifest_module
from sketch_scoring.manifest import (
    ManifestError,
    canonical_display_name,
    discover_manifest,
    load_manifest,
    write_manifest,
)

NFD_PUMA = unicodedata.normalize("NFD", "푸마2")
NFC_PUMA = unicodedata.normalize("NFC", "푸마2")

PNG_BYTES = bytes.fromhex(
    "89504e470d0a1a0a0000000d494844520000000100000001080600000"
    "01f15c4890000000a49444154789c6300010000050001"
    "0d0a2db40000000049454e44ae426082"
)


def _write_image(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(PNG_BYTES)


def _project(tmp: str) -> Path:
    root = Path(tmp)
    (root / "images").mkdir(parents=True, exist_ok=True)
    return root


class ManifestDiscoveryTest(unittest.TestCase):
    def test_discovers_color_sources_and_all_output_directories(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _project(tmp)
            _write_image(root / "images" / "asics_GEL_SONOMA_color.png")
            _write_image(root / "images" / "output-4" / "asics_GEL_SONOMA_sketch.png")
            _write_image(root / "images" / "output-5" / "asics_GEL_SONOMA_sketch.png")

            found = discover_manifest(root / "images")

            self.assertEqual(found["schema_version"], 1)
            item = found["items"]["asics_GEL_SONOMA"]
            self.assertEqual(item["source"], "images/asics_GEL_SONOMA_color.png")
            self.assertFalse(item["needs_review"])
            self.assertEqual(sorted(item["outputs"]), ["output-4", "output-5"])
            self.assertEqual(
                item["outputs"]["output-5"],
                {
                    "path": "images/output-5/asics_GEL_SONOMA_sketch.png",
                    "kind": "clean",
                },
            )

    def test_preserves_existing_confirmed_source_and_output_mapping(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _project(tmp)
            _write_image(root / "images" / "shoe_color.png")
            _write_image(root / "images" / "confirmed_source.png")
            _write_image(root / "images" / "output-4" / "hand_picked.png")
            _write_image(root / "images" / "output-5" / "shoe_sketch.png")

            existing = {
                "schema_version": 1,
                "items": {
                    "shoe": {
                        "display_name": "shoe",
                        "source": "images/confirmed_source.png",
                        "expected_canvas_ratio": "3:4",
                        "needs_review": False,
                        "outputs": {
                            "output-4": {
                                "path": "images/output-4/hand_picked.png",
                                "kind": "annotated_only",
                            }
                        },
                    }
                },
            }

            found = discover_manifest(root / "images", existing)

            item = found["items"]["shoe"]
            self.assertEqual(item["source"], "images/confirmed_source.png")
            self.assertEqual(item["expected_canvas_ratio"], "3:4")
            self.assertEqual(
                item["outputs"]["output-4"],
                {"path": "images/output-4/hand_picked.png", "kind": "annotated_only"},
            )
            self.assertEqual(
                item["outputs"]["output-5"],
                {"path": "images/output-5/shoe_sketch.png", "kind": "clean"},
            )

    def test_marks_irregular_nike_name_for_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _project(tmp)
            _write_image(root / "images" / "nike_p6000.jpeg")
            _write_image(root / "images" / "output-5" / "nike_p6000_sketch.png")

            found = discover_manifest(root / "images")

            item = found["items"]["nike_p6000"]
            self.assertTrue(item["needs_review"])
            self.assertEqual(item["source"], "images/nike_p6000.jpeg")
            self.assertEqual(
                item["outputs"]["output-5"]["path"],
                "images/output-5/nike_p6000_sketch.png",
            )

    def test_duplicate_output_extensions_are_collected_for_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _project(tmp)
            _write_image(root / "images" / "shoe_color.png")
            _write_image(root / "images" / "output-5" / "shoe_sketch.png")
            _write_image(root / "images" / "output-5" / "shoe_sketch.jpeg")

            found = discover_manifest(root / "images")

            item = found["items"]["shoe"]
            self.assertTrue(item["needs_review"])
            record = item["outputs"]["output-5"]
            self.assertNotIn("path", record)
            self.assertEqual(
                sorted(record["candidates"]),
                [
                    "images/output-5/shoe_sketch.jpeg",
                    "images/output-5/shoe_sketch.png",
                ],
            )

            # 확정되지 않은 후보 목록은 채점으로 흘러가지 않습니다.
            path = root / "dataset.json"
            write_manifest(path, found)
            with self.assertRaises(ManifestError):
                load_manifest(path, project_root=root)

            # 사용자가 하나를 확정하면 다시 탐색해도 덮어쓰지 않습니다.
            found["items"]["shoe"]["outputs"]["output-5"] = {
                "path": "images/output-5/shoe_sketch.jpeg",
                "kind": "clean",
            }
            again = discover_manifest(root / "images", found)
            self.assertEqual(
                again["items"]["shoe"]["outputs"]["output-5"],
                {"path": "images/output-5/shoe_sketch.jpeg", "kind": "clean"},
            )

    def test_duplicate_source_extensions_are_collected_for_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _project(tmp)
            _write_image(root / "images" / "shoe_color.png")
            _write_image(root / "images" / "shoe_color.jpeg")

            found = discover_manifest(root / "images")

            item = found["items"]["shoe"]
            self.assertIsNone(item["source"])
            self.assertTrue(item["needs_review"])
            self.assertEqual(
                sorted(item["source_candidates"]),
                ["images/shoe_color.jpeg", "images/shoe_color.png"],
            )

    def test_nfc_display_name_keeps_nfd_filesystem_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _project(tmp)
            _write_image(root / "images" / f"{NFD_PUMA}_color.png")
            _write_image(root / "images" / "output-5" / f"{NFD_PUMA}_sketch.jpeg")
            on_disk_source = next(
                name for name in os.listdir(root / "images") if name.endswith("_color.png")
            )

            found = discover_manifest(root / "images")

            self.assertIn(NFC_PUMA, found["items"])
            item = found["items"][NFC_PUMA]
            self.assertEqual(item["display_name"], NFC_PUMA)
            self.assertEqual(item["source"], f"images/{on_disk_source}")
            self.assertTrue((root / item["source"]).is_file())
            self.assertEqual(canonical_display_name(NFD_PUMA), NFC_PUMA)


class ManifestValidationTest(unittest.TestCase):
    def _manifest_file(self, root: Path, items: dict) -> Path:
        path = root / "dataset.json"
        path.write_text(
            json.dumps({"schema_version": 1, "items": items}, ensure_ascii=False),
            encoding="utf-8",
        )
        return path

    def test_rejects_absolute_image_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _project(tmp)
            absolute = root / "images" / "shoe_color.png"
            _write_image(absolute)
            path = self._manifest_file(
                root, {"shoe": {"source": str(absolute), "outputs": {}}}
            )
            with self.assertRaises(ManifestError):
                load_manifest(path, project_root=root)

    def test_rejects_parent_traversal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _project(tmp)
            _write_image(root.parent / "outside.png")
            path = self._manifest_file(
                root, {"shoe": {"source": "images/../outside.png", "outputs": {}}}
            )
            with self.assertRaises(ManifestError):
                load_manifest(path, project_root=root)

    def test_rejects_symlink_escape(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _project(tmp)
            outside = Path(tmp).parent / f"outside_{Path(tmp).name}.png"
            _write_image(outside)
            self.addCleanup(outside.unlink)
            os.symlink(outside, root / "images" / "link.png")
            path = self._manifest_file(
                root, {"shoe": {"source": "images/link.png", "outputs": {}}}
            )
            with self.assertRaises(ManifestError):
                load_manifest(path, project_root=root)

    def test_rejects_missing_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _project(tmp)
            path = self._manifest_file(
                root, {"shoe": {"source": "images/absent_color.png", "outputs": {}}}
            )
            with self.assertRaises(ManifestError):
                load_manifest(path, project_root=root)

    def test_accepts_clean_and_annotated_only_output_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _project(tmp)
            _write_image(root / "images" / "shoe_color.png")
            _write_image(root / "images" / "output-4" / "shoe_sketch.png")
            _write_image(root / "images" / "output-5" / "shoe_sketch.jpeg")
            path = self._manifest_file(
                root,
                {
                    "shoe": {
                        "source": "images/shoe_color.png",
                        "outputs": {
                            "output-4": "images/output-4/shoe_sketch.png",
                            "output-5": {
                                "path": "images/output-5/shoe_sketch.jpeg",
                                "kind": "annotated_only",
                            },
                        },
                    }
                },
            )

            loaded = load_manifest(path, project_root=root)

            outputs = loaded["items"]["shoe"]["outputs"]
            self.assertEqual(
                outputs["output-4"],
                {"path": "images/output-4/shoe_sketch.png", "kind": "clean"},
            )
            self.assertEqual(
                outputs["output-5"],
                {"path": "images/output-5/shoe_sketch.jpeg", "kind": "annotated_only"},
            )
            self.assertEqual(loaded["items"]["shoe"]["expected_canvas_ratio"], "2:3")
            self.assertEqual(loaded["items"]["shoe"]["display_name"], "shoe")

    def test_rejects_unknown_output_kind(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _project(tmp)
            _write_image(root / "images" / "shoe_color.png")
            _write_image(root / "images" / "output-5" / "shoe_sketch.png")
            path = self._manifest_file(
                root,
                {
                    "shoe": {
                        "source": "images/shoe_color.png",
                        "outputs": {
                            "output-5": {
                                "path": "images/output-5/shoe_sketch.png",
                                "kind": "restored",
                            }
                        },
                    }
                },
            )
            with self.assertRaises(ManifestError):
                load_manifest(path, project_root=root)

    def test_rejects_medial_lateral_symmetry_fields(self):
        forbidden = [
            {"mirror": True},
            {"symmetry": 0.9},
            {"opposite_side": "medial"},
            {"medial_lateral_similarity": 0.5},
        ]
        for extra in forbidden:
            with self.subTest(extra=extra), tempfile.TemporaryDirectory() as tmp:
                root = _project(tmp)
                _write_image(root / "images" / "shoe_color.png")
                item = {"source": "images/shoe_color.png", "outputs": {}}
                item.update(extra)
                path = self._manifest_file(root, {"shoe": item})
                with self.assertRaises(ManifestError):
                    load_manifest(path, project_root=root)

    def test_rejects_nested_symmetry_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _project(tmp)
            _write_image(root / "images" / "shoe_color.png")
            path = self._manifest_file(
                root,
                {
                    "shoe": {
                        "source": "images/shoe_color.png",
                        "outputs": {},
                        "notes": {"compare": {"symmetry": True}},
                    }
                },
            )
            with self.assertRaises(ManifestError):
                load_manifest(path, project_root=root)


class AtomicManifestWriteTest(unittest.TestCase):
    def test_write_manifest_preserves_existing_file_if_replace_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "dataset.json"
            path.write_text('{"schema_version": 1, "items": {}}', encoding="utf-8")
            before = path.read_bytes()

            with patch.object(
                manifest_module.Path, "replace", side_effect=OSError("boom")
            ):
                with self.assertRaises(OSError):
                    write_manifest(path, {"schema_version": 1, "items": {"a": {}}})

            self.assertEqual(path.read_bytes(), before)
            self.assertEqual([p.name for p in Path(tmp).iterdir()], ["dataset.json"])

    def test_write_manifest_writes_utf8_json_without_escapes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "nested" / "dataset.json"
            write_manifest(
                path,
                {
                    "schema_version": 1,
                    "items": {NFC_PUMA: {"display_name": NFC_PUMA, "outputs": {}}},
                },
            )
            text = path.read_text(encoding="utf-8")
            self.assertIn(NFC_PUMA, text)
            self.assertEqual(json.loads(text)["items"][NFC_PUMA]["display_name"], NFC_PUMA)


if __name__ == "__main__":
    unittest.main()
