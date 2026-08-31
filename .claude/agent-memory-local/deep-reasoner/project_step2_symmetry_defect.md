---
name: step2-symmetry-defect
description: Shoe-Image-To-Pattern의 Step 2 좌우 강제 대칭 결함 조사 맥락 — 잠긴(건드리면 안 되는) 규칙 목록과 Step 1 결정성 함정
metadata:
  type: project
---

Step 2(`pattern_unfold`)의 결과 이미지에서 좌우 반쪽(lateral/medial)이 거울상으로 나오는 결함을 2026-08 기준으로 추적 중. 규칙 전체는 `config/prompts.py` 한 파일에 있음.

**Why:** 실물이 비대칭인데도(예: adidas 삼선이 바깥면에만 있음) 여러 프롬프트 수정 후에도 대칭이 유지됨. 원인은 규칙 간 충돌이지 모델의 무작위성이 아님.

**How to apply:**
- 측정으로 9/9 검증되어 **약화 금지**로 못박힌 Step 2 규칙: `fit_rule`(방향), `heel_rule`(뒤축 단일 절개), `flat_rule`, `part_rule`, `guideline_rule`, `background_rule`, `count_rule`. 이 블록들을 삭제·완화하는 제안은 반려 대상. 항목 추가나 범위 한정은 허용.
- Step 1은 temperature=0 결정적이라 같은 신발이면 v8~v11 명세서가 **바이트 단위로 동일**함. 즉 Step 2 프롬프트만 고친 실험들은 모두 같은 명세서 위에서 돌아간 것. Step 2 수정 효과를 볼 때 Step 1 출력이 안 바뀌었다는 사실을 먼저 확인할 것.
- 두 단계는 한 채팅 세션이므로 Step 1 프롬프트 전문이 Step 2 컨텍스트에 남아 있음(`chat_history.json` turn 0 마지막 part). Step 1 규칙도 Step 2 동작에 영향을 준다고 봐야 함.
- Step 2에는 lateral 사진만 재첨부됨(`reference_views: ["lateral"]`). medial은 히스토리에만 존재.
