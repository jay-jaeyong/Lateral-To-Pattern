# 멀티뷰 입력 + 패턴 일치도 개선 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 신발 한 켤레의 여러 각도 사진을 입력으로 받고, 펼치기 전에 실물을 텍스트로 관찰하는 단계를 추가해, 생성된 2D 패턴이 원본 신발의 부품 배치·재봉선·무늬와 더 일치하게 만든다.

**Architecture:** 신발 사진 입력 경로를 둘로 나눈다. `--lateral` 같은 뷰 플래그가 있으면 그것들이 신발 사진 전체를 정의하고, 없으면 기존 폴더 스캔을 쓴다. 두 경로 모두 `(라벨, 경로)` 목록으로 정규화한 뒤 각 이미지 앞에 라벨 텍스트 파트를 끼워 API로 보낸다. 파이프라인은 2스텝에서 3스텝이 되고, 새로 추가되는 첫 스텝만 `response_modalities=["TEXT"]`로 호출해 부품 명세서를 텍스트로 받는다. 그 명세서가 채팅 히스토리를 타고 뒤 스텝의 체크리스트가 된다.

**Tech Stack:** Python 3.11+, google-genai 2.15.0, Pillow, uv. 테스트는 표준 라이브러리 `unittest` (새 의존성 없음).

## Global Constraints

- 브랜치는 `multi-view`다. 다른 브랜치로 옮기지 않는다.
- 새 런타임 의존성을 추가하지 않는다. 테스트는 표준 라이브러리 `unittest`만 쓴다.
- 표기는 `아일릿`이다. `아일렛`으로 쓰지 않는다.
- 뷰 플래그의 API 전송 순서는 항상 `lateral → medial → front → heel → top → bottom`이다. 사용자가 플래그를 준 순서와 무관하다.
- 뷰 라벨 문자열은 정확히 다음과 같다. 프롬프트가 이 문자열을 그대로 지칭하므로 한 글자도 바꾸지 않는다.
  - `바깥쪽 측면(lateral)`
  - `안쪽 측면(medial)`
  - `앞쪽에서 본 모습(front)`
  - `뒤쪽에서 본 모습(heel)`
  - `위에서 본 모습(top)`
  - `바닥(bottom)`
- 이미지 앞에 붙는 라벨 파트의 형식은 `[사진 {index}] {label}`이다. index는 1부터 시작하고, 실제로 로드에 성공한 이미지만 센다.
- 모든 명령은 `uv run`으로 실행한다. 테스트는 `uv run python -m unittest discover -s tests -t . -v`.
- 설계 근거는 `docs/superpowers/specs/2026-08-03-multiview-pattern-fidelity-design.md`에 있다. 판단이 필요하면 그 문서를 따른다.

## 파일 구조

| 파일 | 책임 | 상태 |
|---|---|---|
| `tests/__init__.py` | 테스트 패키지 표시 (빈 파일) | 생성 |
| `tests/test_cli_view_flags.py` | 뷰 플래그 파싱·정규화·run_label 유도 | 생성 |
| `tests/test_labeled_parts.py` | 라벨 파트 조립, 폴더 라벨, parts_builder 분기 | 생성 |
| `tests/test_response_config.py` | 스텝별 응답 모달리티 config 생성과 통과 | 생성 |
| `tests/test_prompts_structure.py` | 프롬프트 3스텝 구조와 라벨 문자열 일치 | 생성 |
| `utils/cli.py` | 뷰 플래그 정의·파싱·검증, 스텝 설정 주입 | 수정 |
| `main.py` | 진입점 배선, run_label 결정, 경고 | 수정 |
| `run.sh` | 이미지 경로 플래그가 있으면 `images/` 사전 검사 생략 | 수정 |
| `handlers/image_handler.py` | `(라벨, 경로)` → 파트 조립 | 수정 |
| `core/_parts_builder.py` | `view_images` 우선 분기 | 수정 |
| `core/pipeline.py` | `view_images`·`response_modalities` 전달, 빈 텍스트 경고 | 수정 |
| `config/gemini_config.py` | 모달리티 목록 → `GenerateContentConfig` | 수정 |
| `services/gemini_client.py` | per-call config 통과 | 수정 |
| `config/prompts.py` | 3스텝 정의와 프롬프트 본문 | 수정 |
| `README.md` | 사용법 문서 | 수정 |

---

### Task 1: 뷰 플래그 CLI

**Files:**
- Create: `tests/__init__.py`
- Create: `tests/test_cli_view_flags.py`
- Modify: `utils/cli.py`
- Modify: `main.py`
- Modify: `run.sh`

**Interfaces:**
- Consumes: 없음 (첫 작업)
- Produces:
  - `utils.cli.VIEW_FLAGS: tuple[tuple[str, str], ...]` — `(플래그이름, 라벨문자열)` 6쌍. 튜플 순서가 곧 API 전송 순서.
  - `utils.cli.parse_args(argv: list[str] | None = None) -> argparse.Namespace`
  - `utils.cli.collect_view_images(args: argparse.Namespace) -> list[tuple[str, Path]]`
  - `utils.cli.derive_run_label(view_images: list[tuple[str, Path]]) -> str | None`
  - `utils.cli.apply_image_overrides(steps, shoe_image=None, guide_image=None, view_images=None) -> list[dict]` — `view_images`가 있으면 `steps[0]["view_images"]`에 넣고 `steps[0]["image_path"]`를 `None`으로 만든다.

- [ ] **Step 1: 테스트 패키지 파일을 만든다**

`tests/__init__.py`를 빈 파일로 만든다.

```bash
mkdir -p tests && touch tests/__init__.py
```

- [ ] **Step 2: 실패하는 테스트를 쓴다**

`tests/test_cli_view_flags.py`:

