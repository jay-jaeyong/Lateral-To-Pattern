"""services/utils/images.py 저수준 이미지 유틸 테스트."""

import tempfile
import unittest
from pathlib import Path

from PIL import Image

from services.utils import images


class ImagesUtilTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)

    def test_load_converts_to_rgb(self):
        """load()는 반드시 RGB로 변환한다. 이게 빠지면 SDK가 인코딩하는
        바이트가 달라지고 골든이 깨진다."""
        path = self.tmp / "gray.png"
        Image.new("L", (4, 4), 128).save(path)
        self.assertEqual(images.load(path).mode, "RGB")

    def test_load_does_not_resize(self):
        path = self.tmp / "a.png"
        Image.new("RGB", (7, 11), (1, 2, 3)).save(path)
        self.assertEqual(images.load(path).size, (7, 11))

    def test_load_missing_file_raises(self):
        with self.assertRaises(FileNotFoundError):
            images.load(self.tmp / "없음.png")

    def test_load_unsupported_extension_raises(self):
        path = self.tmp / "a.txt"
        path.write_text("x")
        with self.assertRaises(ValueError):
            images.load(path)

    def test_is_guideline_file_matches_korean_and_english(self):
        self.assertTrue(images.is_guideline_file(Path("가이드라인_회전5도.png")))
        self.assertTrue(images.is_guideline_file(Path("GUIDELINE.png")))
        self.assertFalse(images.is_guideline_file(Path("lateral.png")))

    def test_list_image_files_can_exclude_guideline(self):
        for name in ("lateral.png", "medial.png", "가이드라인.png"):
            Image.new("RGB", (2, 2)).save(self.tmp / name)
        (self.tmp / "notes.txt").write_text("x")

        every = images.list_image_files(self.tmp)
        without = images.list_image_files(self.tmp, exclude_guideline=True)

        self.assertEqual(len(every), 3)
        self.assertEqual([p.name for p in without], ["lateral.png", "medial.png"])

    def test_find_guideline_returns_the_guideline_file(self):
        for name in ("lateral.png", "가이드라인.png"):
            Image.new("RGB", (2, 2)).save(self.tmp / name)
        found = images.find_guideline(self.tmp)
        self.assertIsNotNone(found)
        self.assertEqual(found.name, "가이드라인.png")

    def test_label_wraps_in_brackets(self):
        self.assertEqual(images.label("바깥쪽 측면(lateral)"), "[바깥쪽 측면(lateral)]")
        self.assertEqual(images.LABEL_FORMAT, "[{label}]")


if __name__ == "__main__":
    unittest.main()
