# Sneaker Upper Pattern Generation — 방법론 설계

> 5뷰 운동화 이미지로부터 단일 upper 전개 패턴(PNG)을 완전 자동 생성하는 파이프라인 설계.
> 제약: 생성 모델 재학습 불가 · 3D 재구성 미사용 · 참조 패턴 1장 · 사람 개입 없음.

---

## 0. 확정 스펙 요약

| 항목 | 값 |
|---|---|
| 입력 | 5뷰 필수 (lateral, medial, top, front, heel), 스튜디오 컷, 메타데이터(뷰종류·각도 0°/45°·좌우발) |
| 대상 | 러닝화 / 스니커즈 |
| 출력 | 단일 전체 upper 패턴 1장, PNG, 고정 캔버스 900×1450 |
| 전개 기준 | 힐 센터 절개, bite line(측포–midsole 경계) → 칼라 → 반대편 bite line |
| 제외 | 설포(tongue), 신끈 |
| 정밀도 | CAD 후보정 전제 초안 |
| 가이드라인 | 위=칼라 2갈래, 아래 노치=토, 검은선=레이싱/설포 개구부 (eyestay 형상 변형 허용) |
| 다트 | 표시 시도(우선), 실패 시 생략 |
| 오버레이 | 아일렛 스테이·토캡·사이드 스트라이프 **실선** 표시 |
| 스케일 | 없음(정규화), 좌우는 오른발 기준 |
| 자동화 | 완전 자동, 사람 개입 없음 |
| 평가 | 전문가 육안 |

### 용어
- **bite line**: 갑피(측포)와 미드솔이 접합되는 경계선. 전개 패턴의 하단 외곽선이 된다.
- **topline**: 발목 개구부(칼라) 상단선.
- **eyestay**: 신끈 구멍(아일렛) 열을 포함하는 보강 영역.
- **오버레이(overlay)**: 베이스 재료 위에 덧붙는 보강·장식 조각 (토캡, 힐 카운터 외피, 사이드 스트라이프, 아일렛 스테이).
- **girth 전개**: 라스트 단면 둘레(girth)를 스테이션별로 계산해 2D로 펼치는 전통 제화 기법.

---

## 1. 아키텍처 원칙

```
[5-view 이미지] ──▶ S0 정규화 ──▶ S1 특징선 추출 ──▶ S2 girth 전개(결정론적)
                                                          │
                              S3 템플릿 정합(TPS) ◀────────┘
                                       │
                              [conditioning map: 벡터 선도]
                                       │
      ┌────────────────────────────────┴───────────────────┐
      │ S4 생성 모델 = 렌더링 + 디테일(다트/오버레이/선품질) │
      └────────────────────────────────┬───────────────────┘
                                       │
                       S5 자동 QA 게이트 → 실패시 재시도(seed 변경)
                                       │
                                  [PNG 출력 + 신뢰도 플래그]
```

**핵심 판단: 기하는 결정론적으로 계산하고, 생성 모델은 렌더러 + 디테일 합성기로 격하한다.**

참조 쌍이 1개뿐이라 few-shot으로 "3D→2D 전개 매핑"을 모델에 가르칠 수 없다. 반면 "주어진 선도를 깔끔한 테크니컬 드로잉으로 렌더링하고, 스타일을 1장의 참조에서 모사"하는 작업은 pretrained ControlNet/IP-Adapter의 기본 능력 범위다. 기하 책임을 S2로 옮기면 참조 1개의 한계가 치명적이지 않게 된다.

---

## 2. S0 — 정규화 전처리

1. **배경 제거**: SAM/rembg 계열로 신발 실루엣 마스크 추출 (흰 배경이므로 임계값 + 마스크 정제로도 충분).
2. **좌우 정규화**: 메타데이터가 left이면 전 뷰 수평 미러 → 항상 오른발 좌표계.
3. **뷰별 자세 정렬**
   - lateral/medial: bite line 최저점 2점(토·힐)을 잇는 직선을 수평으로 회전 보정.
   - top: 라스트 장축(토 최전방점–힐 최후방점)을 수직으로 정렬.
   - front/heel: 좌우 실루엣 폭의 대칭축을 수직으로 정렬. 45° 뷰는 면적 기반 코사인 역보정 대상으로 태깅(§3.4).
