"""주석 스키마, 사이드카 저장과 빨간 박스·끝점 후보 검출 테스트."""

import copy
import json
import os
import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np

from sketch_scoring.annotations import (
    AnnotationError,
    annotation_path,
    detect_red_boxes,
    load_annotations,
    save_annotations,
    suggest_connection_anchors,
    validate_annotation_document,
)

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

REQUIRED_PATH = {
    "id": "toe-cap-boundary",
    "type": "required_path",
    "label": "toe_cap",
    "target_box": [0.11, 0.68, 0.29, 0.82],
    "paths": [[[0.12, 0.74], [0.16, 0.72], [0.22, 0.73], [0.28, 0.78]]],
}

COMPLETE_ROI = {
    "id": "heel-complete",
    "type": "complete_roi",
    "label": "heel",
    "target_box": [0.65, 0.08, 0.88, 0.25],
    "paths": [
        [[0.67, 0.20], [0.73, 0.16], [0.82, 0.15]],
        [[0.70, 0.23], [0.76, 0.21], [0.85, 0.22]],
    ],
}


def _document(*annotations: dict) -> dict:
    return {"schema_version": 1, "annotations": [copy.deepcopy(a) for a in annotations]}


class AnnotationValidationTest(unittest.TestCase):
    def test_accepts_connection_required_path_and_complete_roi(self):
        validated = validate_annotation_document(
            _document(CONNECTION, REQUIRED_PATH, COMPLETE_ROI)
        )
        self.assertEqual(validated["schema_version"], 1)
        self.assertEqual(
            [a["id"] for a in validated["annotations"]],
            ["quarter-seam-1", "toe-cap-boundary", "heel-complete"],
        )
        self.assertEqual(validated["annotations"][0]["type"], "connection")
        self.assertEqual(validated["annotations"][1]["label"], "toe_cap")
        self.assertEqual(len(validated["annotations"][2]["paths"]), 2)
        self.assertEqual(validate_annotation_document(EMPTY_DOCUMENT)["annotations"], [])

    def test_rejects_coordinates_outside_zero_one(self):
        for box in ([-0.01, 0.1, 0.2, 0.3], [0.1, 0.1, 1.2, 0.3]):
            with self.subTest(box=box):
                bad = copy.deepcopy(CONNECTION)
                bad["target_box"] = box
                with self.assertRaises(AnnotationError):
                    validate_annotation_document(_document(bad))

        bad_path = copy.deepcopy(REQUIRED_PATH)
        bad_path["paths"] = [[[0.1, 0.2], [1.4, 0.3]]]
        with self.assertRaises(AnnotationError):
            validate_annotation_document(_document(bad_path))

    def test_rejects_reversed_box_coordinates(self):
        for box in ([0.5, 0.1, 0.2, 0.3], [0.1, 0.6, 0.2, 0.3], [0.1, 0.1, 0.1, 0.3]):
            with self.subTest(box=box):
                bad = copy.deepcopy(CONNECTION)
                bad["target_box"] = box
                with self.assertRaises(AnnotationError):
                    validate_annotation_document(_document(bad))

    def test_connection_requires_exactly_two_anchor_regions(self):
        missing = copy.deepcopy(CONNECTION)
        del missing["anchors"]["end_region"]
        with self.assertRaises(AnnotationError):
            validate_annotation_document(_document(missing))

        extra = copy.deepcopy(CONNECTION)
        extra["anchors"]["middle_region"] = [0.34, 0.44, 0.35, 0.46]
        with self.assertRaises(AnnotationError):
            validate_annotation_document(_document(extra))

        no_anchors = copy.deepcopy(CONNECTION)
        del no_anchors["anchors"]
        with self.assertRaises(AnnotationError):
            validate_annotation_document(_document(no_anchors))

    def test_required_path_requires_at_least_two_points(self):
        short = copy.deepcopy(REQUIRED_PATH)
        short["paths"] = [[[0.12, 0.74]]]
        with self.assertRaises(AnnotationError):
            validate_annotation_document(_document(short))

        malformed = copy.deepcopy(REQUIRED_PATH)
        malformed["paths"] = [[[0.12, 0.74], [0.16]]]
        with self.assertRaises(AnnotationError):
            validate_annotation_document(_document(malformed))

    def test_complete_roi_requires_nonempty_paths(self):
        empty = copy.deepcopy(COMPLETE_ROI)
        empty["paths"] = []
        with self.assertRaises(AnnotationError):
            validate_annotation_document(_document(empty))

        missing = copy.deepcopy(COMPLETE_ROI)
        del missing["paths"]
        with self.assertRaises(AnnotationError):
            validate_annotation_document(_document(missing))

    def test_rejects_duplicate_annotation_ids(self):
        duplicate = copy.deepcopy(REQUIRED_PATH)
        duplicate["label"] = "other"
        with self.assertRaises(AnnotationError):
            validate_annotation_document(_document(REQUIRED_PATH, duplicate))

    def test_rejects_symmetry_and_opposite_side_fields(self):
        for extra in (
            {"mirror": True},
            {"symmetry": 0.4},
            {"opposite_side": "medial"},
            {"medial_lateral_similarity": 0.7},
            {"reflection_pair": "x"},
        ):
            with self.subTest(extra=extra):
                bad = copy.deepcopy(CONNECTION)
                bad.update(extra)
                with self.assertRaises(AnnotationError):
                    validate_annotation_document(_document(bad))

        nested = copy.deepcopy(REQUIRED_PATH)
        nested["label"] = {"symmetry": True}
        with self.assertRaises(AnnotationError):
            validate_annotation_document(_document(nested))

    def test_rejects_unknown_annotation_type_and_unknown_keys(self):
        wrong_type = copy.deepcopy(CONNECTION)
        wrong_type["type"] = "silhouette"
        with self.assertRaises(AnnotationError):
            validate_annotation_document(_document(wrong_type))

        unknown_key = copy.deepcopy(CONNECTION)
        unknown_key["tolerance_px"] = 4
        with self.assertRaises(AnnotationError):
            validate_annotation_document(_document(unknown_key))

    def test_item_id_cannot_escape_annotation_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for bad in ("../evil", "a/b", "..", ".", "", "nike/../../etc", "a\\b"):
                with self.subTest(item_id=bad):
                    with self.assertRaises(AnnotationError):
                        annotation_path(root, bad)
            self.assertEqual(
                annotation_path(root, "푸마2"), root / "푸마2.json"
            )
            self.assertEqual(
                annotation_path(root, "nike_p6000"), root / "nike_p6000.json"
            )


