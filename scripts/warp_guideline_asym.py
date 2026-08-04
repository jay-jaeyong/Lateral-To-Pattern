#!/usr/bin/env python3
"""가이드라인 외곽을 좌우 비대칭으로 변형합니다. (P3-2 실험, 방향 A)

images/가이드라인.jpg → guides/가이드라인_비대칭.png

원본 가이드라인은 채운 마스크 기준 미러 IoU가 0.94로 거의 좌우 대칭입니다.
프롬프트 5순위가 "바깥 재단선을 가이드라인 형태에 맞춘다"이므로, 모델은
대칭인 외곽 틀(이미지 조건)과 "두 반쪽은 서로 다른 면"(텍스트 조건)을 동시에
받습니다. 이미지 조건이 이기기 때문에 내용도 대칭으로 채워집니다.

KAYANO 글자 중복, AM95 스우시 중복이 이 경로로 발생합니다. 규칙 문장,
색 표시, 문자 표시, 구조화 출력으로는 움직이지 않았고, 유일하게 효과가
있었던 것은 medial 사진 투입(이미지 계층의 전역 신호)이었습니다. 그래서
이미지 조건 자체를 비대칭으로 만듭니다.

변형 방향은 라스트 해부학을 따릅니다. 안쪽면(medial)은 엄지 쪽이라 앞으로
갈수록 볼이 차고 곧으며, 바깥면(lateral)은 낮고 더 휩니다. 그래서 축을
고정한 채 앞코로 갈수록 오른쪽 반쪽을 넓히고 왼쪽 반쪽을 좁힙니다.
실제로 두 면 차이가 가장 큰 곳이 앞코 부근이므로 변형도 거기에 몰아줍니다.
KAYANO 14가 앞코로 갈수록 두 면 패턴이 크게 갈리는 대표 사례입니다.

진폭은 채운 마스크 미러 IoU를 지표로 골랐습니다. 원본 0.94에서 0.075→0.90,
0.13→0.86, 0.16→0.85로 내려갑니다. 0.13을 씁니다. 더 키우면 외곽이 실제
라스트 형태에서 멀어지고, 더 줄이면 대칭 편향을 깨지 못합니다.

뒤축(위쪽)은 건드리지 않습니다. 절개선이 만나는 자리라 좌우 길이가 어긋나면
봉합이 성립하지 않습니다.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

SRC = Path("images/가이드라인.jpg")
DST = Path("guides/가이드라인_비대칭.png")

AXIS = 453          # 좌우를 가르는 세로축 (원본 잉크 범위 67~840의 중앙)
HEEL_Y = 46         # 잉크 시작 행 (뒤축 끝)
TOE_Y = 1261        # 잉크 끝 행 (앞코 끝)
AMP = 0.13          # 축에서의 최대 변형 비율
EASE = 1.6          # 1보다 크면 변형이 앞코 쪽에 몰림


def ramp(y: int) -> float:
    """뒤축에서 0, 앞코에서 1이 되는 가중치."""
    if y <= HEEL_Y:
        return 0.0
    if y >= TOE_Y:
        return 1.0
    return ((y - HEEL_Y) / (TOE_Y - HEEL_Y)) ** EASE


def main() -> None:
    src = Image.open(SRC).convert("RGB")
    width, height = src.size
    out = Image.new("RGB", (width, height), (255, 255, 255))

    for y in range(height):
        weight = ramp(y)
        left_scale = 1.0 - AMP * weight    # 바깥면(lateral): 앞으로 갈수록 좁아짐
        right_scale = 1.0 + AMP * weight   # 안쪽면(medial): 앞으로 갈수록 넓어짐

        row = src.crop((0, y, width, y + 1))

        left = row.crop((0, 0, AXIS, 1))
        new_left = max(1, round(AXIS * left_scale))
        left = left.resize((new_left, 1), Image.BICUBIC)
        out.paste(left, (AXIS - new_left, y))

        right = row.crop((AXIS, 0, width, 1))
        new_right = max(1, round((width - AXIS) * right_scale))
        right = right.resize((new_right, 1), Image.BICUBIC)
        out.paste(right, (AXIS, y))

    DST.parent.mkdir(parents=True, exist_ok=True)
    out.save(DST)
    print(f"{DST}  ({out.width}x{out.height})  축={AXIS} 진폭={AMP} 이징={EASE}")
    print("  라벨을 얹으려면: mark_guideline_margin.py의 SRC를 이 파일로 두고 실행")


if __name__ == "__main__":
    main()
