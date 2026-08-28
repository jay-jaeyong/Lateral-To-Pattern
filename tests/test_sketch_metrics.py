"""이미지 디코딩과 결정론적 진단 지표 테스트.

모든 fixture는 메모리에서 만든 작은 합성 이미지입니다. 지표 함수는 파일을
쓰지 않으며 총점을 만들지 않습니다.
"""

import json
import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np

from sketch_scoring.metrics import (
    CONFIDENT_ANCHOR_INK_PIXELS,
    UNCALIBRATED_REASON,
    ImageDecodeError,
    MetricResult,
    ScoringConfig,
    load_rgb,
    score_annotation,
    score_aspect_ratio,
    score_black_fill,
    score_colored_pixels,
    score_complete_roi,
    score_connection,
    score_faint_strokes,
    score_global_metrics,
    score_required_path,
    score_silhouette,
)

CONFIG = ScoringConfig()


def _white(width: int, height: int) -> np.ndarray:
    return np.full((height, width, 3), 255, dtype=np.uint8)


class LoadRgbTest(unittest.TestCase):
    def test_decodes_jpeg_bytes_stored_under_png_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sketch.png"
            image = _white(40, 60)
            cv2.rectangle(image, (5, 5), (30, 40), (0, 0, 0), 2)
            ok, encoded = cv2.imencode(".jpg", cv2.cvtColor(image, cv2.COLOR_RGB2BGR))
            self.assertTrue(ok)
            path.write_bytes(encoded.tobytes())

            loaded = load_rgb(path)

            self.assertEqual(loaded.shape, (60, 40, 3))
            self.assertEqual(loaded.dtype, np.uint8)

    def test_undecodable_bytes_raise_image_decode_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "broken.png"
            path.write_bytes(b"not an image at all")
            with self.assertRaises(ImageDecodeError):
                load_rgb(path)


class MetricResultTest(unittest.TestCase):
    def test_not_scored_has_null_score_and_reason(self):
        result = MetricResult.not_scored("배경 분리 실패", 0.2)
        self.assertIsNone(result.score)
        self.assertEqual(result.status, "not_scored")
        self.assertTrue(result.reason)
        self.assertEqual(result.confidence, 0.2)

    def test_confidence_is_clamped_to_unit_range(self):
        self.assertEqual(MetricResult.not_scored("사유", 1.7).confidence, 1.0)
        self.assertEqual(MetricResult.not_scored("사유", -0.5).confidence, 0.0)

    def test_to_dict_has_the_shared_metric_shape(self):
        payload = MetricResult.not_scored("사유", 0.31).to_dict()
        self.assertEqual(
            sorted(payload), ["confidence", "details", "reason", "score", "status"]
        )
        self.assertNotIn("total", payload)

    def test_details_cannot_be_mutated_from_outside(self):
        source = {"raw_score": 0.4, "nested": {"a": 1}, "series": [1, 2]}
        result = MetricResult(None, "not_scored", 0.5, "사유", source)

        # 넘긴 dict를 나중에 바꿔도 결과는 그대로입니다.
        source["raw_score"] = 99.0
        source["nested"]["a"] = 99
        source["series"].append(3)
        self.assertEqual(result.details["raw_score"], 0.4)
        self.assertEqual(result.details["nested"]["a"], 1)
        self.assertEqual(result.details["series"], (1, 2))

        # 결과를 직접 바꾸려는 시도는 실패합니다.
        with self.assertRaises(TypeError):
            result.details["raw_score"] = 99.0
        with self.assertRaises(TypeError):
            result.details["nested"]["a"] = 99
        with self.assertRaises(AttributeError):
            result.details["series"].append(3)
        with self.assertRaises(Exception):
            result.details = {}

    def test_to_dict_returns_independent_json_serializable_copy(self):
        result = MetricResult(
            None, "not_scored", 0.5, "사유", {"raw_score": 0.4, "nested": {"a": 1}}
        )

        first = result.to_dict()
        first["details"]["raw_score"] = 99.0
        first["details"]["nested"]["a"] = 99

        self.assertEqual(result.details["raw_score"], 0.4)
        self.assertEqual(result.details["nested"]["a"], 1)
        second = result.to_dict()
        self.assertEqual(second["details"]["raw_score"], 0.4)
        self.assertEqual(second["details"]["nested"], {"a": 1})
        self.assertEqual(
            json.loads(json.dumps(second, ensure_ascii=False))["details"]["nested"],
            {"a": 1},
        )

    def test_metric_details_from_a_scored_metric_are_read_only(self):
        result = score_aspect_ratio(_white(512, 768), "2:3", CONFIG)
        with self.assertRaises(TypeError):
            result.details["raw_score"] = 1.0
        self.assertEqual(json.loads(json.dumps(result.to_dict()))["status"], "pass")


