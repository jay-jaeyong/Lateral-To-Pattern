"""
Data Models
-----------
파이프라인 실행에 사용되는 데이터 클래스 정의.

- StepResponse  : 단일 Gemini API 호출 결과 (텍스트 + 이미지)
- StepResult    : 파이프라인 단계별 실행 결과
- PipelineResult: 전체 파이프라인 실행 결과
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image as PILImage


@dataclass
class StepResponse:
    """단일 API 호출의 결과 (텍스트 + 생성 이미지 목록)."""

    text: str = ""
    images: list[PILImage.Image] = field(default_factory=list)

    def has_image(self) -> bool:
        return len(self.images) > 0


@dataclass
class StepResult:
    """단계별 실행 결과."""

    step: int
    name: str
    description: str
    prompt: str
    image_path: Path | None
    response: str                              # Gemini 텍스트 응답
    generated_images: list = field(default_factory=list)  # Gemini 생성 이미지
    output_file: Path | None = None


@dataclass
class PipelineResult:
    """전체 파이프라인 실행 결과."""

    steps: list[StepResult] = field(default_factory=list)

    @property
    def final_output(self) -> str:
        """마지막 단계의 응답을 반환합니다."""
        if not self.steps:
            return ""
        return self.steps[-1].response

    def summary(self) -> str:
        """각 단계 결과의 요약 문자열을 반환합니다."""
        lines = ["=" * 60, "파이프라인 실행 요약", "=" * 60]
        for result in self.steps:
            lines.append(f"\n[Step {result.step}] {result.description}")
            lines.append(f"  입력 이미지: {result.image_path or '없음'}")
            lines.append(f"  생성 이미지: {len(result.generated_images)}장")
            lines.append(f"  저장 위치:   {result.output_file or '저장 안 함'}")
            lines.append(f"  응답 길이:   {len(result.response)}자")
        lines.append("\n" + "=" * 60)
        return "\n".join(lines)
