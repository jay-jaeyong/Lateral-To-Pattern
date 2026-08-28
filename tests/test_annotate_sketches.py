"""로컬 주석 웹앱의 API와 페이지 계약 테스트.

Flask 테스트 클라이언트만 쓰고 서버를 띄우지 않습니다. 모든 경로는 임시
프로젝트 안이며 어떤 요청도 이미지를 수정하지 않습니다.
"""

import json
import os
import shutil
import subprocess
import tempfile
import unicodedata
import unittest
import unittest.mock
from pathlib import Path

import cv2
import numpy as np

from scripts.annotate_sketches import create_app
from sketch_scoring.annotations import load_annotations, save_annotations
from sketch_scoring.manifest import ManifestError
from sketch_scoring.scoring import ANNOTATED_ONLY_REASON, sha256_file

ANNOTATION_ROOT = "annotations/sketch-scoring/items"
NFD_NAME = unicodedata.normalize("NFD", "푸마2")
NFC_NAME = unicodedata.normalize("NFC", "푸마2")

CONNECTION = {
    "id": "quarter-seam-1",
    "type": "connection",
    "target_box": [0.2, 0.4, 0.8, 0.6],
    "anchors": {
        "start_region": [0.30, 0.45, 0.36, 0.55],
        "end_region": [0.62, 0.45, 0.68, 0.55],
    },
}