class AspectMetricTest(unittest.TestCase):
    def test_two_to_three_is_pass(self):
        result = score_aspect_ratio(_white(512, 768), "2:3", CONFIG)
        self.assertEqual(result.status, "pass")
        self.assertAlmostEqual(result.details["raw_score"], 0.0, places=6)

    def test_three_percent_error_is_warn(self):
        result = score_aspect_ratio(_white(512, 746), "2:3", CONFIG)
        self.assertEqual(result.status, "warn")
        self.assertGreater(result.details["raw_score"], CONFIG.aspect_pass_relative_error)
        self.assertLessEqual(result.details["raw_score"], CONFIG.aspect_warn_relative_error)

    def test_landscape_for_portrait_expectation_is_fail(self):
        result = score_aspect_ratio(_white(768, 512), "2:3", CONFIG)
        self.assertEqual(result.status, "fail")
        self.assertIn("방향", result.reason)

    def test_large_error_without_orientation_change_is_fail(self):
        result = score_aspect_ratio(_white(512, 640), "2:3", CONFIG)
        self.assertEqual(result.status, "fail")


class ColorMetricTest(unittest.TestCase):
    def test_black_gray_white_image_passes(self):
        image = _white(256, 256)
        image[10:40, 10:200] = 0
        image[60:80, 10:200] = 140
        result = score_colored_pixels(image, CONFIG)
        self.assertEqual(result.status, "pass")
        self.assertEqual(result.details["raw_score"], 0.0)

    def test_colored_region_fails(self):
        image = _white(256, 256)
        image[50:100, 50:100] = (30, 90, 200)
        result = score_colored_pixels(image, CONFIG)
        self.assertEqual(result.status, "fail")
        self.assertGreater(result.details["raw_score"], CONFIG.chroma_warn_ratio)

    def test_small_jpeg_chroma_noise_does_not_fail(self):
        rng = np.random.default_rng(7)
        image = rng.integers(248, 256, size=(256, 256, 3), dtype=np.uint8)
        cv2.line(image, (10, 10), (240, 240), (0, 0, 0), 2)
        result = score_colored_pixels(image, CONFIG)
        self.assertEqual(result.status, "pass")

    def test_warn_band_between_pass_and_fail(self):
        image = _white(256, 256)
        # 65536 픽셀 중 60 픽셀(0.09%)만 유채색이면 warn 구간입니다.
        image[0, 0:60] = (200, 40, 40)
        result = score_colored_pixels(image, CONFIG)
        self.assertEqual(result.status, "warn")


