"""파이프라인과 config 연결 상태 테스트."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

from PIL import Image

from config.prompts import PIPELINE_STEPS
from core._parts_builder import build_step_parts as real_build_step_parts
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

    def test_required_reference_assembly_error_propagates_before_step2_send(self):
        """참조 재사용 단계의 parts 조립 실패는 prompt-only fallback으로 숨기지 않습니다."""
        steps = [
            {
                "step": 1,
                "name": "step1",
                "description": "test",
                "prompt": "STEP 1 PROMPT",
                "image_path": self.shoe_img,
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

        def fail_only_for_step2(*args, **kwargs):
            if kwargs["step_num"] == 1:
                return real_build_step_parts(*args, **kwargs)
            raise ValueError("reference parts assembly failed")

        with (
            patch("core.pipeline.GeminiClient") as MockClient,
            patch(
                "core.pipeline.build_step_parts",
                side_effect=fail_only_for_step2,
            ) as mock_build_parts,
        ):
            mock_instance = MagicMock()
            MockClient.return_value = mock_instance
            mock_instance.send.return_value = StepResponse(
                text="Step 1 output",
                images=[],
            )

            pipeline = Pipeline(steps=steps, output_dir=Path(self.tmp))
            with self.assertRaisesRegex(ValueError, "reference parts assembly failed"):
                pipeline.run(skip_initial_selection=True)

        self.assertEqual(mock_instance.send.call_count, 1)
        self.assertEqual(
            [call.kwargs["step_num"] for call in mock_build_parts.call_args_list],
            [1, 2],
        )

    def test_single_file_replays_a_labeled_reference(self):
        """단일 파일 입력도 Step 1과 Step 2 모두 라벨+이미지 parts를 사용합니다."""
        steps = [
            {
                "step": 1,
                "name": "step1",
                "description": "test",
                "prompt": "STEP 1 PROMPT",
                "image_path": self.shoe_img,
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
                StepResponse(text="Step 1 output", images=[]),
                StepResponse(text="Step 2 output", images=[]),
            ]

            pipeline = Pipeline(steps=steps, output_dir=Path(self.tmp))
            pipeline.run(skip_initial_selection=True)

        first_parts = mock_instance.send.call_args_list[0][0][0]
        second_parts = mock_instance.send.call_args_list[1][0][0]
        self.assertEqual(first_parts[0], "[사진 1] 파일명: shoe")
        self.assertIsInstance(first_parts[1], Image.Image)
        self.assertEqual(second_parts[0], "[사진 1] 파일명: shoe")
        self.assertIs(second_parts[1], first_parts[1])

    def test_direct_image_folder_replays_all_labeled_views(self):
        """뷰 파일이 바로 들어 있는 폴더는 한 번의 라벨된 멀티뷰 요청이 됩니다."""
        folder = self.tmp / "shoe_views"
        folder.mkdir()
        make_test_image(folder / "lateral.png")
        make_test_image(folder / "medial.png")

        steps = [
            {
                "step": 1,
                "name": "step1",
                "description": "test",
                "prompt": "STEP 1 PROMPT",
                "image_path": folder,
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
                StepResponse(text="Step 1 output", images=[]),
                StepResponse(text="Step 2 output", images=[]),
            ]

            pipeline = Pipeline(steps=steps, output_dir=Path(self.tmp))
            pipeline.run(skip_initial_selection=True)

        first_parts = mock_instance.send.call_args_list[0][0][0]
        second_parts = mock_instance.send.call_args_list[1][0][0]
        self.assertEqual(first_parts[0], "[사진 1] 바깥쪽 측면(lateral)")
        self.assertIsInstance(first_parts[1], Image.Image)
        self.assertEqual(first_parts[2], "[사진 2] 안쪽 측면(medial)")
        self.assertIsInstance(first_parts[3], Image.Image)
        self.assertIs(second_parts[1], first_parts[1])
        self.assertIs(second_parts[3], first_parts[3])

    def test_file_batch_replays_each_labeled_reference(self):
        """파일 batch의 각 실행이 정확한 파일 라벨을 Step 2까지 유지합니다."""
        lateral = make_test_image(self.tmp / "lateral.png")
        front = make_test_image(self.tmp / "front.png")
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
            mock_instance.send.side_effect = [
                StepResponse(text="Step 1 lateral", images=[]),
                StepResponse(text="Step 2 lateral", images=[]),
                StepResponse(text="Step 1 front", images=[]),
                StepResponse(text="Step 2 front", images=[]),
            ]

            pipeline = Pipeline(
                steps=steps,
                output_dir=Path(self.tmp),
                batch_targets=[lateral, front],
            )
            pipeline.run()

        calls = mock_instance.send.call_args_list
        self.assertEqual(calls[0][0][0][0], "[사진 1] 바깥쪽 측면(lateral)")
        self.assertEqual(calls[1][0][0][0], "[사진 1] 바깥쪽 측면(lateral)")
        self.assertEqual(calls[2][0][0][0], "[사진 1] 앞쪽에서 본 모습(front)")
        self.assertEqual(calls[3][0][0][0], "[사진 1] 앞쪽에서 본 모습(front)")
        self.assertIs(calls[1][0][0][1], calls[0][0][0][1])
        self.assertIs(calls[3][0][0][1], calls[2][0][0][1])


if __name__ == "__main__":
    unittest.main()