```python
"""뷰 플래그 파싱과 스텝 설정 주입 테스트."""

import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from utils.cli import (
    VIEW_FLAGS,
    apply_image_overrides,
    collect_view_images,
    derive_run_label,
    parse_args,
)


class ViewFlagOrderTest(unittest.TestCase):
    def test_flag_order_is_fixed(self):
        names = [name for name, _label in VIEW_FLAGS]
        self.assertEqual(
            names, ["lateral", "medial", "front", "heel", "top", "bottom"]
        )

    def test_labels_are_exact(self):
        labels = dict(VIEW_FLAGS)
        self.assertEqual(labels["lateral"], "바깥쪽 측면(lateral)")
        self.assertEqual(labels["medial"], "안쪽 측면(medial)")
        self.assertEqual(labels["front"], "앞쪽에서 본 모습(front)")
        self.assertEqual(labels["heel"], "뒤쪽에서 본 모습(heel)")
        self.assertEqual(labels["top"], "위에서 본 모습(top)")
        self.assertEqual(labels["bottom"], "바닥(bottom)")


class ParseArgsTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.lat = self.tmp / "lat.png"
        self.med = self.tmp / "med.png"
        self.top = self.tmp / "top.png"
        for path in (self.lat, self.med, self.top):
            path.write_bytes(b"not a real image but the file exists")
        self.addCleanup(self._tmp.cleanup)

    def test_collect_orders_by_view_flags_not_argv(self):
        args = parse_args(
            ["--top", str(self.top), "--lateral", str(self.lat), "--medial", str(self.med)]
        )
        collected = collect_view_images(args)
        self.assertEqual(
            [label for label, _path in collected],
            ["바깥쪽 측면(lateral)", "안쪽 측면(medial)", "위에서 본 모습(top)"],
        )
        self.assertEqual([path for _label, path in collected], [self.lat, self.med, self.top])

    def test_no_flags_gives_empty_list(self):
        self.assertEqual(collect_view_images(parse_args([])), [])

    def test_missing_file_exits(self):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            with self.assertRaises(SystemExit):
                parse_args(["--lateral", str(self.tmp / "nope.png")])
        self.assertIn("--lateral", stderr.getvalue())


class DeriveRunLabelTest(unittest.TestCase):
    def test_uses_first_entry_stem(self):
        views = [("바깥쪽 측면(lateral)", Path("/a/b/nike_v2k.png"))]
        self.assertEqual(derive_run_label(views), "nike_v2k")

    def test_empty_gives_none(self):
        self.assertIsNone(derive_run_label([]))


class ApplyImageOverridesTest(unittest.TestCase):
    def base_steps(self):
        return [{"image_path": Path("images"), "guide_image_path": Path("images")}]

    def test_view_images_replace_image_path(self):
        views = [("바깥쪽 측면(lateral)", Path("/a/lat.png"))]
        updated = apply_image_overrides(self.base_steps(), view_images=views)
        self.assertEqual(updated[0]["view_images"], views)
        self.assertIsNone(updated[0]["image_path"])

    def test_view_images_win_over_shoe_image(self):
        views = [("바깥쪽 측면(lateral)", Path("/a/lat.png"))]
        updated = apply_image_overrides(
            self.base_steps(), shoe_image=["/x/other.png"], view_images=views
        )
        self.assertEqual(updated[0]["view_images"], views)
        self.assertIsNone(updated[0]["image_path"])

    def test_shoe_image_still_works_without_view_images(self):
        updated = apply_image_overrides(self.base_steps(), shoe_image=["/x/a.png", "/x/b.png"])
        self.assertEqual(updated[0]["image_path"], Path("/x/a.png"))
        self.assertNotIn("view_images", updated[0])

    def test_guide_image_applies_either_way(self):
        views = [("바깥쪽 측면(lateral)", Path("/a/lat.png"))]
        updated = apply_image_overrides(
            self.base_steps(), guide_image="/g/guide.jpg", view_images=views
        )
        self.assertEqual(updated[0]["guide_image_path"], Path("/g/guide.jpg"))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: 테스트를 돌려 실패를 확인한다**

Run: `uv run python -m unittest discover -s tests -t . -v`
Expected: FAIL — `ImportError: cannot import name 'VIEW_FLAGS' from 'utils.cli'`

- [ ] **Step 4: `utils/cli.py`를 고친다**

파일 전체를 아래로 교체한다.

```python
"""
CLI Utilities
--------------
커맨드라인 인자 파싱 및 이미지 경로 오버라이드 유틸리티.
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


# 뷰 플래그 정의: (플래그 이름, 프롬프트에 붙일 라벨)
# 이 튜플의 순서가 곧 API 전송 순서입니다. 사용자가 플래그를 준 순서와 무관합니다.
# 라벨 문자열은 config/prompts.py의 프롬프트가 그대로 지칭하므로 바꾸면 안 됩니다.
VIEW_FLAGS: tuple[tuple[str, str], ...] = (
    ("lateral", "바깥쪽 측면(lateral)"),
    ("medial", "안쪽 측면(medial)"),
    ("front", "앞쪽에서 본 모습(front)"),
    ("heel", "뒤쪽에서 본 모습(heel)"),
    ("top", "위에서 본 모습(top)"),
    ("bottom", "바닥(bottom)"),
)


def build_parser() -> argparse.ArgumentParser:
    """CLI 인자 파서를 구성합니다."""
    parser = argparse.ArgumentParser(
        description="Lateral-To-Pattern: 신발 실물 사진을 2D 패턴으로 펼치는 Gemini 파이프라인"
    )
    parser.add_argument(
        "--run-label",
        default=None,
        help="실행 식별자 (출력 폴더명). 미입력 시 타임스탬프 자동 생성.",
    )
    parser.add_argument(
        "--output-dir",
        default="output",
        help="결과를 저장할 최상위 디렉터리 (기본값: output/)",
    )
    for name, label in VIEW_FLAGS:
        parser.add_argument(
            f"--{name}",
            default=None,
            metavar="PATH",
            help=f"{label} 사진 경로. 뷰 플래그를 하나라도 주면 --shoe-image와 폴더 선택은 무시됩니다.",
        )
    parser.add_argument(
        "--shoe-image",
        nargs="+",
        metavar="PATH",
        default=None,
        help="신발 실물 사진(사이드뷰) 경로 또는 폴더. 여러 개를 주면 각각 따로 실행합니다. "
             "(미입력 시 config/prompts.py 설정 사용)",
    )
    parser.add_argument(
        "--guide-image",
        default=None,
        help="2D 펼침 가이드라인(틀) 이미지 경로 또는 폴더 (미입력 시 config/prompts.py 설정 사용)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="상세 로그 출력",
    )
    return parser


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """인자를 파싱하고 뷰 플래그 경로가 실제로 있는지 검사합니다.

    없는 파일을 가리키면 API를 부르기 전에 여기서 종료합니다.
    """
    parser = build_parser()
    args = parser.parse_args(argv)

    for name, _label in VIEW_FLAGS:
        value = getattr(args, name, None)
        if value and not Path(value).is_file():
            parser.error(f"--{name} 경로를 찾을 수 없습니다: {value}")

    return args


def collect_view_images(args: argparse.Namespace) -> list[tuple[str, Path]]:
    """주어진 뷰 플래그를 VIEW_FLAGS 순서대로 (라벨, 경로) 목록으로 모읍니다."""
    collected: list[tuple[str, Path]] = []
    for name, label in VIEW_FLAGS:
        value = getattr(args, name, None)
        if value:
            collected.append((label, Path(value)))
    return collected


def derive_run_label(view_images: list[tuple[str, Path]]) -> str | None:
    """뷰 플래그 목록에서 출력 폴더 이름을 유도합니다.

    VIEW_FLAGS 순서상 lateral이 맨 앞이므로, lateral이 있으면 그 파일명이 됩니다.
    """
    return view_images[0][1].stem if view_images else None


def apply_image_overrides(
    steps: list[dict],
    shoe_image: str | list[str] | None = None,
    guide_image: str | None = None,
    view_images: list[tuple[str, Path]] | None = None,
) -> list[dict]:
    """CLI 인자로 전달된 이미지를 첫 단계 설정에 덮어씁니다.

    view_images가 있으면 그것이 신발 사진 전체를 정의하고 image_path는 비웁니다.
    shoe_image가 여러 개면 첫 번째 경로만 단계 설정에 넣습니다.
    나머지는 Pipeline(batch_targets=...)이 개별 실행으로 처리합니다.
    """
    updated = [dict(step_config) for step_config in steps]
    if not updated:
        return updated

    if view_images:
        updated[0]["view_images"] = list(view_images)
        updated[0]["image_path"] = None
        if shoe_image:
            logger.warning("뷰 플래그가 있어 --shoe-image를 무시합니다: %s", shoe_image)
    elif shoe_image:
        first = shoe_image[0] if isinstance(shoe_image, list) else shoe_image
        updated[0]["image_path"] = Path(first)

    if guide_image:
        updated[0]["guide_image_path"] = Path(guide_image)

    return updated
```

- [ ] **Step 5: 테스트를 돌려 통과를 확인한다**

Run: `uv run python -m unittest discover -s tests -t . -v`
Expected: PASS (11 tests)

- [ ] **Step 6: `main.py`를 배선한다**

`main.py`의 import 줄을 바꾼다. 기존:

```python
from utils.cli import build_parser, apply_image_overrides
```

교체:

```python
from utils.cli import (
    apply_image_overrides,
    collect_view_images,
    derive_run_label,
    parse_args,
)
```

`main()` 함수 본문에서 기존의 이 블록을

```python
    parser = build_parser()
    args = parser.parse_args()

    setup_logging(verbose=args.verbose)
    logger = logging.getLogger(__name__)

    logger.info("=" * 60)
    logger.info("Lateral-To-Pattern 파이프라인 시작")
    logger.info("=" * 60)

    # CLI 이미지 경로 오버라이드 적용
    steps = apply_image_overrides(
        PIPELINE_STEPS,
        shoe_image=args.shoe_image,
        guide_image=args.guide_image,
    )

    # If the user provided an explicit run label, use it; otherwise we allow
    # the Pipeline to set the label based on the selected image later.
    run_label = args.run_label

    # 신발 이미지를 2개 이상 받았다면 각각 개별 실행합니다.
    shoe_images = args.shoe_image or []
    batch_targets = [Path(p) for p in shoe_images] if len(shoe_images) > 1 else None
```

이렇게 교체한다.

```python
    args = parse_args()

    setup_logging(verbose=args.verbose)
    logger = logging.getLogger(__name__)

    logger.info("=" * 60)
    logger.info("Lateral-To-Pattern 파이프라인 시작")
    logger.info("=" * 60)

    # 뷰 플래그가 하나라도 있으면 그것들이 신발 사진 전체를 정의합니다.
    view_images = collect_view_images(args)
    if view_images and not args.lateral:
        logger.warning(
            "기준이 되는 --lateral 사진이 없습니다. "
            "받은 사진 중 옆면에 해당하는 것을 기준으로 삼습니다."
        )

    # CLI 이미지 경로 오버라이드 적용
    steps = apply_image_overrides(
        PIPELINE_STEPS,
        shoe_image=args.shoe_image,
        guide_image=args.guide_image,
        view_images=view_images,
    )

    # 뷰 플래그를 쓰면 모델 폴더 이름이 없으므로 lateral 파일명을 출력 폴더로 씁니다.
    # 그 외에는 Pipeline이 선택된 이미지 이름으로 레이블을 정합니다.
    run_label = args.run_label or derive_run_label(view_images)

    # 신발 이미지를 2개 이상 받았다면 각각 개별 실행합니다.
    shoe_images = [] if view_images else (args.shoe_image or [])
    batch_targets = [Path(p) for p in shoe_images] if len(shoe_images) > 1 else None
```

모듈 docstring의 실행 예시에 한 줄을 더한다. 기존 `python main.py --shoe-image shoe_a.jpg shoe_b.jpg shoe_c.jpg   # 이미지마다 개별 실행` 아래에 붙인다.

```
    python main.py --lateral lat.webp --medial med.webp --top top.webp   # 한 켤레 멀티뷰
```

- [ ] **Step 7: `run.sh`의 사전 검사를 조건부로 만든다**

`run.sh`에서 이 블록을 찾는다.

```bash
img_files="$(find images -maxdepth 1 -type f \
    \( -iname '*.png' -o -iname '*.jpg' -o -iname '*.jpeg' -o -iname '*.webp' \) 2>/dev/null || true)"

if [ -z "$img_files" ]; then
    echo "[run.sh] images/ 바로 아래에 이미지가 없습니다. 다음처럼 넣어주세요:"
    echo "         images/가이드라인.jpg     ← 펼칠 틀 (파일명에 '가이드라인' 포함)"
    echo "         images/나이키 탄준.jpg    ← 신발 실물 사이드뷰 (여러 장 가능)"
    exit 1
fi

if ! printf '%s\n' "$img_files" | grep -qiE '가이드라인|가이드|guideline|guide'; then
    echo "[run.sh] images/ 에서 가이드라인 이미지를 찾지 못했습니다."
    echo "         파일명에 '가이드라인'(또는 guideline)이 들어간 이미지를 넣어주세요."
    exit 1
fi
```

전체를 아래로 교체한다.

```bash
# 이미지 경로를 인자로 직접 지정했다면 images/ 사전 검사를 건너뜁니다.
skip_image_check=0
for arg in "$@"; do
    case "$arg" in
        --lateral|--medial|--front|--heel|--top|--bottom|--shoe-image|--guide-image)
            skip_image_check=1
            break
            ;;
    esac
done

if [ "$skip_image_check" -eq 0 ]; then
    shoe_dirs="$(find images -mindepth 1 -maxdepth 1 -type d 2>/dev/null || true)"
    top_files="$(find images -maxdepth 1 -type f \
        \( -iname '*.png' -o -iname '*.jpg' -o -iname '*.jpeg' -o -iname '*.webp' \) \
        2>/dev/null || true)"

    if [ -z "$shoe_dirs" ] && [ -z "$top_files" ]; then
        echo "[run.sh] images/ 아래에 아무것도 없습니다. 다음처럼 넣어주세요:"
        echo "         images/가이드라인.jpg            ← 펼칠 틀 (파일명에 '가이드라인' 포함)"
        echo "         images/나이키_탄준/lateral.webp  ← 모델 폴더 안에 각도별 사진"
        exit 1
    fi

    if ! printf '%s\n' "$top_files" | grep -qiE '가이드라인|가이드|guideline|guide'; then
        echo "[run.sh] images/ 에서 가이드라인 이미지를 찾지 못했습니다."
        echo "         파일명에 '가이드라인'(또는 guideline)이 들어간 이미지를 넣어주세요."
        exit 1
    fi
fi
```

교체 후 `run.sh`에 `img_files` 변수가 남아 있으면 안 된다. `grep -n img_files run.sh`가 아무것도 출력하지 않아야 한다.

- [ ] **Step 8: 손으로 확인한다**

Run: `uv run python main.py --help`
Expected: `--lateral PATH`, `--medial PATH`, `--front PATH`, `--heel PATH`, `--top PATH`, `--bottom PATH`가 도움말에 보인다.

Run: `uv run python main.py --lateral /tmp/does-not-exist.png 2>&1 | tail -2`
Expected: `--lateral 경로를 찾을 수 없습니다: /tmp/does-not-exist.png` 로 종료

Run: `bash -n run.sh && grep -c img_files run.sh || true`
Expected: 문법 오류 없음. `grep`은 `img_files`를 찾지 못하고 `0`을 출력한다.

- [ ] **Step 9: 커밋한다**

```bash
git add tests/__init__.py tests/test_cli_view_flags.py utils/cli.py main.py run.sh
git commit -m "✅ 뷰 플래그(--lateral 등 6개) CLI 추가"
```

---

### Task 2: 라벨 파트 조립

**Files:**
- Create: `tests/test_labeled_parts.py`
- Modify: `handlers/image_handler.py`
- Modify: `core/_parts_builder.py`
- Modify: `core/pipeline.py:246-270` (`_run_step`의 `build_step_parts` 호출부)

**Interfaces:**
- Consumes: Task 1의 `steps[0]["view_images"]` — `list[tuple[str, Path]]`
- Produces:
  - `ImageHandler.LABEL_FORMAT: str` — `"[사진 {index}] {label}"`
  - `ImageHandler.build_labeled_parts(labeled_paths: list[tuple[str, Path]], prompt: str) -> list` — `[라벨1, 이미지1, 라벨2, 이미지2, ..., prompt]`. 로드 가능한 이미지가 하나도 없으면 `[prompt]`.
  - `build_step_parts(..., view_images: list[tuple[str, Path]] | None = None)` — `view_images`가 있으면 `image_path`를 무시한다.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_labeled_parts.py`:

```python
"""라벨이 붙은 이미지 파트 조립 테스트."""

import tempfile
import unittest
from pathlib import Path

from PIL import Image

from core._parts_builder import build_step_parts
from handlers.image_handler import ImageHandler


def make_png(path: Path) -> Path:
    Image.new("RGB", (4, 4), (200, 30, 30)).save(path)
    return path


class BuildLabeledPartsTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def test_interleaves_label_then_image_then_prompt(self):
        a = make_png(self.tmp / "a.png")
        b = make_png(self.tmp / "b.png")
        parts = ImageHandler.build_labeled_parts(
            [("바깥쪽 측면(lateral)", a), ("안쪽 측면(medial)", b)], "PROMPT"
        )
        self.assertEqual(len(parts), 5)
        self.assertEqual(parts[0], "[사진 1] 바깥쪽 측면(lateral)")
        self.assertIsInstance(parts[1], Image.Image)
        self.assertEqual(parts[2], "[사진 2] 안쪽 측면(medial)")
        self.assertIsInstance(parts[3], Image.Image)
        self.assertEqual(parts[4], "PROMPT")

    def test_numbering_counts_only_loaded_images(self):
        good = make_png(self.tmp / "good.png")
        parts = ImageHandler.build_labeled_parts(
            [
                ("바깥쪽 측면(lateral)", self.tmp / "missing.png"),
                ("안쪽 측면(medial)", good),
            ],
            "PROMPT",
        )
        self.assertEqual(parts[0], "[사진 1] 안쪽 측면(medial)")
        self.assertEqual(len(parts), 3)

    def test_no_loadable_image_returns_prompt_only(self):
        parts = ImageHandler.build_labeled_parts(
            [("바깥쪽 측면(lateral)", self.tmp / "missing.png")], "PROMPT"
        )
        self.assertEqual(parts, ["PROMPT"])


class LoadDirImagesTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def test_folder_labels_use_filename(self):
        folder = self.tmp / "nike_v2k"
        folder.mkdir()
        make_png(folder / "01_lateral.png")
        make_png(folder / "02_medial.png")
        parts = ImageHandler._load_dir_images(folder, "PROMPT")
        self.assertEqual(parts[0], "[사진 1] 파일명: 01_lateral")
        self.assertEqual(parts[2], "[사진 2] 파일명: 02_medial")
        self.assertEqual(parts[-1], "PROMPT")

    def test_max_images_truncates(self):
        folder = self.tmp / "nike_v2k"
        folder.mkdir()
        make_png(folder / "01_lateral.png")
        make_png(folder / "02_medial.png")
        parts = ImageHandler._load_dir_images(folder, "PROMPT", max_images=1)
        self.assertEqual(len(parts), 3)
        self.assertEqual(parts[0], "[사진 1] 파일명: 01_lateral")


class BuildStepPartsTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def test_view_images_take_priority_over_image_path(self):
        view = make_png(self.tmp / "view.png")
        folder = self.tmp / "folder"
        folder.mkdir()
        make_png(folder / "ignored.png")

        parts = build_step_parts(
            step_num=1,
            prompt="PROMPT",
            image_path=folder,
            prev_images=[],
            prev_texts=[],
            view_images=[("바깥쪽 측면(lateral)", view)],
        )
        self.assertEqual(parts[0], "[사진 1] 바깥쪽 측면(lateral)")
        self.assertEqual(len(parts), 3)

    def test_falls_back_to_image_path_when_no_view_images(self):
        single = make_png(self.tmp / "single.png")
        parts = build_step_parts(
            step_num=1,
            prompt="PROMPT",
            image_path=single,
            prev_images=[],
            prev_texts=[],
        )
        self.assertIsInstance(parts[0], Image.Image)
        self.assertEqual(parts[-1], "PROMPT")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 테스트를 돌려 실패를 확인한다**

Run: `uv run python -m unittest discover -s tests -t . -v`
Expected: FAIL — `AttributeError: type object 'ImageHandler' has no attribute 'build_labeled_parts'`

- [ ] **Step 3: `handlers/image_handler.py`에 조립 함수를 넣는다**

클래스 상수 영역에 `LABEL_FORMAT`을 더한다. `GUIDELINE_KEYWORDS` 정의 바로 아래에 넣는다.

```python
    # 이미지 앞에 붙는 라벨 텍스트 파트의 형식.
    # Pillow가 로드할 때 파일명을 버리므로, 어느 각도 사진인지는 이 라벨로만 전달됩니다.
    LABEL_FORMAT = "[사진 {index}] {label}"
```

`build_parts` 아래, `# 내부 헬퍼` 구분선 위에 새 메서드를 넣는다.

```python
    @staticmethod
    def build_labeled_parts(labeled_paths: list[tuple[str, Path]], prompt: str) -> list:
        """(라벨, 경로) 목록을 [라벨, 이미지, ..., 프롬프트] 파트로 조립합니다.

        Args:
            labeled_paths: (라벨 문자열, 이미지 경로) 튜플 목록. 목록 순서가 전송 순서입니다.
            prompt: 맨 뒤에 붙일 텍스트 프롬프트.

        Returns:
            Gemini API에 전달할 parts 리스트.
            로드 가능한 이미지가 하나도 없으면 [prompt]만 반환합니다.
        """
        parts: list = []
        index = 1
        for label, path in labeled_paths:
            try:
                image = ImageHandler.load(path)
            except Exception as exc:  # noqa: BLE001
                logger.warning("이미지 로드 실패: %s — %s", path, exc)
                continue
            parts.append(ImageHandler.LABEL_FORMAT.format(index=index, label=label))
            parts.append(image)
            index += 1

        if not parts:
            logger.info("로드된 이미지가 없습니다 — 프롬프트만으로 진행합니다.")
            return [prompt]

        parts.append(prompt)
        return parts
```

`_load_dir_images`의 본문 마지막 절반을 교체한다. 기존:

```python
        images: list[Image.Image] = []
        for f in image_files:
            try:
                images.append(ImageHandler.load(f))
            except Exception as exc:
                logger.warning("이미지 로드 실패: %s — %s", f, exc)

        if not images:
            logger.info("로드된 이미지 없음: %s — 프롬프트만으로 진행합니다.", folder)
            return [prompt]

        logger.info("폴더 '%s'에서 이미지 %d장 로드 완료", folder.name, len(images))
        return [*images, prompt]
```

교체:

```python
        # 폴더 방식은 뷰 종류를 알 수 없으므로 파일명을 라벨로 넘겨 모델이 판단하게 합니다.
        parts = ImageHandler.build_labeled_parts(
            [(f"파일명: {f.stem}", f) for f in image_files], prompt
        )
        loaded = (len(parts) - 1) // 2
        logger.info("폴더 '%s'에서 이미지 %d장 로드 완료", folder.name, loaded)
        return parts
```

- [ ] **Step 4: `core/_parts_builder.py`에 분기를 넣는다**

`build_step_parts`의 시그니처에 인자를 더한다. 기존 `max_images: int | None = None,` 다음 줄에 넣는다.

```python
    view_images: list[tuple[str, Path]] | None = None,
```

docstring의 Args 목록 끝에 한 줄을 더한다.

```
        view_images     : (라벨, 경로) 목록. 주어지면 image_path 대신 이것을 쓴다
```

본문의 첫 줄을 교체한다. 기존:

```python
    # ── 1. 현재 단계의 주 입력 이미지 + 프롬프트 로드 ──────────────────
    parts = list(prebuilt_parts) if prebuilt_parts is not None else _load_images(prompt, image_path, max_images)
```

교체:

```python
    # ── 1. 현재 단계의 주 입력 이미지 + 프롬프트 로드 ──────────────────
    if prebuilt_parts is not None:
        parts = list(prebuilt_parts)
    elif view_images:
        # 뷰 플래그로 받은 사진이 있으면 image_path는 무시합니다.
        parts = ImageHandler.build_labeled_parts(view_images, prompt)
    else:
        parts = _load_images(prompt, image_path, max_images)
```

- [ ] **Step 5: `core/pipeline.py`가 `view_images`를 넘기게 한다**

`_run_step` 안에서 설정을 읽는 줄들 사이에 한 줄을 더한다. 기존 `guide_image_path = config.get("guide_image_path")` 다음에 넣는다.

```python
        view_images = config.get("view_images")
```

`build_step_parts(...)` 호출에 인자를 더한다. 기존 `max_images=config.get("max_images"),` 다음 줄에 넣는다.

```python
                    view_images=view_images,
```

- [ ] **Step 6: 테스트를 돌려 통과를 확인한다**

Run: `uv run python -m unittest discover -s tests -t . -v`
Expected: PASS (18 tests)

- [ ] **Step 7: 커밋한다**

```bash
git add tests/test_labeled_parts.py handlers/image_handler.py core/_parts_builder.py core/pipeline.py
git commit -m "✅ 이미지마다 각도 라벨을 붙여 전송"
```

---

### Task 3: 스텝별 응답 모달리티

**Files:**
- Create: `tests/test_response_config.py`
- Modify: `config/gemini_config.py`
- Modify: `services/gemini_client.py:68` (`send` 시그니처)와 `:141` 부근 (`send_message` 호출)
- Modify: `core/pipeline.py:319` 부근 (`self._client.send(parts)` 호출)

**Interfaces:**
- Consumes: 없음
- Produces:
  - `config.gemini_config.build_response_config(modalities: list[str] | None) -> types.GenerateContentConfig | None` — `None`이나 빈 목록이면 `None`을 반환해 세션 기본 설정을 그대로 쓰게 한다.
  - `GeminiClient.send(parts: list, config=None) -> StepResponse`
  - 스텝 설정의 선택 키 `response_modalities: list[str]`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_response_config.py`:

```python
"""스텝별 응답 모달리티 config 생성과 전달 테스트."""

import unittest

from config.gemini_config import IMAGE_CONFIG, build_response_config
from core.models import StepResponse
from services.gemini_client import GeminiClient


class BuildResponseConfigTest(unittest.TestCase):
    def test_none_means_use_session_default(self):
        self.assertIsNone(build_response_config(None))

    def test_empty_list_means_use_session_default(self):
        self.assertIsNone(build_response_config([]))

    def test_text_only_has_no_image_config(self):
        config = build_response_config(["TEXT"])
        self.assertEqual(list(config.response_modalities), ["TEXT"])
        self.assertIsNone(config.image_config)

    def test_image_keeps_image_config(self):
        config = build_response_config(["TEXT", "IMAGE"])
        self.assertEqual(list(config.response_modalities), ["TEXT", "IMAGE"])
        self.assertIs(config.image_config, IMAGE_CONFIG)


class FakeResponse:
    parts: list = []


class FakeChat:
    def __init__(self):
        self.calls: list = []

    def send_message(self, message, config=None):
        self.calls.append((message, config))
        return FakeResponse()


class SendPassesConfigTest(unittest.TestCase):
    def make_client(self) -> GeminiClient:
        client = GeminiClient.__new__(GeminiClient)  # __init__은 API 키를 요구하므로 건너뜁니다
        client._chat = FakeChat()
        return client

    def test_config_is_forwarded(self):
        client = self.make_client()
        config = build_response_config(["TEXT"])
        result = client.send(["hello"], config=config)
        self.assertIsInstance(result, StepResponse)
        self.assertIs(client._chat.calls[0][1], config)

    def test_default_config_is_none(self):
        client = self.make_client()
        client.send(["hello"])
        self.assertIsNone(client._chat.calls[0][1])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 테스트를 돌려 실패를 확인한다**

Run: `uv run python -m unittest discover -s tests -t . -v`
Expected: FAIL — `ImportError: cannot import name 'build_response_config' from 'config.gemini_config'`

- [ ] **Step 3: `config/gemini_config.py`에 헬퍼를 넣는다**

`CHAT_CONFIG` 정의 다음, `# 재시도 설정` 구분선 앞에 넣는다.

```python
# ─────────────────────────────────────────────
# 스텝별 응답 모달리티 오버라이드
# ─────────────────────────────────────────────
def build_response_config(
    modalities: list[str] | None,
) -> types.GenerateContentConfig | None:
    """스텝 하나만 다른 모달리티로 부를 때 쓸 config를 만듭니다.

    관찰 스텝처럼 텍스트 응답이 필요한 경우에 씁니다.
    None이나 빈 목록이면 None을 반환해 세션 기본값(CHAT_CONFIG)을 그대로 쓰게 합니다.
    """
    if not modalities:
        return None

    kwargs = {
        "response_modalities": list(modalities),
        "safety_settings": SAFETY_SETTINGS,
        "temperature": 0,
    }
    if "IMAGE" in modalities:
        kwargs["image_config"] = IMAGE_CONFIG

    return types.GenerateContentConfig(**kwargs)
```

- [ ] **Step 4: `services/gemini_client.py`가 config를 통과시키게 한다**

`send` 시그니처를 바꾼다. 기존:

```python
    def send(self, parts: list) -> StepResponse:
```

교체:

```python
    def send(self, parts: list, config=None) -> StepResponse:
```

docstring의 Args에 한 줄을 더한다.

```
            config: 이 호출에만 적용할 GenerateContentConfig. None이면 채팅 세션 기본값을 씁니다.
```

`send_message` 호출을 바꾼다. 기존:

```python
                response = self._chat.send_message(parts)
```

교체:

```python
                response = self._chat.send_message(parts, config=config)
```

- [ ] **Step 5: `core/pipeline.py`가 스텝 설정을 config로 바꿔 넘기게 한다**

import에 헬퍼를 더한다. 기존 `from config.prompts import PIPELINE_STEPS` 다음 줄에 넣는다.

```python
from config.gemini_config import build_response_config
```

`_run_step` 안 `self._client.send(parts)` 호출을 교체한다. 기존:

```python
            # Gemini API 호출 → 텍스트 + 생성 이미지
            step_response: StepResponse = self._client.send(parts)
```

교체:

```python
            # Gemini API 호출 → 텍스트 + 생성 이미지
            # 관찰 스텝처럼 텍스트 응답이 필요한 단계만 모달리티를 바꿔 부릅니다.
            response_modalities = config.get("response_modalities")
            step_response: StepResponse = self._client.send(
                parts, config=build_response_config(response_modalities)
            )

            if response_modalities and "TEXT" in response_modalities and not step_response.text:
                logger.warning(
                    "Step %d: TEXT 응답을 요청했지만 텍스트가 비어 있습니다. "
                    "다음 단계로 넘길 명세서가 없습니다.",
                    step_num,
                )
```

- [ ] **Step 6: 테스트를 돌려 통과를 확인한다**

Run: `uv run python -m unittest discover -s tests -t . -v`
Expected: PASS (24 tests)

- [ ] **Step 7: 커밋한다**

```bash
git add tests/test_response_config.py config/gemini_config.py services/gemini_client.py core/pipeline.py
git commit -m "✅ 스텝별 응답 모달리티 오버라이드"
```

---

### Task 4: 프롬프트 3스텝 재구성

**Files:**
- Create: `tests/test_prompts_structure.py`
- Modify: `config/prompts.py`

**Interfaces:**
- Consumes: Task 1의 `VIEW_FLAGS` 라벨 문자열, Task 3의 `response_modalities` 스텝 키
- Produces: `PIPELINE_STEPS` 3개 — `part_survey`(step 1), `pattern_unfold`(step 2), `line_art_conversion`(step 3)

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_prompts_structure.py`:

```python
"""프롬프트 3스텝 구조와 라벨 문자열 일치 테스트."""

import unittest

from config.prompts import PIPELINE_STEPS
from utils.cli import VIEW_FLAGS


class PipelineShapeTest(unittest.TestCase):
    def test_three_steps_in_order(self):
        self.assertEqual([s["step"] for s in PIPELINE_STEPS], [1, 2, 3])
        self.assertEqual(
            [s["name"] for s in PIPELINE_STEPS],
            ["part_survey", "pattern_unfold", "line_art_conversion"],
        )

    def test_survey_step_asks_for_text_and_all_images(self):
        survey = PIPELINE_STEPS[0]
        self.assertEqual(survey["response_modalities"], ["TEXT"])
        self.assertIsNone(survey["max_images"])
        self.assertIsNone(survey["guide_image_path"])
        self.assertIsNotNone(survey["image_path"])

    def test_unfold_step_relies_on_history_and_takes_the_guide(self):
        unfold = PIPELINE_STEPS[1]
        self.assertIsNone(unfold["image_path"])
        self.assertIsNotNone(unfold["guide_image_path"])
        self.assertNotIn("response_modalities", unfold)


class PromptContentTest(unittest.TestCase):
    def prompts(self) -> list[str]:
        return [step["prompt"] for step in PIPELINE_STEPS]

    def test_no_positional_photo_references(self):
        for step, prompt in zip(PIPELINE_STEPS, self.prompts()):
            self.assertNotIn("첫번째 사진", prompt, msg=step["name"])
            self.assertNotIn("두번째 사진", prompt, msg=step["name"])

    def test_spelling_is_ailrit(self):
        for step, prompt in zip(PIPELINE_STEPS, self.prompts()):
            self.assertNotIn("아일렛", prompt, msg=step["name"])

    def test_unfold_has_priority_block(self):
        unfold = PIPELINE_STEPS[1]["prompt"]
        self.assertIn('"priority"', unfold)
        for rank in ("1순위", "2순위", "3순위", "4순위"):
            self.assertIn(rank, unfold)

    def test_unfold_has_multiview_rule(self):
        self.assertIn('"multiview_rule"', PIPELINE_STEPS[1]["prompt"])

    def test_unfold_names_the_lateral_label_exactly(self):
        lateral_label = dict(VIEW_FLAGS)["lateral"]
        self.assertIn(lateral_label, PIPELINE_STEPS[1]["prompt"])

    def test_survey_demands_unconfirmed_list(self):
        survey = PIPELINE_STEPS[0]["prompt"]
        self.assertIn("미확인", survey)
        self.assertIn('"coverage"', survey)

    def test_line_art_cross_checks_the_survey(self):
        self.assertIn('"survey_rule"', PIPELINE_STEPS[2]["prompt"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 테스트를 돌려 실패를 확인한다**

Run: `uv run python -m unittest discover -s tests -t . -v`
Expected: FAIL — `AssertionError: Lists differ: [1, 2] != [1, 2, 3]`

- [ ] **Step 3: `config/prompts.py`의 모듈 docstring과 상수 주석을 고친다**

모듈 docstring의 마지막 블록을 교체한다. 기존:

```
API에 전달되는 순서:
    [신발 실물 사진(사이드뷰), 2D 펼침 가이드라인(틀), 프롬프트]
```

교체:

```
스텝 정의에 쓸 수 있는 선택 키:
        - response_modalities: 이 스텝만 다른 응답 모달리티로 호출 (예: ["TEXT"])
        - view_images        : (라벨, 경로) 목록. CLI 뷰 플래그가 런타임에 주입합니다

API에 전달되는 순서:
    Step 1  [라벨, 신발 사진, 라벨, 신발 사진, ..., 프롬프트]        → 텍스트 명세서
    Step 2  [가이드라인, 앞 단계 명세서, 프롬프트]                   → 펼친 패턴 이미지
    Step 3  [앞 단계 생성 이미지, 앞 단계 명세서, 프롬프트]           → 라인 아트 이미지
```

`IMAGES_BASE` 위 주석 블록을 교체한다. 기존:

```
# images/
#   ├── 가이드라인.jpg      ← 이름에 '가이드라인'이 들어간 파일 = 펼칠 틀
#   ├── 나이키 탄준.jpg     ← 나머지 이미지 = 신발 실물 사이드뷰 (실행 시 선택)
#   └── 뉴발란스 992.png
#
# 실행하면 가이드라인을 뺀 이미지 목록이 뜨고, 번호로 하나를 고르거나
# 'all'을 입력해 전부 순서대로 돌릴 수 있습니다.
```

교체:

```
# images/
#   ├── 가이드라인.jpg          ← 이름에 '가이드라인'이 들어간 파일 = 펼칠 틀
#   ├── 나이키_탄준/            ← 모델 폴더. 안에 각도별 사진을 넣습니다
#   │     ├── lateral.webp
#   │     └── medial.webp
#   └── 뉴발란스_992/
#
# 실행하면 모델 폴더 목록이 뜨고, 번호로 하나를 고르거나 'all'을 입력해
# 전부 순서대로 돌릴 수 있습니다. 폴더 안 사진은 전부 함께 전달됩니다.
#
# CLI 뷰 플래그(--lateral, --medial, --front, --heel, --top, --bottom)를
# 하나라도 주면 이 폴더 탐색을 건너뛰고 그 사진들만 씁니다.
```

- [ ] **Step 4: `part_survey` 스텝을 `PIPELINE_STEPS` 맨 앞에 넣는다**

`PIPELINE_STEPS: list[dict] = [` 바로 다음에 삽입한다.

```python
    {
        "step": 1,
        "name": "part_survey",
        "description": "부품 관찰 - 멀티뷰 실물 사진 → 부품 명세서",
        "prompt": (
            """{
                "persona": "실물을 보고 재단 부품을 읽어내는 신발 패턴 설계자",
                "input": [
                    "같은 신발 한 켤레를 여러 각도에서 찍은 실물 사진들. 각 사진 앞에 '[사진 N] 각도' 형태의 라벨이 붙어 있어",
                    "라벨이 '파일명: ...' 형태면 파일명으로 각도를 짐작하고, 짐작이 안 되면 사진을 보고 판단해"
                ],
                "task": [
                    "이 신발의 Upper(MIDSOLE 라인 위쪽)를 재단 부품 단위로 읽어서 명세서를 작성해",
                    "***이미지를 만들지 말고 텍스트로만 답해***",
                    "다음 단계에서 이 명세서를 체크리스트로 쓸 거야. 하나씩 대조할 수 있게 구체적으로 써"
                ],
                "survey": [
                    "부품 목록: 패널·오버레이·보강재를 하나씩 이름 붙여 나열하고, 각각의 재질과 색을 적어",
                    "부품 경계: 각 부품이 어디서 시작해 어디서 끝나는지, 어느 부품과 어디서 만나는지 적어",
                    "재봉선: 부품 경계마다 실이 몇 줄인지(싱글/더블), 박음질이 직선인지 지그재그인지 적어",
                    "아일릿: 끈구멍이 한쪽에 몇 개인지 세고, 보강재가 있는지, 간격이 균일한지 적어",
                    "무늬: 메쉬·천공·엠보싱·니트 조직이 어느 부품에 있는지, 대략 몇 개가 어떤 배치로 있는지 적어",
                    "글자·로고: 어디에 무슨 글자가 어떤 크기로 있는지 적어"
                ],
                "coverage": [
                    "***항목마다 어느 라벨의 사진에서 확인했는지 같이 적어***",
                    "***어떤 사진으로도 확인하지 못한 부위는 '미확인'이라고 분명히 적어. 추측해서 채우지 마***",
                    "안쪽 측면, 앞코, 뒤꿈치, 발등 위는 특히 사진에 있는지 먼저 확인하고, 없으면 미확인으로 남겨",
                    "**명세서 맨 끝에 '미확인 목록'을 따로 모아서 정리해**"
                ],
                "exclude": [
                    "SOLE에 해당하는 모든 부분(MIDSOLE, OUTSOLE, 밑창, 에어유닛, 솔 옆면)은 명세서에서 제외",
                    "TONGUE(설포), LACE(신발끈), 신발 내부, 깔창도 제외"
                ],
                "caution": [
                    "***추측 금지. 사진에서 실제로 본 것만 적어***",
                    "**미확인 항목을 숨기지 마. 미확인 목록이 다음 단계에서 공백으로 남길 자리야**",
                    "일반적인 신발이 보통 어떻게 생겼는지가 아니라, 이 사진 속 신발이 실제로 어떤지를 적어"
                ]
            }"""
        ),
        "image_path": SHOE_PHOTO_BASE,
        "guide_image_path": None,
        "max_images": None,
        "response_modalities": ["TEXT"],
        "save_output": True,
    },
```

- [ ] **Step 5: `pattern_unfold` 스텝을 고친다**

`"step": 1,` / `"name": "pattern_unfold",`인 dict에서 아래를 바꾼다.

`"step": 1,` → `"step": 2,`

`"input"` 배열 전체를 교체한다. 기존:

```python
                "input": [
                    "첫번째 사진: 신발 실물 사진 (사이드뷰)",
                    "두번째 사진: 실물을 펼쳐 놓을 가이드라인(틀)"
                ],
```

교체 (앞에 `priority` 블록을 함께 넣는다):

```python
                "priority": [
                    "***아래 규칙들이 서로 부딪히면 이 순서대로 이겨. 위에 있는 게 항상 우선이야***",
                    "1순위 — 실물 사진과 앞 단계 명세서에 근거가 있는 것만 그린다. 근거가 없으면 공백으로 남긴다",
                    "2순위 — 부품 경계, 재봉선, 아일릿 위치와 개수, 무늬 배치는 실물 비율 그대로 옮긴다. 가이드라인에 맞추려고 늘리거나 줄이거나 옮기지 않는다",
                    "3순위 — 패턴의 바깥 재단선만 가이드라인 형태에 맞춘다",
                    "4순위 — 가이드라인 안쪽을 채운다",
                    "***아래 다른 항목에 '반드시', '절대', '실패야' 같은 강한 표현이 있어도 이 순서를 뒤집지 못해***"
                ],
                "input": [
                    "앞쪽 사진들: 같은 신발을 여러 각도에서 찍은 실물 사진. 각 사진 앞에 '[사진 N] 각도' 라벨이 붙어 있어",
                    "그중 '바깥쪽 측면(lateral)' 라벨이 붙은 사진이 기준 사진이야. 전체 형태와 비율은 이 사진을 따라. 그 라벨이 없으면 바깥쪽 옆면이 가장 잘 보이는 사진을 기준으로 삼아",
                    "가이드라인 이미지: 이번 요청에 함께 넣은 2D 펼침 가이드라인(틀)",
                    "앞 단계에서 작성한 부품 명세서: 이번 결과물이 지켜야 할 체크리스트야"
                ],
                "multiview_rule": [
                    "기준 사진에 안 보이는 부위는 다른 각도 사진에서 근거를 찾아. 안쪽면은 '안쪽 측면(medial)', 발등 위는 '위에서 본 모습(top)' 사진을 봐",
                    "***어느 사진에도 없는 부위는 상상해서 만들지 말고 공백으로 남겨. 사진이 부족한 건 지어낼 이유가 아니야***",
                    "**앞 단계 명세서에서 '미확인'이라고 적힌 부위가 바로 공백으로 남길 자리야**",
                    "각도가 달라 같은 부품이 다르게 보이면, 그 부품이 가장 정면으로 크게 찍힌 사진을 기준으로 삼아",
                    "사진에 반대쪽 짝이 같이 찍혀 있으면 무시하고, 기준 사진과 같은 쪽 신발만 펼쳐"
                ],
```

`"task"` 배열의 세 줄을 교체한다. 기존:

```python
                    "첫번째 사진의 Upper를 3D 입체라고 생각했을때, 실제로 뜯어서 평면에 펼쳐 놓은 모습을 두번째 사진의 라인에 정확히 맞춰서 보여줘.",
                    "첫번째 사진에서 MIDSOLE 라인 위로 모든 부분을 **추가/삭제 없이** 두번째 사진의 가이드라인에 맞게 펼쳐줘",
                    "***새로 그리거나 도면·일러스트로 바꾸지 말고***, 첫번째 사진의 갑피 '실물 그대로'를 평평하게 펴서 놓은 실사 결과물이어야 해"
```

교체:

```python
                    "실물 사진의 Upper를 3D 입체라고 생각했을때, 실제로 뜯어서 평면에 펼쳐 놓은 모습을 가이드라인 이미지의 라인에 맞춰서 보여줘.",
                    "실물 사진에서 MIDSOLE 라인 위로 모든 부분을 **추가/삭제 없이** 가이드라인에 맞게 펼쳐줘",
                    "***새로 그리거나 도면·일러스트로 바꾸지 말고***, 실물 사진의 갑피 '실물 그대로'를 평평하게 펴서 놓은 실사 결과물이어야 해"
```

`"fit_rule"` 배열의 두 줄을 교체한다. 기존:

```python
                    "***두번째 사진의 가이드라인이 곧 최종 재단선이야. 그 선 안쪽만 패턴이고, 선 바깥에는 아무것도 없어야 해***",
```

교체:

```python
                    "가이드라인은 패턴의 '바깥 재단선' 형태를 정하는 기준이야. 그 선 안쪽만 패턴이고, 선 바깥에는 아무것도 없어야 해",
```

기존:

```python
                    "**가이드라인 안쪽은 실물에 실제로 있는 부분으로 빈틈없이 꽉 채워**",
```

교체:

```python
                    "가이드라인 안쪽은 실물에 실제로 있는 부분으로 채워. 다만 이건 4순위라, 1~3순위와 부딪히면 채우지 말고 비워둬",
```

`"task_rule"` 배열의 한 줄을 교체한다. 기존:

```python
                    "**발등 부위는 가이드라인의 라인 '중앙에 완전 밀착되게' 펼쳐줘**",
```

교체:

```python
                    "발등 부위는 가이드라인 라인 중앙에 맞춰 펼쳐줘. 다만 실물의 부품 경계나 아일릿 간격을 바꿔가면서까지 맞추지는 마",
```

`"task_rule"` 배열의 한 줄을 교체한다. 기존:

```python
                    "**실물 사진의 색상, 재질, 질감, 광택, 글자, 구멍, 재봉선, 윤곽등 모든 특징을 *추가/삭제 없이 오차없이* 그대로 유지한 채 펼쳐야해**",
```

교체:

```python
                    "**실물 사진의 색상, 재질, 질감, 광택, 글자, 구멍, 재봉선, 윤곽등 모든 특징을 *추가/삭제 없이 오차없이* 그대로 유지한 채 펼쳐야해. 앞 단계 명세서에 적힌 부품·재봉선·무늬가 기준이야**",
```

`"guideline_rule"` 배열의 첫 줄을 교체한다. 기존:

```python
                    "***두번째 사진의 가이드라인은 위치와 형태를 맞추기 위한 참고용일 뿐, 결과물에는 절대 보이면 안돼***",
```

교체:

```python
                    "***가이드라인 이미지는 위치와 형태를 맞추기 위한 참고용일 뿐, 결과물에는 절대 보이면 안돼***",
```

`"empty_rule"` 배열의 한 줄을 교체한다. 기존:

```python
                    "**첫번째 사진에서 근거를 찾을 수 없는 부분은 전부 아무것도 없는 흰 공백으로 남겨**",
```

교체:

```python
                    "**어느 실물 사진에서도 근거를 찾을 수 없는 부분은 전부 아무것도 없는 흰 공백으로 남겨**",
```

`"caution"` 배열의 마지막 항목 앞에 한 줄을 더한다.

```python
                    "**앞 단계 명세서의 부품 목록·아일릿 개수·무늬 배치와 결과물이 맞는지 출력 전에 대조해**",
```

마지막으로 이 스텝의 설정 키를 바꾼다. 기존:

```python
        "image_path": SHOE_PHOTO_BASE,
        "guide_image_path": GUIDELINE_BASE,
        "max_images": 1,
        "save_output": True,
```

교체:

```python
        # ponytail: 신발 사진을 재전송하지 않고 앞 스텝의 채팅 히스토리에 의존합니다.
        #           원본 밀착도가 부족하면 Pipeline._initial_images에서 꺼내 재주입하세요.
        "image_path": None,
        "guide_image_path": GUIDELINE_BASE,
        "save_output": True,
```

- [ ] **Step 6: `line_art_conversion` 스텝을 고친다**

`"step": 2,` → `"step": 3,`

`"input"` 배열을 교체한다. 기존:

```python
            "input": [
                "앞 단계에서 펼쳐낸 2D 패턴 이미지"
            ],
```

교체:

```python
            "input": [
                "앞 단계에서 펼쳐낸 2D 패턴 이미지",
                "그 앞 단계에서 작성한 부품 명세서"
            ],
```

`"detail_rule"` 배열 다음, `"caution"` 배열 앞에 새 배열을 넣는다.

```python
            "survey_rule":
                [
                    "**부품 명세서에 적힌 부품 목록, 아일릿 개수, 재봉선 종류(싱글/더블·직선/지그재그), 무늬 배치와 대조하면서 그려**",
                    "***명세서에 '미확인'이라고 적힌 부위는 선을 그리지 말고 비워둬***",
                    "명세서에 없는 부품이나 무늬를 새로 만들어 넣지 마"
                ],
```

- [ ] **Step 7: 테스트를 돌려 통과를 확인한다**

Run: `uv run python -m unittest discover -s tests -t . -v`
Expected: PASS (34 tests)

- [ ] **Step 8: 파이프라인이 임포트되는지 확인한다**

Run: `uv run python -c "from config.prompts import PIPELINE_STEPS; print([ (s['step'], s['name']) for s in PIPELINE_STEPS ])"`
Expected: `[(1, 'part_survey'), (2, 'pattern_unfold'), (3, 'line_art_conversion')]`

- [ ] **Step 9: 커밋한다**

```bash
git add tests/test_prompts_structure.py config/prompts.py
git commit -m "✅ 관찰 스텝 추가 및 실물 우선 규칙 순위 도입"
```

---

### Task 5: 문서와 손 확인

**Files:**
- Modify: `README.md`

**Interfaces:**
- Consumes: Task 1~4 전부
- Produces: 없음

- [ ] **Step 1: `README.md` 상단 개요를 고친다**

기존:

```
[신발 실물 사진(사이드뷰) + 2D 펼침 가이드라인(틀) + 프롬프트]
    → Gemini API (패턴 펼치기)
    → output/ 저장
```

교체:

```
[신발 실물 사진(여러 각도)]
    → Gemini API (부품 관찰)      → 부품 명세서 텍스트
    → Gemini API (패턴 펼치기)    → 2D 전개 패턴 이미지
    → Gemini API (라인 아트 변환) → 라인 아트 이미지
    → output/ 저장
```

문서 두 번째 줄 `현재는 **패턴 펼치기 단일 스텝**만 실행합니다.`를 교체한다.

```
관찰 → 펼치기 → 라인 아트 3스텝을 같은 채팅 세션에서 순차 실행합니다.
```

- [ ] **Step 2: `README.md`의 폴더 구조 블록을 고친다**

기존:

```
├── images/                  # 입력 이미지 (전부 여기 바로 아래에 둡니다)
│   ├── 가이드라인.jpg        # 파일명에 '가이드라인' 포함 → 펼칠 틀로 자동 인식
│   ├── 나이키 탄준.jpg       # 나머지 이미지 = 신발 실물 사이드뷰
│   └── 뉴발란스 992.png
```

교체:

```
├── images/                  # 입력 이미지
│   ├── 가이드라인.jpg        # 파일명에 '가이드라인' 포함 → 펼칠 틀로 자동 인식
│   ├── 나이키_탄준/          # 모델 폴더. 안의 사진이 전부 함께 전달됩니다
│   │   ├── lateral.webp
│   │   └── medial.webp
│   └── 뉴발란스_992/
```

바로 아래 문단도 교체한다. 기존:

```
실행하면 가이드라인을 뺀 이미지 목록이 번호와 함께 뜹니다. 번호로 하나를 고르거나
`all`을 입력하면 전부 순서대로 실행되고, 출력 폴더는 각 파일명으로 만들어집니다.
```

교체:

```
실행하면 모델 폴더 목록이 번호와 함께 뜹니다. 번호로 하나를 고르거나 `all`을 입력하면
전부 순서대로 실행되고, 출력 폴더는 각 폴더명으로 만들어집니다.

`images/` 바로 아래에 가이드라인이 아닌 낱개 이미지가 있으면 "파일 하나 고르기" 모드로
동작해 멀티뷰가 켜지지 않습니다. 신발 사진은 반드시 모델 폴더 안에 넣으세요.
```

- [ ] **Step 3: `README.md`의 데이터 흐름 표를 3스텝으로 고친다**

`### 패턴 펼치기 (단일 스텝)` 제목부터 `### Step 2 — 라인 아트 변환` 표 끝까지를 통째로 교체한다.

```markdown
### Step 1 — 부품 관찰

| 항목 | 내용 |
|------|------|
| **입력 이미지** | 뷰 플래그로 준 사진들, 또는 선택한 모델 폴더 안의 사진 전부 |
| **라벨** | 각 사진 앞에 `[사진 N] 바깥쪽 측면(lateral)` 형태의 텍스트를 붙여 전달 |
| **프롬프트** | Upper를 재단 부품 단위로 읽어 명세서 작성. 확인 못 한 부위는 '미확인'으로 명시 |
| **API 입력** | `[라벨, 사진, 라벨, 사진, ..., 프롬프트]` |
| **응답 모달리티** | 이 스텝만 `["TEXT"]` |
| **출력** | 부품 명세서 텍스트 |

### Step 2 — 패턴 펼치기

| 항목 | 내용 |
|------|------|
| **입력** | 가이드라인 이미지 + Step 1 명세서 (신발 사진은 채팅 히스토리에 남아 있음) |
| **프롬프트** | 실물 우선 4단계 규칙에 따라 Upper를 3D→2D로 전개 |
| **API 입력** | `[가이드라인_이미지, Step1_명세서, 프롬프트]` |
| **출력** | 2D 전개 패턴 이미지 |

### Step 3 — 라인 아트 변환

| 항목 | 내용 |
|------|------|
| **입력** | Step 2가 생성한 패턴 이미지 + Step 1 명세서 |
| **프롬프트** | 모든 선을 구분해 라인 아트로. 아일릿 개수와 무늬 배치를 명세서와 대조 |
| **API 입력** | `[Step2_생성_이미지, Step1_명세서, 프롬프트]` |
| **출력** | 라인 아트 패턴 이미지 |
```

- [ ] **Step 4: `README.md`의 실행 예시에 뷰 플래그를 넣는다**

기존 블록에서 이 부분을 찾는다.

```bash
# 이미지 직접 지정 (선택 과정 건너뛰기)
./run.sh --shoe-image "images/나이키 탄준.jpg" --guide-image "images/가이드라인.jpg"
```

바로 위에 새 예시를 넣는다.

```bash
# 각도별로 직접 지정 (한 켤레 멀티뷰). 준 것만 쓰이고, 빠진 각도가 있어도 됩니다.
./run.sh --lateral shoes/v2k/lat.webp --medial shoes/v2k/med.webp --top shoes/v2k/top.webp

# 뷰 플래그는 항상 lateral → medial → front → heel → top → bottom 순으로 전달됩니다.
# 플래그를 하나라도 주면 --shoe-image와 폴더 선택은 무시됩니다.
```

- [ ] **Step 5: 전체 테스트를 돌린다**

Run: `uv run python -m unittest discover -s tests -t . -v`
Expected: PASS (34 tests)

- [ ] **Step 6: `images/`를 정리한다**

낱개 신발 사진 10개를 모델 폴더로 옮기고, 쓰지 않는 빈 폴더를 지운다.

```bash
cd images
for f in *.webp; do
    [ -e "$f" ] || continue
    name="${f%.*}"
    mkdir -p "$name"
    git mv "$f" "$name/lateral.webp" 2>/dev/null || mv "$f" "$name/lateral.webp"
done
cd ..
git rm -r --quiet images/step1 images/step2 images/step3
```

Run: `find images -maxdepth 2 | sort`
Expected: `images/가이드라인.jpg`와 모델 폴더 10개, 각 폴더 안에 `lateral.webp` 하나씩. `step1`/`step2`/`step3`는 없어야 한다.

- [ ] **Step 7: 실제로 한 번 돌려본다**

Run: `uv run python main.py --verbose --lateral "images/nike_v2k_run_opp1/lateral.webp" --guide-image "images/가이드라인.jpg" 2>&1 | tee /tmp/multiview-run.log | tail -40`

Expected:
- `API REQUEST PARTS` 로그의 Step 1에 `[사진 1] 바깥쪽 측면(lateral)` 텍스트 파트와 이미지가 보인다
- `output/lateral/step_01_part_survey.md`가 생기고 안에 명세서 텍스트가 있다
- Step 2의 `API REQUEST PARTS`에 `[Previous Step 1 Output]`으로 시작하는 명세서 텍스트가 들어 있다
- `output/lateral/step_02_pattern_unfold_generated_01.png`가 생긴다

실패하면 로그에서 다음을 확인한다.
- `TEXT 응답을 요청했지만 텍스트가 비어 있습니다` 경고가 있으면 `send_message(config=...)`가 먹지 않은 것이다. `services/gemini_client.py`의 `send_message` 호출을 확인한다.
- 이미지가 하나도 안 들어갔으면 `handlers/image_handler.py`의 `build_labeled_parts`를 확인한다.

- [ ] **Step 8: 커밋한다**

```bash
git add README.md images
git commit -m "📝 멀티뷰 3스텝 문서화 및 images/ 모델 폴더 정리"
```

---

## Self-Review

**Spec coverage**

| 스펙 항목 | 담당 |
|---|---|
| 1-1 뷰 플래그 6개, 고정 전송 순서, 라벨 문자열 | Task 1 |
| 1-1 run_label 유도, `--shoe-image` 무시 경고 | Task 1 |
| 1-2 모델 폴더 재편, 빈 step 폴더 삭제 | Task 5 Step 6 |
| 1-3 라벨 파트 조립, 폴더는 파일명 라벨 | Task 2 |
| 2 3스텝 구조, 스텝 2는 히스토리 의존 | Task 4 |
| 2 `response_modalities` 스텝 키 | Task 3, Task 4 |
| 3 스텝 1 명세서 프롬프트 | Task 4 Step 4 |
| 3 스텝 2 priority·input·multiview_rule·기존 규칙 약화 | Task 4 Step 5 |
| 3 스텝 3 명세서 대조 | Task 4 Step 6 |
| 4 검증 항목 | Task 1 Step 8, Task 5 Step 7 |
| 5 `--lateral` 없음 경고 | Task 1 Step 6 |
| 5 없는 파일 → `parser.error` | Task 1 Step 4 |
| 5 TEXT 요청했는데 빈 응답 → 경고 | Task 3 Step 5 |
| 5 `run.sh` 사전 검사 생략 | Task 1 Step 7 |
| 파일별 변경 표 10개 파일 | Task 1~5 전부 |

**타입 일관성**

- `view_images`의 타입은 `list[tuple[str, Path]]`로 Task 1(생성) → Task 2(소비) → Task 4(테스트) 전부 동일하다.
- 라벨 문자열은 `utils.cli.VIEW_FLAGS`가 단일 출처이고, `tests/test_prompts_structure.py`가 프롬프트 본문과 대조해 어긋나면 실패한다.
- `build_response_config`의 반환은 `GenerateContentConfig | None`이고, `GeminiClient.send`의 `config` 인자와 `chat.send_message(config=)`가 같은 타입을 받는다.
- `ImageHandler.LABEL_FORMAT`은 Task 2에서 정의하고 Task 2 테스트만 참조한다.

**남은 위험**

- `chats.Chat.send_message(config=...)`가 세션 config를 완전히 대체하는지 부분 병합하는지는 실행해봐야 안다. Task 5 Step 7에서 확인하고, 명세서가 비면 그 자리에서 잡는다.
- 스텝 2가 채팅 히스토리에 의존하는 선택은 실측 전이다. 밀착도가 부족하면 `config/prompts.py`의 `ponytail:` 주석이 가리키는 대로 `Pipeline._initial_images` 재주입으로 올린다.
