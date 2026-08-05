"""Step 3에는 이전 단계 텍스트(명세서)를 넣지 않는다는 것을 잠그는 테스트."""

import tempfile
import unittest
from pathlib import Path

from PIL import Image

from config.prompts import PIPELINE_STEPS
from core._parts_builder import build_step_parts


def make_png(path: Path) -> Path:
    Image.new("RGB", (4, 4), (200, 30, 30)).save(path)
    return path


class IncludePrevTextsFlagTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def test_include_prev_texts_false_omits_prev_text(self):
        image = make_png(self.tmp / "step2.png")
        parts = build_step_parts(
            step_num=3,
            prompt="PROMPT",
            image_path=image,
            prev_images=[],
            prev_texts=["명세서 내용"],
            include_prev_texts=False,
        )
        for part in parts:
            if isinstance(part, str):
                self.assertNotIn("명세서 내용", part)

    def test_default_still_includes_prev_text(self):
        image = make_png(self.tmp / "step2.png")
        parts = build_step_parts(
            step_num=3,
            prompt="PROMPT",
            image_path=image,
            prev_images=[],
            prev_texts=["명세서 내용"],
        )
        joined = "\n".join(p for p in parts if isinstance(p, str))
        self.assertIn("명세서 내용", joined)


class Step3ConfigFlagTest(unittest.TestCase):
    def test_step3_disables_include_prev_texts(self):
        step3 = PIPELINE_STEPS[2]
        self.assertEqual(step3["step"], 3)
        self.assertFalse(step3.get("include_prev_texts", True))


if __name__ == "__main__":
    unittest.main()
