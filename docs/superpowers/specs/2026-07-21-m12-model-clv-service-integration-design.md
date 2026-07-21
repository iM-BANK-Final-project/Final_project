# M12 Model and CLV Service Integration Design

## 1. Purpose

Replace the RM web service's retired event-label model and customer-value proxy contract with the final contracts implemented in:

- `src/models/web_202512_m12_final_model.ipynb`
- `src/수익성F(y선정포함).ipynb`

The service must expose only the 3,341 firms that are eligible for the final target formula at the 2025-12 operating cutoff. It must rank customers by FISIM-based six-month potential loss rather than by `risk_probability × customer_value_proxy`.

## 2. Source-of-Truth Hierarchy

The two final notebooks above are authoritative for the operating target, model, profitability, CLV, and defense-priority contracts. Active project documentation must be updated to distinguish the earlier retrospective event label from the final rolling intervention target.

- `Y_지속거래약화_3M70` remains historical evidence for a retrospective first-event label. It is not the deployed model target.
- `Y_INTERVENE_M12_v2` is the final rolling six-month prediction target used by the deployed model.
- `README.md`, `AGENTS.md`, `financial_dormancy.md`, `y_setting_pipeline.md`, and `src/models/model.md` must describe this distinction consistently.

## 3. Final Target Contract

For a cutoff month `c`, define four activity axes:

- `D`: 요구불입금금액 + 요구불출금금액
- `A`: 자동이체금액
- `C`: 창구거래금액 + 인터넷뱅킹거래금액 + 스마트뱅킹거래금액 + 폰뱅킹거래금액 + ATM거래금액
- `K`: 신용카드사용금액 + 체크카드사용금액

For each axis `g`:

```text
ONSET_g:
  c+1, c+2, c+3의 각 전년동월비가 모두 0.60 미만

PERSIST_g:
  mean(c+4:c+6) / mean(c-11:c) < 0.70

W_g = ONSET_g AND PERSIST_g
```

The final target is:

```text
Y_INTERVENE_M12_v2 = W_D AND (W_A OR W_C OR W_K)
```

An axis is not evaluable when any onset YoY denominator is zero or when its 12-month persistence baseline is zero. The full target is eligible only when `D` is evaluable and at least one of `A`, `C`, or `K` is evaluable. Ineligible cases are not converted to zero.

Locked target results are:

- Rolling grid: 64,068 rows
- Eligible rows: 63,572
- Positive rows: 1,966
- Eligible firms across the rolling grid: 3,354
- Positive firms across the rolling grid: 639

## 4. Final Model Contract

- Feature set: `FS2_R1_DACK_DYNAMIC`
- Feature count: 56
- Model: LightGBM
- Probability calibration: Isotonic regression fitted on grouped out-of-fold predictions
- Final test cutoff: 2025-06
- Final training rows: 43,499
- Final test rows: 3,346
- Final test positives: 119
- Operating cutoff: 2025-12
- Operating population exposed by the service: 3,341 target-eligible firms
- Segment identifiers and industry fields are explanation and stability-audit fields, not model inputs.
- `risk_probability` means the probability of `Y_INTERVENE_M12_v2` during the next six months. It is not a probability of closure, default, or confirmed churn.

The active service consumes `src/models/web_m12_intervene_v2_scores_202512_eligible_3341.csv`, verifies exactly 3,341 unique eligible firms, and calculates all operating outputs inside that population. The 31 ineligible firms are excluded before export and remain excluded from the database, API, KPIs, filters, and UI.

## 5. FISIM Profitability Contract

The production preparation code must reproduce the final notebook instead of the retired quarterly-FTP implementation.

For firm `i` and month `m`:

```text
L  = 여신_운전자금대출잔액 + 여신_시설자금대출잔액
DS = 거치식예금잔액 + 적립식예금잔액
DR = 요구불예금잔액

V_FTP(i,m)
  = L  × (기업대출금리_m - FTP_m)
  + DS × (FTP_m - 저축성수신금리_m)
  + DR × (FTP_m - 요구불금리)
```

Unit rules:

- 기업대출금리 and 저축성수신금리 are monthly percentages and are divided by 100 once.
- Monthly FTP is already a decimal and is not rescaled.
- The monthly demand-deposit rate is `0.01% = 0.0001`.
- Month-end balances are used directly. Monthly-average balances and day-count annualization are not used.
- Negative monthly FISIM values are preserved for reverse-margin diagnosis.
- D/A/C/K activity, relationship features, segments, and industry are not direct FISIM inputs.

## 6. Six-Month CLV and Defense Priority

For cutoff `c = 2025-12`, forecast months `c+1` through `c+6` use the corresponding prior-year month-end balances. The loan, saving-deposit, demand-deposit, and FTP spreads are fixed at their cutoff-month values.

For risk probability `p` and horizon month `h`:

```text
S(h) = (1 - p)^(h/6)

CLV_NoRisk = sum(predicted_FISIM_h for h=1..6)

CLV_Risk = sum(
  predicted_FISIM_h × S(h) / (1 + p)
  for h=1..6
)

PotentialLoss = CLV_NoRisk - CLV_Risk
defense_value = max(PotentialLoss, 0)
```

