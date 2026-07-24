# Project Working Notes

## Project Topic

기업금융 RM을 위한 **향후 6개월 지속거래약화 예측, FISIM CLV 기반 방어 우선순위, 세그먼트 맞춤 추천, 저장 SHAP 기반 전략 보고서 서비스**.

## Source-of-Truth Order

현재 운영 정의가 충돌하면 아래 순서로 판단한다.

1. `src/models/web_service_m12_final_scoring.py`
2. `src/models/web_m12_final_scores_202512_all_3372.csv`
3. `src/models/web_m12_final_risk_trend_202507_202512.csv`
4. `src/수익성F(y선정포함).ipynb`
5. `docs/superpowers/specs/2026-07-23-final-164-model-service-integration-design.md`
6. `financial_dormancy.md`
7. `src/models/model.md`

`y_setting_pipeline.md`와 2026-07-13 이전 설계·코드는 과거 Y 탐색 이력이다.

## Service Flow

```text
36개월 완전관측 3,372개 법인
→ Y_INTERVENE_M12_v2 164피처 LightGBM·Platt 점수
→ score_eligible=True 3,341개만 서비스 노출
→ FISIM 기반 CLV_Risk·PotentialLoss
→ 방어순위
→ 세그먼트 기반 맞춤 추천
→ 저장 SHAP 기반 Gemini AI 전략 보고서·PDF
```

## Final Y Contract

최종 운영 Y는 `Y_INTERVENE_M12_v2`다.

```text
D = 요구불입금금액 + 요구불출금금액
A = 자동이체금액
C = 창구 + 인터넷뱅킹 + 스마트뱅킹 + 폰뱅킹 + ATM 거래금액
K = 신용카드사용금액 + 체크카드사용금액

ONSET_g   = c+1~c+3 각 월의 전년동월비 < 0.60
PERSIST_g = mean(c+4:c+6) / mean(c-11:c) < 0.70
W_g       = ONSET_g AND PERSIST_g

Y_INTERVENE_M12_v2 = W_D AND (W_A OR W_C OR W_K)
```

- D가 판정 가능하고 A/C/K 중 하나 이상이 판정 가능할 때만 적격이다.
- ONSET의 전년동월 분모 또는 PERSIST의 과거 12개월 평균이 0인 축은 판정 불가능이다.
- 부적격을 Y=0으로 대체하지 않는다.
- 롤링 lock: 전체 64,068행, 적격 63,572행, 양성 1,966행, 적격 법인 3,354개, 양성 법인 639개.
- `Y_지속거래약화_3M70`은 과거 사후 first-event 라벨이며 배포 target이 아니다.

## Final Model Contract

- Feature set: `FS_FINAL_164_TUNED`, 164개
- Model: LightGBM
- Calibration: validation에서 잠근 Platt
- Operating threshold: `0.26479401324821045`
- Probability status: `VALIDATION_PLATT_LOCKED_SERVICE_REESTIMATION_DEFERRED`
- Operating cutoff: 2025-12
- Input score artifact: `src/models/web_m12_final_scores_202512_all_3372.csv`
- Input trend artifact: `src/models/web_m12_final_risk_trend_202507_202512.csv`
- Service population: `score_eligible=True`인 정확히 3,341개; 나머지 31개 완전 제외
- Risk bands: 적격 확률순위 기준 `G1_TOP_1`, `G2_1_TO_3`, `G3_3_TO_5`, `G4_5_TO_10`, `G5_REST`
- Threshold-positive: 적격 3,341개 중 181개
- Local explanation: 고객별 절대 기여도 기준 `SHAP Top 10`, DB 총 33,410행

`risk_probability`는 향후 6개월 지속거래약화 target 발생 확률이며 실제 해지·부도·확정 휴면 확률이 아니다. 업종·세그먼트는 설명 및 안정성 감사용이지 모델 입력이 아니다.

## FISIM and CLV

```text
L  = 운전자금대출잔액 + 시설자금대출잔액
DS = 거치식예금잔액 + 적립식예금잔액
DR = 요구불예금잔액

V_FTP = L  × (기업대출금리 - FTP)
      + DS × (FTP - 저축성수신금리)
      + DR × (FTP - 0.0001)
```

