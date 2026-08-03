"""가이드라인 경로 검증과 스텝 적용 대상 테스트.

--guide-image는 가이드라인을 실제로 쓰는 스텝에만 적용되어야 하고,
플래그를 생략해 기본 경로가 쓰이는 경우에도 같은 검증을 받아야 합니다.
"""

import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from config.prompts import PIPELINE_STEPS
from utils.cli import apply_image_overrides, guide_path_problem, parse_args


def make_png(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (4, 4), (0, 0, 0)).save(path)
    return path


class GuidePathProblemTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def test_missing_path_is_a_problem(self):
        self.assertIsNotNone(guide_path_problem(self.tmp / "nope"))

    def test_plain_file_is_fine_whatever_its_name(self):
        self.assertIsNone(guide_path_problem(make_png(self.tmp / "template.png")))

    def test_folder_with_a_guideline_is_fine(self):
        folder = self.tmp / "with"
        make_png(folder / "가이드라인.png")
        self.assertIsNone(guide_path_problem(folder))

    def test_folder_without_a_guideline_is_a_problem(self):
        folder = self.tmp / "without"
        make_png(folder / "template.png")
        problem = guide_path_problem(folder)
        self.assertIsNotNone(problem)
        self.assertIn("가이드라인", problem)

    def test_empty_folder_is_a_problem(self):
        folder = self.tmp / "empty"
        folder.mkdir()
        self.assertIsNotNone(guide_path_problem(folder))


class GuideOverrideTargetsTheRightStepTest(unittest.TestCase):
    def test_override_skips_steps_that_take_no_guideline(self):
        # 관찰 스텝은 guide_image_path가 None입니다. 여기에 틀이 들어가면
        # 모델이 2D 틀을 신발 사진의 일부로 관찰하게 됩니다.
        steps = apply_image_overrides(PIPELINE_STEPS, guide_image="/g/mine.jpg")
        by_name = {step["name"]: step for step in steps}
        self.assertIsNone(by_name["part_survey"]["guide_image_path"])
        self.assertIsNone(by_name["line_art_conversion"].get("guide_image_path"))

    def test_override_reaches_the_step_that_unfolds(self):
        steps = apply_image_overrides(PIPELINE_STEPS, guide_image="/g/mine.jpg")
        by_name = {step["name"]: step for step in steps}
        self.assertEqual(by_name["pattern_unfold"]["guide_image_path"], Path("/g/mine.jpg"))

    def test_defaults_are_untouched_without_the_flag(self):
        steps = apply_image_overrides(PIPELINE_STEPS)
        by_name = {step["name"]: step for step in steps}
        self.assertIsNone(by_name["part_survey"]["guide_image_path"])
        self.assertIsNotNone(by_name["pattern_unfold"]["guide_image_path"])


class ParseArgsGuideValidationTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def parse(self, argv):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            try:
                return parse_args(argv), stderr.getvalue()
            except SystemExit:
                return None, stderr.getvalue()

    def test_folder_without_a_guideline_exits(self):
        folder = self.tmp / "without"
        make_png(folder / "template.png")
        args, err = self.parse(["--guide-image", str(folder)])
        self.assertIsNone(args)
        self.assertIn("--guide-image", err)

    def test_folder_with_a_guideline_passes(self):
        folder = self.tmp / "with"
        make_png(folder / "guideline.png")
        args, _err = self.parse(["--guide-image", str(folder)])
        self.assertIsNotNone(args)


if __name__ == "__main__":
    unittest.main()
