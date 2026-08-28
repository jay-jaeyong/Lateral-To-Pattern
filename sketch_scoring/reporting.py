"""실행별 상세 JSON과 판본 비교 CSV.

실행 디렉터리는 보존만 하고 덮어쓰지 않습니다. `latest.json`만 원자적으로
교체합니다. 이미지, 마스크, 축소본과 오버레이는 저장하지 않습니다. 단일 총점,
종합 점수와 순위 열은 만들지 않습니다.
"""

from __future__ import annotations

import csv
import io
import json
import re
import statistics
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import NamedTuple

from .manifest import version_sort_key

RESULTS_NAME = "results.json"
SUMMARY_NAME = "summary.csv"
LATEST_NAME = "latest.json"

CSV_HEADER = [
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
]

LOWER_IS_BETTER = "lower"
HIGHER_IS_BETTER = "higher"

# 방향은 지표 이름에서 추론하지 않고 여기서 선언합니다.
# 값은 (details에서 읽을 항목, 방향)입니다.
GLOBAL_SERIES: dict[str, tuple[str, str]] = {
    "aspect_ratio": ("raw_score", LOWER_IS_BETTER),
    "silhouette_iou": ("raw_score", HIGHER_IS_BETTER),
    "colored_pixels": ("raw_score", LOWER_IS_BETTER),
    "black_fill": ("raw_score", LOWER_IS_BETTER),
    "faint_strokes": ("raw_score", LOWER_IS_BETTER),
}

# complete_roi는 누락과 추가 선을 각각 따로 보고합니다.
ANNOTATION_SERIES: dict[str, dict[str, tuple[str, str]]] = {
    "connection": {"connection": ("gap_normalized", LOWER_IS_BETTER)},
    "required_path": {"required_path": ("detection_ratio", HIGHER_IS_BETTER)},
    "complete_roi": {
        "complete_roi.missing_ratio": ("missing_ratio", LOWER_IS_BETTER),
        "complete_roi.extra_ratio": ("extra_ratio", LOWER_IS_BETTER),
    },
}


class Entry(NamedTuple):
    status: str
    reason: str | None
    value: float | None


def _series_order() -> list[tuple[str, str]]:
    order = [(name, spec[1]) for name, spec in GLOBAL_SERIES.items()]
    for series in ANNOTATION_SERIES.values():
        order.extend((name, spec[1]) for name, spec in series.items())
    return order


def _entry(metric: dict, field: str) -> Entry:
    value = (metric.get("details") or {}).get(field)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        value = None
    return Entry(str(metric.get("status")), metric.get("reason"), value)


def _collect(result: dict) -> tuple[dict[tuple[str, str], dict[str, Entry]], list[str]]:
    """(판본, 지표) -> {비교키: 항목}. 비교키는 판본 사이에서 안정적입니다."""
    collected: dict[tuple[str, str], dict[str, Entry]] = {}
    versions: set[str] = set()
    for item_id, per_version in (result.get("items") or {}).items():
        for version, output in (per_version or {}).items():
            versions.add(version)
            for name, metric in (output.get("metrics") or {}).items():
                spec = GLOBAL_SERIES.get(name)
                if spec is None:
                    continue
                collected.setdefault((version, name), {})[item_id] = _entry(
                    metric, spec[0]
                )
            for annotation in output.get("annotations") or []:
                series = ANNOTATION_SERIES.get(annotation.get("type"), {})
                key = f"{item_id}/{annotation.get('id')}"
                for name, spec in series.items():
                    collected.setdefault((version, name), {})[key] = _entry(
                        annotation.get("metric") or {}, spec[0]
                    )
    return collected, sorted(versions, key=version_sort_key)


def build_summary_csv(result: dict) -> str:
    """지표별 중앙값과 개선·동일·악화 수를 판본 순서대로 집계합니다."""
    collected, versions = _collect(result)
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(CSV_HEADER)

    for index, version in enumerate(versions):
        previous = versions[index - 1] if index else None
        for series, direction in _series_order():
            entries = collected.get((version, series))
            if not entries:
                continue
            values = [entry.value for entry in entries.values() if entry.value is not None]
            statuses = Counter(entry.status for entry in entries.values())
            reasons = Counter(
                entry.reason
                for entry in entries.values()
                if entry.status == "not_scored" and entry.reason
            )
            improved = same = worsened = 0
            before = collected.get((previous, series), {}) if previous else {}
            for key, entry in entries.items():
                earlier = before.get(key)
                if earlier is None or earlier.value is None or entry.value is None:
                    continue
                if entry.value == earlier.value:
                    same += 1
                elif (entry.value < earlier.value) == (direction == LOWER_IS_BETTER):
                    improved += 1
                else:
                    worsened += 1
            writer.writerow(
                [
                    version,
                    series,
                    f"{statistics.median(values):.6f}" if values else "",
                    improved,
                    same,
                    worsened,
                    statuses.get("pass", 0),
                    statuses.get("warn", 0),
                    statuses.get("fail", 0),
                    statuses.get("not_scored", 0),
                    "; ".join(
                        f"{reason}={count}" for reason, count in sorted(reasons.items())
                    ),
                ]
            )
    return buffer.getvalue()


def _sanitized_label(label: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._가-힣-]+", "-", str(label)).strip("-._")
    return cleaned or "run"


def _atomic_write_text(path: Path, text: str) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    try:
        temporary.replace(path)
    except OSError:
        temporary.unlink(missing_ok=True)
        raise


def write_run_reports(result: dict, reports_root: Path, label: str) -> Path:
    """새 실행 디렉터리에 결과를 쓰고 `latest.json`만 교체합니다."""
    reports_root = Path(reports_root)
    reports_root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    base = f"{stamp}-{_sanitized_label(label)}"
    run_dir = reports_root / base
    suffix = 2
    while run_dir.exists():
        # 이전 실행을 절대 덮어쓰지 않습니다.
        run_dir = reports_root / f"{base}-{suffix}"
        suffix += 1
    run_dir.mkdir(parents=True)

    _atomic_write_text(
        run_dir / RESULTS_NAME, json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    )
    _atomic_write_text(run_dir / SUMMARY_NAME, build_summary_csv(result))
    _atomic_write_text(
        reports_root / LATEST_NAME,
        json.dumps(
            {
                "run_id": run_dir.name,
                "results": f"{run_dir.name}/{RESULTS_NAME}",
                "summary": f"{run_dir.name}/{SUMMARY_NAME}",
                "written_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
    )
    return run_dir
