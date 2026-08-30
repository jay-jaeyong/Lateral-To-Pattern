"""신발 사진 입력 해석 테스트. 모드 추측 없이 규약을 요구한다."""

import tempfile
import unittest
from pathlib import Path

from PIL import Image

from services.color_pattern import photo_input


class ResolveTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.shoe = Path(self._tmp.name) / "adidas_ORKETRO"
        self.shoe.mkdir()

    def _make(self, name: str):
        Image.new("RGB", (4, 4)).save(self.shoe / name)

    def test_resolve_returns_views_in_declared_order_not_file_order(self):
        """API 전송 순서는 VIEW_LABELS의 순서다. 파일 시스템 순서가 아니다."""
        self._make("top.png")
        self._make("lateral.png")
        self._make("medial.png")
        labels = [label for label, _ in photo_input.resolve(self.shoe)]
        self.assertEqual(labels, [
            "바깥쪽 측면(lateral)",
            "안쪽 측면(medial)",
            "위에서 본 모습(top)",
        ])

    def test_resolve_prefers_extensions_in_order(self):
        for ext in ("png", "webp"):
            Image.new("RGB", (4, 4)).save(self.shoe / f"lateral.{ext}")
        (_, path), = photo_input.resolve(self.shoe)
        self.assertEqual(path.suffix, ".webp")

    def test_missing_folder_raises_before_any_api_call(self):
        with self.assertRaises(FileNotFoundError):
            photo_input.resolve(self.shoe.parent / "없는신발")

    def test_folder_without_recognisable_views_raises(self):
        """낱개 파일을 놓고 돌리던 방식은 이제 실패한다. 예전에는 파일 선택
        모드로 조용히 넘어가 라벨 없는 한 장이 되었고, Step 2의 참조 사진도
        함께 사라졌다."""
        Image.new("RGB", (4, 4)).save(self.shoe / "adidas_ORKETRO_color.png")
        with self.assertRaises(FileNotFoundError) as ctx:
            photo_input.resolve(self.shoe)
        self.assertIn("lateral", str(ctx.exception))


class BuildPartsTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.shoe = self.tmp / "shoe"
        self.shoe.mkdir()
        for name in ("lateral.png", "medial.png"):
            Image.new("RGB", (4, 4)).save(self.shoe / name)
        self.guide = self.tmp / "가이드라인.png"
        Image.new("RGB", (4, 4)).save(self.guide)

    def test_survey_parts_are_label_image_pairs_then_prompt(self):
        parts = photo_input.build_survey_parts(photo_input.resolve(self.shoe), "PROMPT")
        self.assertEqual(parts[0], "[바깥쪽 측면(lateral)]")
        self.assertEqual(parts[2], "[안쪽 측면(medial)]")
        self.assertEqual(parts[-1], "PROMPT")
        self.assertEqual(len(parts), 5)

    def test_unfold_parts_are_exactly_the_eight_parts_in_order(self):
        parts = photo_input.build_unfold_parts(
            photo_input.resolve(self.shoe), self.guide, "명세서 본문", "PROMPT"
        )
        self.assertEqual(len(parts), 8)
        self.assertEqual(parts[0], "[바깥쪽 측면(lateral)]")
        self.assertEqual(parts[2], "[안쪽 측면(medial)]")
        self.assertEqual(parts[4], photo_input.GUIDE_LABEL)
        self.assertEqual(parts[6], "[Previous Step 1 Output]\n명세서 본문")
        self.assertEqual(parts[7], "PROMPT")
        self.assertEqual(sum(1 for p in parts if hasattr(p, "mode")), 3)

    def test_guide_label_value_is_unchanged(self):
        """라벨이 없으면 모델이 이 틀을 신발 사진 중 하나로 읽는다."""
        self.assertEqual(
            photo_input.GUIDE_LABEL,
            "[가이드라인] 2D 펼침 틀 — 신발 사진이 아니야",
        )

    def test_unfold_uses_only_the_two_side_views(self):
        """reference_views가 ['lateral', 'medial']인 현 동작을 유지한다."""
        Image.new("RGB", (4, 4)).save(self.shoe / "top.png")
        parts = photo_input.build_unfold_parts(
            photo_input.resolve(self.shoe), self.guide, "s", "PROMPT"
        )
        self.assertNotIn("[위에서 본 모습(top)]", [p for p in parts if isinstance(p, str)])


if __name__ == "__main__":
    unittest.main()
