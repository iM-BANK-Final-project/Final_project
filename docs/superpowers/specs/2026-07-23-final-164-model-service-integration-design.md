# FS_FINAL_164_TUNED 서비스 통합 설계

## 1. 목표

현재 서비스의 `FS2_R1_DACK_DYNAMIC` 56피처·LightGBM·Isotonic 계약을 팀이 확정한 `FS_FINAL_164_TUNED` 164피처·LightGBM·Platt 계약으로 교체한다.

서비스는 새 2025-12 점수에서 `score_eligible=True`인 3,341개 법인만 노출하고, 새 위험확률로 FISIM 기반 `CLV_Risk`, `PotentialLoss`, `defense_rank`를 다시 계산한다. DB, API, 필터, 배지, AI 보고서와 PDF는 새 모델의 5개 위험구간과 SHAP Top 10을 일관되게 사용한다.

## 2. 범위와 비범위

### 범위

- 새 점수·추세 CSV 검증과 서비스 입력 전환
- 새 위험확률 기반 CLV·방어순위 재계산
- SQLite 위험구간·임계값 계약 교체
- API 필드와 필터 쿼리 교체
- 전체 프론트엔드의 5단계 위험구간 표시
- 164피처 SHAP 프롬프트·후처리 전환
- README, AGENTS, 모델 문서의 source-of-truth 갱신

### 비범위

- 모델 재학습 또는 Platt 재적합
- 164개 피처 원천 생성
- joblib 번들 생성
- 2025-07~12 점수 재산출
- 3,341개 적격 정의 또는 `Y_INTERVENE_M12_v2` 변경

웹 요청에서는 모델·SHAP·CLV를 계산하지 않는다. 팀이 제공한 사전 계산 CSV를 검증하고 DB로 적재한다.

## 3. 권위 입력

### 3.1 운영 점수

경로:

```text
src/models/web_m12_final_scores_202512_all_3372.csv
```

잠금값:

- 전체 3,372행, 법인ID 3,372개
- 기준월 `202512`
- `score_eligible=True` 3,341개
- `score_eligible=False` 31개
- target `Y_INTERVENE_M12_v2`
- feature set `FS_FINAL_164_TUNED`
- feature count `164`
- calibration `PLATT`
- threshold `0.26479401324821045`
- probability status `VALIDATION_PLATT_LOCKED_SERVICE_REESTIMATION_DEFERRED`
- 적격 고객 SHAP Top 10 결측 없음

31개 비적격 행에는 참고용 확률과 SHAP이 있더라도 DB·API·KPI·필터·화면에서 완전히 제외한다.

### 3.2 월별 위험 추세

경로:

```text
src/models/web_m12_final_risk_trend_202507_202512.csv
```

정확히 2025-07~2025-12의 6행이어야 하고 모델명은 모든 행에서 `FS_FINAL_164_TUNED_LIGHTGBM_PLATT`여야 한다. `high_risk_count`와 `high_risk_share`는 `risk_probability >= 0.26479401324821045`인 적격 고객 수와 비중이다.

2025-12 잠금값:

```text
eligible_count  = 3341
average_risk    = 0.052368465336916116
high_risk_count = 181
high_risk_share = 181 / 3341
```

12월 추세 값은 운영 점수 CSV와 허용오차 `1e-12` 안에서 일치해야 한다.

### 3.3 Git 관리

최종 점수 CSV, 최종 추세 CSV와 점수 생성 코드는 서비스 재현에 필요한 운영 산출물로 추적한다. joblib과 대용량 원천·피처 CSV는 기존 `.gitignore` 정책을 유지한다.

## 4. 위험확률과 위험구간

`risk_probability`는 Platt 보정된 향후 6개월 `Y_INTERVENE_M12_v2` 발생확률이다. 해지·부도·폐업 확률이 아니다.

위험구간은 적격 3,341개 내부의 안정적 내림차순 순위로 정한다.

| code | name | order | 2025-12 count |
|---|---|---:|---:|
| `G1_TOP_1` | 상위 1% | 1 | 34 |
| `G2_1_TO_3` | 상위 1~3% | 2 | 67 |
| `G3_3_TO_5` | 상위 3~5% | 3 | 67 |
| `G4_5_TO_10` | 상위 5~10% | 4 | 167 |
| `G5_REST` | 나머지 90% | 5 | 3,006 |

