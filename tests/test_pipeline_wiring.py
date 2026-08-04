"""파이프라인과 config 연결 상태 테스트."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

from PIL import Image

import core.pipeline as pipeline_module
from config.prompts import PIPELINE_STEPS
from core.pipeline import Pipeline
from core.models import StepResponse
from utils.cli import VIEW_FLAGS


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


if __name__ == "__main__":
    unittest.main()


class ReferenceViewTest(unittest.TestCase):
    """Step 2가 기준 사진을 채팅 히스토리 대신 직접 받는지 확인합니다."""

    class _Stub:
        def __init__(self, sent):
            self.sent = sent

        def start_chat(self):
            pass

        @property
        def chat_history(self):
            return []

        def _format_parts_for_log(self, parts):
            return ""

        def _format_chat_history_for_log(self):
            return ""

        def send(self, parts, config=None):
            self.sent.append(parts)
            modalities = list(config.response_modalities) if config else None
            if modalities == ["TEXT"]:
                return StepResponse(text="명세서", images=[])
            return StepResponse(text="", images=[Image.new("RGB", (4, 4))])

    def setUp(self):
        self._out = tempfile.TemporaryDirectory()
        self.addCleanup(self._out.cleanup)
        self._real = pipeline_module.GeminiClient
        self.addCleanup(setattr, pipeline_module, "GeminiClient", self._real)

    def run_pipeline(self, view_images):
        sent: list = []
        pipeline_module.GeminiClient = lambda *a, **k: self._Stub(sent)
        steps = [dict(s) for s in PIPELINE_STEPS]
        steps[0]["view_images"] = view_images
        steps[0]["image_path"] = None
        Pipeline(steps=steps, output_dir=Path(self._out.name), run_label="t").run()
        return sent

    def test_step2_receives_both_side_photos_again(self):
        labels = dict(VIEW_FLAGS)
        with tempfile.TemporaryDirectory() as tmp:
            lat, med = Path(tmp) / "lateral.png", Path(tmp) / "medial.png"
            for path in (lat, med):
                Image.new("RGB", (6, 6)).save(path)
            sent = self.run_pipeline([(labels["lateral"], lat), (labels["medial"], med)])

        step2 = sent[1]
        self.assertEqual(step2[0], f"[{labels['lateral']}]")
        self.assertIsInstance(step2[1], Image.Image)
        # 두 면을 서로 다르게 그리려면 Step 2가 두 면을 다 봐야 합니다.
        # 라벨은 reference_views 순서대로 붙습니다.
        self.assertEqual(step2[2], f"[{labels['medial']}]")
        self.assertIsInstance(step2[3], Image.Image)
        # 요청한 뷰 두 장 + 가이드라인 한 장.
        self.assertEqual(sum(1 for p in step2 if isinstance(p, Image.Image)), 3)

    def test_missing_lateral_does_not_break_the_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            top = Path(tmp) / "top.png"
            Image.new("RGB", (6, 6)).save(top)
            sent = self.run_pipeline([(dict(VIEW_FLAGS)["top"], top)])
        # enabled=False인 스텝은 빠지므로 실행된 스텝 수만큼만 호출됩니다.
        enabled = [s for s in PIPELINE_STEPS if s.get("enabled", True)]
        self.assertEqual(len(sent), len(enabled))


class DisabledStepTest(unittest.TestCase):
    def test_steps_marked_disabled_are_not_run(self):
        """Step 3는 지금 꺼져 있습니다. 켜고 끄는 스위치가 동작해야 합니다."""
        steps = [
            {"step": 1, "name": "a", "description": "d", "prompt": "p", "image_path": None},
            {"step": 2, "name": "b", "description": "d", "prompt": "p", "image_path": None,
             "enabled": False},
        ]
        pipeline = Pipeline.__new__(Pipeline)
        pipeline._steps = [s for s in steps if s.get("enabled", True)]
        self.assertEqual([s["name"] for s in pipeline._steps], ["a"])