class AnnotationPersistenceTest(unittest.TestCase):
    def test_load_missing_returns_empty_document(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(load_annotations(Path(tmp), "nike_p6000"), EMPTY_DOCUMENT)

    def test_save_then_load_roundtrip_keeps_normalized_coordinates(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "items"
            path = save_annotations(root, "푸마2", _document(CONNECTION))
            self.assertTrue(path.is_file())
            text = path.read_text(encoding="utf-8")
            self.assertIn("quarter-seam-1", text)
            reloaded = load_annotations(root, "푸마2")
            self.assertEqual(
                reloaded["annotations"][0]["anchors"]["start_region"],
                [0.32, 0.45, 0.33, 0.47],
            )

    def test_invalid_document_does_not_replace_existing_sidecar(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = save_annotations(root, "nike_p6000", _document(REQUIRED_PATH))
            before = path.read_bytes()
            bad = copy.deepcopy(REQUIRED_PATH)
            bad["target_box"] = [0.9, 0.1, 0.2, 0.3]
            with self.assertRaises(AnnotationError):
                save_annotations(root, "nike_p6000", _document(bad))
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(sorted(p.name for p in root.iterdir()), ["nike_p6000.json"])

    def test_red_box_import_does_not_touch_sidecar_until_save(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = save_annotations(root, "푸마2", _document(REQUIRED_PATH))
            before = path.read_bytes()

            rgb = np.full((100, 200, 3), 255, dtype=np.uint8)
            cv2.rectangle(rgb, (40, 20), (120, 70), (255, 0, 0), 3)
            candidates = detect_red_boxes(rgb)
            self.assertEqual(len(candidates), 1)
            self.assertEqual(path.read_bytes(), before)

            confirmed = copy.deepcopy(CONNECTION)
            confirmed["target_box"] = [round(v, 3) for v in candidates[0]]
            save_annotations(root, "푸마2", _document(REQUIRED_PATH, confirmed))
            self.assertNotEqual(path.read_bytes(), before)
            self.assertEqual(len(load_annotations(root, "푸마2")["annotations"]), 2)


class SidecarPathSafetyTest(unittest.TestCase):
    """사이드카 경로는 심볼릭 링크로도 주석 루트를 벗어날 수 없습니다."""

    def _outside_file(self) -> Path:
        handle = tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        )
        handle.write('{"schema_version": 1, "annotations": [], "secret": true}')
        handle.close()
        path = Path(handle.name)
        self.addCleanup(lambda: path.unlink(missing_ok=True))
        return path

    def test_file_symlink_escape_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "items"
            root.mkdir()
            outside = self._outside_file()
            before = outside.read_bytes()
            os.symlink(outside, root / "escape.json")

            with self.assertRaises(AnnotationError):
                annotation_path(root, "escape")
            with self.assertRaises(AnnotationError):
                load_annotations(root, "escape")
            with self.assertRaises(AnnotationError):
                save_annotations(root, "escape", _document(REQUIRED_PATH))

            self.assertEqual(outside.read_bytes(), before)

    def test_symlinked_item_directory_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as away:
            root = Path(tmp) / "items"
            os.symlink(Path(away), root)
            outside = Path(away) / "푸마2.json"
            outside.write_text("original", encoding="utf-8")

            with self.assertRaises(AnnotationError):
                load_annotations(root, "푸마2")
            with self.assertRaises(AnnotationError):
                save_annotations(root, "푸마2", _document(REQUIRED_PATH))

            self.assertEqual(outside.read_text(encoding="utf-8"), "original")
            self.assertEqual(
                sorted(p.name for p in Path(away).iterdir()), ["푸마2.json"]
            )

    def test_symlink_inside_the_root_is_allowed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "items"
            root.mkdir()
            real = save_annotations(root, "nike_p6000", _document(REQUIRED_PATH))
            os.symlink(real, root / "alias.json")

            self.assertEqual(
                load_annotations(root, "alias")["annotations"][0]["id"],
                "toe-cap-boundary",
            )


class RedBoxDetectionTest(unittest.TestCase):
    def test_detects_single_normalized_red_box(self):
        rgb = np.full((100, 200, 3), 255, dtype=np.uint8)
        cv2.rectangle(rgb, (40, 20), (120, 70), (255, 0, 0), 3)

        boxes = detect_red_boxes(rgb)

        self.assertEqual(len(boxes), 1)
        # 정규화 좌표를 픽셀로 되돌려 선 두께(3px)만큼의 오차만 허용합니다.
        pixels = [
            boxes[0][0] * 200,
            boxes[0][1] * 100,
            boxes[0][2] * 200,
            boxes[0][3] * 100,
        ]
        for value, expected in zip(pixels, [40, 20, 120, 70]):
            self.assertLessEqual(abs(value - expected), 3.0)

    def test_ignores_round_logo_blob(self):
        rgb = np.full((100, 200, 3), 255, dtype=np.uint8)
        cv2.circle(rgb, (150, 60), 12, (220, 20, 20), -1)

        self.assertEqual(detect_red_boxes(rgb), [])

    def test_sorts_boxes_top_to_bottom_then_left_to_right(self):
        rgb = np.full((200, 200, 3), 255, dtype=np.uint8)
        cv2.rectangle(rgb, (110, 10), (180, 60), (255, 0, 0), 3)
        cv2.rectangle(rgb, (10, 10), (80, 60), (255, 0, 0), 3)
        cv2.rectangle(rgb, (10, 120), (80, 180), (255, 0, 0), 3)

        boxes = detect_red_boxes(rgb)

        self.assertEqual(len(boxes), 3)
        self.assertLess(boxes[0][0], boxes[1][0])
        self.assertLess(boxes[1][1], boxes[2][1])
        for box in boxes:
            self.assertTrue(all(0.0 <= value <= 1.0 for value in box))

    def test_merges_overlapping_components_of_one_box(self):
        rgb = np.full((100, 200, 3), 255, dtype=np.uint8)
        cv2.rectangle(rgb, (40, 20), (120, 70), (255, 0, 0), 3)
        # JPEG 압축으로 위쪽 테두리가 두 곳 끊겨 성분이 둘로 갈라진 상황.
        rgb[18:24, 58:62] = 255
        rgb[18:24, 92:96] = 255

        boxes = detect_red_boxes(rgb)

        self.assertEqual(len(boxes), 1)
        self.assertAlmostEqual(boxes[0][0], 0.20, delta=0.03)

    def test_ignores_black_lines(self):
        rgb = np.full((100, 200, 3), 255, dtype=np.uint8)
        cv2.line(rgb, (10, 50), (190, 50), (0, 0, 0), 2)

        self.assertEqual(detect_red_boxes(rgb), [])


class AnchorSuggestionTest(unittest.TestCase):
    TARGET_BOX = [0.1, 0.1, 0.9, 0.9]

    def _canvas(self) -> np.ndarray:
        return np.full((100, 200, 3), 255, dtype=np.uint8)

    def test_two_fragment_ends_are_suggested(self):
        rgb = self._canvas()
        cv2.line(rgb, (0, 50), (80, 50), (0, 0, 0), 2)
        cv2.line(rgb, (120, 50), (199, 50), (0, 0, 0), 2)

        anchors = suggest_connection_anchors(rgb, self.TARGET_BOX)

        self.assertEqual(len(anchors), 2)
        for box in anchors:
            self.assertTrue(all(0.0 <= value <= 1.0 for value in box))
            self.assertLess(box[0], box[2])
            self.assertLess(box[1], box[3])
        self.assertLess(anchors[0][0], anchors[1][0])
        self.assertAlmostEqual((anchors[0][0] + anchors[0][2]) / 2, 80 / 200, delta=0.03)
        self.assertAlmostEqual((anchors[1][0] + anchors[1][2]) / 2, 120 / 200, delta=0.03)

    def test_thick_fragment_ends_are_suggested(self):
        rgb = self._canvas()
        cv2.line(rgb, (0, 50), (80, 50), (0, 0, 0), 5)
        cv2.line(rgb, (120, 50), (199, 50), (0, 0, 0), 5)

        anchors = suggest_connection_anchors(rgb, self.TARGET_BOX)

        self.assertEqual(len(anchors), 2)
        self.assertAlmostEqual((anchors[0][0] + anchors[0][2]) / 2, 80 / 200, delta=0.05)
        self.assertAlmostEqual((anchors[1][0] + anchors[1][2]) / 2, 120 / 200, delta=0.05)

    def test_t_junction_branch_returns_no_candidates(self):
        rgb = self._canvas()
        cv2.line(rgb, (0, 50), (80, 50), (0, 0, 0), 2)
        cv2.line(rgb, (120, 50), (199, 50), (0, 0, 0), 2)
        # 오른쪽 조각에서 갈라진 가지가 있으면 어느 끝이 짝인지 알 수 없습니다.
        cv2.line(rgb, (150, 50), (150, 25), (0, 0, 0), 2)

        self.assertEqual(suggest_connection_anchors(rgb, self.TARGET_BOX), [])

    def test_solid_blob_edge_is_not_an_endpoint(self):
        rgb = self._canvas()
        cv2.line(rgb, (0, 50), (80, 50), (0, 0, 0), 2)
        cv2.line(rgb, (120, 50), (199, 50), (0, 0, 0), 2)
        cv2.rectangle(rgb, (30, 20), (60, 40), (0, 0, 0), -1)

        self.assertEqual(len(suggest_connection_anchors(rgb, self.TARGET_BOX)), 2)

    def test_no_ink_returns_no_candidates(self):
        self.assertEqual(suggest_connection_anchors(self._canvas(), self.TARGET_BOX), [])

    def test_single_endpoint_returns_no_candidates(self):
        rgb = self._canvas()
        cv2.line(rgb, (0, 50), (80, 50), (0, 0, 0), 2)

        self.assertEqual(suggest_connection_anchors(rgb, self.TARGET_BOX), [])

    def test_three_endpoints_return_no_candidates(self):
        rgb = self._canvas()
        cv2.line(rgb, (0, 30), (60, 30), (0, 0, 0), 2)
        cv2.line(rgb, (100, 30), (199, 30), (0, 0, 0), 2)
        cv2.line(rgb, (0, 70), (70, 70), (0, 0, 0), 2)

        self.assertEqual(suggest_connection_anchors(rgb, self.TARGET_BOX), [])

    def test_ink_outside_target_box_is_ignored(self):
        rgb = self._canvas()
        cv2.line(rgb, (0, 50), (80, 50), (0, 0, 0), 2)
        cv2.line(rgb, (120, 50), (199, 50), (0, 0, 0), 2)
        cv2.line(rgb, (0, 95), (199, 95), (0, 0, 0), 2)

        self.assertEqual(len(suggest_connection_anchors(rgb, self.TARGET_BOX)), 2)


if __name__ == "__main__":
    unittest.main()