CSV의 `risk_rank_eligible`, `risk_band`, `risk_band_name`, `risk_band_order`를 저장하되 다음을 다시 검증한다.

- 순위는 1~3,341이 중복 없이 연속
- 동일 위험확률은 법인ID 오름차순으로 순위 결정
- 구간 code·name·order가 순위 경계와 일치
- 5개 구간 합계가 3,341

기존 확률 `0.60`, `0.75` 기반 `WATCH/MEDIUM/HIGH` 위험등급은 폐기한다.

## 5. 임계값과 운영 우선순위

`predicted_positive_model_scope`는 적격 고객에 대해 `risk_probability >= threshold`일 때 1이다. 2025-12에는 181개다.

Overview와 월별 추세에서 기존 “고위험” 문구는 “모델 임계값 이상”으로 바꾼다.

추천 전략의 `priority_level`은 위험구간과 별개의 실행 우선순위로 유지하고 다음처럼 파생한다.

| 위험구간 | priority_level | 접촉 전략 |
|---|---|---|
| `G1_TOP_1` | `URGENT` | RM 최우선 직접 접촉 |
| `G2_1_TO_3` | `HIGH` | RM 우선 직접 접촉 |
| `G3_3_TO_5` | `MEDIUM_HIGH` | RM 단기 계획 접촉 |
| `G4_5_TO_10` | `MEDIUM` | RM 계획 접촉 |
| `G5_REST` | `WATCH` | 모니터링 후 필요 시 접촉 |

방어순위의 기본 정렬은 계속 `defense_rank`이며 위험구간은 보조 판단 정보다.

## 6. CLV와 방어순위

수익성 수식과 실제 6개월 기간은 변경하지 않는다.

```text
CLV_NoRisk   = Σ actual_FISIM_m, m=2025-07..2025-12
CLV_Risk     = CLV_NoRisk / (1 + new_risk_probability)
PotentialLoss = CLV_NoRisk - CLV_Risk
defense_value = max(PotentialLoss, 0)
```

`defense_rank`는 새 `defense_value`, 새 위험확률, `CLV_NoRisk` 내림차순 후 법인ID 오름차순으로 다시 계산한다. 운영 점수와 CLV CSV의 위험확률은 허용오차 `1e-12` 안에서 같아야 한다.

## 7. SQLite 계약

원자적 DB 재생성 방식을 유지한다. 기존 DB를 인플레이스 마이그레이션하지 않고 임시 DB를 완성한 뒤 교체한다.

### `risk_scores`

```text
corporate_id
as_of_month
model_name
risk_probability
risk_rank
risk_band
risk_band_name
risk_band_order
predicted_positive
threshold
```

`model_name`은 `FS_FINAL_164_TUNED_LIGHTGBM_PLATT`다.

### `customer_snapshots`

기존 `risk_level`을 제거하고 다음을 추가한다.

```text
risk_rank
risk_band
risk_band_name
risk_band_order
predicted_positive
threshold
```

### `monthly_summaries`와 `risk_trends`

`monthly_summaries.high_risk_share`와 `risk_trends.high_risk_count`, `risk_trends.high_risk_share`는 입력 CSV 호환을 위해 유지하되 서비스 의미는 “모델 임계값 이상 고객 수·비중”으로 잠근다.

인덱스는 `risk_level` 대신 `(as_of_month, risk_band_order)`와 `(as_of_month, risk_band)`를 사용한다.

## 8. API 계약

### 고객

기존 `riskLevel`을 제거하고 아래 필드를 반환한다.

```text
riskBand
riskBandName
riskBandOrder
riskRank
predictedPositive
threshold
```

`risk`는 기존과 같이 백분율 숫자로 반환한다.

### 필터

기존 `riskLevels`와 쿼리 `risk_level`을 제거한다.

```text
riskBands: [
  { code: "G1_TOP_1", name: "상위 1%", order: 1 },
  ...
]
```

고객·추천 API는 `risk_band=<code>`를 받는다.

추천 응답에도 `riskBand`, `riskBandName`, `riskBandOrder`를 포함해 실행 우선순위 `priority`와 고객 위험구간을 구분한다.

### Overview

기존 `highRiskShare`는 `thresholdShare`로 바꾸고 월별 항목도 다음을 사용한다.

```text
thresholdShare
thresholdCount
eligibleCount
averageRisk
```

내부 CSV와 DB 컬럼명이 `high_risk_*`이더라도 공개 API와 UI에서는 임계값 의미를 명시한다.