class BlackFillMetricTest(unittest.TestCase):
    def test_thin_black_lines_are_not_fill(self):
        image = _white(256, 256)
        cv2.line(image, (20, 20), (230, 30), (0, 0, 0), 3)
        cv2.line(image, (20, 200), (230, 120), (0, 0, 0), 2)
        cv2.circle(image, (128, 128), 60, (0, 0, 0), 2)
        result = score_black_fill(image, CONFIG)
        self.assertEqual(result.status, "pass")
        self.assertEqual(result.details["raw_score"], 0.0)

    def test_wide_solid_black_region_is_fill(self):
        image = _white(256, 256)
        image[40:100, 40:120] = 0
        result = score_black_fill(image, CONFIG)
        self.assertEqual(result.status, "fail")
        self.assertGreater(result.details["raw_score"], CONFIG.fill_warn_ratio)

    def test_closed_line_interior_white_is_not_fill(self):
        image = _white(256, 256)
        cv2.rectangle(image, (40, 40), (200, 200), (0, 0, 0), 3)
        result = score_black_fill(image, CONFIG)
        self.assertEqual(result.status, "pass")


class FaintStrokeMetricTest(unittest.TestCase):
    def test_antialiasing_next_to_dark_core_is_excluded(self):
        image = _white(256, 256)
        image[100:103, 20:200] = 0
        image[98:100, 20:200] = 150
        image[103:105, 20:200] = 150
        result = score_faint_strokes(image, CONFIG)
        self.assertEqual(result.status, "not_scored")
        self.assertEqual(result.reason, UNCALIBRATED_REASON)
        self.assertEqual(result.details["raw_score"], 0.0)

    def test_gray_line_without_dark_core_is_counted(self):
        image = _white(256, 256)
        image[100:104, 20:200] = 150
        result = score_faint_strokes(image, CONFIG)
        self.assertEqual(result.status, "not_scored")
        self.assertGreater(result.details["raw_score"], 0.0)
        self.assertIsNone(result.score)


class SilhouetteMetricTest(unittest.TestCase):
    def _source(self) -> np.ndarray:
        source = _white(200, 300)
        cv2.rectangle(source, (40, 60), (160, 240), (30, 60, 200), -1)
        return source

    def _output(self, offset: int = 0) -> np.ndarray:
        output = _white(200, 300)
        cv2.rectangle(
            output, (40 + offset, 60), (160 + offset, 240), (0, 0, 0), 2
        )
        return output

    def test_high_contrast_pair_returns_numeric_iou_and_confidence(self):
        result = score_silhouette(self._source(), self._output(), CONFIG)
        self.assertEqual(result.status, "not_scored")
        self.assertEqual(result.reason, UNCALIBRATED_REASON)
        self.assertIsNone(result.score)
        self.assertGreater(result.details["raw_score"], 0.9)
        self.assertGreaterEqual(result.confidence, CONFIG.silhouette_min_confidence)

    def test_low_contrast_source_is_not_scored_with_separation_reason(self):
        source = _white(200, 300)
        cv2.rectangle(source, (40, 60), (160, 240), (252, 252, 252), -1)

        result = score_silhouette(source, self._output(), CONFIG)

        self.assertEqual(result.status, "not_scored")
        self.assertIn("색차", result.reason)
        self.assertIsNone(result.details.get("raw_score"))
        self.assertLess(result.confidence, CONFIG.silhouette_min_confidence)

    def test_translated_output_lowers_iou_because_no_registration(self):
        aligned = score_silhouette(self._source(), self._output(), CONFIG)
        shifted = score_silhouette(self._source(), self._output(offset=40), CONFIG)
        self.assertLess(shifted.details["raw_score"], aligned.details["raw_score"] - 0.1)

    def test_horizontal_flip_lowers_iou_because_no_reflection(self):
        source = _white(200, 300)
        points = np.array([[20, 40], [180, 90], [60, 260]], dtype=np.int32)
        cv2.fillPoly(source, [points], (30, 60, 200))
        output = _white(200, 300)
        cv2.polylines(output, [points], True, (0, 0, 0), 2)
        flipped = np.ascontiguousarray(output[:, ::-1])

        upright = score_silhouette(source, output, CONFIG)
        mirrored = score_silhouette(source, flipped, CONFIG)

        self.assertGreater(upright.details["raw_score"], 0.9)
        self.assertLess(mirrored.details["raw_score"], upright.details["raw_score"] - 0.1)


