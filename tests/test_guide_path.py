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
from core._parts_builder import _load_guide_images
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


class LoadGuideImagesTest(unittest.TestCase):
    """_load_guide_images는 파일만 허용하고 폴더는 거부합니다."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def test_rejects_directory_with_guideline_keyword(self):
        # 회귀 방지: 과거에는 폴더에서 가이드라인을 찾아 사용했습니다.
        # 이제는 폴더가 주어지면 경고하고 []를 반환합니다.
        folder = self.tmp / "guides"
        make_png(folder / "가이드라인.png")
        result = _load_guide_images(folder)
        self.assertEqual(result, [])

    def test_loads_explicit_file(self):
        # 파일 경로가 주어지면 그 파일을 로드합니다.
        guide_file = make_png(self.tmp / "guides" / "가이드라인.png")
        result = _load_guide_images(guide_file)
        self.assertEqual(len(result), 1)
        # Image.Image 객체인지 확인합니다.
        from PIL.Image import Image as PILImage
        self.assertIsInstance(result[0], PILImage)

    def test_returns_empty_for_missing_file(self):
        # 파일이 없으면 []를 반환합니다.
        missing = self.tmp / "nope.png"
        result = _load_guide_images(missing)
        self.assertEqual(result, [])


class ApplyImageOverridesGuideResolutionTest(unittest.TestCase):
    """apply_image_overrides는 디렉터리 가이드라인을 파일로 해석합니다."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def test_directory_override_resolves_to_file(self):
        # 디렉터리를 guide_image로 주면 그 안의 가이드라인 파일로 해석합니다.
        folder = self.tmp / "guides"
        guide_file = make_png(folder / "가이드라인.png")
        steps = apply_image_overrides(PIPELINE_STEPS, guide_image=str(folder))
        by_name = {step["name"]: step for step in steps}
        result = by_name["pattern_unfold"]["guide_image_path"]
        # 결과는 파일 경로여야 합니다.
        self.assertTrue(result.is_file() if result.exists() else result.suffix != "")

    def test_file_override_passes_through_unchanged(self):
        # 파일을 guide_image로 주면 그대로 사용합니다.
        guide_file = make_png(self.tmp / "가이드라인.png")
        steps = apply_image_overrides(PIPELINE_STEPS, guide_image=str(guide_file))
        by_name = {step["name"]: step for step in steps}
        result = by_name["pattern_unfold"]["guide_image_path"]
        self.assertEqual(result, guide_file)


class DefaultGuidelineIsFilepathTest(unittest.TestCase):
    """PIPELINE_STEPS의 Step 2 가이드라인이 파일 경로임을 확인합니다."""

    def test_step_2_guideline_is_file_path(self):
        # 기본 가이드라인은 파일 경로여야 합니다.
        steps = PIPELINE_STEPS
        by_name = {step["name"]: step for step in steps}
        guide_path = by_name["pattern_unfold"]["guide_image_path"]
        self.assertIsNotNone(guide_path)
        path = Path(guide_path) if isinstance(guide_path, str) else guide_path
        # 파일 경로인지 확인: suffix가 있어야 함 (확장자가 있어야 함)
        self.assertNotEqual(path.suffix, "", f"Expected file path with extension, got: {path}")


class PipelineWiringGuideTest(unittest.TestCase):
    """Step 2가 가이드라인 + 기준 사진 2개를 받는지 확인합니다."""

    def test_step_2_gets_labeled_parts(self):
        # Step 2는 reference_views가 설정되어 있어야 합니다.
        by_name = {step["name"]: step for step in PIPELINE_STEPS}
        step_2 = by_name["pattern_unfold"]
        # reference_views가 설정되어 있는지 확인합니다.
        self.assertIn("reference_views", step_2)
        # lateral과 medial이 모두 들어가 있는지 확인합니다.
        self.assertIn("lateral", step_2["reference_views"])
        self.assertIn("medial", step_2["reference_views"])


if __name__ == "__main__":
    unittest.main()
