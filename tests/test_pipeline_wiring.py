"""파이프라인과 config 연결 상태 테스트."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

from PIL import Image

from config.prompts import PIPELINE_STEPS
from core.pipeline import Pipeline
from core.models import StepResponse


def make_test_image(path: Path) -> Path:
    """테스트용 이미지를 생성합니다."""
    Image.new("RGB", (4, 4), (100, 100, 100)).save(path)
    return path


class PipelineWiringTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

        # 테스트용 이미지 생성
        self.shoe_img = make_test_image(self.tmp / "shoe.png")
        self.guide_img = make_test_image(self.tmp / "guide.png")

    def test_step1_receives_text_config(self):
        """Step 1이 TEXT 응답 modality config를 받는지 확인합니다."""
        steps = [
            {
                "step": 1,
                "name": "test_step",
                "description": "test",
                "prompt": "test prompt",
                "image_path": self.shoe_img,
                "response_modalities": ["TEXT"],
                "save_output": False,
            }
        ]

        with patch("core.pipeline.GeminiClient") as MockClient:
            mock_instance = MagicMock()
            MockClient.return_value = mock_instance

            # Step 1의 응답을 설정합니다 (TEXT 응답)
            mock_instance.send.return_value = StepResponse(
                text="Test specification",
                images=[],
            )

            pipeline = Pipeline(steps=steps, output_dir=Path(self.tmp))
            pipeline.run(skip_initial_selection=True)

            # send() 호출을 확인합니다
            self.assertTrue(mock_instance.send.called)
            call_args = mock_instance.send.call_args
            config_arg = call_args.kwargs.get("config") if call_args.kwargs else None

            # config가 None이 아니어야 합니다
            self.assertIsNotNone(config_arg, "Step 1 should receive a config")
            # response_modalities가 ["TEXT"]여야 합니다
            self.assertEqual(list(config_arg.response_modalities), ["TEXT"])

    def test_step2_receives_no_config(self):
        """Step 2가 config=None을 받는지 확인합니다."""
        steps = [
            {
                "step": 1,
                "name": "step1",
                "description": "test",
                "prompt": "test prompt",
                "image_path": self.shoe_img,
                "response_modalities": ["TEXT"],
                "save_output": False,
            },
            {
                "step": 2,
                "name": "step2",
                "description": "test",
                "prompt": "test prompt",
                "image_path": None,
                "guide_image_path": self.guide_img,
                "save_output": False,
            },
        ]

        with patch("core.pipeline.GeminiClient") as MockClient:
            mock_instance = MagicMock()
            MockClient.return_value = mock_instance

            # 단계별 응답
            mock_instance.send.side_effect = [
                StepResponse(text="Step 1 output", images=[]),
                StepResponse(text="Step 2 output", images=[MagicMock()]),
            ]

            pipeline = Pipeline(steps=steps, output_dir=Path(self.tmp))
            pipeline.run(skip_initial_selection=True)

            # 두 번의 send() 호출이 있어야 합니다
            self.assertEqual(mock_instance.send.call_count, 2)

            # 두 번째 호출(Step 2)의 config를 확인합니다
            second_call_args = mock_instance.send.call_args_list[1]
            config_arg = second_call_args.kwargs.get("config")
            self.assertIsNone(config_arg, "Step 2 should receive config=None")

    def test_step1_text_appears_in_step2_parts(self):
        """Step 1의 텍스트 응답이 Step 2의 parts에 나타나는지 확인합니다."""
        step1_text = "부품 목록: ..."

        steps = [
            {
                "step": 1,
                "name": "step1",
                "description": "test",
                "prompt": "test prompt",
                "image_path": self.shoe_img,
                "response_modalities": ["TEXT"],
                "save_output": False,
            },
            {
                "step": 2,
                "name": "step2",
                "description": "test",
                "prompt": "test prompt",
                "image_path": None,
                "guide_image_path": self.guide_img,
                "save_output": False,
            },
        ]

        with patch("core.pipeline.GeminiClient") as MockClient:
            mock_instance = MagicMock()
            MockClient.return_value = mock_instance

            # Step 1이 텍스트를 반환하도록 설정
            mock_instance.send.side_effect = [
                StepResponse(text=step1_text, images=[]),
                StepResponse(text="Step 2 output", images=[MagicMock()]),
            ]

            pipeline = Pipeline(steps=steps, output_dir=Path(self.tmp))
            pipeline.run(skip_initial_selection=True)

            # Step 2의 parts에 Step 1의 텍스트가 포함되어야 합니다
            second_call_args = mock_instance.send.call_args_list[1]
            parts = second_call_args[0][0]

            # parts 중 하나는 문자열이어야 하고 Step 1의 텍스트를 포함해야 합니다
            text_parts = [p for p in parts if isinstance(p, str)]
            combined_text = " ".join(text_parts)
            self.assertIn(step1_text, combined_text)

    def test_step2_replays_step1_reference_parts_in_order(self):
        """Step 2가 Step 1의 라벨+이미지를 같은 순서로 재사용하는지 확인합니다."""
        first_view = make_test_image(self.tmp / "lateral.png")
        second_view = make_test_image(self.tmp / "medial.png")
        step1_text = "Step 1 specification"

        steps = [
            {
                "step": 1,
                "name": "step1",
                "description": "test",
                "prompt": "STEP 1 PROMPT",
                "image_path": None,
                "view_images": [
                    ("바깥쪽 측면(lateral)", first_view),
                    ("안쪽 측면(medial)", second_view),
                ],
                "response_modalities": ["TEXT"],
                "save_output": False,
            },
            {
                "step": 2,
                "name": "step2",
                "description": "test",
                "prompt": "STEP 2 PROMPT",
                "image_path": None,
                "guide_image_path": self.guide_img,
                "reuse_initial_references": True,
                "save_output": False,
            },
        ]

        with patch("core.pipeline.GeminiClient") as MockClient:
            mock_instance = MagicMock()
            MockClient.return_value = mock_instance
            mock_instance.send.side_effect = [
                StepResponse(text=step1_text, images=[]),
                StepResponse(text="Step 2 output", images=[]),
            ]

            pipeline = Pipeline(steps=steps, output_dir=Path(self.tmp))
            pipeline.run(skip_initial_selection=True)

            parts = mock_instance.send.call_args_list[1][0][0]

        self.assertEqual(parts[0], "[사진 1] 바깥쪽 측면(lateral)")
        self.assertIsInstance(parts[1], Image.Image)
        self.assertEqual(parts[2], "[사진 2] 안쪽 측면(medial)")
        self.assertIsInstance(parts[3], Image.Image)
        self.assertEqual(parts[4], "[가이드라인]")
        self.assertIsInstance(parts[5], Image.Image)
        self.assertIn(step1_text, parts[6])
        self.assertEqual(parts[7], "STEP 2 PROMPT")

    def test_step2_requiring_references_fails_before_send_when_missing(self):
        """재사용할 실물 참조가 없으면 Step 2 API 호출 전에 실패합니다."""
        steps = [
            {
                "step": 1,
                "name": "step1",
                "description": "test",
                "prompt": "STEP 1 PROMPT",
                "image_path": None,
                "response_modalities": ["TEXT"],
                "save_output": False,
            },
            {
                "step": 2,
                "name": "step2",
                "description": "test",
                "prompt": "STEP 2 PROMPT",
                "image_path": None,
                "guide_image_path": self.guide_img,
                "reuse_initial_references": True,
                "save_output": False,
            },
        ]

        with patch("core.pipeline.GeminiClient") as MockClient:
            mock_instance = MagicMock()
            MockClient.return_value = mock_instance
            mock_instance.send.return_value = StepResponse(
                text="Step 1 output",
                images=[],
            )

            pipeline = Pipeline(steps=steps, output_dir=Path(self.tmp))
            with self.assertRaisesRegex(RuntimeError, "실물 참조 이미지"):
                pipeline.run(skip_initial_selection=True)

            self.assertEqual(mock_instance.send.call_count, 1)


if __name__ == "__main__":
    unittest.main()