class GlobalMetricBundleTest(unittest.TestCase):
    def test_bundle_returns_independent_metric_results(self):
        source = _white(200, 300)
        cv2.rectangle(source, (40, 60), (160, 240), (30, 60, 200), -1)
        output = _white(200, 300)
        cv2.rectangle(output, (40, 60), (160, 240), (0, 0, 0), 2)

        metrics = score_global_metrics(source, output, "2:3", CONFIG)

        self.assertEqual(
            sorted(metrics),
            [
                "aspect_ratio",
                "black_fill",
                "colored_pixels",
                "faint_strokes",
                "silhouette_iou",
            ],
        )
        for name, result in metrics.items():
            with self.subTest(metric=name):
                self.assertIsInstance(result, MetricResult)
                self.assertIn(result.status, {"pass", "warn", "fail", "not_scored"})
                self.assertTrue(0.0 <= result.confidence <= 1.0)
                if result.status == "not_scored":
                    self.assertTrue(result.reason)

    def test_one_broken_metric_does_not_break_the_bundle(self):
        from unittest.mock import patch

        source = _white(200, 300)
        output = _white(200, 300)
        with patch(
            "sketch_scoring.metrics.score_black_fill", side_effect=RuntimeError("boom")
        ):
            metrics = score_global_metrics(source, output, "2:3", CONFIG)

        self.assertEqual(metrics["black_fill"].status, "not_scored")
        self.assertIn("boom", metrics["black_fill"].reason)
        self.assertEqual(metrics["aspect_ratio"].status, "pass")