4. **한 쌍 처리**: top/front/heel에 두 짝이 있으면 연결성분 분리 → 메타데이터의 발 기준으로 선택(오른발이 화면상 어느 쪽인지는 뷰별 규칙 테이블로 결정).
5. **스케일 정규화**: 각 뷰의 신발 길이를 1.0으로 정규화. 이후 모든 계산은 무차원.

---

## 3. S1 — 특징선 추출

### 3.1 lateral / medial에서
- **bite line** (측포–midsole 경계): 색/텍스처 불연속 경계. midsole은 통상 무채·단색·고명도 → 수직 스캔라인별로 상향 탐색하며 색상 클러스터 전환점 검출 → 스플라인 피팅.
- **topline (칼라 상단선)**: 실루엣 상단 윤곽 중 힐~중족 구간.
- **throat / eyestay 전방선**: 레이싱 개구부의 전단점(vamp point) 및 아일렛 스테이 내측 곡선.
- **아일렛 중심점 열**: 원형 홀 검출 → 개수 N, 간격, 스테이 곡률.
- **오버레이 윤곽**: 토캡, 힐 카운터 외피, 사이드 스트라이프 — 색/재질 세그멘테이션 후 폐곡선 추출.

### 3.2 top에서
- 길이축 스테이션별 **반폭(half-width) 프로파일** `w(t)`.
- 레이싱 개구부 및 설포 외곽 → **제외 영역 마스크**.
- 토박스 최대폭 위치, 칼라 개구부 타원.

### 3.3 front에서
- 전족부 **단면 형상 prior**: 토박스 높이 h, 반폭 w, 실루엣 곡률 → 단면을 초타원(superellipse) `|x/w|^n + |y/h|^n = 1` 로 근사, n을 실루엣에서 추정.

### 3.4 heel에서
- 힐 카운터 높이, 후족부 단면 초타원 파라미터, 칼라 후방 높이.

**45° 뷰 보정**: 45° 뷰에서는 폭은 거의 보존되지만 높이 방향이 `cos45° ≈ 0.707`로 압축되고 상면이 노출된다. 높이 성분에 `1/cos45°` 역보정을 적용하되, **45° 뷰는 폭/단면형상(n) 추정에만 쓰고 절대 높이는 lateral/medial에서 가져오도록 우선순위를 고정**한다(오차 전파 차단).

---

## 4. S2 — Girth 전개 (결정론적, 3D 미사용)

전통 제화의 *mean form / girth development* 원리를 2D 계산으로 구현한다.

1. 길이축을 M개 스테이션 `t_i` (i=1..M, M≈60)로 등분.
2. 각 스테이션에서 단면을 구성: 반폭 `w(t_i)` (top), 높이 `h(t_i)` = topline 높이 − bite line 높이 (lateral/medial 각각), 형상지수 `n(t_i)` (front/heel에서 보간).
3. 단면 초타원의 **bite line → topline 구간 호길이** `L_med(t_i)`, `L_lat(t_i)`를 수치적분.
4. 전개 좌표
   - 세로축(패턴 높이 방향) = 호길이 `L`
   - 가로축(패턴 폭 방향) = 스테이션 누적 길이 `∫√(1+(dz/dt)²)dt` (bite line의 3D 경로 길이 근사)
5. **수축계수(shrink factor)** `k` 적용: 갑피 소재 신축 보정. 메시/니트 우세 → `k = 0.92` 기본값, 파라미터로 노출 (§8.3 A5 실험 대상).
6. 힐 센터를 좌우 끝단으로, 토 센터를 하단 노치로 배치 → 가이드라인과 동일한 토폴로지의 **점군 → B-스플라인 폐곡선**.
7. 제외 영역(설포·레이싱)을 동일 좌표계로 매핑 → 검은 내측 폐곡선.
8. 오버레이 폐곡선·아일렛 위치도 동일 매핑 적용.

