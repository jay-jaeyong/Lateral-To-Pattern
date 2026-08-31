"""scripts/run_parallel.sh 인자 처리 테스트.

이 스크립트는 bash라서 서브프로세스로 실행해 검증한다. 실제 파이썬/Gemini
호출은 하지 않는다 — PY 환경변수로 스텁 스크립트를 대신 꽂는다.
"""

import os
import shutil
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "run_parallel.sh"


class RunParallelTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.repo = Path(self._tmp.name)

        (self.repo / "scripts").mkdir()
        shutil.copy(SCRIPT, self.repo / "scripts" / "run_parallel.sh")

        self.log_file = self.repo / "fake_calls.log"
        stub = self.repo / "fake_python"
        stub.write_text(
            "#!/usr/bin/env bash\n"
            'echo "$@" >> "$FAKE_LOG"\n'
        )
        stub.chmod(stub.stat().st_mode | stat.S_IEXEC)
        self.stub = stub

    def _run(self, args, shoe_dirs=("shoeA",)):
        for name in shoe_dirs:
            (self.repo / "inputs" / "photos" / name).mkdir(parents=True, exist_ok=True)
        env = {
            **os.environ,
            "PY": str(self.stub),
            "FAKE_LOG": str(self.log_file),
        }
        return subprocess.run(
            ["bash", "scripts/run_parallel.sh", *args],
            cwd=self.repo,
            env=env,
            capture_output=True,
            text=True,
            timeout=20,
        )

    def test_sketch_pattern_alone_is_rejected_before_any_run(self):
        """sketch_pattern은 inputs/photos/*/를 훑는 이 스크립트의 범위 밖이다."""
        result = self._run(["sketch_pattern"])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("sketch_pattern", result.stderr)
        self.assertFalse(self.log_file.exists())

    def test_unknown_service_is_rejected(self):
        result = self._run(["no_such_service"])
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.log_file.exists())

    def test_jobs_and_repeat_flags_are_parsed_not_treated_as_services(self):
        """--jobs 2 --repeat 3가 서비스명으로 오인되어 전부 실패하던 결함."""
        result = self._run(["--jobs", "2", "--repeat", "3", "color_pattern"])
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("동시 2개", result.stdout)
        self.assertIn("반복 3회", result.stdout)

        lines = self.log_file.read_text().splitlines()
        self.assertEqual(len(lines), 1)
        self.assertIn("color_pattern", lines[0])
        self.assertIn("--repeat 3", lines[0])
        self.assertNotIn("--jobs", lines[0])

    def test_env_vars_still_work_as_defaults(self):
        for name in ("shoeA",):
            (self.repo / "inputs" / "photos" / name).mkdir(parents=True, exist_ok=True)
        env = {
            **os.environ,
            "PY": str(self.stub),
            "FAKE_LOG": str(self.log_file),
            "JOBS": "1",
            "REPEAT": "2",
        }
        result = subprocess.run(
            ["bash", "scripts/run_parallel.sh"],
            cwd=self.repo,
            env=env,
            capture_output=True,
            text=True,
            timeout=20,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("반복 2회", result.stdout)


if __name__ == "__main__":
    unittest.main()
