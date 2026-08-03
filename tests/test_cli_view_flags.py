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
        self.assertEqual(labels["front"], "쿼터 프론트 뷰(quarter front)")
        self.assertEqual(labels["heel"], "쿼터 힐 뷰(quarter heel)")
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

    def test_missing_shoe_image_exits(self):
        # R4/S4: --shoe-image with nonexistent path must exit
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            with self.assertRaises(SystemExit):
                parse_args(["--shoe-image", str(self.tmp / "nope.png")])
        self.assertIn("--shoe-image", stderr.getvalue())

    def test_missing_guide_image_exits(self):
        # R4/S4: --guide-image with nonexistent path must exit
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            with self.assertRaises(SystemExit):
                parse_args(["--guide-image", str(self.tmp / "nope.png")])
        self.assertIn("--guide-image", stderr.getvalue())


class DeriveRunLabelTest(unittest.TestCase):
    def test_uses_first_entry_stem(self):
        views = [("바깥쪽 측면(lateral)", Path("/a/b/nike_v2k.png"))]
        self.assertEqual(derive_run_label(views), "nike_v2k")

    def test_empty_gives_none(self):
        self.assertIsNone(derive_run_label([]))

    def test_view_flag_stem_uses_parent_directory(self):
        # R5: /a/b/lateral.png should use parent directory "b"
        views = [("바깥쪽 측면(lateral)", Path("/a/b/lateral.png"))]
        self.assertEqual(derive_run_label(views), "b")

    def test_directory_named_after_view_flag_uses_directory_name(self):
        # R5: a directory named "lateral" should return "lateral", not parent "images"
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            lateral_dir = Path(tmp) / "lateral"
            lateral_dir.mkdir()
            views = [("바깥쪽 측면(lateral)", lateral_dir)]
            self.assertEqual(derive_run_label(views), "lateral")


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