class ConnectionMetricTest(unittest.TestCase):
    SIZE = 256
    BOX = [0.2, 0.4, 0.8, 0.6]
    # ROI는 x 51..205, y 102..154 이므로 대각선은 아래 값입니다.
    ROI_DIAGONAL = float(np.hypot(205 - 51, 154 - 102))

    def _anchor(self, center_x: int, center_y: int, radius: int = 6) -> list[float]:
        return [
            (center_x - radius) / self.SIZE,
            (center_y - radius) / self.SIZE,
            (center_x + radius) / self.SIZE,
            (center_y + radius) / self.SIZE,
        ]

    def _annotation(self) -> dict:
        return {
            "id": "quarter-seam-1",
            "type": "connection",
            "target_box": self.BOX,
            "anchors": {
                "start_region": self._anchor(118, 128),
                "end_region": self._anchor(142, 128),
            },
        }

    def _canvas(self) -> np.ndarray:
        return _white(self.SIZE, self.SIZE)

    def _broken(self) -> np.ndarray:
        image = self._canvas()
        cv2.line(image, (60, 128), (120, 128), (0, 0, 0), 3)
        cv2.line(image, (140, 128), (200, 128), (0, 0, 0), 3)
        return image

    def test_same_component_touching_both_anchors_passes(self):
        image = self._canvas()
        cv2.line(image, (60, 128), (200, 128), (0, 0, 0), 3)

        result = score_connection(image, self._annotation(), CONFIG)

        self.assertEqual(result.status, "pass")
        self.assertIs(result.score, True)
        self.assertTrue(result.details["connected"])
        self.assertEqual(result.details["gap_pixels"], 0.0)
        self.assertEqual(result.details["gap_normalized"], 0.0)
        self.assertEqual(
            result.details["start_component"], result.details["end_component"]
        )

    def test_two_components_fail_and_report_gap(self):
        result = score_connection(self._broken(), self._annotation(), CONFIG)

        self.assertEqual(result.status, "fail")
        self.assertFalse(result.details["connected"])
        # 두께 3px 선은 양 끝이 2px씩 늘어나므로 실제 흰 단절은 138-122=16px입니다.
        self.assertAlmostEqual(result.details["gap_pixels"], 16.0, delta=1.5)
        self.assertNotEqual(
            result.details["start_component"], result.details["end_component"]
        )

    def test_missing_ink_in_one_anchor_is_not_scored(self):
        image = self._canvas()
        cv2.line(image, (60, 128), (120, 128), (0, 0, 0), 3)

        result = score_connection(image, self._annotation(), CONFIG)

        self.assertEqual(result.status, "not_scored")
        self.assertIn("앵커", result.reason)
        self.assertIsNone(result.score)

    def test_nearby_unrelated_line_does_not_replace_anchor_component(self):
        image = self._broken()
        # 두 앵커에 닿지 않는 무관한 선이 단절 구간을 지나갑니다.
        cv2.line(image, (130, 105), (130, 150), (0, 0, 0), 3)

        result = score_connection(image, self._annotation(), CONFIG)

        self.assertEqual(result.status, "fail")
        self.assertFalse(result.details["connected"])
        # 무관한 선까지의 거리(약 6px)가 아니라 두 앵커 성분 사이 거리(16px)여야 합니다.
        self.assertAlmostEqual(result.details["gap_pixels"], 16.0, delta=1.5)

    def test_low_pixel_component_spanning_both_anchors_does_not_connect(self):
        image = self._canvas()
        # 의도한 재단선은 굵고 끊겨 있습니다.
        cv2.line(image, (60, 128), (118, 128), (0, 0, 0), 5)
        cv2.line(image, (142, 128), (200, 128), (0, 0, 0), 5)
        # 두 앵커 박스에 모두 걸치지만 픽셀이 적은 무관한 성분입니다.
        cv2.line(image, (112, 123), (148, 123), (0, 0, 0), 1)

        result = score_connection(image, self._annotation(), CONFIG)

        self.assertEqual(result.status, "fail")
        self.assertIs(result.score, False)
        self.assertFalse(result.details["connected"])
        self.assertNotEqual(
            result.details["start_component"], result.details["end_component"]
        )
        # 굵은 재단선 두 조각 사이 거리를 보고해야 합니다.
        self.assertAlmostEqual(result.details["gap_pixels"], 18.0, delta=3.0)

    def _tiny_annotation(self) -> dict:
        """앵커를 2x2 픽셀로 좁혀 앵커 잉크를 최소치까지 줄입니다."""
        return {
            "id": "quarter-seam-1",
            "type": "connection",
            "target_box": self.BOX,
            "anchors": {
                "start_region": self._anchor(119, 128, radius=1),
                "end_region": self._anchor(141, 128, radius=1),
            },
        }

    def test_low_confidence_disconnected_fragments_are_not_scored_with_gap(self):
        image = self._canvas()
        # 1픽셀 두께라 좁은 앵커 안에 잉크가 두 개만 들어옵니다.
        cv2.line(image, (60, 128), (120, 128), (0, 0, 0), 1)
        cv2.line(image, (140, 128), (200, 128), (0, 0, 0), 1)

        result = score_connection(image, self._tiny_annotation(), CONFIG)

        self.assertEqual(result.status, "not_scored")
        self.assertIsNone(result.score)
        self.assertLess(result.confidence, CONFIG.connection_min_confidence)
        self.assertIn("단정할 수 없음", result.reason)
        # 진단값은 그대로 남아 사람이 확인할 수 있습니다.
        self.assertFalse(result.details["connected"])
        self.assertGreater(result.details["gap_pixels"], 0.0)
        self.assertAlmostEqual(
            result.details["gap_normalized"],
            result.details["gap_pixels"] / self.ROI_DIAGONAL,
            places=6,
        )
        self.assertNotEqual(
            result.details["start_component"], result.details["end_component"]
        )
        self.assertLessEqual(result.details["start_component_ink"], 2)
        self.assertLessEqual(result.details["end_component_ink"], 2)

    def test_isolated_speckles_do_not_inflate_anchor_evidence(self):
        """앵커에 흩어진 잡티는 재단선 후보의 근거가 아닙니다."""
        image = self._canvas()
        # 지배 성분(재단선 후보)은 앵커마다 잉크가 2픽셀뿐입니다.
        cv2.line(image, (60, 128), (113, 128), (0, 0, 0), 1)
        cv2.line(image, (146, 128), (200, 128), (0, 0, 0), 1)
        # 서로 떨어진 1픽셀 잡티를 두 앵커 안에 여러 개 흩뿌립니다.
        speckles = 0
        for base_x in (114, 138):
            for offset in (0, 3, 6, 9):
                for y in (123, 132):
                    image[y, base_x + offset] = 0
                    speckles += 1
        self.assertEqual(speckles, 16)

        result = score_connection(image, self._annotation(), CONFIG)

        # 앵커 전체 잉크를 셌다면 신뢰도가 1.0이 되어 fail로 단정했을 상황입니다.
        self.assertEqual(result.details["start_component_ink"], 2)
        self.assertEqual(result.details["end_component_ink"], 2)
        self.assertEqual(result.status, "not_scored")
        self.assertLess(result.confidence, CONFIG.connection_min_confidence)
        self.assertIn("지배 성분", result.reason)
        self.assertFalse(result.details["connected"])
        self.assertGreater(result.details["gap_pixels"], 0.0)

    def test_dominant_fragment_ink_is_reported_for_confident_verdicts(self):
        connected = self._canvas()
        cv2.line(connected, (60, 128), (200, 128), (0, 0, 0), 3)
        passed = score_connection(connected, self._annotation(), CONFIG)
        self.assertEqual(passed.status, "pass")
        self.assertGreaterEqual(
            passed.details["start_component_ink"], CONFIDENT_ANCHOR_INK_PIXELS
        )

        failed = score_connection(self._broken(), self._annotation(), CONFIG)
        self.assertEqual(failed.status, "fail")
        self.assertGreaterEqual(
            failed.details["end_component_ink"], CONFIDENT_ANCHOR_INK_PIXELS
        )

    def test_low_confidence_connected_fragment_is_also_not_scored(self):
        image = self._canvas()
        # 이어져 있어도 근거가 적으면 pass로 단정하지 않습니다(불확실성 대칭).
        cv2.line(image, (60, 128), (200, 128), (0, 0, 0), 1)

        result = score_connection(image, self._tiny_annotation(), CONFIG)

        self.assertEqual(result.status, "not_scored")
        self.assertIsNone(result.score)
        self.assertLess(result.confidence, CONFIG.connection_min_confidence)
        self.assertTrue(result.details["connected"])
        self.assertEqual(result.details["gap_pixels"], 0.0)
        self.assertEqual(
            result.details["start_component"], result.details["end_component"]
        )

    def test_sufficient_evidence_keeps_pass_and_fail_verdicts(self):
        connected = self._canvas()
        cv2.line(connected, (60, 128), (200, 128), (0, 0, 0), 3)
        passed = score_connection(connected, self._annotation(), CONFIG)
        self.assertEqual(passed.status, "pass")
        self.assertGreaterEqual(passed.confidence, CONFIG.connection_min_confidence)

        failed = score_connection(self._broken(), self._annotation(), CONFIG)
        self.assertEqual(failed.status, "fail")
        self.assertGreaterEqual(failed.confidence, CONFIG.connection_min_confidence)

    def test_confidence_floor_is_configurable(self):
        image = self._canvas()
        cv2.line(image, (60, 128), (120, 128), (0, 0, 0), 1)
        cv2.line(image, (140, 128), (200, 128), (0, 0, 0), 1)
        annotation = self._tiny_annotation()

        strict = score_connection(image, annotation, CONFIG)
        relaxed = score_connection(
            image, annotation, ScoringConfig(connection_min_confidence=0.0)
        )

        self.assertEqual(strict.status, "not_scored")
        self.assertEqual(relaxed.status, "fail")
        self.assertEqual(
            strict.details["gap_pixels"], relaxed.details["gap_pixels"]
        )

    def test_result_has_gap_pixels_and_normalized_gap(self):
        result = score_connection(self._broken(), self._annotation(), CONFIG)

        for key in (
            "connected",
            "gap_pixels",
            "gap_normalized",
            "start_component",
            "end_component",
        ):
            self.assertIn(key, result.details)
        self.assertAlmostEqual(
            result.details["gap_normalized"],
            result.details["gap_pixels"] / self.ROI_DIAGONAL,
            places=6,
        )
        # 연결 지표는 불변식이므로 불리언 점수를 확정합니다.
        self.assertIs(result.score, False)