## 9. 프론트엔드 계약

지속거래약화, CRM 우선순위, 맞춤추천, AI 보고서의 고객 위험 배지는 5개 위험구간을 사용한다.

| 위험구간 | tone |
|---|---|
| 상위 1% | 진한 coral |
| 상위 1~3% | coral |
| 상위 3~5% | amber |
| 상위 5~10% | blue |
| 나머지 90% | gray 또는 연한 mint |

필터는 code를 API에 보내고 label에는 한국어 name을 표시한다. 확률 숫자는 기존처럼 소수점 한 자리까지 표시한다.

Overview:

- “고위험 비중” → “모델 임계값 이상 비중”
- 상세 문구에 임계값 `26.5%`를 표시
- 월별 그래프 보조 문구 “고위험” → “임계값 이상”
- 6개월 평균위험 선과 임계값 이상 비중 막대 구조는 유지

추천 카드의 실행 우선순위 배지와 고객 위험구간 배지는 구분해 함께 표시한다.

## 10. SHAP·AI 보고서·PDF

UI와 PDF에는 새 CSV의 SHAP Top 10을 순위대로 모두 표시한다. SHAP 값은 LightGBM raw-score 공간의 로컬 기여도이며 확률 변화량이나 인과효과로 표현하지 않는다.

기존 56피처 고정 목록 검증을 새 164피처 명명 규칙 검증으로 교체한다.

허용 구조:

- 관계 기본 피처
- `DACK__<D|A|C|K>__<metric>`
- `EXP_DIFF__<D|A|C|K>__<metric>`
- `EXP_PATH__<D|A|C|K>__<metric>`
- `EXP_CROSS__<metric>__<aggregation>`
- `EXP_KM__<metric>`

`CTX__`, `SEG__`와 알 수 없는 prefix는 SHAP 모델 피처로 허용하지 않는다.

보고서 프롬프트에는 다음 모델 문맥을 전달한다.

```text
featureSet  = FS_FINAL_164_TUNED
featureCount = 164
calibration = PLATT
threshold = 0.26479401324821045
riskBand = 고객의 5단계 위험구간
```

Top 10 원본은 모두 전달하고, 보고서 문장만 같은 축·유사 피처를 하나의 신호로 묶는다. 정량값, 순위, feature 이름은 Gemini가 재생성하지 않는다.

## 11. 문서 source-of-truth

통합 완료 후 source-of-truth 순서를 다음처럼 바꾼다.

1. `src/models/web_service_m12_final_scoring.py`
2. `src/models/web_m12_final_scores_202512_all_3372.csv`
3. `src/models/web_m12_final_risk_trend_202507_202512.csv`
4. `src/수익성F(y선정포함).ipynb`
5. 이 통합 설계

기존 `web_202512_m12_final_model.ipynb`, 56피처·Isotonic 문서와 점수는 이전 운영 모델 근거로만 취급한다.

확률 상태 `VALIDATION_PLATT_LOCKED_SERVICE_REESTIMATION_DEFERRED`는 모델 문서에 그대로 기록하고 숨기지 않는다.

## 12. 실패 처리와 검증

다음 조건이면 기존 SQLite를 교체하지 않는다.

- 입력 파일·필수 컬럼 누락
- 전체 3,372개 또는 적격 3,341개 불일치
- 31개 비적격이 서비스 테이블에 포함
- 확률·임계값·순위·위험구간 계약 위반
- SHAP Top 10 결측·비유한 값·중복 순위
- 추세 6개월 또는 12월 대조 불일치
- CLV 위험확률 대조 불일치

완료 검증:

- DB 고객·위험·세그먼트·CLV·추천 각 3,341행
- SHAP 33,410행
- 추세 6행
- 5개 위험구간 수 `34/67/67/167/3006`
- 임계값 이상 181개
- API 필터·정렬·보고서가 5개 구간을 사용
- 백엔드 전체 테스트 통과
- 프론트엔드 전체 테스트와 production build 통과
- 통합 실행 후 주요 5개 페이지 수동 확인

## 13. 롤백

DB 생성 실패 시 기존 SQLite는 원자적 교체 전 상태를 유지한다. 배포 후 문제가 발견되면 통합 커밋을 되돌리고 이전 점수 경로로 DB를 재생성한다. 모델 재학습이나 수동 DB 수정으로 롤백하지 않는다.