- 은행 금리는 월별 percentage이므로 `/100` 한 번만 적용한다.
- FTP는 월별 decimal 그대로 사용한다.
- 월말 잔액을 쓰며 월평잔·일수 연환산은 사용하지 않는다.
- 음수 FISIM은 역마진 진단을 위해 보존한다.
- CLV 가치 기초는 기준월 포함 최근 실제 6개월 월별 FISIM 합계다. 2025-12 운영에서는 2025-07~12를 사용한다.
- 미래 잔액·2026년 수익성과 생존확률은 예측하지 않는다.

```text
CLV_NoRisk = Σ actual_FISIM_m, m=c-5..c
CLV_Risk = CLV_NoRisk / (1+p)
PotentialLoss = CLV_NoRisk - CLV_Risk
defense_value = max(PotentialLoss, 0)
```

양수 defense value만 `defense_rank`를 갖는다. 순위는 defense value, risk, `CLV_NoRisk` 내림차순 후 법인ID 오름차순이다.

DB는 `CLV_NoRisk`도 저장하지만 UI의 고객가치 항목은 `CLV_Risk`, `PotentialLoss`만 표시한다. 과거 customer value proxy와 위험×대리점수 우선순위는 사용하지 않는다. `PotentialLoss`는 확정 회계손실이 아니다.

## Data and Service Rules

- 원천은 2023-01~2025-12, 121,392행, 3,372개 법인, 법인별 연속 36개월이어야 한다.
- 고객-월 중복, 필수 잔액 결측·음수, 비정상 확률, 중복 법인ID는 실패 처리한다.
- 서비스 준비 실패 시 기존 SQLite를 교체하지 않는다.
- DB, API, KPI, filter options, UI의 모든 모집단은 적격 3,341개다.
- feature는 기준월까지만 사용하고 target의 미래 관찰창을 누수시키지 않는다.
- 웹 요청 중 모델·CLV·SHAP은 재계산하지 않고 사전 계산 결과만 조회한다.

## UI and API Contract

고객 응답 필드는 `riskBand`, `riskBandName`, `riskBandOrder`, `riskRank`, `predictedPositive`, `threshold`, `clvRisk`, `potentialLoss`, nullable `defenseRank`다. Overview는 `thresholdShare`와 월별 `thresholdCount`를 사용하며 합계는 `potentialLossTotal`이다. 기본 우선순위는 방어순위이며 null은 마지막이다.

필터는 업종, 지역, 전담여부, 약화유형, 세그먼트를 유지한다. UI에는 아래 문구를 표시한다.

> 최근 6개월 실제 FISIM을 위험확률로 조정한 경제적 기여가치 추정치이며 확정 회계손실이 아닙니다.

AI 보고서는 “향후 6개월 지속거래약화 가능성”, “조기관리 필요”, “추천 접촉 전략”을 사용한다.

## Gemini AI Report Contract

- `POST /api/reports/{corporate_id}/generate`: 적격 고객의 저장 위험·`CLV_Risk`·`PotentialLoss`·D/A/C/K·`SHAP Top 10`·추천을 근거로 6개 고정 섹션을 Gemini에서 생성한다.
- `POST /api/reports/{corporate_id}/pdf`: 화면 보고서를 DB 근거와 다시 대조한 후 A4 한국어 PDF를 메모리에서 생성한다.
- 인증은 `GEMINI_API_KEY` 또는 기존 Vertex AI 환경변수를 사용하며 비밀 값을 프론트엔드에 노출하지 않는다.
- PDF 폰트는 `RM_REPORT_FONT_PATH` 또는 지원 OS의 한국어 폰트 fallback을 사용한다.
- AI 보고서와 PDF는 DB에 저장하지 않는다. 정량 수치와 SHAP은 Gemini가 재생성하지 않는다.

## Current Artifacts

- Main design: `financial_dormancy.md`
- Integration spec: `docs/superpowers/specs/2026-07-23-final-164-model-service-integration-design.md`
- Final scoring code: `src/models/web_service_m12_final_scoring.py`
- Final score artifact: `src/models/web_m12_final_scores_202512_all_3372.csv`
- Final trend artifact: `src/models/web_m12_final_risk_trend_202507_202512.csv`
- Final target/CLV notebook: `src/수익성F(y선정포함).ipynb`
- Model notes: `src/models/model.md`
- FISIM/CLV implementation: `src/backend/m12_clv.py`
- Service preparation: `src/backend/prepare_service_database.py`
- Historical Y evidence: `y_setting_pipeline.md`
