"""파이프라인과 config 연결 상태 테스트."""

import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

from PIL import Image

import core.pipeline as pipeline_module
from config.prompts import PIPELINE_STEPS
from core.pipeline import Pipeline, _as_pil_image
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

    def test_step3_include_prev_texts_false_omits_step1_spec(self):
        """include_prev_texts=False인 스텝(Step 3)의 parts에는 Step 1 명세서가
        없어야 하고, include_prev_texts를 지정하지 않은 스텝(Step 2)의 parts에는
        여전히 있어야 합니다. config.get("include_prev_texts", True) 전달이
        끊기면(예: 그 인자를 지우면) 이 테스트가 실패해야 합니다."""
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
            {
                "step": 3,
                "name": "step3",
                "description": "test",
                "prompt": "test prompt",
                "image_path": None,
                "save_output": False,
                "include_prev_texts": False,
            },
        ]

        with patch("core.pipeline.GeminiClient") as MockClient:
            mock_instance = MagicMock()
            MockClient.return_value = mock_instance

            mock_instance.send.side_effect = [
                StepResponse(text=step1_text, images=[]),
                StepResponse(text="Step 2 output", images=[MagicMock()]),
                StepResponse(text="Step 3 output", images=[MagicMock()]),
            ]

            pipeline = Pipeline(steps=steps, output_dir=Path(self.tmp))
            pipeline.run(skip_initial_selection=True)

            self.assertEqual(mock_instance.send.call_count, 3)

            step2_parts = mock_instance.send.call_args_list[1][0][0]
            step2_text_parts = [p for p in step2_parts if isinstance(p, str)]
            self.assertIn(step1_text, " ".join(step2_text_parts))

            step3_parts = mock_instance.send.call_args_list[2][0][0]
            step3_text_parts = [p for p in step3_parts if isinstance(p, str)]
            self.assertNotIn(step1_text, " ".join(step3_text_parts))

    class _SessionTrackingStub:
        """start_chat() 호출 횟수와 그때마다 바뀌는 chat_history를 추적하는
        가짜 클라이언트. 매 start_chat() 호출마다 새 세션이 시작된 것처럼
        chat_history를 그 세션의 턴만 담긴 새 리스트로 바꿉니다."""

        def __init__(self, responses):
            self._responses = list(responses)
            self.start_chat_call_count = 0
            self._history = []
            self.sent_parts = []

        def start_chat(self):
            self.start_chat_call_count += 1
            self._history = []

        @property
        def chat_history(self):
            return self._history

        def _format_parts_for_log(self, parts):
            return ""

        def _format_chat_history_for_log(self):
            return ""

        def send(self, parts, config=None):
            self.sent_parts.append(parts)
            response = self._responses.pop(0)
            # 실제 GeminiClient처럼 이번 턴을 현재 세션의 히스토리에 남깁니다.
            self._history.append(f"turn:{response.text}")
            return response

    def test_fresh_session_step_starts_new_chat_and_omits_history(self):
        """fresh_session=True인 스텝(Step 3) 실행 직전에 start_chat()이 다시
        호출되어야 하고, 그 스텝의 parts에는 Step 1 명세서 텍스트가 없어야
        합니다. Pipeline.run에서 fresh_session 분기를 지우면 이 테스트가
        실패해야 합니다(start_chat 호출 횟수가 1로 줄어듭니다)."""
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
            {
                "step": 3,
                "name": "step3",
                "description": "test",
                "prompt": "test prompt",
                "image_path": None,
                "save_output": False,
                "include_prev_texts": False,
                "fresh_session": True,
            },
        ]

        stub = self._SessionTrackingStub([
            StepResponse(text=step1_text, images=[]),
            StepResponse(text="Step 2 output", images=[MagicMock()]),
            StepResponse(text="Step 3 output", images=[MagicMock()]),
        ])
        with patch("core.pipeline.GeminiClient", lambda: stub), patch.object(
            pipeline_module.OutputHandler, "save_final"
        ):
            pipeline = Pipeline(steps=steps, output_dir=Path(self.tmp))
            pipeline.run(skip_initial_selection=True)

        # 파이프라인 시작 시 1회 + Step 3 직전 fresh_session으로 1회 = 총 2회
        self.assertEqual(stub.start_chat_call_count, 2)

        step3_parts = stub.sent_parts[2]
        step3_text_parts = [p for p in step3_parts if isinstance(p, str)]
        self.assertNotIn(step1_text, " ".join(step3_text_parts))

    def test_save_final_history_includes_turns_before_and_after_fresh_session(self):
        """세션을 끊기 전(Step 1·2)과 끊은 후(Step 3)의 히스토리가 모두
        save_final에 넘겨진 chat_history에 들어 있어야 합니다. Pipeline.run에서
        _history_archive를 합치지 않고 self._client.chat_history만 넘기면
        이 테스트가 실패해야 합니다(끊기 전 턴이 사라집니다)."""
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
            {
                "step": 3,
                "name": "step3",
                "description": "test",
                "prompt": "test prompt",
                "image_path": None,
                "save_output": False,
                "include_prev_texts": False,
                "fresh_session": True,
            },
        ]

        stub = self._SessionTrackingStub([
            StepResponse(text="Step 1 output", images=[]),
            StepResponse(text="Step 2 output", images=[MagicMock()]),
            StepResponse(text="Step 3 output", images=[MagicMock()]),
        ])
        with patch("core.pipeline.GeminiClient", lambda: stub), patch.object(
            pipeline_module.OutputHandler, "save_final"
        ) as mock_save_final:
            pipeline = Pipeline(steps=steps, output_dir=Path(self.tmp))
            pipeline.run(skip_initial_selection=True)

            self.assertTrue(mock_save_final.called)
            saved_history = mock_save_final.call_args.kwargs.get("chat_history")
            # 끊기 전(Step 1·2) 세션의 턴과, 끊은 후(Step 3) 세션의 턴이 모두 있어야 합니다.
            self.assertIn("turn:Step 1 output", saved_history)
            self.assertIn("turn:Step 2 output", saved_history)
            self.assertIn("turn:Step 3 output", saved_history)

    def test_opted_in_step_postprocesses_before_save_and_result(self):
        raw = Image.new("RGB", (8, 8), "blue")
        processed = Image.new("RGB", (8, 8), "white")
        step = {
            "step": 3,
            "name": "line_art_conversion",
            "description": "sketch",
            "prompt": "prompt",
            "image_path": None,
            "postprocess_sketch": True,
        }

        with patch("core.pipeline.GeminiClient") as MockClient, patch(
            "core.pipeline.postprocess_sketch", return_value=processed
        ) as postprocess:
            MockClient.return_value.send.return_value = StepResponse(images=[raw])
            pipeline = Pipeline(steps=[step], output_dir=self.tmp)
            pipeline._output_handler.save_step = MagicMock(return_value=self.tmp / "step.md")

            result = pipeline._run_step(step)

        postprocess.assert_called_once_with(raw)
        saved = pipeline._output_handler.save_step.call_args.kwargs["generated_images"]
        self.assertIs(saved[0], processed)
        self.assertIs(result.generated_images[0], processed)

    def test_unflagged_step_keeps_original_generated_image(self):
        raw = Image.new("RGB", (8, 8), "blue")
        step = {
            "step": 2,
            "name": "pattern_unfold",
            "description": "color",
            "prompt": "prompt",
            "image_path": None,
            "save_output": False,
        }

        with patch("core.pipeline.GeminiClient") as MockClient, patch(
            "core.pipeline.postprocess_sketch"
        ) as postprocess:
            MockClient.return_value.send.return_value = StepResponse(images=[raw])
            pipeline = Pipeline(steps=[step], output_dir=self.tmp)

            result = pipeline._run_step(step)

        postprocess.assert_not_called()
        self.assertIs(result.generated_images[0], raw)


class AsPilImageTest(unittest.TestCase):
    """core.pipeline._as_pil_image가 genai.types.Image류(PIL이 아닌 객체)를
    실제로 PIL Image로 변환하는지 확인합니다."""

    class _GenaiImageStub:
        def __init__(self, image_bytes, mime_type="image/png"):
            self.image_bytes = image_bytes
            self.mime_type = mime_type

    class _NeitherStub:
        """PIL Image도 아니고 image_bytes도 없는 객체."""

    def test_converts_genai_image_bytes_to_pil_image(self):
        buf = io.BytesIO()
        Image.new("RGB", (12, 9), "blue").save(buf, format="PNG")
        stub = self._GenaiImageStub(buf.getvalue())

        result = _as_pil_image(stub)

        self.assertIsInstance(result, Image.Image)
        self.assertEqual(result.size, (12, 9))

    def test_object_without_image_bytes_raises_attribute_error_loudly(self):
        with self.assertRaises(AttributeError):
            _as_pil_image(self._NeitherStub())


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
