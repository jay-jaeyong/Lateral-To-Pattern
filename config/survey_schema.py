"""
부품 명세서 스키마 (Pydantic v2)
------------------------------

부품 명세서를 구조화된 JSON으로 검증하기 위한 Pydantic v2 모델입니다.

배경:
  - 모델이 반복해서 '경계' 필드를 빠뜨렸습니다
  - 대칭성 카테고리를 고정된 다섯 가지 이외로 발명했습니다
  - 한 번의 실행에서 로고 부품 전체가 빠졌습니다
  - '형태'에 옆에서 본 실루엣만 적고 위에서 본 평면 모양을 빼먹었습니다

이 스키마를 response_schema로 사용하면:
  - 필드 누락이 기계적으로 차단됩니다 (응답 JSON이 유효하려면 모든 필드를 포함해야 함)
  - 대칭성 어휘가 정확히 다섯 가지로만 강제됩니다
  - 표식(로고)이 전용 필드를 가져 자동으로 누락되지 않습니다
  - 평면 모양이 측면 실루엣과 별도 필드를 가져 함께 기록됩니다
"""

from typing import Literal
from pydantic import BaseModel


class Symmetry:
    """대칭성 분류 (리터럴 타입)."""

    TYPE = Literal[
        "양쪽",
        "한쪽만(바깥쪽)",
        "한쪽만(안쪽)",
        "중앙(좌우 구분 없음)",
        "확인 불가",
    ]


class Part(BaseModel):
    """재단 부품 (패널, 오버레이, 보강재 등)."""

    부품명: str
    재질: str
    색상: str
    형태: str
    평면형태: str  # 위에서 본 모습(top)에서의 평면 모양. 측면 실루엣과 따로 적는다
    경계: str  # 반드시 포함되어야 함
    위치: str
    접합방식: str
    재봉선: str
    표면요철: str
    대칭성: Symmetry.TYPE
    모양차이: str  # 대칭성이 '양쪽'일 때 좌우 모양 차이; 그 외에는 미해당 사유
    확인사진: str


class Marking(BaseModel):
    """로고·글자·인쇄 표식."""

    이름: str
    재질: str
    색상: str
    형태: str
    위치: str
    접합방식: str
    대칭성: Symmetry.TYPE
    확인사진: str


class Survey(BaseModel):
    """전체 부품 명세서."""

    분석대상짝: Literal["왼발", "오른발"]
    부품목록: list[Part]
    표식목록: list[Marking]
    미확인목록: list[str]
