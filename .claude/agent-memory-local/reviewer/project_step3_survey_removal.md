---
name: project-step3-survey-removal
description: Step 3에서 Step 1 명세서를 빼는 작업은 parts 경로(include_prev_texts)와 채팅 히스토리 경로(fresh_session) 둘 다 막아야 완성된다 — 2026-08-05 워킹 트리에서 둘 다 구현됨
metadata:
  type: project
---

Step 3(라인 아트)에 Step 1 명세서가 들어가면 모델이 평면 패턴을 트레이싱하는 대신 완성된 3D 신발을 그린다. 명세서가 Step 3에 도달하는 경로는 **두 개**이고, 둘 다 막아야 한다.

1. `include_prev_texts=False` — `core/_parts_builder.py`의 `_insert_prev_texts` 호출을 건너뛴다. 요청 parts에서만 뺀다.
2. `fresh_session=True` — `Pipeline.run`이 그 스텝 직전에 `self._client.start_chat()`을 다시 불러 Step 1·2가 쌓은 히스토리를 끊는다. 끊긴 턴은 `Pipeline._history_archive`에 보관해 `save_final(chat_history=self._history_archive + self._client.chat_history)`로 합쳐 저장한다.

**Why:** 근거인 통제 실험(5모델 × 2회, `scripts/sketch_no_survey.py`)은 매번 새 `GeminiClient()` + `start_chat()`으로 돌아서 "명세서가 히스토리에도 없는" 조건이었다. 1번만으로는 그 조건을 재현하지 못한다 — 명세서가 모델 자기 응답 턴으로 히스토리에 남아 재전송된다.

**How to apply:** Step 3의 3D 회귀가 다시 보고되면 두 플래그가 **모두** `config/prompts.py`의 `PIPELINE_STEPS[2]`에 살아 있는지 확인하라. 하나만 있으면 절반만 막힌 상태다. Step 3의 유일한 실질 입력인 Step 2 생성 이미지는 `previous_images`(파이썬 메모리) → `_prepend_prev_images` 경로라서 세션 재시작에 영향받지 않는다 — 측정으로 확인했다. `PIPELINE_STEPS[2]["enabled"]`는 여전히 False라 이 경로는 실제 API 호출로 검증된 바 없다.
