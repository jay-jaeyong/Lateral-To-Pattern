"""결정론적 진단 지표.

모든 계산은 메모리에서만 일어납니다. 어떤 함수도 이미지를 저장하거나 수정하지
않고, 지표를 하나의 총점으로 합치지 않습니다. 각 지표는 수치, 상태, 신뢰도와
필요하면 `not_scored` 사유를 독립적으로 돌려줍니다.

사람이 승인한 정상 사례가 없는 지표(실루엣 IoU, 흐린 획, 주석 기반 지표)는
수치와 신뢰도만 기록하고 상태는 `not_scored`로 둡니다.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType

import cv2
import numpy as np

STATUSES = ("pass", "warn", "fail", "not_scored")
UNCALIBRATED_REASON = "정상 사례 기반 문턱 미확정"
LOW_SEPARATION_REASON = "원단과 배경의 색차가 분리 기준보다 작음"

# 스케치 출력에서 잉크로 볼 밝기 상한(비백색).
NONWHITE_MAX = 240
# 실루엣 마스크에서 무시할 잡티 성분 크기(전체 대비).
MIN_COMPONENT_AREA_RATIO = 0.0005
# 전경 면적이 이 범위를 벗어나면 배경 추정이 실패한 것으로 봅니다.
PLAUSIBLE_AREA_MIN = 0.02
PLAUSIBLE_AREA_MAX = 0.85
# 앵커에서 잉크를 신뢰성 있게 찾았다고 볼 최소·충분 픽셀 수.
MIN_ANCHOR_INK_PIXELS = 2
CONFIDENT_ANCHOR_INK_PIXELS = 8
# 기대 폴리라인이 이보다 짧으면 위치 오차 통계를 신뢰하지 않습니다.
CONFIDENT_EXPECTED_PATH_PIXELS = 20
MISSING_ANCHOR_REASON = "앵커 영역에서 잉크를 신뢰성 있게 찾지 못함"
LOW_ANCHOR_EVIDENCE_REASON = "앵커 잉크가 적어 연결 여부를 단정할 수 없음"


class ImageDecodeError(ValueError):
    """이미지 바이트를 디코드할 수 없음."""


def _frozen(value: object) -> object:
    """중첩 구조까지 읽기 전용으로 바꿔 결과가 나중에 변형되지 않게 합니다."""
    if isinstance(value, Mapping):
        return MappingProxyType({key: _frozen(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_frozen(item) for item in value)
    return value


def _thawed(value: object) -> object:
    """JSON으로 직렬화할 수 있는 새 가변 사본을 만듭니다."""
    if isinstance(value, Mapping):
        return {key: _thawed(item) for key, item in value.items()}
    if isinstance(value, tuple) or (
        isinstance(value, Sequence) and not isinstance(value, (str, bytes))
    ):
        return [_thawed(item) for item in value]
    return value


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
    # 원본 전경 분리에 쓰는 Lab 거리 문턱(OpenCV 8비트 Lab 스케일).
    silhouette_lab_distance: float = 18.0
    # 주석 지표에서 재단선 잉크로 볼 밝기 상한.
    ink_max_value: int = 128
    # 연결 판정을 확정하는 최소 신뢰도. 앵커 잉크가 이보다 적으면 연결·단절을
    # 단정하지 않고 진단값만 남깁니다(기본 0.5 = 앵커마다 잉크 4픽셀).
    connection_min_confidence: float = 0.5
    path_tolerance_px: int = 5


@dataclass(frozen=True)
class MetricResult:
    score: bool | float | dict | None
    status: str
    confidence: float
    reason: str | None = None
    details: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.status not in STATUSES:
            raise ValueError(f"알 수 없는 지표 상태: {self.status}")
        clamped = min(1.0, max(0.0, float(self.confidence)))
        object.__setattr__(self, "confidence", clamped)
        if self.status == "not_scored" and not self.reason:
            raise ValueError("not_scored 지표에는 사유가 필요함")
        # 호출자가 넘긴 dict를 나중에 바꿔도 결과가 흔들리지 않도록 방어적으로
        # 복사한 뒤 중첩 구조까지 읽기 전용으로 고정합니다.
        object.__setattr__(self, "score", _frozen(self.score))
        object.__setattr__(self, "details", _frozen(self.details or {}))

    @classmethod
    def not_scored(
        cls, reason: str, confidence: float = 0.0, **details: object
    ) -> "MetricResult":
        return cls(None, "not_scored", confidence, reason, dict(details))

    @classmethod
    def graded(
        cls,
        status: str,
        raw_score: float,
        *,
        confidence: float = 1.0,
        reason: str | None = None,
        **details: object,
    ) -> "MetricResult":
        payload = {"raw_score": float(raw_score)}
        payload.update(details)
        return cls(float(raw_score), status, confidence, reason, payload)

    def to_dict(self) -> dict:
        """JSON으로 직렬화할 수 있는 새 가변 사본(호출마다 독립)."""
        return {
            "score": _thawed(self.score),
            "status": self.status,
            "confidence": self.confidence,
            "reason": self.reason,
            "details": _thawed(self.details),
        }


def _metric_not_calibrated(
    raw_score: float, confidence: float, **details: object
) -> MetricResult:
    """수치와 신뢰도만 기록하고 상태는 미채점으로 남기는 지표."""
    payload = {"raw_score": float(raw_score)}
    payload.update(details)
    return MetricResult(None, "not_scored", confidence, UNCALIBRATED_REASON, payload)


def safe_metric(function, *args, **kwargs) -> MetricResult:
    """지표 하나가 실패해도 다른 지표와 항목을 중단시키지 않습니다."""
    try:
        return function(*args, **kwargs)
    except Exception as exc:  # noqa: BLE001 - 지표별 실패 격리가 목적
        return MetricResult.not_scored(f"지표 계산 실패: {exc}", 0.0)


def load_rgb(path: Path) -> np.ndarray:
    """파일 확장자가 아니라 실제 바이트를 디코드합니다."""
    path = Path(path)
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ImageDecodeError(f"이미지를 읽을 수 없음: {path}") from exc
    data = np.frombuffer(raw, dtype=np.uint8)
    bgr = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if bgr is None:
        raise ImageDecodeError(f"이미지를 디코드할 수 없음: {path}")
    return cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)


def _banded_status(value: float, pass_max: float, warn_max: float) -> str:
    if value <= pass_max:
        return "pass"
    if value <= warn_max:
        return "warn"
    return "fail"


def _gray(rgb: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(np.ascontiguousarray(rgb, dtype=np.uint8), cv2.COLOR_RGB2GRAY)


def _clamp_unit(value: float) -> float:
    return min(1.0, max(0.0, float(value)))


def score_aspect_ratio(
    output_rgb: np.ndarray, expected_ratio: str, config: ScoringConfig
) -> MetricResult:
    height, width = output_rgb.shape[:2]
    parts = str(expected_ratio).split(":")
    if len(parts) != 2:
        return MetricResult.not_scored(f"기대 화면비 형식이 잘못됨: {expected_ratio}", 0.0)
    expected = float(parts[0]) / float(parts[1])
    actual = width / height
    relative_error = abs(actual - expected) / expected
    details = {
        "expected_ratio": str(expected_ratio),
        "expected": expected,
        "actual": actual,
        "width": int(width),
        "height": int(height),
    }
    if (expected < 1.0) != (actual < 1.0) and expected != 1.0 and actual != 1.0:
        return MetricResult.graded(
            "fail",
            relative_error,
            reason=f"기대 방향과 실제 방향이 다름 (기대 {expected:.3f}, 실제 {actual:.3f})",
            **details,
        )
    status = _banded_status(
        relative_error,
        config.aspect_pass_relative_error,
        config.aspect_warn_relative_error,
    )
    reason = None if status == "pass" else f"화면비 상대 편차 {relative_error:.3f}"
    return MetricResult.graded(status, relative_error, reason=reason, **details)


def score_colored_pixels(
    output_rgb: np.ndarray, config: ScoringConfig
) -> MetricResult:
    channels = output_rgb.astype(np.int16)
    chroma = channels.max(axis=2) - channels.min(axis=2)
    colored = chroma > config.chroma_threshold
    ratio = float(colored.mean())
    status = _banded_status(ratio, config.chroma_pass_ratio, config.chroma_warn_ratio)
    return MetricResult.graded(
        status,
        ratio,
        reason=None if status == "pass" else f"유채색 픽셀 비율 {ratio:.5f}",
        colored_pixels=int(colored.sum()),
        total_pixels=int(colored.size),
        chroma_threshold=config.chroma_threshold,
    )


def score_black_fill(output_rgb: np.ndarray, config: ScoringConfig) -> MetricResult:
    gray = _gray(output_rgb)
    dark = (gray <= config.dark_threshold).astype(np.uint8)
    if not dark.any():
        return MetricResult.graded("pass", 0.0, deep_pixels=0, total_pixels=int(dark.size))
    # 0 테두리를 덧붙여 경계에 닿은 어두운 영역도 밝은 픽셀까지의 거리를 갖게 합니다.
    padded = np.pad(dark, 1)
    distances = cv2.distanceTransform(padded, cv2.DIST_L2, 3)[1:-1, 1:-1]
    deep = distances > config.fill_half_width_px
    ratio = float(deep.mean())
    status = _banded_status(ratio, config.fill_pass_ratio, config.fill_warn_ratio)
    return MetricResult.graded(
        status,
        ratio,
        reason=None if status == "pass" else f"선 굵기보다 넓은 검정 내부 비율 {ratio:.5f}",
        deep_pixels=int(deep.sum()),
        total_pixels=int(deep.size),
        fill_half_width_px=config.fill_half_width_px,
    )


def score_faint_strokes(output_rgb: np.ndarray, config: ScoringConfig) -> MetricResult:
    gray = _gray(output_rgb)
    candidate = (gray >= config.faint_low) & (gray <= config.faint_high)
    # 5x5 국소 최소값. 회색 픽셀 주변에 검은 중심선이 있으면 안티앨리어싱이므로
    # 흐린 획으로 세지 않습니다.
    local_minimum = cv2.erode(gray, np.ones((5, 5), np.uint8))
    faint = candidate & (local_minimum > config.faint_dark_core)
    ratio = float(faint.mean())
    return _metric_not_calibrated(
        ratio,
        1.0,
        faint_pixels=int(faint.sum()),
        candidate_pixels=int(candidate.sum()),
        total_pixels=int(faint.size),
    )


def _keep_meaningful_components(mask: np.ndarray) -> np.ndarray:
    """의미 있는 성분을 모두 유지합니다(패턴은 조각이 여러 개입니다)."""
    count, labels, stats, _ = cv2.connectedComponentsWithStats(
        mask.astype(np.uint8), connectivity=8
    )
    minimum_area = MIN_COMPONENT_AREA_RATIO * mask.size
    kept = np.zeros(mask.shape, dtype=bool)
    for index in range(1, count):
        if stats[index, cv2.CC_STAT_AREA] >= minimum_area:
            kept |= labels == index
    return kept


def _source_foreground(
    source_rgb: np.ndarray, config: ScoringConfig
) -> tuple[np.ndarray, float]:
    """테두리에서 배경을 추정해 원본 전경 마스크와 신뢰도를 계산합니다."""
    lab = cv2.cvtColor(
        np.ascontiguousarray(source_rgb, dtype=np.uint8), cv2.COLOR_RGB2LAB
    ).astype(np.float32)
    height, width = lab.shape[:2]
    band = max(2, int(round(0.04 * min(height, width))))
    border = np.concatenate(
        [
            lab[:band, :].reshape(-1, 3),
            lab[-band:, :].reshape(-1, 3),
            lab[:, :band].reshape(-1, 3),
            lab[:, -band:].reshape(-1, 3),
        ]
    )
    background = np.median(border, axis=0)
    distances = np.linalg.norm(lab - background, axis=2)
    threshold = float(config.silhouette_lab_distance)

    border_distances = np.linalg.norm(border - background, axis=1)
    border_spread = float(np.percentile(border_distances, 90))
    border_stability = _clamp_unit(1.0 - border_spread / threshold)

    mask = _keep_meaningful_components(distances > threshold)
    area_ratio = float(mask.mean())
    if mask.any():
        separation = _clamp_unit(
            (float(np.median(distances[mask])) - threshold) / threshold
        )
    else:
        separation = 0.0

    if area_ratio <= 0.0:
        area_plausibility = 0.0
    elif area_ratio < PLAUSIBLE_AREA_MIN:
        area_plausibility = area_ratio / PLAUSIBLE_AREA_MIN
    elif area_ratio <= PLAUSIBLE_AREA_MAX:
        area_plausibility = 1.0
    else:
        area_plausibility = _clamp_unit((0.98 - area_ratio) / (0.98 - PLAUSIBLE_AREA_MAX))

    confidence = min(border_stability, separation, area_plausibility)
    return mask, confidence


def _output_silhouette(output_rgb: np.ndarray) -> np.ndarray:
    """스케치의 비백색 잉크 외곽선을 채워 조각 실루엣을 만듭니다(이 지표 전용)."""
    ink = (_gray(output_rgb) < NONWHITE_MAX).astype(np.uint8)
    contours, _ = cv2.findContours(ink, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    mask = np.zeros(ink.shape, dtype=np.uint8)
    if contours:
        cv2.drawContours(mask, contours, -1, 1, thickness=cv2.FILLED)
    return mask.astype(bool)


def _to_canvas(mask: np.ndarray, config: ScoringConfig) -> np.ndarray:
    """비교 계산을 위해서만 메모리에서 공통 정규화 캔버스로 축소합니다."""
    resized = cv2.resize(
        mask.astype(np.uint8),
        (config.canvas_width, config.canvas_height),
        interpolation=cv2.INTER_NEAREST,
    )
    return resized.astype(bool)


def score_silhouette(
    source_rgb: np.ndarray, output_rgb: np.ndarray, config: ScoringConfig
) -> MetricResult:
    source_mask, confidence = _source_foreground(source_rgb, config)
    if confidence < config.silhouette_min_confidence:
        return MetricResult.not_scored(
            LOW_SEPARATION_REASON,
            confidence,
            source_area_ratio=float(source_mask.mean()),
        )

    source_canvas = _to_canvas(source_mask, config)
    output_canvas = _to_canvas(_output_silhouette(output_rgb), config)
    union = int(np.logical_or(source_canvas, output_canvas).sum())
    if union == 0:
        return MetricResult.not_scored("원본과 출력에서 전경을 찾지 못함", 0.0)
    intersection = int(np.logical_and(source_canvas, output_canvas).sum())
    iou = intersection / union
    # 평행 이동·회전·반전·워핑 없이 정규화 좌표를 그대로 비교합니다.
    return _metric_not_calibrated(
        iou,
        confidence,
        intersection_pixels=intersection,
        union_pixels=union,
        source_area_ratio=float(source_canvas.mean()),
        output_area_ratio=float(output_canvas.mean()),
    )


def _normalized_box_to_pixels(
    box: Sequence[float], width: int, height: int
) -> tuple[int, int, int, int]:
    x1 = max(0, min(width - 1, int(round(float(box[0]) * width))))
    y1 = max(0, min(height - 1, int(round(float(box[1]) * height))))
    x2 = max(x1 + 1, min(width, int(round(float(box[2]) * width))))
    y2 = max(y1 + 1, min(height, int(round(float(box[3]) * height))))
    return x1, y1, x2, y2


def _ink_mask(rgb: np.ndarray, config: ScoringConfig) -> np.ndarray:
    return _gray(rgb) <= config.ink_max_value


def _rasterize_paths(
    paths: Sequence[Sequence[Sequence[float]]],
    width: int,
    height: int,
    thickness: int = 1,
) -> np.ndarray:
    """정규화 폴리라인을 출력 원본 해상도 캔버스에 그립니다(메모리 전용)."""
    mask = np.zeros((height, width), dtype=np.uint8)
    for path in paths:
        points = np.array(
            [[int(round(float(x) * width)), int(round(float(y) * height))] for x, y in path],
            dtype=np.int32,
        )
        if len(points) >= 2:
            cv2.polylines(mask, [points], False, 1, thickness=thickness)
    return mask.astype(bool)


def _anchor_component(
    labels: np.ndarray,
    anchor_box: Sequence[float],
    roi: tuple[int, int, int, int],
    width: int,
    height: int,
) -> tuple[int, int] | None:
    """앵커 영역의 지배 성분과 **그 성분의** 픽셀 수를 돌려줍니다.

    성분 목록이 아니라 지배 성분만 돌려줍니다. 앵커에 살짝 걸친 무관한 성분이
    양쪽 앵커에 모두 나타나도 연결로 판정하지 않기 위함입니다.

    픽셀 수도 앵커 전체 잉크가 아니라 지배 성분의 잉크만 셉니다. 앵커에 흩어진
    잡티까지 더하면 실제 재단선 후보의 근거가 실제보다 커 보이기 때문입니다.
    """
    x1, y1, x2, y2 = roi
    ax1, ay1, ax2, ay2 = _normalized_box_to_pixels(anchor_box, width, height)
    left, top = max(ax1 - x1, 0), max(ay1 - y1, 0)
    right, bottom = min(ax2 - x1, x2 - x1), min(ay2 - y1, y2 - y1)
    if right <= left or bottom <= top:
        return None
    window = labels[top:bottom, left:right]
    ids, counts = np.unique(window[window > 0], return_counts=True)
    if ids.size == 0 or int(counts.max()) < MIN_ANCHOR_INK_PIXELS:
        return None
    strongest = int(counts.argmax())
    return int(ids[strongest]), int(counts[strongest])


def score_connection(
    output_rgb: np.ndarray, annotation: dict, config: ScoringConfig
) -> MetricResult:
    """같은 재단선의 양쪽 앵커가 하나의 잉크 성분으로 이어지는지 검사합니다.

    연결 판정은 각 앵커에서 독립적으로 고른 지배 성분이 같은 성분인지로만
    결정합니다. 성분 목록의 교집합을 쓰면 앵커에 몇 픽셀 걸친 무관한 성분이
    양쪽에 나타나기만 해도 연결로 판정되기 때문입니다. 대신 지배 성분이
    실제 재단선이 아니면 연결된 선을 `fail`로 볼 수 있는데, 조용히 통과시키는
    것보다 사람이 확인하도록 시끄럽게 실패하는 편이 안전합니다.

    단절 거리는 흰 끊김을 진단하기 위한 추정값이며 이미지를 잇거나 고치지
    않습니다. 정규화 좌표를 출력 원본 해상도에 그대로 얹고 이동·반전·워핑을
    하지 않습니다.
    """
    height, width = output_rgb.shape[:2]
    roi = _normalized_box_to_pixels(annotation["target_box"], width, height)
    x1, y1, x2, y2 = roi
    diagonal = float(np.hypot(x2 - x1, y2 - y1))
    ink = _ink_mask(output_rgb, config)[y1:y2, x1:x2]
    _, labels = cv2.connectedComponents(ink.astype(np.uint8), connectivity=8)

    anchors = annotation.get("anchors") or {}
    found = {}
    for key in ("start_region", "end_region"):
        if key not in anchors:
            return MetricResult.not_scored(f"앵커 {key}가 없음", 0.0)
        picked = _anchor_component(labels, anchors[key], roi, width, height)
        if picked is None:
            return MetricResult.not_scored(
                MISSING_ANCHOR_REASON, 0.0, missing_anchor=key
            )
        found[key] = picked

    start_dominant, start_ink = found["start_region"]
    end_dominant, end_ink = found["end_region"]
    # 근거는 지배 성분의 잉크만 씁니다. 앵커에 흩어진 잡티는 재단선 후보의
    # 근거가 아니므로 신뢰도를 부풀리지 않습니다.
    dominant_ink = min(start_ink, end_ink)
    confidence = _clamp_unit(dominant_ink / CONFIDENT_ANCHOR_INK_PIXELS)

    connected = start_dominant == end_dominant
    if connected:
        gap = 0.0
    else:
        # 지배 성분만 비교하므로 근처의 무관한 선이 앵커 성분을 대신하지 않습니다.
        away_from_start = (labels != start_dominant).astype(np.uint8)
        distances = cv2.distanceTransform(
            away_from_start, cv2.DIST_L2, cv2.DIST_MASK_PRECISE
        )
        gap = float(distances[labels == end_dominant].min())
    normalized = gap / diagonal if diagonal else 0.0
    details = {
        "start_component_ink": start_ink,
        "end_component_ink": end_ink,
        "roi_diagonal_px": diagonal,
        "start_component": start_dominant,
        "end_component": end_dominant,
        "connected": connected,
        "gap_pixels": gap,
        "gap_normalized": normalized,
        "raw_score": normalized,
    }

    if confidence < config.connection_min_confidence:
        # 앵커 잉크가 적으면 연결과 단절 어느 쪽도 단정하지 않습니다. 판정만
        # 보류하고 성분·단절 진단값은 그대로 남겨 사람이 확인할 수 있게 합니다.
        return MetricResult.not_scored(
            f"{LOW_ANCHOR_EVIDENCE_REASON} (앵커 지배 성분 잉크 {dominant_ink}픽셀, "
            f"신뢰도 {confidence:.2f})",
            confidence,
            **details,
        )

    if connected:
        return MetricResult(True, "pass", confidence, None, details)
    return MetricResult(
        False,
        "fail",
        confidence,
        f"두 앵커가 같은 잉크 성분이 아니며 최소 단절 {gap:.1f}px",
        details,
    )


def _expected_path_errors(
    output_rgb: np.ndarray, annotation: dict, config: ScoringConfig
) -> dict | None:
    """기대 폴리라인 픽셀에서 출력 잉크까지의 거리를 ROI 원본 해상도로 측정합니다."""
    height, width = output_rgb.shape[:2]
    x1, y1, x2, y2 = _normalized_box_to_pixels(annotation["target_box"], width, height)
    expected = _rasterize_paths(annotation.get("paths") or [], width, height)[
        y1:y2, x1:x2
    ]
    expected_pixels = int(expected.sum())
    if expected_pixels == 0:
        return None
    ink = _ink_mask(output_rgb, config)[y1:y2, x1:x2]
    diagonal = float(np.hypot(x2 - x1, y2 - y1))
    if ink.any():
        distances = cv2.distanceTransform(
            (~ink).astype(np.uint8), cv2.DIST_L2, cv2.DIST_MASK_PRECISE
        )
        errors = distances[expected]
    else:
        # 잉크가 전혀 없으면 거리 변환이 성립하지 않으므로 ROI 대각선으로 채웁니다.
        errors = np.full(expected_pixels, diagonal, dtype=np.float32)
    return {
        "expected": expected,
        "ink": ink,
        "errors": errors,
        "diagonal": diagonal,
        "expected_pixels": expected_pixels,
    }


def _path_statistics(measured: dict, config: ScoringConfig) -> tuple[float, dict, float]:
    errors = measured["errors"]
    detection_ratio = float((errors <= config.path_tolerance_px).mean())
    statistics = {
        "detection_ratio": detection_ratio,
        "median_error_px": float(np.median(errors)),
        "p95_error_px": float(np.percentile(errors, 95)),
        "expected_pixels": measured["expected_pixels"],
    }
    confidence = _clamp_unit(
        measured["expected_pixels"] / CONFIDENT_EXPECTED_PATH_PIXELS
    )
    return detection_ratio, statistics, confidence


def score_required_path(
    output_rgb: np.ndarray, annotation: dict, config: ScoringConfig
) -> MetricResult:
    """기대 경계의 검출률과 위치 오차만 측정합니다(박스 안 다른 선은 무시)."""
    measured = _expected_path_errors(output_rgb, annotation, config)
    if measured is None:
        return MetricResult.not_scored("기대 경계가 검사 영역 안에 없음", 0.0)
    detection_ratio, statistics, confidence = _path_statistics(measured, config)
    return _metric_not_calibrated(detection_ratio, confidence, **statistics)


def score_complete_roi(
    output_rgb: np.ndarray, annotation: dict, config: ScoringConfig
) -> MetricResult:
    """누락 비율과 주석되지 않은 추가 선 비율을 함께 측정합니다.

    `raw_score`는 판본 비교용 대표값인 누락 비율이고, 추가 선 비율은
    `details["extra_ratio"]`에 함께 남깁니다.
    """
    measured = _expected_path_errors(output_rgb, annotation, config)
    if measured is None:
        return MetricResult.not_scored("기대 경계가 검사 영역 안에 없음", 0.0)
    detection_ratio, statistics, confidence = _path_statistics(measured, config)

    ink = measured["ink"]
    ink_pixels = int(ink.sum())
    if ink_pixels == 0:
        extra_ratio = 0.0
    else:
        # 허용 거리 띠는 측정 전용이며 출력 이미지를 바꾸지 않습니다.
        to_expected = cv2.distanceTransform(
            (~measured["expected"]).astype(np.uint8), cv2.DIST_L2, cv2.DIST_MASK_PRECISE
        )
        band = to_expected <= config.path_tolerance_px
        extra_ratio = float(int((ink & ~band).sum()) / ink_pixels)

    return _metric_not_calibrated(
        1.0 - detection_ratio,
        confidence,
        missing_ratio=1.0 - detection_ratio,
        extra_ratio=extra_ratio,
        output_ink_pixels=ink_pixels,
        **statistics,
    )


def score_annotation(
    output_rgb: np.ndarray, annotation: dict, config: ScoringConfig
) -> MetricResult:
    """주석 종류에 맞는 지표를 고릅니다."""
    kind = annotation.get("type")
    if kind == "connection":
        return score_connection(output_rgb, annotation, config)
    if kind == "required_path":
        return score_required_path(output_rgb, annotation, config)
    if kind == "complete_roi":
        return score_complete_roi(output_rgb, annotation, config)
    return MetricResult.not_scored(f"지원하지 않는 주석 종류: {kind}", 0.0)


def score_global_metrics(
    source_rgb: np.ndarray,
    output_rgb: np.ndarray,
    expected_ratio: str,
    config: ScoringConfig,
) -> dict[str, MetricResult]:
    """전체 이미지 지표를 서로 독립적으로 계산합니다(총점 없음)."""
    return {
        "aspect_ratio": safe_metric(
            score_aspect_ratio, output_rgb, expected_ratio, config
        ),
        "silhouette_iou": safe_metric(
            score_silhouette, source_rgb, output_rgb, config
        ),
        "colored_pixels": safe_metric(score_colored_pixels, output_rgb, config),
        "black_fill": safe_metric(score_black_fill, output_rgb, config),
        "faint_strokes": safe_metric(score_faint_strokes, output_rgb, config),
    }
