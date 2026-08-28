"""주석 스키마 검증, 사이드카 저장과 빨간 박스·끝점 후보 검출.

모든 좌표는 `[0, 1]` 정규화 좌표입니다. 검출 함수는 파일 경로가 아니라 RGB
배열을 받으므로 `metrics` 모듈과 순환 import가 생기지 않습니다. 검출 결과는
후보일 뿐이며, 사용자가 확인해 저장을 요청할 때까지 사이드카를 건드리지
않습니다.
"""

from __future__ import annotations

import json
import math
import re
import unicodedata
from pathlib import Path

import cv2
import numpy as np

SCHEMA_VERSION = 1
ANNOTATION_TYPES = {"connection", "required_path", "complete_roi"}
ANCHOR_KEYS = ("start_region", "end_region")
ALLOWED_KEYS = {"id", "type", "target_box", "anchors", "paths", "label"}

# 반전·대칭·반대쪽 비교는 설계상 만들지 않으므로 관련 키를 재귀적으로 거부합니다.
FORBIDDEN_KEY_TOKENS = (
    "mirror",
    "symmetry",
    "symmetric",
    "reflect",
    "opposite_side",
    "medial",
    "lateral",
)

_ITEM_ID_PATTERN = re.compile(r"^[A-Za-z0-9_.가-힣-]+$")

# 빨간 박스 검출
RED_MIN = 180
RED_DOMINANCE = 60
MIN_BOX_AREA_RATIO = 0.0001
MIN_SIDE_COVERAGE = 0.6
REQUIRED_COVERED_SIDES = 3

# 끝점 후보 검출
INK_MAX_VALUE = 128
CLUSTER_RATIO = 0.02
MAX_TIP_RING_COVERAGE = 0.35
MAX_RING_RADIUS = 12
MIN_COMPONENT_PIXELS = 6
MIN_LINE_ELONGATION = 4.0


class AnnotationError(ValueError):
    """주석 스키마 또는 사이드카 경로 위반."""


def _reject_forbidden_keys(value: object) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            lowered = str(key).lower()
            if any(token in lowered for token in FORBIDDEN_KEY_TOKENS):
                raise AnnotationError(f"대칭·반전 비교 필드는 지원하지 않음 ({key})")
            _reject_forbidden_keys(child)
    elif isinstance(value, list):
        for child in value:
            _reject_forbidden_keys(child)


