"""신발 사진 입력 해석.

inputs/photos/<신발>/ 구조를 요구한다. 폴더 내용을 보고 모드를 추측하지
않는다. 예전 build_parts는 파일이 낱개로 있으면 파일 선택 모드로 넘어가
라벨 없는 한 장을 보냈고, 그때 Step 2의 참조 사진도 함께 사라졌다.
"""

from __future__ import annotations

from pathlib import Path

from services.utils import images

# 이 튜플의 순서가 곧 API 전송 순서다. 파일 시스템 순서와 무관하다.
# 라벨 문자열은 프롬프트가 그대로 지칭하므로 바꾸면 안 된다.
VIEW_LABELS: tuple[tuple[str, str], ...] = (
    ("lateral", "바깥쪽 측면(lateral)"),
    ("medial", "안쪽 측면(medial)"),
    ("front", "앞쪽에서 본 모습(front)"),
    ("heel", "뒤쪽에서 본 모습(heel)"),
    ("top", "위에서 본 모습(top)"),
    ("bottom", "바닥(bottom)"),
)

# 같은 뷰에 여러 확장자가 있으면 이 순서로 고른다.
EXTENSIONS = ("webp", "jpg", "jpeg", "png")

# Step 2가 직접 받는 뷰. 나머지는 채팅 히스토리로만 닿는다.
UNFOLD_VIEWS = ("lateral", "medial")

# Step 1 survey에서 제외하는 뷰. heel 라벨/이미지는 부품 명세서 단계에
# 쓰지 않는다. 같은 채팅 세션이므로 여기서 빼면 Step 2 히스토리에도
# heel 이미지가 남지 않는다.
SURVEY_EXCLUDE_VIEWS = ("heel",)

# 가이드라인 이미지 앞에 붙는 라벨. core/_parts_builder.py의 GUIDE_LABEL을
# 값 그대로 옮긴 것이다. 라벨이 없으면 모델이 이 틀을 신발 사진 중 하나로 읽는다.
GUIDE_LABEL = "[가이드라인] 2D 펼침 틀 — 신발 사진이 아니야"


def resolve(shoe_dir: Path) -> list[tuple[str, Path]]:
    """<신발> 폴더에서 (라벨, 경로) 쌍을 뷰 선언 순서대로 만든다."""
    shoe_dir = Path(shoe_dir)
    if not shoe_dir.is_dir():
        raise FileNotFoundError(
            f"신발 사진 폴더가 없습니다: {shoe_dir}\n"
            f"inputs/photos/<신발>/ 아래에 뷰별 파일을 두세요."
        )

    found: list[tuple[str, Path]] = []
    for name, view_label in VIEW_LABELS:
        for ext in EXTENSIONS:
            candidate = shoe_dir / f"{name}.{ext}"
            if candidate.is_file():
                found.append((view_label, candidate))
                break

    if not found:
        expected = ", ".join(f"{n}.{{{'|'.join(EXTENSIONS)}}}" for n, _ in VIEW_LABELS)
        raise FileNotFoundError(
            f"인식 가능한 뷰 파일이 없습니다: {shoe_dir}\n"
            f"기대하는 파일명: {expected}"
        )
    return found


def build_survey_parts(photos: list[tuple[str, Path]], prompt: str) -> list:
    """[라벨, 이미지] 쌍을 뷰 순서대로 늘어놓고 끝에 프롬프트를 둔다.

    SURVEY_EXCLUDE_VIEWS에 속한 뷰(heel)는 resolve()가 찾아냈어도 여기서
    걸러낸다.
    """
    excluded = {label for name, label in VIEW_LABELS if name in SURVEY_EXCLUDE_VIEWS}
    parts: list = []
    for view_label, path in photos:
        if view_label in excluded:
            continue
        parts.append(images.label(view_label))
        parts.append(images.load(path))
    parts.append(prompt)
    return parts


def build_unfold_parts(
    photos: list[tuple[str, Path]],
    guide_path: Path,
    survey_text: str,
    prompt: str,
) -> list:
    """측면 두 장 + 가이드라인 + 명세서 + 프롬프트, 정확히 이 순서로 8개."""
    wanted = {label for name, label in VIEW_LABELS if name in UNFOLD_VIEWS}
    parts: list = []
    for view_label, path in photos:
        if view_label in wanted:
            parts.append(images.label(view_label))
            parts.append(images.load(path))
    parts.append(GUIDE_LABEL)
    parts.append(images.load(guide_path))
    parts.append(f"[Previous Step 1 Output]\n{survey_text}")
    parts.append(prompt)
    return parts
