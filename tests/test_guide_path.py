"""가이드라인 기본 경로 검증 테스트.

`scripts/_common.DEFAULT_GUIDE`가 가리키는 파일이 실제로 존재하고,
`inputs/guides/` 아래에 있는지 확인한다. 파일을 옮기고 상수를 안 옮기거나
그 반대인 경우 여기서 걸린다.
"""

import unittest
from pathlib import Path

from scripts._common import DEFAULT_GUIDE


class DefaultGuidePathTest(unittest.TestCase):
    def test_default_guide_exists(self):
        self.assertTrue(
            DEFAULT_GUIDE.is_file(),
            f"기본 가이드라인을 찾을 수 없습니다: {DEFAULT_GUIDE}",
        )

    def test_default_guide_is_under_inputs_guides(self):
        self.assertEqual(DEFAULT_GUIDE.parent, Path("inputs/guides"))


if __name__ == "__main__":
    unittest.main()