def _finite(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AnnotationError(f"좌표가 숫자가 아님: {value!r}")
    number = float(value)
    if not math.isfinite(number):
        raise AnnotationError("좌표가 유한한 수가 아님")
    return number


def _validated_box(value: object, where: str) -> list[float]:
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        raise AnnotationError(f"{where}: 박스는 [x1, y1, x2, y2] 네 수여야 함")
    x1, y1, x2, y2 = (_finite(item) for item in value)
    for number in (x1, y1, x2, y2):
        if not 0.0 <= number <= 1.0:
            raise AnnotationError(f"{where}: 정규화 좌표가 [0, 1] 범위를 벗어남")
    if not (x1 < x2 and y1 < y2):
        raise AnnotationError(f"{where}: 박스 좌표 순서가 잘못됨")
    return [x1, y1, x2, y2]


def _validated_path(value: object, where: str) -> list[list[float]]:
    if not isinstance(value, (list, tuple)) or len(value) < 2:
        raise AnnotationError(f"{where}: 폴리라인은 점이 두 개 이상이어야 함")
    points: list[list[float]] = []
    for point in value:
        if not isinstance(point, (list, tuple)) or len(point) != 2:
            raise AnnotationError(f"{where}: 폴리라인 점은 [x, y] 형식이어야 함")
        x, y = (_finite(item) for item in point)
        if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
            raise AnnotationError(f"{where}: 정규화 좌표가 [0, 1] 범위를 벗어남")
        points.append([x, y])
    return points


def _validated_annotation(annotation: object, index: int) -> dict:
    where = f"annotations[{index}]"
    if not isinstance(annotation, dict):
        raise AnnotationError(f"{where}: 주석이 객체가 아님")
    _reject_forbidden_keys(annotation)

    unknown = set(annotation) - ALLOWED_KEYS
    if unknown:
        raise AnnotationError(f"{where}: 지원하지 않는 필드 {sorted(unknown)}")

    annotation_id = annotation.get("id")
    if not isinstance(annotation_id, str) or not annotation_id.strip():
        raise AnnotationError(f"{where}: id가 없음")
    annotation_type = annotation.get("type")
    if annotation_type not in ANNOTATION_TYPES:
        raise AnnotationError(f"{where}: 알 수 없는 주석 종류 ({annotation_type})")

    validated = {
        "id": annotation_id,
        "type": annotation_type,
        "target_box": _validated_box(annotation.get("target_box"), f"{where}.target_box"),
    }
    if "label" in annotation:
        label = annotation["label"]
        if not isinstance(label, str):
            raise AnnotationError(f"{where}: label은 문자열이어야 함")
        validated["label"] = label

    if annotation_type == "connection":
        anchors = annotation.get("anchors")
        if not isinstance(anchors, dict) or set(anchors) != set(ANCHOR_KEYS):
            raise AnnotationError(
                f"{where}: connection은 start_region과 end_region 두 앵커만 가져야 함"
            )
        validated["anchors"] = {
            key: _validated_box(anchors[key], f"{where}.anchors.{key}")
            for key in ANCHOR_KEYS
        }
        if "paths" in annotation:
            raise AnnotationError(f"{where}: connection은 paths를 갖지 않음")
    else:
        paths = annotation.get("paths")
        if not isinstance(paths, list) or not paths:
            raise AnnotationError(f"{where}: {annotation_type}은 폴리라인이 하나 이상 필요함")
        validated["paths"] = [
            _validated_path(path, f"{where}.paths[{position}]")
            for position, path in enumerate(paths)
        ]
        if "anchors" in annotation:
            raise AnnotationError(f"{where}: {annotation_type}은 anchors를 갖지 않음")

    return validated


def validate_annotation_document(document: dict) -> dict:
    """주석 문서를 검증하고 정규화된 사본을 돌려줍니다."""
    if not isinstance(document, dict):
        raise AnnotationError("주석 문서가 객체가 아님")
    if document.get("schema_version") != SCHEMA_VERSION:
        raise AnnotationError(
            f"지원하지 않는 주석 schema_version: {document.get('schema_version')}"
        )
    annotations = document.get("annotations")
    if not isinstance(annotations, list):
        raise AnnotationError("annotations가 배열이 아님")

    validated = []
    seen: set[str] = set()
    for index, annotation in enumerate(annotations):
        item = _validated_annotation(annotation, index)
        if item["id"] in seen:
            raise AnnotationError(f"주석 id가 중복됨: {item['id']}")
        seen.add(item["id"])
        validated.append(item)
    return {"schema_version": SCHEMA_VERSION, "annotations": validated}


def annotation_path(annotation_root: Path, item_id: str) -> Path:
    """사이드카 경로를 계산합니다. item_id는 주석 루트를 벗어날 수 없습니다.

    이름 검사만으로는 부족합니다. 사이드카 파일 자체가 외부 파일을 가리키는
    심볼릭 링크이거나 상위 디렉터리가 외부로 연결된 링크일 수 있으므로 실제
    경로를 해석해 주석 루트 안인지 확인합니다.
    """
    if not isinstance(item_id, str):
        raise AnnotationError("item_id가 문자열이 아님")
    normalized = unicodedata.normalize("NFC", item_id)
    if normalized in {".", ".."} or not _ITEM_ID_PATTERN.match(normalized):
        raise AnnotationError(f"허용되지 않는 item_id: {item_id!r}")
    root = Path(annotation_root)
    if root.is_symlink():
        # 주석 루트 자체가 링크면 그 아래 모든 경로가 밖으로 나갑니다.
        raise AnnotationError(f"주석 루트가 심볼릭 링크임: {root}")
    candidate = root / f"{normalized}.json"
    if not candidate.resolve().is_relative_to(root.resolve()):
        raise AnnotationError(f"주석 경로가 주석 루트를 벗어남: {candidate}")
    return candidate


def load_annotations(annotation_root: Path, item_id: str) -> dict:
    """사이드카를 읽습니다. 파일이 없으면 빈 문서를 돌려줍니다."""
    path = annotation_path(annotation_root, item_id)
    if not path.is_file():
        return {"schema_version": SCHEMA_VERSION, "annotations": []}
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AnnotationError(f"주석 파일을 읽을 수 없음: {path}") from exc
    return validate_annotation_document(document)


def save_annotations(annotation_root: Path, item_id: str, document: dict) -> Path:
    """검증을 통과한 문서만 원자적으로 저장합니다."""
    path = annotation_path(annotation_root, item_id)
    validated = validate_annotation_document(document)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(validated, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    try:
        temporary.replace(path)
    except OSError:
        temporary.unlink(missing_ok=True)
        raise
    return path


def _as_rgb(rgb: np.ndarray) -> np.ndarray:
    array = np.asarray(rgb)
    if array.ndim != 3 or array.shape[2] != 3:
        raise AnnotationError("RGB 배열이 아님")
    return array


def _covered_sides(mask: np.ndarray) -> int:
    height, width = mask.shape
    band = max(2, int(math.ceil(0.05 * min(height, width))))
    coverages = (
        mask[:band, :].any(axis=0).mean(),
        mask[max(height - band, 0) :, :].any(axis=0).mean(),
        mask[:, :band].any(axis=1).mean(),
        mask[:, max(width - band, 0) :].any(axis=1).mean(),
    )
    return sum(1 for value in coverages if value >= MIN_SIDE_COVERAGE)


def _merge_overlapping(rects: list[list[int]]) -> list[list[int]]:
    merged = [list(rect) for rect in rects]
    changed = True
    while changed:
        changed = False
        for i in range(len(merged)):
            for j in range(i + 1, len(merged)):
                a, b = merged[i], merged[j]
                if a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]:
                    merged[i] = [
                        min(a[0], b[0]),
                        min(a[1], b[1]),
                        max(a[2], b[2]),
                        max(a[3], b[3]),
                    ]
                    del merged[j]
                    changed = True
                    break
            if changed:
                break
    return merged


def detect_red_boxes(rgb: np.ndarray) -> list[list[float]]:
    """합성된 빨간 사각형 후보를 정규화 좌표로 돌려줍니다(저장하지 않음)."""
    array = _as_rgb(rgb)
    height, width = array.shape[:2]
    channels = array.astype(np.int16)
    red = (
        (channels[:, :, 0] >= RED_MIN)
        & (channels[:, :, 0] >= channels[:, :, 1] + RED_DOMINANCE)
        & (channels[:, :, 0] >= channels[:, :, 2] + RED_DOMINANCE)
    ).astype(np.uint8)

    count, labels, stats, _ = cv2.connectedComponentsWithStats(red, connectivity=8)
    minimum_area = max(1.0, MIN_BOX_AREA_RATIO * height * width)
    rects: list[list[int]] = []
    for index in range(1, count):
        x, y, box_width, box_height, area = stats[index]
        if area < minimum_area:
            continue
        component = labels[y : y + box_height, x : x + box_width] == index
        # 사각형 테두리는 최소 세 변에 빨간 픽셀이 이어져 있습니다. 둥근 로고
        # 같은 덩어리는 이 조건에서 걸러집니다.
        if _covered_sides(component) < REQUIRED_COVERED_SIDES:
            continue
        rects.append([int(x), int(y), int(x + box_width), int(y + box_height)])

    boxes = [
        [x1 / width, y1 / height, x2 / width, y2 / height]
        for x1, y1, x2, y2 in _merge_overlapping(rects)
    ]
    boxes.sort(key=lambda box: (box[1], box[0]))
    return boxes


def _box_to_pixels(box: list[float], width: int, height: int) -> tuple[int, int, int, int]:
    x1 = max(0, min(width - 1, int(round(box[0] * width))))
    y1 = max(0, min(height - 1, int(round(box[1] * height))))
    x2 = max(x1 + 1, min(width, int(round(box[2] * width))))
    y2 = max(y1 + 1, min(height, int(round(box[3] * height))))
    return x1, y1, x2, y2


def _ring_offsets(radius: int) -> list[tuple[int, int]]:
    """반지름 `radius`인 원 위의 이웃 좌표를 각도 순서로 돌려줍니다."""
    offsets: list[tuple[int, int]] = []
    steps = max(8, int(round(2 * math.pi * radius)))
    for step in range(steps):
        angle = 2 * math.pi * step / steps
        offset = (
            int(round(radius * math.cos(angle))),
            int(round(radius * math.sin(angle))),
        )
        if offset not in offsets:
            offsets.append(offset)
    return offsets


def _stroke_half_width(ink: np.ndarray) -> float:
    # 잉크가 크롭 경계에 닿아 있으면 거리 변환이 배경을 찾지 못하므로 0 테두리를
    # 한 픽셀 덧붙인 뒤 계산합니다.
    padded = np.pad(ink, 1)
    distances = cv2.distanceTransform(padded, cv2.DIST_L2, 3)[1:-1, 1:-1]
    return max(1.0, float(np.percentile(distances[ink > 0], 90)))


def _tip_mask(ink: np.ndarray, radius: int) -> np.ndarray:
    """선 끝(팁) 픽셀을 국소 이웃 개수로 찾습니다.

    3x3 8-이웃 개수는 굵기 1px 선에서만 통하므로 같은 원리를 반지름 `radius`의
    링으로 확장했습니다. 링에서 잉크가 이어진 구간(호)이 하나면 선이 한쪽으로만
    뻗은 끝이고, 둘이면 선 내부, 셋 이상이면 갈림점(T자 교차)입니다. 굵은 덩어리
    가장자리도 호가 하나이므로 링에서 잉크가 차지하는 비율까지 함께 제한합니다.
    닫힘·팽창·세선화 없이 원본 잉크 픽셀만 읽습니다.
    """
    height, width = ink.shape
    offsets = _ring_offsets(radius)
    padded = np.pad(ink.astype(bool), radius)
    ring = np.stack(
        [
            padded[radius + dy : radius + dy + height, radius + dx : radius + dx + width]
            for dx, dy in offsets
        ]
    )
    arcs = (ring & ~np.roll(ring, 1, axis=0)).sum(axis=0)
    coverage = ring.sum(axis=0) / len(offsets)
    return (ink > 0) & (arcs == 1) & (coverage <= MAX_TIP_RING_COVERAGE)


def suggest_connection_anchors(
    rgb: np.ndarray, target_box: list[float]
) -> list[list[float]]:
    """끊긴 선의 양쪽 끝 후보가 정확히 두 개일 때만 앵커 박스를 제안합니다."""
    array = _as_rgb(rgb)
    box = _validated_box(target_box, "target_box")
    height, width = array.shape[:2]
    x1, y1, x2, y2 = _box_to_pixels(box, width, height)
    roi = array[y1:y2, x1:x2]
    if roi.size == 0:
        return []

    gray = cv2.cvtColor(roi.astype(np.uint8), cv2.COLOR_RGB2GRAY)
    ink = (gray <= INK_MAX_VALUE).astype(np.uint8)
    if not ink.any():
        return []

    roi_height, roi_width = ink.shape
    diagonal = math.hypot(roi_width, roi_height)

    # 성분마다 자기 굵기에 맞는 링 반지름을 씁니다. 다른 성분의 잉크는 보지
    # 않으므로 근처의 무관한 선이 끝점을 가리지 않습니다.
    count, labels = cv2.connectedComponents(ink, connectivity=8)
    tips = np.zeros(ink.shape, dtype=bool)
    ring_radius = 3
    for index in range(1, count):
        ys, xs = np.nonzero(labels == index)
        if xs.size < MIN_COMPONENT_PIXELS:
            continue
        top, bottom, left, right = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
        component = (labels[top:bottom, left:right] == index).astype(np.uint8)
        half_width = _stroke_half_width(component)
        if max(bottom - top, right - left) < MIN_LINE_ELONGATION * 2.0 * half_width:
            # 자기 굵기에 비해 짧은 성분(넓은 검정 면, 점)은 재단선이 아니므로
            # 끝점을 찾지 않습니다. 면 채움은 별도 지표가 측정합니다.
            continue
        radius = int(min(max(3.0, 2.0 * half_width + 2.0), MAX_RING_RADIUS))
        tips[top:bottom, left:right] |= _tip_mask(component, radius)
        ring_radius = max(ring_radius, radius)

    if not tips.any():
        return []

    # 링 반지름 안쪽 끝은 ROI를 자른 자리이므로 실제 선 끝으로 보지 않습니다.
    margin = max(float(ring_radius), CLUSTER_RATIO * diagonal)
    tolerance = max(2.0 * ring_radius, CLUSTER_RATIO * diagonal)

    count, _, stats, centroids = cv2.connectedComponentsWithStats(
        tips.astype(np.uint8), connectivity=8
    )
    clusters: list[dict] = []
    for index in range(1, count):
        x, y, box_width, box_height, _ = stats[index]
        center = (float(centroids[index][0]), float(centroids[index][1]))
        if (
            center[0] <= margin
            or center[1] <= margin
            or center[0] >= roi_width - 1 - margin
            or center[1] >= roi_height - 1 - margin
        ):
            continue
        clusters.append(
            {
                "center": center,
                "box": [int(x), int(y), int(x + box_width), int(y + box_height)],
            }
        )

    # 같은 팁에서 갈라진 조각은 하나로 묶습니다.
    merged: list[dict] = []
    for cluster in clusters:
        for other in merged:
            if math.dist(cluster["center"], other["center"]) <= tolerance:
                other["box"] = [
                    min(other["box"][0], cluster["box"][0]),
                    min(other["box"][1], cluster["box"][1]),
                    max(other["box"][2], cluster["box"][2]),
                    max(other["box"][3], cluster["box"][3]),
                ]
                other["center"] = (
                    (other["center"][0] + cluster["center"][0]) / 2,
                    (other["center"][1] + cluster["center"][1]) / 2,
                )
                break
        else:
            merged.append(cluster)

    if len(merged) != 2:
        return []

    pad = float(ring_radius)
    anchors = []
    for cluster in merged:
        box_x1, box_y1, box_x2, box_y2 = cluster["box"]
        anchors.append(
            [
                max(0.0, (x1 + box_x1 - pad) / width),
                max(0.0, (y1 + box_y1 - pad) / height),
                min(1.0, (x1 + box_x2 + pad) / width),
                min(1.0, (y1 + box_y2 + pad) / height),
            ]
        )
    anchors.sort(key=lambda item: (item[0], item[1]))
    return anchors