class RequiredPathMetricTest(unittest.TestCase):
    SIZE = 256
    BOX = [0.1, 0.1, 0.9, 0.9]
    PATH = [[0.2, 0.5], [0.4, 0.45], [0.6, 0.5]]

    def _annotation(self) -> dict:
        return {
            "id": "toe-cap-boundary",
            "type": "required_path",
            "label": "toe_cap",
            "target_box": self.BOX,
            "paths": [self.PATH],
        }

    def _points(self, shift: int = 0) -> np.ndarray:
        return np.array(
            [[round(x * self.SIZE), round(y * self.SIZE) + shift] for x, y in self.PATH],
            dtype=np.int32,
        )

    def _output(self, shift: int | None = 0) -> np.ndarray:
        image = _white(self.SIZE, self.SIZE)
        if shift is not None:
            cv2.polylines(image, [self._points(shift)], False, (0, 0, 0), 2)
        return image

    def test_exact_output_path_is_detected(self):
        result = score_required_path(self._output(0), self._annotation(), CONFIG)

        self.assertEqual(result.status, "not_scored")
        self.assertEqual(result.reason, UNCALIBRATED_REASON)
        self.assertIsNone(result.score)
        self.assertAlmostEqual(result.details["detection_ratio"], 1.0, places=6)
        self.assertLessEqual(result.details["median_error_px"], 1.0)
        self.assertLessEqual(result.details["p95_error_px"], 1.5)

    def test_small_shift_stays_within_tolerance(self):
        result = score_required_path(self._output(3), self._annotation(), CONFIG)

        self.assertAlmostEqual(result.details["detection_ratio"], 1.0, places=6)
        self.assertGreater(result.details["median_error_px"], 1.0)
        self.assertLessEqual(result.details["median_error_px"], CONFIG.path_tolerance_px)

    def test_large_shift_is_not_detected(self):
        result = score_required_path(self._output(12), self._annotation(), CONFIG)

        self.assertEqual(result.details["detection_ratio"], 0.0)
        self.assertGreater(result.details["median_error_px"], CONFIG.path_tolerance_px)

    def test_missing_output_line_reports_zero_detection(self):
        result = score_required_path(self._output(None), self._annotation(), CONFIG)

        self.assertEqual(result.details["detection_ratio"], 0.0)
        self.assertGreater(result.details["median_error_px"], 0.0)
        self.assertEqual(result.status, "not_scored")

    def test_unrelated_line_in_roi_is_ignored(self):
        image = self._output(0)
        cv2.line(image, (40, 215), (215, 215), (0, 0, 0), 2)

        result = score_required_path(image, self._annotation(), CONFIG)

        self.assertAlmostEqual(result.details["detection_ratio"], 1.0, places=6)
        self.assertLessEqual(result.details["median_error_px"], 1.0)


