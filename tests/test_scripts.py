"""스크립트 인자 처리 테스트. API는 호출하지 않는다."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from scripts import _common, run_all, run_service


class LabelTest(unittest.TestCase):
    def test_repeat_one_has_no_suffix(self):
        self.assertEqual(_common.run_labels("shoe_v7", 1), ["shoe_v7"])

    def test_repeat_many_gets_numbered_suffixes(self):
        self.assertEqual(
            _common.run_labels("shoe_v7", 3),
            ["shoe_v7-1", "shoe_v7-2", "shoe_v7-3"],
        )

    def test_derive_label_uses_the_folder_name_for_a_directory(self):
        self.assertEqual(_common.derive_label(Path("inputs/photos/adidas_ORKETRO")),
                         "adidas_ORKETRO")

    def test_derive_label_uses_the_stem_for_a_file(self):
        self.assertEqual(_common.derive_label(Path("inputs/color_patterns/a_color.png")),
                         "a_color")


class RunServiceTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.color = self.tmp / "a_color.png"
        Image.new("RGB", (4, 4)).save(self.color)

    def test_unknown_service_name_exits_nonzero(self):
        with self.assertRaises(SystemExit):
            run_service.main(["nope", "--input", str(self.color)])

    def test_sketch_pattern_runs_once_per_repeat(self):
        calls = []
        with patch.object(run_service, "SERVICES", {
            "sketch_pattern": type("M", (), {
                "run": staticmethod(lambda path, out, archive=None: calls.append(out) or path)
            })
        }):
            run_service.main([
                "sketch_pattern", "--input", str(self.color),
                "--out", str(self.tmp / "outputs"), "--repeat", "2",
            ])
        self.assertEqual(len(calls), 2)


class RunAllTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.shoe = self.tmp / "shoe"
        self.shoe.mkdir()
        Image.new("RGB", (4, 4)).save(self.shoe / "lateral.png")

    def test_color_pattern_output_path_is_handed_to_sketch_pattern(self):
        """서비스 간 핸드오프는 파일이다."""
        produced = self.tmp / "produced.png"
        Image.new("RGB", (4, 4)).save(produced)
        received = []

        fake_cp = type("M", (), {"run": staticmethod(
            lambda shoe_dir, guide, out, archive=None: produced)})
        fake_sp = type("M", (), {"run": staticmethod(
            lambda path, out, archive=None: received.append(path) or path)})

        with patch.object(run_all, "color_pattern", fake_cp), \
             patch.object(run_all, "sketch_pattern", fake_sp):
            run_all.main(["--input", str(self.shoe), "--out", str(self.tmp / "outputs")])

        self.assertEqual(received, [produced])


if __name__ == "__main__":
    unittest.main()
