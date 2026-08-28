"""스케치 출력 진단 하네스.

이 패키지는 진단 전용입니다. 생성 파이프라인(`core/`, `services/`,
`handlers/`, `config/`, `main.py`, `scripts/run_step3_on_color_patterns.py`)은
이 패키지를 import하지 않으며, 채점 결과가 저장·삭제·재생성 동작을 유발하지
않습니다. 서브모듈은 필요할 때 직접 import합니다(무거운 OpenCV 의존성을
패키지 import 시점에 끌어오지 않기 위함).
"""

__version__ = "1"

DIAGNOSTIC_ONLY = True