### 4.1 다트 산정
전개 불가능성(non-developability)은 **가우스 곡률 프록시**로 추정한다. 인접 스테이션 간 단면 곡률 변화율이 큰 구간 = 토박스 앞단, 힐 곡면.

- **토**: 하단 노치가 흡수 → 노치 각도를 곡률 적분값에 비례해 결정(기본 15~30°).
- **힐**: 힐 센터 절개가 흡수 → 좌우 끝단 상부 곡률로 절개 각 결정.
- **잔여**: 누적 각결손 > 8° 초과 시 **쐐기 다트 1~2개**를 vamp 측면에 삽입. 미초과 시 다트 없음.
- 이 계산이 불안정하다고 판정되면(§9 F6) 다트 생략으로 강등하고 플래그를 기록한다.

---

## 5. S3 — 템플릿 정합

가이드라인 도면을 **의미론적 템플릿**으로 사용한다.

**랜드마크 정의**

| ID | 위치 |
|---|---|
| L1 | 힐 상단 좌/우 |
| L2 | 칼라 최저점 좌/우 |
| L3 | vamp point (레이싱 개구부 전단) |
| L4 | 토 노치 정점 |
| L5 | bite line 좌/우 최하점 |
| L6 | eyestay 최광점 |

- S2 결과의 대응 랜드마크와 **TPS(thin-plate spline) 정합**. 가이드라인 이탈이 허용되므로 변형 에너지 상한은 느슨하게: 랜드마크 최대 이동 ≤ 캔버스 폭의 12%.
- 900×1450 캔버스에 배치. **여기서 나온 벡터 선도가 conditioning map이다.**
- **색 규약**: 외곽선 = 파란색(#1F5C99 계열, 1.5px), 내측 분할·오버레이 = 검정(3px), 노치 tick = 검정 짧은선.

> **파라메트릭 템플릿 확장 대비**: S2/S3의 모든 좌표를 무차원으로 유지하고, `scale_field` 슬롯(현재 null)을 메타데이터에 남겨둔다. 사이즈/라스트 데이터가 들어오면 S2 5단계의 정규화 해제 + S3 캔버스 스케일링만 교체하면 파라메트릭 템플릿으로 전환된다.

---

## 6. S4 — 생성 모델 제어 스펙

### 6.1 오픈소스 경로 (권장 주경로)
- **베이스**: Flux.1-dev 또는 SDXL
- **ControlNet**: `lineart` (주) + `softedge`(보조). conditioning image = S3 벡터 선도 래스터화. `controlnet_conditioning_scale = 0.85~1.0` (기하 이탈 억제).
- **IP-Adapter**: 참조 패턴 1장 입력, `scale = 0.35~0.5`. 역할은 **선 두께·색 규약·도면 톤 전이만**. scale을 높이면 참조의 형상까지 끌려오므로 상한 준수.
- **인페인팅 리파인 패스** (마스크 국소, 기하 보존)
  1. eyestay 영역 → 신발별 실측 형상 반영
  2. 오버레이 라인 영역 → 실선 품질 정리
  3. 토 노치 / 힐 끝단 → 다트·노치 표기
- 해상도: 900×1450 직접 생성 또는 1024 기반 + 리사이즈.

### 6.2 상용 API 경로 (비교/폴백)
Gemini 2.5 Flash Image, GPT-Image-1 edit, Seedream 4 등 multi-image 편집 지원 모델.

- 입력 이미지 3장: ① S3 conditioning map ② 참조 패턴 ③ 5뷰 합성 시트(2×3 그리드, 뷰 라벨 텍스트 번인)
- API는 ControlNet 강도 제어가 없으므로 **"conditioning map의 선을 절대 이동시키지 말고 그대로 정리·강조만 하라"**는 지시를 프롬프트 최상단에 배치하고, S5 게이트에서 이탈량을 측정해 거부한다.

### 6.3 프롬프트 템플릿 (영문 고정, 변수 `{}`)

```
TASK: Produce a flat 2D shoe upper pattern technical drawing.

INPUTS
- Image 1 = CONTROL LINE DRAWING. This is the geometric ground truth.
- Image 2 = STYLE REFERENCE. Copy only line weight, color convention, drafting style.
- Image 3 = 5-view photos of the target sneaker (lateral, medial, top, front, heel).

HARD RULES
1. Reproduce every line of Image 1 at its exact position. Do NOT move,
   rescale, or re-proportion any contour. You may only clean, close,
   and smooth strokes.
2. Output on a pure white background, no shading, no perspective,
   no 3D rendering, no photorealism. Flat vector-like line art only.
3. Color convention: outer boundary = thin blue line. Inner division
   lines, lace/tongue opening, overlay outlines = thick black line.
4. The pattern is ONE single continuous upper piece, split at the heel
   center. The two upward branches are the ankle collar. The downward
   notch at the bottom is the toe center.
5. EXCLUDE the tongue and the laces entirely. The black inner closed
   curve is the lacing/tongue opening.
6. Draw overlay outlines as SOLID black lines: eyestay, toe cap,
   side stripe, heel counter — positioned per Image 3.
7. Mark notches as short black ticks, {DART_CLAUSE}.
8. No text, no dimensions, no labels, no watermark, no drop shadow.
9. Single centered pattern, canvas 900x1450, right foot.

STYLE: flat technical pattern draft, CAD-like, clean closed contours,
uniform stroke, print-ready line drawing.
```

`{DART_CLAUSE}` = `and draw {N} wedge darts at the marked positions` 또는 `do not add any darts`

**Negative prompt** (오픈소스)

```
photorealistic, 3d render, perspective, shading, gradient, shadow,
texture, fabric weave, sneaker photo, two shoes, pair, text, watermark,
dimension lines, sketchy strokes, open contour, colored fill
```

---

## 7. S5 — 자동 QA 게이트

사람 개입이 없으므로 게이트가 유일한 안전장치다. 각 항목 실패 시 seed 변경 재시도(최대 4회), 이후 최선안 + 플래그 출력.

| # | 게이트 | 판정 | 임계 |
|---|---|---|---|
| G1 | 외곽 폐곡선 1개 | 연결성분/홀 카운트 | 정확히 1 |
| G2 | 내측 개구부 존재 | 내부 홀 1개 | 정확히 1 |
| G3 | 좌우 대칭 | 수직축 미러 IoU | ≥ 0.93 |
| G4 | 기하 이탈량 | S3 선도 대비 Chamfer distance | ≤ 캔버스폭 3% |
| G5 | 종횡비 | S2 예측 대비 | ±8% |
| G6 | 색 규약 분리 | 파란/검정 픽셀 클러스터 분리도 | 이진 판정 |
| G7 | 선 끊김 | 스켈레톤 엔드포인트 수 | ≤ 예상 노치 수 |
| G8 | 오염물 | 텍스트/사진 텍스처 검출 | 없음 |
| G9 | 아일렛 개수 정합 | 검출 tick 수 vs S1의 N | 일치 |

---

## 8. 실험 계획

### 8.1 데이터셋
- 개발셋 10켤레 / 테스트셋 30~50켤레. 러닝화 : 스니커즈 ≈ 1:1.
- 층화 변수: 아일렛 개수(4~7), 오버레이 복잡도(단순/중간/복잡), 소재(메시 우세 / 가죽·스웨이드 우세), 미드솔 높이(로우/청키).

### 8.2 모델 비교 (동일 conditioning map 고정)

| ID | 구성 |
|---|---|
| M1 | SDXL + ControlNet-lineart |
| M2 | Flux.1-dev + ControlNet-union |
| M3 | Qwen-Image-Edit |
| M4 | Gemini 2.5 Flash Image |
| M5 | GPT-Image-1 edit |

### 8.3 어블레이션

| ID | 제거/변경 | 검증 목적 |
|---|---|---|
| A1 | conditioning map 제거 (프롬프트+5뷰만) | S2/S3 기하 파이프라인의 기여도 |
| A2 | IP-Adapter 제거 | 참조 1장의 스타일 전이 효과 |
| A3 | 5뷰 → lateral+top 2뷰 | 뷰 필수성 검증 |
| A4 | 인페인팅 패스 제거 | 국소 리파인 필요성 |
| A5 | shrink factor k ∈ {0.88, 0.92, 0.96, 1.0} | 전개 계수 민감도 |
| A6 | 다트 on/off | 다트 표시 실효성 |
| A7 | 45° 뷰 → 0° 뷰 | 45° 보정 로직 검증 |
| A8 | ControlNet scale ∈ {0.6, 0.85, 1.0} | 기하 고정 vs 디테일 자유도 트레이드오프 |

### 8.4 평가 프로토콜 (전문가 육안)
전문가 2명 이상, 블라인드·랜덤화, 5점 척도 6축.

1. **외곽선 타당성** — bite line/topline이 실제 신발과 부합하는가
2. **eyestay 형상 충실도** — 레이싱 개구부가 대상 신발을 반영하는가
3. **오버레이 위치 정확도** — 토캡/스트라이프/스테이 위치
4. **대칭·비례** — 좌우 대칭 및 길이/높이 비
5. **선 품질** — 폐곡선, 균일 스트로크, CAD 임포트 가능성
6. **후보정 공수** — "이 초안을 봉제 가능 수준으로 만드는 데 필요한 수정량" (1 = 전면 재작업 … 5 = 거의 없음)

집계: 축별 평균 + 총점. 신뢰도는 Krippendorff's α (목표 ≥ 0.67).

**정량 프록시(회귀 방지용 CI 지표)**: G3 대칭 IoU, G4 Chamfer, G5 종횡비 오차, S2 girth 잔차. 육안 평가는 비용이 크므로 프록시로 1차 스크리닝 후 상위안만 전문가에게 올린다.

### 8.5 성공 기준
- 총점 평균 ≥ 3.5/5, 축6(후보정 공수) ≥ 3.0
- G1~G9 자동 통과율 ≥ 85% (재시도 포함)

---

## 9. 실패 모드와 대응

| ID | 실패 모드 | 원인 | 대응 |
|---|---|---|---|
| F1 | bite line 오검출 (미드솔이 갑피와 동색·투명 케이지) | 색 불연속 소실 | lateral/medial 상호 검증 + top 뷰 실루엣 폭 변화점으로 대체 추정, 실패 시 라스트 표준 bite line 프로파일로 폴백 + 플래그 |
| F2 | 청키 미드솔이 갑피를 가림 | 하부 정보 손실 | 가려진 구간은 인접 스테이션 스플라인 외삽, 신뢰도 하향 |
| F3 | 니트/양말형 갑피로 설포 경계 불명확 | 개구부 정의 붕괴 | 아일렛 열 + 칼라 개구부로 개구부 경계 합성, "sock-fit" 서브모드 분기 |
| F4 | 생성 모델이 포토리얼 신발을 그림 | 프롬프트 우세 실패 | ControlNet scale ↑, negative 강화, 게이트 G8 거부 후 재시도 |
| F5 | 모델이 참조 패턴을 그대로 복사 (형상 미반영) | IP-Adapter scale 과다 | scale ≤ 0.5 고정, G4 Chamfer가 "너무 작은" 이상치(참조와 동일)도 탐지 |
| F6 | 다트 계산 불안정 (곡률 프록시 노이즈) | 2D 단면 근사 한계 | 누적 각결손 신뢰구간 폭 > 5°면 다트 생략, 플래그 |
| F7 | 45° 뷰 원근 왜곡으로 치수 과대 | 코사인 보정 부족 | 45° 뷰는 형상지수·폭 추정 전용, 절대 높이는 lateral 우선 (§3.4) |
| F8 | 한 쌍 이미지에서 잘못된 발 선택 | 연결성분 순서 가정 오류 | 토 방향 비대칭(내측 곡선이 더 직선적)으로 좌우 재확인, 메타데이터와 불일치 시 메타데이터 우선 |
| F9 | 선 끊김 / 열린 윤곽 | 디퓨전 스트로크 특성 | G7 실패 → 모폴로지 클로징 후처리, 그래도 실패 시 재시도 |
| F10 | 좌우 비대칭 출력 | 확률적 생성 | S3 선도를 좌우 대칭화 후 조건화 + 출력에 미러-평균 옵션 |
| F11 | 오버레이 실선이 분할선과 혼동 | 색·두께만으로 구분 | 오버레이는 별도 인페인팅 패스로 마지막에 합성, 레이어 분리 유지 |
| F12 | 생성 모델이 기여 없음 (S3 선도가 곧 답) | 아키텍처 상 가능 | **실패가 아니라 유효한 결과** — A1/A8 어블레이션으로 확인되면 모델을 후처리 정리 전용으로 축소하고 파이프라인 단순화 |

---

## 10. 남은 리스크 · 후속 결정 필요

1. **shrink factor k**는 소재 의존적이며 스케일 정보 없이 검증 불가 → A5 실험 결과에 따라 소재 세그멘테이션 기반 k 룩업테이블 도입 여부 결정.
2. **참조 패턴 1개**는 스타일 전이의 병목이다. 추가 확보 시 IP-Adapter 다중 참조로 즉시 개선 가능하므로, 개발 중 3~5쌍 확보를 권한다(재학습 아님).
3. **완전 자동 + 육안 평가** 조합은 프로덕션 리스크가 있다. G1~G9 통과율이 85%에 못 미치면 최소한 "플래그된 케이스만 사람이 검토"하는 부분 HITL 도입을 재검토해야 한다.
4. **F12가 현실화될 가능성이 상당히 높다.** 이 경우 "이미지 생성 AI로 패턴 생성"이라는 요구사항의 해석을 (a) 모델이 기하를 생성 → (b) 모델이 도면을 렌더링 중 어느 쪽으로 볼지 이해관계자 합의가 필요하다.

---

## 부록 A. 3D→2D 변환 오픈소스 도구 조사

> 본 설계는 §0 제약에 따라 3D 재구성을 사용하지 않는다. 이 부록은 그 제약이 해제될 경우(스캔 데이터 확보, 라스트 모델 제공 등) 즉시 참조할 수 있도록 대안 경로의 도구 지형을 정리한 것이다. §A.4의 특허 항목은 상용화 검토 시 선행 확인 대상이다.

### A.0 두 계열의 구분

3D를 2D로 바꾸는 오픈소스는 목적에 따라 완전히 다른 두 계열로 갈린다.

| 계열 | 하는 일 | 이 프로젝트와의 관계 |
|---|---|---|
| **곡면 전개** (flattening / surface parameterization) | 3D 곡면을 왜곡 최소로 평면에 펼쳐 재단 조각을 얻는다 | S2 girth 전개를 대체할 수 있는 경로 |
| **직교 투상** (HLR, hidden line removal) | 솔리드를 정투상 뷰·단면도로 투영해 치수 기입 도면을 만든다 | 패턴이 아니라 기술도면 출력용. 후공정 산출물 포맷에만 관여 |

패턴 재단이 목표이므로 관심 대상은 전자다. 후자는 결과 패턴을 DXF 도면으로 문서화할 때만 쓰인다.

### A.1 곡면 전개 계열 (패턴 재단용)

| 도구 | 라이선스 | 알고리즘 / 특징 | 이 프로젝트 적합성 |
|---|---|---|---|
| **Boundary First Flattening (BFF)** | 저장소 확인 필요(상용 시 주의) | 등각 전개. 경계 형상과 원뿔 특이점(cone singularity)을 직접 지정 → 왜곡을 어디로 밀어낼지 통제 가능. 대화형 속도 | **높음.** 발등·힐의 이중 곡률에서 왜곡 배분을 제어할 수 있는 유일한 실용 도구 |
| **libigl** | MPL2 (Python 바인딩 有) | LSCM(등각·선형), ARAP(거리 보존·국소/전역 반복), SCP(스펙트럴 등각) | **높음.** 신발 논문들의 Wang·Smith·Yuen 에너지 최소화 전개와 동일 계열 |
| **Blender + Seams to Sewing Pattern** | GPL | UV 언랩으로 시임을 그은 뒤 UV를 3D 월드 공간 평면 조각으로 되돌리고 SVG 내보내기 | **중간.** 실물 재봉 전제로 설계됨. 입력 메시가 매니폴드·노멀 정상이어야 함 |
| **xatlas** | MIT | 자동 UV 아틀라스 생성 (상향식 차트 병합) | **낮음.** 국소 기하만 보므로 조각이 잘게 쪼개짐. 시임은 사람/규칙이 지정하는 편이 낫다 |
| **Seamly2D** | GPLv3+ | 전개가 아니라 파라메트릭 패턴 제작 CAD. 치수를 named variable로 사용 | **후공정.** 전개 결과를 다듬고 사이즈 전개하는 단계. §5의 `scale_field` 확장과 개념적으로 대응 |
| **DXF2papercraft** | GPL, 개발 중단 | 다면체 DXF의 인접 면 단위 접이식 전개 | **부적합.** 곡면 근사가 아닌 순수 다면체 전개. Blender Paper Model 확장이 현역 대안 |

**알려진 함정**
- ARAP 결과는 단사(bijective) 보장이 없어 조각이 겹칠 수 있다. 단사성이 필요하면 절개선과 파라미터화를 동시 최적화하는 OptCuts 계열을 봐야 한다.
- 큰 메시에서 LSCM이 "Numerical issue"로 실패하는 사례가 보고되어 있다. 메시 정규화와 단일 경계 루프 확인이 1차 대응이다.
- BFF·ARAP 모두 시임(경계)을 사람이 정의해야 한다. **전개 품질을 결정하는 변수는 알고리즘 선택이 아니라 시임 정의다.**

### A.2 직교 투상 계열 (기술도면용)

| 도구 | 라이선스 | 특징 |
|---|---|---|
| **FreeCAD TechDraw** | LGPL2+ | 정투상 뷰·단면도·상세도 + 치수 기입 → DXF/SVG/PDF. 내부적으로 OCCT HLR 사용. 공식 문서 자체가 "3D 없이 2D 도면만 필요하면 LibreCAD/QCad를 쓰라"고 안내 |
| **OCCT `HLRBRep` + pythonocc / build123d** | LGPL2.1+exception / Apache2 | 파이프라인에 코드로 박아 넣는 경로. `HLRBRep_Algo`는 정확한 곡선, `HLRBRep_PolyAlgo`는 폴리곤 근사(고속). 가시 예각선·실루엣·스무스 에지·은선 실루엣을 종류별 추출 → 레이어 분리 DXF. `ExportDXF`로 단위·색·선종 지정 |
| **OpenSCAD `projection()`** | GPL2 | 3D를 그대로 눌러 2D DXF/SVG로 내보내는 최소 수단 |
| **trimesh + ezdxf** | MIT | Python만으로 단면 추출 후 DXF 작성. 가장 가벼움 |

**주의**: OCCT HLR은 겹친 선(superimposed lines)을 제거하지 않으므로 후처리가 필요하다.

### A.3 3D 경유 대안 경로 (제약 해제 시)

현재 파이프라인(§1)을 3D 경유로 교체하면 다음 순서가 된다.

1. 5뷰 이미지에서 라스트/어퍼 표면 복원.
2. 페더라인·인스텝 중심선·힐 중심선을 **측지선(geodesic)으로 그어 표면을 패치로 분할**. 전통 제화의 style line 작업에 해당한다.
3. 각 패치를 ARAP 또는 BFF로 전개.
4. DXF 내보내기 + 봉제 여유 부가.

**S2와의 대응 관계**: 2단계가 §4의 스테이션 분할을, 3단계가 §4의 3~4단계 호길이 적분을 대체한다. 반대로 §4.1의 다트 산정은 3D 경유 시 가우스 곡률을 프록시가 아니라 직접 계산할 수 있어 F6(다트 계산 불안정)이 구조적으로 해소된다. 즉 **3D 경유의 최대 이득은 다트 정확도이고, 최대 비용은 2단계 시임 정의의 자동화**다.

### A.4 선행 조사 결과 · 특허

- **신발 전용 오픈소스 전개 도구는 존재하지 않는다.** 학술 논문과 특허만 있고 실행 가능한 코드가 공개된 사례를 찾지 못했다. 범용 파라미터라이제이션에 신발 제약을 얹는 것이 유일한 경로다.
- 표준 참조 알고리즘: Wang, Smith & Yuen, "Surface flattening based on energy model", *Computer Aided Design* 34 (2002) 823–833. 에너지 최소화 계열의 원전이며 §4의 girth 전개와 목적이 같다.
- 대안 계열: 전개 가능 스트립(developable strip) 근사 — 곡면을 전개 가능한 띠들로 쪼개 왜곡 없이 빠르게 펼친다.
- **특허 주의**: US 11,972,537(3D 신발 갑피 템플릿 평면화 — 라스트를 medial/lateral/insole/opening 4면으로 보고 3D 경계선으로 분할 후 에너지 최소 2D 격자 획득), US 11,132,474(2D 패널과 3D 형상 간 전단사 변형함수 `f`의 역매핑). 상용화 전 확인 필요.

### A.5 참고 링크

- [Boundary First Flattening](https://geometrycollective.github.io/boundary-first-flattening/)
- [libigl tutorial](https://libigl.github.io/tutorial/) · [libigl Python bindings](https://github.com/libigl/libigl-python-bindings/blob/main/tutorial/tutorials.ipynb)
- [Seams to Sewing Pattern (원작)](https://thomaskole.nl/s2s/) · [유지보수 포크](https://github.com/artyredd/blender-seams-to-sewing-pattern)
- [FreeCAD TechDraw Workbench](https://github.com/FreeCAD/FreeCAD-documentation/blob/main/wiki/TechDraw_Workbench.md) · [TechDraw 튜토리얼(2025)](https://blog.freecad.org/2025/10/10/tutorial-getting-started-with-techdraw/)
- [OCCT HLRBRep_PolyAlgo](https://dev.opencascade.org/doc/occt-7.7.0/refman/html/class_h_l_r_b_rep___poly_algo.html) · [pythonocc HLRBRep API](http://www.aliyuncad.com/OCC.Core.HLRBRep.html) · [build123d Import/Export](https://build123d.readthedocs.io/en/latest/import_export.html)
- [Seamly2D](https://github.com/FashionFreedom/Seamly2D)
- [PartUV: Part-Based UV Unwrapping](https://arxiv.org/html/2511.16659v1) · [Flatten Anything](https://arxiv.org/pdf/2405.14633)
- [신발 3D 곡면 평면 전개 논문](https://link.springer.com/article/10.1007/s12206-008-0609-0) · [라스트 표면 재구성·전개](https://www.scrigroup.com/limba/engleza/124/RECONSTRUCTION-AND-FLATTENING-74882.php) · [US 11,972,537](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/11972537)