def _save_image(path: Path, rgb: np.ndarray, suffix: str = ".png") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ok, encoded = cv2.imencode(suffix, cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
    assert ok
    path.write_bytes(encoded.tobytes())


def _source() -> np.ndarray:
    image = np.full((300, 200, 3), 255, dtype=np.uint8)
    cv2.rectangle(image, (40, 60), (160, 240), (30, 60, 200), -1)
    return image


def _sketch(*, red_box: bool = True, ends: int = 2) -> np.ndarray:
    image = np.full((300, 200, 3), 255, dtype=np.uint8)
    cv2.rectangle(image, (40, 60), (160, 240), (0, 0, 0), 2)
    # 검사 영역(y 120..180) 안에서 끊긴 재단선.
    cv2.line(image, (0, 150), (80, 150), (0, 0, 0), 3)
    cv2.line(image, (120, 150), (199, 150), (0, 0, 0), 3)
    if ends > 2:
        cv2.line(image, (0, 185), (60, 185), (0, 0, 0), 3)
    if red_box:
        cv2.rectangle(image, (60, 130), (140, 170), (255, 0, 0), 3)
    return image


def _project(
    tmp: str,
    *,
    kind: str = "clean",
    item_id: str = "shoe",
    ends: int = 2,
    red_box: bool = True,
) -> Path:
    root = Path(tmp)
    (root / ANNOTATION_ROOT).mkdir(parents=True, exist_ok=True)
    suffix = ".jpeg" if kind == "annotated_only" else ".png"
    source_name = f"{item_id}_color.png"
    output_name = f"{item_id}_sketch{suffix}"
    _save_image(root / "images" / source_name, _source())
    _save_image(
        root / "images" / "output-5" / output_name,
        _sketch(ends=ends, red_box=red_box),
        suffix,
    )
    manifest = root / "annotations" / "sketch-scoring" / "dataset.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "items": {
                    unicodedata.normalize("NFC", item_id): {
                        "display_name": unicodedata.normalize("NFC", item_id),
                        "source": f"images/{source_name}",
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
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return root


def _client(root: Path):
    app = create_app(
        root / "annotations" / "sketch-scoring" / "dataset.json",
        project_root=root,
        annotation_root=root / ANNOTATION_ROOT,
    )
    return app.test_client()


def _snapshot(root: Path) -> dict:
    return {
        str(path): (sha256_file(path), path.stat().st_mtime_ns)
        for path in sorted((root / "images").rglob("*"))
        if path.is_file()
    }


class ImageApiTest(unittest.TestCase):
    def test_images_lists_nfc_display_names_and_versions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _project(tmp, item_id=NFD_NAME, kind="annotated_only")
            response = _client(root).get("/api/images")

            self.assertEqual(response.status_code, 200)
            items = response.get_json()["items"]
            self.assertEqual(len(items), 1)
            item = items[0]
            self.assertEqual(item["display_name"], NFC_NAME)
            self.assertEqual(item["id"], NFC_NAME)
            self.assertEqual(item["expected_canvas_ratio"], "2:3")
            self.assertEqual(
                item["versions"],
                [{"version": "output-5", "kind": "annotated_only", "exists": True}],
            )
            self.assertEqual(response.headers["Cache-Control"], "no-store")

    def test_image_serves_only_manifest_source_or_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _project(tmp)
            client = _client(root)

            source = client.get("/api/image/shoe?kind=source")
            self.assertEqual(source.status_code, 200)
            self.assertEqual(
                source.data, (root / "images" / "shoe_color.png").read_bytes()
            )
            self.assertEqual(source.mimetype, "image/png")
            self.assertEqual(source.headers["Cache-Control"], "no-store")

            output = client.get("/api/image/shoe?kind=output&version=output-5")
            self.assertEqual(output.status_code, 200)
            self.assertEqual(
                output.data,
                (root / "images" / "output-5" / "shoe_sketch.png").read_bytes(),
            )

            self.assertEqual(client.get("/api/image/shoe?kind=mask").status_code, 400)

    def test_unknown_item_is_404(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _project(tmp)
            response = _client(root).get("/api/image/absent?kind=source")
            self.assertEqual(response.status_code, 404)
            self.assertIn("error", response.get_json())

    def test_unknown_version_is_404(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _project(tmp)
            response = _client(root).get("/api/image/shoe?kind=output&version=output-9")
            self.assertEqual(response.status_code, 404)

    def test_path_traversal_cannot_escape_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _project(tmp)
            outside = root / "secret.txt"
            outside.write_text("secret", encoding="utf-8")
            client = _client(root)

            for target in (
                "/api/image/..%2f..%2fsecret.txt?kind=source",
                "/api/image/../secret.txt?kind=source",
                "/api/image/shoe?kind=output&version=..%2f..%2fsecret.txt",
                "/api/annotations/..%2f..%2fescape",
            ):
                with self.subTest(target=target):
                    self.assertIn(client.get(target).status_code, {400, 404, 308})

    def test_no_route_writes_image_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _project(tmp)
            client = _client(root)
            before = _snapshot(root)

            client.get("/")
            client.get("/api/images")
            client.get("/api/image/shoe?kind=source")
            client.get("/api/image/shoe?kind=output&version=output-5")
            client.get("/api/annotations/shoe")
            client.post(
                "/api/annotations/shoe",
                json={"schema_version": 1, "annotations": [CONNECTION]},
            )
            client.post("/api/import-red-boxes/shoe", json={"version": "output-5"})
            client.post(
                "/api/suggest-anchors/shoe",
                json={"version": "output-5", "target_box": [0.1, 0.4, 0.9, 0.6]},
            )
            client.post("/api/score/shoe", json={"version": "output-5"})

            self.assertEqual(_snapshot(root), before)
            written = sorted(
                path.relative_to(root).as_posix()
                for path in root.rglob("*")
                if path.is_file()
            )
            for path in written:
                self.assertTrue(
                    path.startswith("images/") or path.startswith("annotations/"),
                    f"허용되지 않은 위치에 파일이 생겼습니다: {path}",
                )


class AnnotationApiTest(unittest.TestCase):
    def test_get_missing_annotations_returns_empty_document(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _project(tmp)
            response = _client(root).get("/api/annotations/shoe")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(
                response.get_json(), {"schema_version": 1, "annotations": []}
            )
            self.assertEqual(response.headers["Cache-Control"], "no-store")

    def test_post_validates_saves_and_reloads_document(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _project(tmp)
            client = _client(root)

            response = client.post(
                "/api/annotations/shoe",
                json={"schema_version": 1, "annotations": [CONNECTION]},
            )

            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.get_json()["saved"])
            stored = load_annotations(root / ANNOTATION_ROOT, "shoe")
            self.assertEqual(stored["annotations"][0]["id"], "quarter-seam-1")
            reloaded = client.get("/api/annotations/shoe").get_json()
            self.assertEqual(reloaded["annotations"][0]["target_box"], [0.2, 0.4, 0.8, 0.6])

    def test_invalid_coordinates_return_400_without_replacing_existing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _project(tmp)
            path = save_annotations(
                root / ANNOTATION_ROOT,
                "shoe",
                {"schema_version": 1, "annotations": [CONNECTION]},
            )
            before = path.read_bytes()
            bad = dict(CONNECTION, target_box=[0.2, 0.4, 1.4, 0.6])

            response = _client(root).post(
                "/api/annotations/shoe", json={"schema_version": 1, "annotations": [bad]}
            )

            self.assertEqual(response.status_code, 400)
            self.assertIn("error", response.get_json())
            self.assertEqual(path.read_bytes(), before)

    def test_oversized_post_returns_json_413_without_replacing_sidecar(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _project(tmp)
            path = save_annotations(
                root / ANNOTATION_ROOT,
                "shoe",
                {"schema_version": 1, "annotations": [CONNECTION]},
            )
            before = path.read_bytes()
            client = _client(root)

            # 본문 크기 제한(1MB)을 넘기는 요청.
            oversized = {
                "schema_version": 1,
                "annotations": [dict(CONNECTION, label="가" * 600_000)],
            }
            response = client.post("/api/annotations/shoe", json=oversized)

            self.assertEqual(response.status_code, 413)
            self.assertEqual(response.mimetype, "application/json")
            self.assertEqual(response.headers["Cache-Control"], "no-store")
            self.assertIn("error", response.get_json())
            self.assertTrue(response.get_json()["error"])
            self.assertEqual(path.read_bytes(), before)

    def test_red_box_import_returns_candidates_without_saving(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _project(tmp)
            client = _client(root)
            sidecar = root / ANNOTATION_ROOT / "shoe.json"

            response = client.post(
                "/api/import-red-boxes/shoe", json={"version": "output-5"}
            )

            self.assertEqual(response.status_code, 200)
            candidates = response.get_json()["candidates"]
            self.assertEqual(len(candidates), 1)
            for value in candidates[0]:
                self.assertTrue(0.0 <= value <= 1.0)
            self.assertFalse(sidecar.exists())

    def test_ambiguous_anchor_suggestion_returns_empty_candidates(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _project(tmp, ends=3, red_box=False)
            response = _client(root).post(
                "/api/suggest-anchors/shoe",
                json={"version": "output-5", "target_box": [0.05, 0.35, 0.95, 0.65]},
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.get_json()["anchors"], [])

    def test_unambiguous_anchor_suggestion_returns_two_boxes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _project(tmp, ends=2, red_box=False)
            response = _client(root).post(
                "/api/suggest-anchors/shoe",
                json={"version": "output-5", "target_box": [0.05, 0.45, 0.95, 0.55]},
            )
            anchors = response.get_json()["anchors"]
            self.assertEqual(len(anchors), 2)
            for box in anchors:
                self.assertTrue(all(0.0 <= value <= 1.0 for value in box))

    def test_invalid_target_box_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _project(tmp)
            response = _client(root).post(
                "/api/suggest-anchors/shoe",
                json={"version": "output-5", "target_box": [0.9, 0.4, 0.2, 0.6]},
            )
            self.assertEqual(response.status_code, 400)


class ScoreApiTest(unittest.TestCase):
    def test_score_returns_diagnostic_result_without_writing_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _project(tmp)
            save_annotations(
                root / ANNOTATION_ROOT,
                "shoe",
                {"schema_version": 1, "annotations": [CONNECTION]},
            )
            client = _client(root)

            response = client.post("/api/score/shoe", json={"version": "output-5"})

            self.assertEqual(response.status_code, 200)
            result = response.get_json()["result"]
            self.assertEqual(result["version"], "output-5")
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
            self.assertEqual(len(result["annotations"]), 1)
            for metric in result["metrics"].values():
                self.assertIn(
                    metric["status"], {"pass", "warn", "fail", "not_scored"}
                )
            self.assertNotIn("total", result)
            self.assertFalse((root / "reports").exists())

    def test_annotated_only_output_is_not_scored(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _project(tmp, kind="annotated_only")
            response = _client(root).post("/api/score/shoe", json={"version": "output-5"})

            result = response.get_json()["result"]
            self.assertEqual(result["kind"], "annotated_only")
            for metric in result["metrics"].values():
                self.assertEqual(metric["status"], "not_scored")
                self.assertEqual(metric["reason"], ANNOTATED_ONLY_REASON)

    def test_unknown_version_is_404(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _project(tmp)
            response = _client(root).post("/api/score/shoe", json={"version": "output-1"})
            self.assertEqual(response.status_code, 404)


class SidecarSymlinkApiTest(unittest.TestCase):
    """웹 API도 주석 루트를 벗어나는 사이드카를 읽거나 쓰지 않습니다."""

    def _outside(self, directory: Path) -> Path:
        path = directory / "outside.json"
        path.write_text(
            '{"schema_version": 1, "annotations": [], "secret": "외부"}', encoding="utf-8"
        )
        return path

    def test_external_file_symlink_is_rejected_by_get_and_post(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as away:
            root = _project(tmp)
            outside = self._outside(Path(away))
            before = outside.read_bytes()
            os.symlink(outside, root / ANNOTATION_ROOT / "shoe.json")
            client = _client(root)

            read = client.get("/api/annotations/shoe")
            self.assertEqual(read.status_code, 400)
            self.assertIn("error", read.get_json())
            self.assertNotIn("secret", read.get_data(as_text=True))

            write = client.post(
                "/api/annotations/shoe",
                json={"schema_version": 1, "annotations": [CONNECTION]},
            )
            self.assertEqual(write.status_code, 400)
            self.assertEqual(outside.read_bytes(), before)

    def _replace_items_with_symlink(self, root: Path, away: Path) -> None:
        items = root / ANNOTATION_ROOT
        for path in items.iterdir():
            path.unlink()
        items.rmdir()
        os.symlink(away, items)

    def test_symlinked_item_directory_is_rejected_at_app_creation(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as away:
            root = _project(tmp)
            self._replace_items_with_symlink(root, Path(away))
            outside = self._outside(Path(away))
            before = outside.read_bytes()

            # 앱이 아예 만들어지지 않습니다(허용된 쓰기 루트 밖이므로).
            with self.assertRaises(ManifestError):
                _client(root)

            self.assertEqual(outside.read_bytes(), before)

    def test_symlinked_item_directory_swapped_later_is_rejected_per_request(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as away:
            root = _project(tmp)
            client = _client(root)
            # 서버가 뜬 뒤에 디렉터리가 링크로 바뀐 상황.
            self._replace_items_with_symlink(root, Path(away))
            outside = self._outside(Path(away))
            before = outside.read_bytes()

            self.assertEqual(client.get("/api/annotations/shoe").status_code, 400)
            self.assertEqual(
                client.post(
                    "/api/annotations/shoe",
                    json={"schema_version": 1, "annotations": [CONNECTION]},
                ).status_code,
                400,
            )
            self.assertEqual(outside.read_bytes(), before)
            self.assertEqual(
                sorted(path.name for path in Path(away).iterdir()), ["outside.json"]
            )


class AnnotatedOnlyAnchorTest(unittest.TestCase):
    """빨간 표시가 합성된 출력에서는 앵커를 자동 추정하지 않습니다."""

    def _red_seam(self) -> np.ndarray:
        image = np.full((300, 200, 3), 255, dtype=np.uint8)
        # 끊긴 빨간 사각형 변. 순수 빨강의 휘도는 76이라 잉크로 보이며,
        # 이대로 추정하면 가짜 끝점이 정확히 두 개 나옵니다.
        cv2.line(image, (0, 150), (80, 150), (255, 0, 0), 3)
        cv2.line(image, (120, 150), (199, 150), (255, 0, 0), 3)
        return image

    def test_fixture_would_otherwise_yield_two_false_endpoints(self):
        from sketch_scoring.annotations import suggest_connection_anchors

        anchors = suggest_connection_anchors(self._red_seam(), [0.05, 0.45, 0.95, 0.55])
        self.assertEqual(len(anchors), 2)

    def test_annotated_only_output_returns_no_anchors_without_decoding(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _project(tmp, kind="annotated_only")
            _save_image(
                root / "images" / "output-5" / "shoe_sketch.jpeg",
                self._red_seam(),
                ".jpeg",
            )
            client = _client(root)

            with unittest.mock.patch("scripts.annotate_sketches.load_rgb") as decode:
                response = client.post(
                    "/api/suggest-anchors/shoe",
                    json={"version": "output-5", "target_box": [0.05, 0.45, 0.95, 0.55]},
                )

            decode.assert_not_called()
            self.assertEqual(response.status_code, 200)
            payload = response.get_json()
            self.assertEqual(payload["anchors"], [])
            self.assertIn("클릭", payload["reason"])

    def test_clean_output_still_suggests_anchors(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _project(tmp, ends=2, red_box=False)
            response = _client(root).post(
                "/api/suggest-anchors/shoe",
                json={"version": "output-5", "target_box": [0.05, 0.45, 0.95, 0.55]},
            )
            self.assertEqual(len(response.get_json()["anchors"]), 2)


class CanvasGeometryContractTest(unittest.TestCase):
    """이미지 밖 좌표는 저장되기 전에 거부됩니다."""

    TEMPLATE = Path(__file__).resolve().parent.parent / "templates" / "annotate.html"

    def _contract_source(self) -> str:
        text = self.TEMPLATE.read_text(encoding="utf-8")
        start = text.index("/* --- geometry-contract-start")
        end = text.index("/* --- geometry-contract-end")
        return text[start:end]

    def test_every_annotation_input_site_uses_the_guard(self):
        text = self.TEMPLATE.read_text(encoding="utf-8")
        # 박스 시작, 박스 완료, 폴리라인·앵커 클릭 세 지점 + 정의 1회.
        self.assertEqual(text.count("acceptAnnotationPoint"), 4)
        self.assertIn("function acceptAnnotationPoint", text)

    def test_drag_uses_constrained_translation_not_per_coordinate_clamping(self):
        text = self.TEMPLATE.read_text(encoding="utf-8")
        self.assertIn("function translateAnnotation", text)
        self.assertIn("function constrainedDelta", text)
        self.assertIn("function annotationExtent", text)
        # 좌표별로 자르는 이동 함수는 남아 있지 않아야 합니다.
        self.assertNotIn("function shiftBox", text)
        self.assertNotIn("function moveAnnotation", text)

    @unittest.skipUnless(shutil.which("node"), "node가 없어 JS 계약 검사를 건너뜁니다")
    def test_drag_keeps_size_children_and_range(self):
        script = self._contract_source() + """
const base = {
  id: "seam-1", type: "connection",
  target_box: [0.20, 0.30, 0.40, 0.50],
  anchors: { start_region: [0.22, 0.34, 0.26, 0.38],
             end_region:   [0.34, 0.42, 0.38, 0.46] }
};
const withPaths = {
  id: "heel-1", type: "complete_roi",
  target_box: [0.60, 0.60, 0.90, 0.90],
  paths: [[[0.62, 0.64], [0.70, 0.70], [0.88, 0.86]]]
};
const size = (box) => [box[2] - box[0], box[3] - box[1]];
const close = (a, b) => Math.abs(a - b) < 1e-12;

function checkRange(annotation, label) {
  const flat = [...annotation.target_box];
  if (annotation.anchors) {
    for (const key of Object.keys(annotation.anchors)) flat.push(...annotation.anchors[key]);
  }
  if (annotation.paths) {
    for (const path of annotation.paths) for (const p of path) flat.push(...p);
  }
  for (const value of flat) {
    if (!(value >= 0 && value <= 1)) {
      throw new Error(label + ": 좌표가 범위를 벗어남 " + value);
    }
  }
}

// 네 방향으로 한참 지나치게 끌어도 크기와 상대 위치가 유지되고 범위 안입니다.
for (const [dx, dy, label] of [[-5, 0, "왼쪽"], [5, 0, "오른쪽"],
                               [0, -5, "위쪽"], [0, 5, "아래쪽"],
                               [-5, -5, "왼위"], [5, 5, "오른아래"]]) {
  for (const original of [base, withPaths]) {
    const moved = translateAnnotation(original, dx, dy);
    checkRange(moved, label);

    const before = size(original.target_box);
    const after = size(moved.target_box);
    if (!close(before[0], after[0]) || !close(before[1], after[1])) {
      throw new Error(label + ": 박스 크기가 바뀜 " + JSON.stringify([before, after]));
    }
    if (!(after[0] > 0 && after[1] > 0)) throw new Error(label + ": 박스가 찌그러짐");

    const shiftX = moved.target_box[0] - original.target_box[0];
    const shiftY = moved.target_box[1] - original.target_box[1];
    if (original.anchors) {
      for (const key of Object.keys(original.anchors)) {
        for (let i = 0; i < 4; i += 1) {
          const expected = original.anchors[key][i] + (i % 2 === 0 ? shiftX : shiftY);
          if (!close(moved.anchors[key][i], expected)) {
            throw new Error(label + ": 앵커 상대 위치가 깨짐 " + key);
          }
        }
      }
    }
    if (original.paths) {
      original.paths.forEach((path, pi) => path.forEach((point, qi) => {
        if (!close(moved.paths[pi][qi][0], point[0] + shiftX)
            || !close(moved.paths[pi][qi][1], point[1] + shiftY)) {
          throw new Error(label + ": 폴리라인 상대 위치가 깨짐");
        }
      }));
    }
  }
}

// 각 변에 정확히 붙습니다.
if (!close(translateAnnotation(base, -5, 0).target_box[0], 0)) throw new Error("왼쪽 변에 붙지 않음");
if (!close(translateAnnotation(base, 5, 0).target_box[2], 1)) throw new Error("오른쪽 변에 붙지 않음");
if (!close(translateAnnotation(base, 0, -5).target_box[1], 0)) throw new Error("위쪽 변에 붙지 않음");
if (!close(translateAnnotation(base, 0, 5).target_box[3], 1)) throw new Error("아래쪽 변에 붙지 않음");

// 자식이 박스 밖으로 나와 있어도 그 자식 기준으로 이동이 제한됩니다.
const overhang = {
  id: "seam-2", type: "connection",
  target_box: [0.50, 0.50, 0.60, 0.60],
  anchors: { start_region: [0.44, 0.44, 0.48, 0.48],
             end_region:   [0.62, 0.62, 0.66, 0.66] }
};
const left = translateAnnotation(overhang, -5, -5);
checkRange(left, "돌출-왼위");
if (!close(left.anchors.start_region[0], 0)) throw new Error("돌출 자식이 기준이 되지 않음");
const right = translateAnnotation(overhang, 5, 5);
checkRange(right, "돌출-오른아래");
if (!close(right.anchors.end_region[2], 1)) throw new Error("돌출 자식이 기준이 되지 않음");

// 이동량이 범위 안이면 그대로 적용됩니다.
const small = translateAnnotation(base, 0.05, -0.05);
if (!close(small.target_box[0], 0.25) || !close(small.target_box[1], 0.25)) {
  throw new Error("정상 이동이 왜곡됨");
}
// 원본은 변경되지 않습니다.
if (!close(base.target_box[0], 0.20)) throw new Error("원본이 변형됨");
console.log("OK");
"""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "drag.mjs"
            path.write_text(script, encoding="utf-8")
            finished = subprocess.run(
                [shutil.which("node"), str(path)], capture_output=True, text=True
            )
        self.assertEqual(finished.returncode, 0, finished.stderr)
        self.assertIn("OK", finished.stdout)

    def test_resize_uses_the_bounded_geometry_function(self):
        text = self.TEMPLATE.read_text(encoding="utf-8")
        self.assertIn("function resizedBox", text)
        self.assertIn("function enforceBoxBounds", text)
        self.assertIn("const MIN_BOX_SIZE", text)
        # 크기 조절은 target_box만 바꿉니다.
        self.assertIn(
            "annotation.target_box = resizedBox(\n"
            "      state.drag.snapshot.target_box, state.drag.handle, point\n"
            "    );",
            text,
        )

    @unittest.skipUnless(shutil.which("node"), "node가 없어 JS 계약 검사를 건너뜁니다")
    def test_resize_keeps_positive_minimum_size_and_range(self):
        script = self._contract_source() + """
const HANDLES = ["w", "e", "n", "s", "nw", "ne", "sw", "se"];
const box = [0.30, 0.40, 0.60, 0.70];
const close = (a, b) => Math.abs(a - b) < 1e-12;

function checkBox(result, label) {
  for (const value of result) {
    if (!(value >= 0 && value <= 1)) throw new Error(label + ": 범위를 벗어남 " + value);
  }
  const width = result[2] - result[0];
  const height = result[3] - result[1];
  if (!(width >= MIN_BOX_SIZE - 1e-12)) throw new Error(label + ": 너비가 최소치 미달 " + width);
  if (!(height >= MIN_BOX_SIZE - 1e-12)) throw new Error(label + ": 높이가 최소치 미달 " + height);
  if (!(width > 0 && height > 0)) throw new Error(label + ": 크기가 0 이하");
}

// 반대쪽 변까지, 그리고 한참 지나쳐서 끌어도 최소 크기와 범위를 지킵니다.
const targets = [
  [0.60, 0.70], [0.30, 0.40],           // 정확히 반대쪽 변
  [0.95, 0.95], [0.05, 0.05],           // 반대쪽 변을 지나서
  [2.0, 2.0], [-2.0, -2.0],             // 이미지 밖으로 한참
  [0.60, 0.40], [0.30, 0.70]
];
for (const handle of HANDLES) {
  for (const point of targets) {
    const result = resizedBox(box, handle, point);
    checkBox(result, handle + " -> " + JSON.stringify(point));
  }
}

// 손잡이가 건드리지 않는 변은 그대로 유지됩니다.
const west = resizedBox(box, "w", [0.10, 0.99]);
if (!close(west[1], box[1]) || !close(west[3], box[3]) || !close(west[2], box[2])) {
  throw new Error("서쪽 손잡이가 다른 변을 바꿈");
}
if (!close(west[0], 0.10)) throw new Error("서쪽 손잡이가 적용되지 않음");
const north = resizedBox(box, "n", [0.99, 0.10]);
if (!close(north[0], box[0]) || !close(north[2], box[2]) || !close(north[3], box[3])) {
  throw new Error("북쪽 손잡이가 다른 변을 바꿈");
}
if (!close(north[1], 0.10)) throw new Error("북쪽 손잡이가 적용되지 않음");

// 반대쪽 변을 지나치면 뒤집히지 않고 최소 크기에서 멈춥니다.
const flipped = resizedBox(box, "w", [0.95, 0.5]);
if (!close(flipped[2] - flipped[0], MIN_BOX_SIZE)) {
  throw new Error("서쪽을 지나쳐 끌었을 때 최소 크기가 아님 " + (flipped[2] - flipped[0]));
}
if (!(flipped[0] < flipped[2])) throw new Error("박스가 뒤집힘");
const flippedSouth = resizedBox(box, "n", [0.5, 0.99]);
if (!close(flippedSouth[3] - flippedSouth[1], MIN_BOX_SIZE)) {
  throw new Error("북쪽을 지나쳐 끌었을 때 최소 크기가 아님");
}

// 모서리 손잡이는 두 축을 함께 제한합니다.
const corner = resizedBox(box, "se", [-2, -2]);
if (!close(corner[2] - corner[0], MIN_BOX_SIZE) || !close(corner[3] - corner[1], MIN_BOX_SIZE)) {
  throw new Error("모서리 손잡이가 두 축을 제한하지 않음");
}
checkBox(corner, "se 극단");

// 이미 찌그러진 박스가 들어와도 결과는 유효합니다.
checkBox(resizedBox([0.999, 0.999, 1.0, 1.0], "se", [2, 2]), "찌그러진 입력");
checkBox(resizedBox([0.0, 0.0, 0.0001, 0.0001], "nw", [-1, -1]), "0 크기 입력");

// 입력 배열은 변형되지 않습니다.
if (!close(box[0], 0.30) || !close(box[2], 0.60)) throw new Error("입력 박스가 변형됨");
console.log("OK");
"""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "resize.mjs"
            path.write_text(script, encoding="utf-8")
            finished = subprocess.run(
                [shutil.which("node"), str(path)], capture_output=True, text=True
            )
        self.assertEqual(finished.returncode, 0, finished.stderr)
        self.assertIn("OK", finished.stdout)

    @unittest.skipUnless(shutil.which("node"), "node가 없어 JS 계약 검사를 건너뜁니다")
    def test_out_of_image_points_are_rejected_before_appending(self):
        script = self._contract_source() + """
const rejected = [[-0.01, 0.5], [0.5, 1.2], [1.5, 0.5], [0.5, -0.5],
                  [NaN, 0.5], [0.5, Infinity], [-3, -3]];
const accepted = [[0, 0], [1, 1], [0.5, 0.5], [0.999, 0.001]];
for (const point of rejected) {
  if (acceptAnnotationPoint(point) !== null) {
    throw new Error("이미지 밖 좌표가 거부되지 않음: " + JSON.stringify(point));
  }
}
for (const point of accepted) {
  if (acceptAnnotationPoint(point) !== point) {
    throw new Error("이미지 안 좌표가 거부됨: " + JSON.stringify(point));
  }
}
// 가장자리로 끌어붙이지 않는지 확인합니다.
if (clamp01(-0.01) !== 0 || clamp01(1.2) !== 1) { throw new Error("clamp01 계약 위반"); }
if (acceptAnnotationPoint([-0.01, 0.5]) !== null) { throw new Error("여백 클릭이 0으로 저장됨"); }
console.log("OK");
"""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "contract.mjs"
            path.write_text(script, encoding="utf-8")
            finished = subprocess.run(
                [shutil.which("node"), str(path)], capture_output=True, text=True
            )
        self.assertEqual(finished.returncode, 0, finished.stderr)
        self.assertIn("OK", finished.stdout)


class NoStoreHeaderTest(unittest.TestCase):
    """정상 응답과 오류 응답 모두 캐시되지 않아야 합니다."""

    def test_every_response_including_errors_sets_no_store(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _project(tmp)
            client = _client(root)
            cases = [
                # (설명, 응답, 기대 상태, 기대 content type)
                ("페이지", client.get("/"), 200, "text/html"),
                ("목록", client.get("/api/images"), 200, "application/json"),
                (
                    "원본 이미지",
                    client.get("/api/image/shoe?kind=source"),
                    200,
                    "image/png",
                ),
                (
                    "주석 읽기",
                    client.get("/api/annotations/shoe"),
                    200,
                    "application/json",
                ),
                (
                    "없는 항목",
                    client.get("/api/image/absent?kind=source"),
                    404,
                    "application/json",
                ),
                (
                    "없는 판본",
                    client.get("/api/image/shoe?kind=output&version=output-9"),
                    404,
                    "application/json",
                ),
                (
                    "잘못된 kind",
                    client.get("/api/image/shoe?kind=mask"),
                    400,
                    "application/json",
                ),
                (
                    "주석 스키마 오류",
                    client.post(
                        "/api/annotations/shoe",
                        json={
                            "schema_version": 1,
                            "annotations": [dict(CONNECTION, target_box=[1.4, 0, 2, 1])],
                        },
                    ),
                    400,
                    "application/json",
                ),
                (
                    "주석 JSON 아님",
                    client.post(
                        "/api/annotations/shoe",
                        data="not json",
                        content_type="application/json",
                    ),
                    400,
                    "application/json",
                ),
                (
                    "잘못된 target_box",
                    client.post(
                        "/api/suggest-anchors/shoe",
                        json={"version": "output-5", "target_box": [0.9, 0.4, 0.2, 0.6]},
                    ),
                    400,
                    "application/json",
                ),
                (
                    "없는 채점 판본",
                    client.post("/api/score/shoe", json={"version": "output-9"}),
                    404,
                    "application/json",
                ),
                # 프레임워크가 만드는 404(라우트 없음)도 캐시되지 않습니다.
                ("없는 경로", client.get("/api/nope"), 404, "text/html"),
                (
                    "허용되지 않은 메서드",
                    client.delete("/api/annotations/shoe"),
                    405,
                    "text/html",
                ),
                (
                    "본문 초과",
                    client.post(
                        "/api/annotations/shoe",
                        json={
                            "schema_version": 1,
                            "annotations": [dict(CONNECTION, label="가" * 600_000)],
                        },
                    ),
                    413,
                    "application/json",
                ),
            ]
            for label, response, status, mimetype in cases:
                with self.subTest(case=label):
                    self.assertEqual(response.status_code, status)
                    self.assertEqual(response.mimetype, mimetype)
                    self.assertEqual(
                        response.headers.get("Cache-Control"),
                        "no-store",
                        f"{label} 응답에 no-store가 없습니다",
                    )
                    if mimetype == "application/json" and status >= 400:
                        self.assertIn("error", response.get_json())

    def test_after_request_hook_is_the_single_source_of_the_header(self):
        source = Path(create_app.__code__.co_filename).read_text(encoding="utf-8")
        self.assertIn("@app.after_request", source)
        self.assertIn('response.headers["Cache-Control"] = "no-store"', source)
        # 응답마다 헤더를 되풀이하지 않습니다.
        self.assertNotIn("NO_STORE", source)


class UiContractTest(unittest.TestCase):
    def _page(self) -> str:
        with tempfile.TemporaryDirectory() as tmp:
            root = _project(tmp)
            response = _client(root).get("/")
            self.assertEqual(response.status_code, 200)
            return response.get_data(as_text=True)

    def test_page_has_canvas_selectors_and_annotation_type_controls(self):
        page = self._page()
        self.assertEqual(page.count('id="annotation-canvas"'), 1)
        for identifier in (
            'id="item-select"',
            'id="version-select"',
            'id="image-kind-select"',
            'id="annotation-type"',
        ):
            self.assertIn(identifier, page)
        for value in ("connection", "required_path", "complete_roi"):
            self.assertIn(f'value="{value}"', page)

    def test_page_has_every_required_control(self):
        page = self._page()
        for identifier in (
            "mode-box",
            "mode-path",
            "mode-anchor",
            "mode-select",
            "mode-pan",
            "finish-path",
            "delete-selected",
            "save-annotations",
            "import-red-boxes",
            "suggest-anchors",
            "score-output",
            "zoom-in",
            "zoom-out",
            "zoom-reset",
        ):
            with self.subTest(control=identifier):
                self.assertIn(f'id="{identifier}"', page)

    def test_page_shows_status_legend(self):
        page = self._page()
        for status in ("pass", "warn", "fail", "not_scored"):
            self.assertIn(status, page)

    def test_page_defines_required_javascript_functions(self):
        page = self._page()
        for name in (
            "imageToNormalized",
            "normalizedToImage",
            "drawOverlay",
            "saveAnnotations",
            "loadScore",
        ):
            with self.subTest(function=name):
                self.assertIn(f"function {name}", page)

    def test_page_does_not_load_external_frontend_frameworks(self):
        page = self._page().lower()
        for forbidden in ("react", "vue", "streamlit", "cdn.", "https://"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, page)


if __name__ == "__main__":
    unittest.main()
