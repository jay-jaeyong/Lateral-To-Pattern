"""라벨이 붙은 이미지 파트 조립 테스트."""

import re
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
        self.assertEqual(parts[0], "[바깥쪽 측면(lateral)]")
        self.assertIsInstance(parts[1], Image.Image)
        self.assertEqual(parts[2], "[안쪽 측면(medial)]")
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
        self.assertEqual(parts[0], "[안쪽 측면(medial)]")
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
        self.assertEqual(parts[0], "[파일명: 01_lateral]")
        self.assertEqual(parts[2], "[파일명: 02_medial]")
        self.assertEqual(parts[-1], "PROMPT")

    def test_max_images_truncates(self):
        folder = self.tmp / "nike_v2k"
        folder.mkdir()
        make_png(folder / "01_lateral.png")
        make_png(folder / "02_medial.png")
        parts = ImageHandler._load_dir_images(folder, "PROMPT", max_images=1)
        self.assertEqual(len(parts), 3)
        self.assertEqual(parts[0], "[파일명: 01_lateral]")


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
        self.assertEqual(parts[0], "[바깥쪽 측면(lateral)]")
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


class GuideLabelTest(unittest.TestCase):
    """가이드라인에 라벨이 없으면 실물 사진의 '[사진 N]' 중 하나로 읽힙니다."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def test_guide_image_is_labelled_and_unnumbered(self):
        from core._parts_builder import GUIDE_LABEL

        guide_dir = self.tmp / "guides"
        guide_dir.mkdir()
        make_png(guide_dir / "가이드라인.png")

        parts = build_step_parts(
            step_num=2,
            prompt="PROMPT",
            image_path=None,
            prev_images=[],
            prev_texts=[],
            guide_image_path=guide_dir,
        )
        self.assertIn(GUIDE_LABEL, parts)
        # "[사진 N]" 번호 형식이면 안 됩니다. 설명 문구에 '사진'이 들어가는 건 무방합니다.
        self.assertIsNone(re.search(r"\[사진 \d", GUIDE_LABEL))
        # 라벨 바로 뒤에 가이드라인 이미지가 와야 합니다.
        self.assertIsInstance(parts[parts.index(GUIDE_LABEL) + 1], Image.Image)
