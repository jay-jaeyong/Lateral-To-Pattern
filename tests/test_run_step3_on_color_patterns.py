import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from scripts import run_step3_on_color_patterns as runner


class Step3BatchRunnerTest(unittest.TestCase):
    def test_discovers_only_color_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            Image.new("RGB", (2, 2), "white").save(folder / "a_color.png")
            Image.new("RGB", (2, 2), "white").save(folder / "a_sketch.png")
            self.assertEqual(
                [path.name for path in runner.find_color_patterns(folder)],
                ["a_color.png"],
            )

    def test_routes_output_to_v3_without_touching_source(self):
        source = Path("images/new_patterns/model_color.png")
        output = runner.sketch_output_path(source, Path("images/new_patterns/v3"))
        self.assertEqual(output, Path("images/new_patterns/v3/model_sketch.png"))

    def test_convert_one_uses_fixed_2to3_default_image_config(self):
        """Step 3는 더 이상 입력 화면비를 따라가지 않습니다. 이 스텝의
        match_input_aspect_ratio가 꺼져 있으므로 build_response_config(None, ...)는
        None을 돌려주고, per-call config가 None이면 GeminiClient.send는 채팅
        세션 기본값(CHAT_CONFIG → IMAGE_CONFIG, 4K/2:3 고정)을 그대로 씁니다."""
        raw = Image.new("RGB", (20, 30), "blue")
        sent_configs = []

        class FakeClient:
            def start_chat(self):
                pass

            def send(self, parts, config=None):
                from core.models import StepResponse

                sent_configs.append(config)
                return StepResponse(images=[raw])

        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            source = folder / "model_color.png"
            output_dir = folder / "v3"
            Image.new("RGB", (20, 30), "white").save(source)

            with patch.object(runner, "GeminiClient", return_value=FakeClient()):
                output = runner.convert_one(source, output_dir)

            self.assertEqual(output, output_dir / "model_sketch.png")
            self.assertIsNone(sent_configs[0])
            self.assertIsNot(runner.STEP3.get("match_input_aspect_ratio", False), True)
            self.assertEqual(Image.open(output).getpixel((10, 15)), (0, 0, 255))

    def test_convert_one_does_not_regenerate_when_response_has_no_image(self):
        class FakeClient:
            def __init__(self):
                self.send_calls = 0

            def start_chat(self):
                pass

            def send(self, parts, config=None):
                from core.models import StepResponse

                self.send_calls += 1
                return StepResponse(text="no image", images=[])

        client = FakeClient()
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            source = folder / "model_color.png"
            output_dir = folder / "v3"
            Image.new("RGB", (20, 30), "white").save(source)

            with patch.object(runner, "GeminiClient", return_value=client):
                output = runner.convert_one(source, output_dir)

            self.assertIsNone(output)
            self.assertEqual(client.send_calls, 1)
            self.assertFalse((output_dir / "model_sketch.png").exists())

    def test_convert_one_sends_only_the_original_image_even_for_a_faint_input(self):
        """이전에는 명도차가 작은(옅은) 입력에서 aid_image가 보조 이미지를 붙여
        4개 파트(라벨×2, 이미지×2)를 보냈습니다. 그 경로를 완전히 걷어냈으므로,
        이 조건에서도 항상 [라벨, 원본 이미지, STEP3_PROMPT] 3개 파트만 보내야
        하고 *_aid 파일도 쓰지 않아야 합니다."""
        raw = Image.new("RGB", (20, 30), "blue")
        sent_parts: list = []

        class FakeClient:
            def start_chat(self):
                pass

            def send(self, parts, config=None):
                from core.models import StepResponse

                sent_parts.append(parts)
                return StepResponse(images=[raw])

        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            source = folder / "model_color.png"
            output_dir = folder / "v3"
            # 배경과 명도차가 아주 작은(옅은) 부품 하나. 이전 aid_image 경로라면
            # 이런 입력에서 보조 이미지를 붙였을 조건입니다.
            faint = Image.new("RGB", (200, 200), "white")
            for x in range(60, 140):
                for y in range(60, 140):
                    faint.putpixel((x, y), (250, 250, 250))
            faint.save(source)

            # ImageHandler.load가 돌려주는 객체를 원본 그대로(별도 복사나
            # 파생 이미지 없이) 파츠에 담아 보내는지 확인합니다. 관련 없는
            # 임의의 센티널 대신, 이 테스트가 구성한 실제 옅은(faint) 이미지
            # 객체 자체를 load의 반환값으로 삼아 정체성을 검증합니다.
            with patch.object(runner, "GeminiClient", return_value=FakeClient()), \
                 patch.object(runner.ImageHandler, "load", return_value=faint):
                runner.convert_one(source, output_dir)

            parts = sent_parts[0]
            self.assertEqual(len(parts), 3)
            self.assertEqual(parts[0], "[원본 컬러 패턴]")
            self.assertIs(parts[1], faint)
            self.assertEqual(parts[2], runner.STEP3_PROMPT)

            aid_files = list(output_dir.glob("*_aid*"))
            self.assertEqual(aid_files, [])

    def test_convert_one_skips_when_output_already_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            source = folder / "model_color.png"
            output_dir = folder / "v3"
            output_dir.mkdir(parents=True)
            Image.new("RGB", (20, 20), "white").save(source)

            existing_out = output_dir / "model_sketch.png"
            Image.new("RGB", (5, 5), "black").save(existing_out)
            existing_bytes = existing_out.read_bytes()

            with patch.object(
                runner, "GeminiClient", side_effect=AssertionError("should not be called")
            ):
                output = runner.convert_one(source, output_dir)

            self.assertEqual(output, existing_out)
            self.assertEqual(existing_out.read_bytes(), existing_bytes)


if __name__ == "__main__":
    unittest.main()
