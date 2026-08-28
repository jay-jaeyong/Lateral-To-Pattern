"""골든 parts 하네스.

Gemini로 나가는 요청을 재구조화 전후로 비교하기 위한 직렬화 도구.
생성된 이미지는 비교하지 않는다 — 이미지 모델은 temperature 0에서도
실행마다 다른 픽셀을 내놓으므로 골든으로 잡을 수 있는 값이 아니다.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from PIL import Image as PILImage

GOLDEN_DIR = Path(__file__).parent / "golden"

# 골든을 다시 쓰려면 GOLDEN_UPDATE=1로 실행한다.
# 재구조화 중에는 절대 켜지 않는다. 켜면 회귀가 조용히 골든으로 덮인다.
UPDATE = os.environ.get("GOLDEN_UPDATE") == "1"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def describe_part(part) -> dict:
    """파트 하나를 골든 레코드로 만든다.

    이미지는 경로가 아니라 픽셀을 해시한다. load()가 convert("RGB")를
    수행하므로, 이동 중 그것이 빠지거나 리사이즈가 끼어들면 SDK가
    인코딩하는 바이트가 달라진다. 경로만 기록하면 그걸 통과시킨다.
    """
    if isinstance(part, str):
        return {"kind": "text", "len": len(part), "sha256": _sha(part.encode("utf-8"))}

    if isinstance(part, PILImage.Image):
        return {
            "kind": "pil",
            "mode": part.mode,
            "size": list(part.size),
            "sha256": _sha(part.tobytes()),
        }

    inline = getattr(part, "inline_data", None)
    data = getattr(inline, "data", None) if inline is not None else None
    mime = getattr(inline, "mime_type", None) if inline is not None else None
    if data is None:
        data = getattr(part, "image_bytes", None)
        mime = getattr(part, "mime_type", None)
    if data is not None:
        return {"kind": "bytes", "mime_type": mime, "sha256": _sha(data)}

    raise TypeError(f"골든에 기록할 수 없는 파트 타입입니다: {type(part).__name__}")


def describe_config(config) -> dict | None:
    """GenerateContentConfig를 골든 레코드로 만든다. None이면 None."""
    if config is None:
        return None
    image_config = getattr(config, "image_config", None)
    schema = getattr(config, "response_schema", None)
    thinking = getattr(config, "thinking_config", None)
    modalities = getattr(config, "response_modalities", None)
    return {
        "response_modalities": list(modalities) if modalities else None,
        "response_mime_type": getattr(config, "response_mime_type", None),
        "response_schema": getattr(schema, "__name__", None),
        "temperature": getattr(config, "temperature", None),
        "thinking_level": getattr(thinking, "thinking_level", None),
        "image_config": None if image_config is None else {
            "image_size": image_config.image_size,
            "aspect_ratio": image_config.aspect_ratio,
        },
    }


class RecordingClient:
    """send()가 받은 것을 골든 레코드로 남기는 스텁 클라이언트."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls: list[dict] = []
        self.start_chat_call_count = 0
        self._history: list = []

    def start_chat(self):
        self.start_chat_call_count += 1
        self._history = []

    @property
    def chat_history(self):
        return self._history

    def _format_parts_for_log(self, parts):
        return ""

    def _format_chat_history_for_log(self):
        return ""

    def send(self, parts, config=None):
        self.calls.append({
            "parts": [describe_part(p) for p in parts],
            "config": describe_config(config),
        })
        response = self._responses.pop(0)
        self._history.append(f"turn:{response.text}")
        return response


def assert_golden(testcase, name: str, call: dict) -> None:
    """골든 파일과 대조한다. GOLDEN_UPDATE=1이면 파일을 쓴다."""
    GOLDEN_DIR.mkdir(exist_ok=True)
    path = GOLDEN_DIR / f"{name}.json"
    serialized = json.dumps(call, ensure_ascii=False, indent=2, sort_keys=True)

    if UPDATE:
        path.write_text(serialized + "\n", encoding="utf-8")
        return

    testcase.assertTrue(
        path.exists(),
        f"골든 파일이 없습니다: {path}. GOLDEN_UPDATE=1로 한 번 생성하세요.",
    )
    expected = json.loads(path.read_text(encoding="utf-8"))
    testcase.assertEqual(
        expected, call,
        f"\n{name}의 API 요청이 골든과 다릅니다.\n"
        f"재구조화가 Gemini로 나가는 바이트를 바꿨습니다. 여기서 멈추세요.",
    )


# ── fixture ────────────────────────────────────────────────────────────────
# 실제 신발 사진에 의존하지 않는 결정적인 작은 이미지.
# PNG RGB 왕복은 무손실이므로 매 실행 같은 픽셀이 나온다.

_VIEW_LABELS = (
    ("lateral", "바깥쪽 측면(lateral)"),
    ("medial", "안쪽 측면(medial)"),
    ("front", "앞쪽에서 본 모습(front)"),
    ("heel", "뒤쪽에서 본 모습(heel)"),
    ("top", "위에서 본 모습(top)"),
)


def make_fixture_photos(directory: Path) -> list[tuple[str, Path]]:
    """(라벨, 경로) 쌍을 뷰 순서대로 만든다."""
    directory.mkdir(parents=True, exist_ok=True)
    pairs = []
    for index, (name, label) in enumerate(_VIEW_LABELS):
        path = directory / f"{name}.png"
        PILImage.new("RGB", (6, 6), (index * 31, index * 17, index * 43)).save(path)
        pairs.append((label, path))
    return pairs


def make_fixture_guide(directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "가이드라인_fixture.png"
    PILImage.new("RGB", (8, 8), (250, 250, 250)).save(path)
    return path


def make_fixture_color_pattern(directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "fixture_color.png"
    PILImage.new("RGB", (10, 15), (200, 30, 30)).save(path)
    return path