class CompleteRoiMetricTest(unittest.TestCase):
    SIZE = 256
    BOX = [0.1, 0.1, 0.9, 0.9]
    PATHS = [
        [[0.2, 0.5], [0.4, 0.45], [0.6, 0.5]],
        [[0.2, 0.6], [0.4, 0.58], [0.6, 0.62]],
    ]

    def _annotation(self) -> dict:
        return {
            "id": "heel-complete",
            "type": "complete_roi",
            "label": "heel",
            "target_box": self.BOX,
            "paths": self.PATHS,
        }

    def _points(self, path: list) -> np.ndarray:
        return np.array(
            [[round(x * self.SIZE), round(y * self.SIZE)] for x, y in path],
            dtype=np.int32,
        )

    def _output(self, paths: list) -> np.ndarray:
        image = _white(self.SIZE, self.SIZE)
        for path in paths:
            cv2.polylines(image, [self._points(path)], False, (0, 0, 0), 2)
        return image

    def test_exact_paths_have_low_missing_and_extra(self):
        result = score_complete_roi(self._output(self.PATHS), self._annotation(), CONFIG)

        self.assertEqual(result.status, "not_scored")
        self.assertEqual(result.reason, UNCALIBRATED_REASON)
        self.assertLess(result.details["missing_ratio"], 0.05)
        self.assertLess(result.details["extra_ratio"], 0.05)

    def test_absent_expected_path_raises_missing_ratio(self):
        result = score_complete_roi(
            self._output(self.PATHS[:1]), self._annotation(), CONFIG
        )

        self.assertGreater(result.details["missing_ratio"], 0.3)
        self.assertLess(result.details["extra_ratio"], 0.05)

    def test_unannotated_extra_line_raises_extra_ratio(self):
        image = self._output(self.PATHS)
        cv2.line(image, (60, 200), (200, 200), (0, 0, 0), 2)

        result = score_complete_roi(image, self._annotation(), CONFIG)

        self.assertLess(result.details["missing_ratio"], 0.05)
        self.assertGreater(result.details["extra_ratio"], 0.2)

    def test_ink_outside_target_box_is_ignored(self):
        image = self._output(self.PATHS)
        cv2.line(image, (10, 245), (245, 245), (0, 0, 0), 2)

        result = score_complete_roi(image, self._annotation(), CONFIG)

        self.assertLess(result.details["extra_ratio"], 0.05)

    def test_no_output_ink_gives_numeric_missing_ratio(self):
        result = score_complete_roi(
            _white(self.SIZE, self.SIZE), self._annotation(), CONFIG
        )

        self.assertEqual(result.details["missing_ratio"], 1.0)
        self.assertEqual(result.details["extra_ratio"], 0.0)
        self.assertEqual(result.status, "not_scored")