`defense_rank` is assigned only when `defense_value > 0`. Ranking uses this deterministic order:

1. `defense_value` descending
2. `risk_probability` descending
3. `CLV_NoRisk` descending
4. `corporate_id` ascending

The service stores `CLV_NoRisk` for audit and reproducibility but does not display it. The UI displays only `CLV_Risk` and `PotentialLoss` as customer-value fields. `PotentialLoss` is a six-month FISIM-based potential CLV exposure, not confirmed accounting loss.

The retired `customer_value_proxy`, `risk_probability × customer_value_proxy`, and the old meaning of `crm_priority_score` are removed from the active database, API, UI, and documentation.

## 7. Data Preparation and Database Flow

The service database preparation command consumes:

- Corporate monthly source: `outputs/iM뱅크데이터_거시경제지표포함.csv`
- Operating scores: `src/models/web_m12_intervene_v2_scores_202512_eligible_3341.csv`
- Monthly FTP: `outputs/iM뱅크_월별_추정FTP_2023_2025.csv`
- Monthly loan and saving-deposit rates: `outputs/예대금리차2023~2025_순.csv`

The preparation layer must:

1. Validate the 121,392-row, 3,372-firm, 36-month source panel and unique firm-month keys.
2. Reject missing, nonnumeric, or negative required balance inputs.
3. Normalize the cutoff to `2025-12`.
4. Filter scores to the 3,341 eligible firms and reject duplicate or missing firm identifiers.
5. Build monthly FISIM values and the six-month CLV forecast.
6. Derive deterministic defense ranks.
7. Reuse the score artifact's current segment, segment transition, D/A/C/K change rates, and top-three SHAP factors.
8. Atomically replace the SQLite database only after every validation passes.

The active service schema exposes explicit CLV fields:

- `clv_no_risk`
- `clv_risk`
- `potential_loss`
- `defense_value`
- `defense_rank`, nullable for non-defense targets

It also retains risk, segment, weakening-signal, recommendation, and SHAP tables needed by the existing pages. Legacy value-proxy fields are not retained under misleading aliases.

## 8. API Contract

Priority and customer responses replace the retired fields:

```text
remove: valueProxy
remove: profitability
remove: priorityScore
remove: priorityRank

add: clvRisk
add: potentialLoss
add: defenseRank
```

Priority endpoints sort by `defenseRank` by default. Customers without a positive potential loss have a null defense rank and appear after ranked defense targets with a deterministic corporate-ID tie-break.

The overview summary replaces the retired CRM-priority-score total with the sum of positive potential losses and reports it as `potentialLossTotal`. All summary denominators use the 3,341 eligible firms.

## 9. Frontend Contract

The CRM priority page keeps the existing filters for industry, region, dedicated coverage, weakening type, and segment. Its value and priority columns are:

- `CLV_Risk`
- `PotentialLoss`
- `방어순위`

The page does not display `CLV_NoRisk`, a customer-value proxy, generic profitability, or the retired CRM priority score. The overview page labels the aggregate as `잠재손실 방어대상 합계`.

The UI includes this interpretation note near CLV and potential-loss values:

> FISIM 기반 향후 6개월 경제적 기여가치 추정치이며 확정 회계손실이 아닙니다.

Existing in-progress AI report robustness changes are preserved. Reports use the final score artifact's SHAP factors and refer to `향후 6개월 지속거래약화 가능성`, `조기관리 필요`, and `추천 접촉 전략` without describing the score as churn, closure, or default risk.

## 10. Validation and Failure Behavior

Database preparation fails without replacing the existing database when any of these contracts fail:

- Operating score rows after filtering are not exactly 3,341 unique firms.
- The source panel is not exactly 3,372 firms with 36 unique consecutive months per firm.
- The source does not cover 2023-01 through 2025-12.
- Required balance, rate, FTP, score, or identifier fields are missing or invalid.
- Rate or FTP files do not map exactly one record to each required month.
- A CLV forecast does not contain exactly six rows per scored firm.
- Risk probabilities fall outside `[0, 1]`.
- CLV or potential-loss values are non-finite.
- Positive defense ranks are not consecutive integers starting at 1.

Tests cover:

- Exact FISIM formula and unit conversions
- No monthly-average balance or annualization factor
- Six-month survival and CLV formulas
- Zero-risk and negative-FISIM edge cases
- Eligible-population filtering and the 3,341-row lock
- Deterministic defense ranking, including null ranks
- Schema and API removal of legacy customer-value fields
- Priority, overview, risk, recommendation, and AI-report API responses
- Frontend rendering of `CLV_Risk`, `PotentialLoss`, and the interpretation note
- Frontend absence of customer-value proxy and retired priority-score copy
- Atomic database replacement on validation failure

## 11. Compatibility and Change Safety

- The SQLite database is a generated artifact and is rebuilt with the new schema; no in-place legacy migration is required.
- Existing uncommitted user changes in repository, service-builder, AI-report, styles, interpretation, and tests must be preserved and incorporated rather than overwritten.
- Historical label and model implementations remain available for provenance but are not invoked by the active service path.
- The preparation command must be runnable from the repository root without notebook execution or machine-specific absolute paths.
