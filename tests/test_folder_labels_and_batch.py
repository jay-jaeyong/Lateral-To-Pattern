"""폴더 모드 라벨링과 배치 실행 테스트.

폴더 모드는 파일명이 뷰 이름이면 뷰 플래그와 같은 정식 라벨을 붙여야 합니다.
그래야 프롬프트가 '바깥쪽 측면(lateral)'으로 기준 사진을 지목할 수 있고,
쿼터 뷰 설명이 걸립니다.
"""

import tempfile
import unittest
from pathlib import Path

from PIL import Image

import core.pipeline as pipeline_module
from config.prompts import PIPELINE_STEPS
from core.models import StepResponse
from core.pipeline import Pipeline
from handlers.image_handler import ImageHandler
from utils.cli import VIEW_FLAGS, label_image_files

LABELS = dict(VIEW_FLAGS)


def make_png(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (4, 4), (10, 20, 30)).save(path)
    return path


class LabelImageFilesTest(unittest.TestCase):
    def test_view_stems_get_canonical_labels_in_flag_order(self):
        # 알파벳순이면 front가 먼저 오지만, VIEW_FLAGS 순서에서는 lateral이 먼저입니다.
        paths = [Path("top.webp"), Path("front.webp"), Path("lateral.webp")]
        labeled = label_image_files(paths)
        self.assertEqual(
            [label for label, _p in labeled],
            [LABELS["lateral"], LABELS["front"], LABELS["top"]],
        )

    def test_front_and_heel_labels_do_not_assert_a_quarter_angle(self):
        # front/heel 사진은 정면일 수도 쿼터일 수도 있으므로 라벨이 각도를 단정하면 안 됩니다.
        labeled = dict(
            (p.stem, label)
            for label, p in label_image_files([Path("front.webp"), Path("heel.webp")])
        )
        self.assertEqual(labeled["front"], "앞쪽에서 본 모습(front)")
        self.assertEqual(labeled["heel"], "뒤쪽에서 본 모습(heel)")
        for label in labeled.values():
            self.assertNotIn("쿼터", label)

    def test_matching_is_case_insensitive(self):
        labeled = label_image_files([Path("LATERAL.WEBP")])
        self.assertEqual(labeled[0][0], LABELS["lateral"])

    def test_unknown_stems_keep_filename_label_and_go_last(self):
        labeled = label_image_files([Path("IMG_2931.webp"), Path("lateral.webp")])
        self.assertEqual(
            [label for label, _p in labeled],
            [LABELS["lateral"], "파일명: IMG_2931"],
        )


class LoadDirImagesLabelTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self._tmp.name) / "nike_x"
        for name in ("front.png", "lateral.png", "top.png"):
            make_png(self.folder / name)
        self.addCleanup(self._tmp.cleanup)

    def test_folder_mode_emits_canonical_labels(self):
        parts = ImageHandler._load_dir_images(self.folder, "PROMPT")
        self.assertEqual(parts[0], f"[{LABELS['lateral']}]")
        self.assertEqual(parts[2], f"[{LABELS['front']}]")
        self.assertEqual(parts[4], f"[{LABELS['top']}]")

    def test_max_images_keeps_the_reference_photo(self):
        # 정렬 전에 잘라내면 알파벳순 첫 장인 front가 남아 기준 사진이 사라집니다.
        parts = ImageHandler._load_dir_images(self.folder, "PROMPT", max_images=1)
        self.assertEqual(parts[0], f"[{LABELS['lateral']}]")
        self.assertEqual(len(parts), 3)


class StubClient:
    """API를 부르지 않고 파이프라인을 끝까지 돌리기 위한 대역."""

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
        modalities = list(config.response_modalities) if config else None
        if modalities == ["TEXT"]:
            return StepResponse(text="명세서", images=[])
        return StepResponse(text="", images=[Image.new("RGB", (4, 4))])


class RunForEachTest(unittest.TestCase):
    def setUp(self):
        self._src = tempfile.TemporaryDirectory()
        self._out = tempfile.TemporaryDirectory()
        self.src = Path(self._src.name)
        self.out = Path(self._out.name)
        self._real_client = pipeline_module.GeminiClient
        pipeline_module.GeminiClient = lambda *a, **k: StubClient()
        self.addCleanup(self._src.cleanup)
        self.addCleanup(self._out.cleanup)
        self.addCleanup(setattr, pipeline_module, "GeminiClient", self._real_client)

    def run_batch(self, targets: list[Path]) -> list[str]:
        Pipeline(
            steps=[dict(step) for step in PIPELINE_STEPS],
            output_dir=self.out,
            batch_targets=targets,
        ).run()
        return sorted(entry.name for entry in self.out.iterdir())

    def test_directory_with_no_usable_image_is_skipped(self):
        good = self.src / "nike_x"
        make_png(good / "lateral.png")
        empty = self.src / "heic_only"
        empty.mkdir()
        (empty / "IMG_001.HEIC").write_bytes(b"not a supported image")

        # 건너뛰지 않으면 heic_only 폴더에 다른 신발 사진으로 만든 결과가 들어갑니다.
        self.assertEqual(self.run_batch([good, empty]), ["nike_x"])

    def test_identically_named_folders_all_get_distinct_labels(self):
        targets = []
        for brand in ("brandA", "brandB", "brandC"):
            folder = self.src / brand / "runner"
            make_png(folder / "lateral.png")
            targets.append(folder)

        created = self.run_batch(targets)
        self.assertEqual(len(created), 3, f"출력 폴더가 겹쳤습니다: {created}")
        self.assertEqual(len(set(created)), 3)

    def test_directory_target_sends_every_view_in_flag_order(self):
        folder = self.src / "nike_x"
        for name in ("top.png", "front.png", "lateral.png"):
            make_png(folder / name)

        sent: list = []
        stub = StubClient()
        original_send = stub.send

        def recording_send(parts, config=None):
            sent.append(parts)
            return original_send(parts, config=config)

        stub.send = recording_send
        pipeline_module.GeminiClient = lambda *a, **k: stub

        Pipeline(
            steps=[dict(step) for step in PIPELINE_STEPS],
            output_dir=self.out,
            batch_targets=[folder],
        ).run()

        labels = [part for part in sent[0] if isinstance(part, str)][:-1]
        self.assertEqual(
            labels,
            [
                f"[{LABELS['lateral']}]",
                f"[{LABELS['front']}]",
                f"[{LABELS['top']}]",
            ],
        )


if __name__ == "__main__":
    unittest.main()
