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

    def test_initial_references_precede_guide_and_previous_text(self):
        reference = Image.new("RGB", (4, 4), "red")
        guide = make_png(self.tmp / "guide.png")

        parts = build_step_parts(
            step_num=2,
            prompt="PROMPT",
            image_path=None,
            prev_images=[],
            prev_texts=["SPEC"],
            guide_image_path=guide,
            initial_reference_parts=["[사진 1] 바깥쪽 측면(lateral)", reference],
        )

        self.assertEqual(parts[0], "[사진 1] 바깥쪽 측면(lateral)")
        self.assertIs(parts[1], reference)
        self.assertEqual(parts[2], "[가이드라인]")
        self.assertIsInstance(parts[3], Image.Image)
        self.assertEqual(parts[4], "[Previous Step 1 Output]\nSPEC")
        self.assertEqual(parts[5], "PROMPT")

    def test_initial_reference_parts_are_copied_before_assembly(self):
        reference = Image.new("RGB", (4, 4), "red")
        initial_reference_parts = ["[사진 1] 바깥쪽 측면(lateral)", reference]

        parts = build_step_parts(
            step_num=2,
            prompt="PROMPT",
            image_path=None,
            prev_images=[],
            prev_texts=[],
            initial_reference_parts=initial_reference_parts,
        )

        parts.pop(0)
        self.assertEqual(
            initial_reference_parts,
            ["[사진 1] 바깥쪽 측면(lateral)", reference],
        )


if __name__ == "__main__":
    unittest.main()