class ScoreAnnotationDispatchTest(unittest.TestCase):
    def test_dispatches_each_supported_type(self):
        image = _white(256, 256)
        cv2.line(image, (60, 128), (200, 128), (0, 0, 0), 3)
        cases = {
            "connection": ConnectionMetricTest()._annotation(),
            "required_path": RequiredPathMetricTest()._annotation(),
            "complete_roi": CompleteRoiMetricTest()._annotation(),
        }
        for name, annotation in cases.items():
            with self.subTest(annotation=name):
                result = score_annotation(image, annotation, CONFIG)
                self.assertIsInstance(result, MetricResult)
                self.assertIn(result.status, {"pass", "warn", "fail", "not_scored"})

    def test_unknown_type_is_not_scored(self):
        result = score_annotation(
            _white(64, 64),
            {"id": "x", "type": "silhouette", "target_box": [0.1, 0.1, 0.9, 0.9]},
            CONFIG,
        )
        self.assertEqual(result.status, "not_scored")
        self.assertTrue(result.reason)

    def test_no_annotation_metric_writes_files(self):
        import os

        image = _white(256, 256)
        cv2.line(image, (60, 128), (200, 128), (0, 0, 0), 3)
        with tempfile.TemporaryDirectory() as tmp:
            cwd = os.getcwd()
            os.chdir(tmp)
            try:
                score_annotation(image, ConnectionMetricTest()._annotation(), CONFIG)
                score_annotation(image, RequiredPathMetricTest()._annotation(), CONFIG)
                score_annotation(image, CompleteRoiMetricTest()._annotation(), CONFIG)
                self.assertEqual(os.listdir(tmp), [])
            finally:
                os.chdir(cwd)


if __name__ == "__main__":
    unittest.main()
