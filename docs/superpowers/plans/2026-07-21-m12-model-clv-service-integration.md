# M12 Model and CLV Service Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the RM service around the final `Y_INTERVENE_M12_v2` operating scores and FISIM-based `CLV_Risk`, `PotentialLoss`, and `defense_rank` for exactly 3,341 eligible firms.

**Architecture:** Add a focused CLV calculation module that reproduces the final notebook from repository CSV inputs, then reshape the service builder and generated SQLite schema around explicit CLV fields. Keep the existing risk, signal, recommendation, and SHAP flows, while updating API and React consumers to remove the retired customer-value proxy contract.

**Tech Stack:** Python 3.10, pandas, NumPy, SQLite, FastAPI/Pydantic, pytest, React 19, Vite, Vitest/Testing Library

## Global Constraints

- Operating cutoff is exactly `2025-12`.
- Service population is exactly the 3,341 rows where `score_eligible == True`.
- Final target is `Y_INTERVENE_M12_v2`; `Y_지속거래약화_3M70` is historical only.
- Model is LightGBM with Isotonic calibration and feature set `FS2_R1_DACK_DYNAMIC` containing 56 features.
- FISIM uses month-end balances directly, monthly bank-rate percentages divided by 100 once, monthly FTP decimals unchanged, and demand-deposit monthly rate `0.0001`.
- Six-month CLV uses prior-year same-month balances and cutoff-month spreads.
- UI displays `CLV_Risk` and `PotentialLoss`, not `CLV_NoRisk`.
- Existing uncommitted user edits must be preserved.

---

### Task 1: Final FISIM and CLV calculation module

**Files:**
- Create: `src/backend/m12_clv.py`
- Create: `tests/test_m12_clv.py`

**Interfaces:**
- Produces: `build_monthly_rates(ftp: pd.DataFrame, bank_rates: pd.DataFrame) -> pd.DataFrame`
- Produces: `build_monthly_fisim(source: pd.DataFrame, rates: pd.DataFrame) -> pd.DataFrame`
- Produces: `build_operating_clv(source: pd.DataFrame, rates: pd.DataFrame, scores: pd.DataFrame, cutoff: str = "2025-12") -> pd.DataFrame`
- Output columns: `법인ID`, `기준월`, `CLV_NoRisk`, `CLV_Risk`, `PotentialLoss`, `defense_value`, `defense_rank`

- [ ] **Step 1: Write failing rate and FISIM contract tests**

```python
def test_monthly_fisim_uses_month_end_balances_without_annualization():
    rates = pd.DataFrame({
        "월": [pd.Period("2025-12", freq="M")],
        "대출스프레드_월": [0.04],
        "저축성수신스프레드_월": [0.01],
        "요구불스프레드_월": [0.002],
    })
    source = source_row(
        month=202512,
        loan_working=100.0,
        loan_facility=50.0,
        saving_fixed=20.0,
        saving_installment=10.0,
        demand=40.0,
    )
    result = build_monthly_fisim(source, rates)
    assert result.loc[0, "FISIM_CONTRIB_M"] == pytest.approx(
        150.0 * 0.04 + 30.0 * 0.01 + 40.0 * 0.002
    )
```

- [ ] **Step 2: Run the focused tests and verify the module is missing**

Run: `conda run -n final pytest tests/test_m12_clv.py -q`

Expected: FAIL because `src.backend.m12_clv` does not exist.

- [ ] **Step 3: Implement rate normalization and monthly FISIM**

```python
DEMAND_DEPOSIT_RATE_MONTHLY_DECIMAL = 0.0001

def build_monthly_rates(ftp: pd.DataFrame, bank_rates: pd.DataFrame) -> pd.DataFrame:
    ftp_work = ftp[["month", "monthly_recombined_ytd_rate_decimal"]].copy()
    ftp_work["월"] = pd.PeriodIndex(ftp_work["month"].astype(str), freq="M")
    ftp_work["FTP_월_decimal"] = pd.to_numeric(
        ftp_work["monthly_recombined_ytd_rate_decimal"], errors="raise"
    )
    if len(ftp_work) != 36 or not ftp_work["월"].is_unique:
        raise ValueError("FTP는 2023-01~2025-12의 고유한 36개월이어야 합니다.")

    rate_work = bank_rates.copy()
    rate_work["은행"] = rate_work["은행"].ffill()
    month_columns = [
        column for column in rate_work.columns
        if re.fullmatch(r"\d{4}년\d{2}월", str(column))
    ]
    selected = rate_work.loc[
        rate_work["은행"].astype(str).str.contains("iM뱅크", na=False)
        & rate_work["구분"].isin(["기업대출금리", "저축성수신금리"]),
        ["구분", *month_columns],
    ]
    if selected["구분"].value_counts().to_dict() != {
        "기업대출금리": 1,
        "저축성수신금리": 1,
    }:
        raise ValueError("iM뱅크 기업대출·저축성수신 금리는 각각 한 행이어야 합니다.")
    long = selected.melt(id_vars="구분", var_name="금리기준월", value_name="월율_pct")
    parts = long["금리기준월"].str.extract(r"(?P<year>\d{4})년(?P<month>\d{2})월")
    long["월"] = pd.PeriodIndex(parts["year"] + "-" + parts["month"], freq="M")
    long["월율_pct"] = pd.to_numeric(long["월율_pct"], errors="raise")
    pivot = long.pivot(index="월", columns="구분", values="월율_pct").reset_index()
    result = ftp_work[["월", "FTP_월_decimal"]].merge(
        pivot, on="월", how="inner", validate="one_to_one"
    )
    result["기업대출금리_월_decimal"] = result["기업대출금리"] / 100
    result["저축성수신금리_월_decimal"] = result["저축성수신금리"] / 100
    result["대출스프레드_월"] = (
        result["기업대출금리_월_decimal"] - result["FTP_월_decimal"]
    )
    result["저축성수신스프레드_월"] = (
        result["FTP_월_decimal"] - result["저축성수신금리_월_decimal"]
    )
    result["요구불스프레드_월"] = (
        result["FTP_월_decimal"] - DEMAND_DEPOSIT_RATE_MONTHLY_DECIMAL
    )
    return result.sort_values("월").reset_index(drop=True)

def build_monthly_fisim(source: pd.DataFrame, rates: pd.DataFrame) -> pd.DataFrame:
    balance_columns = [
        "여신_운전자금대출잔액", "여신_시설자금대출잔액",
        "거치식예금잔액", "적립식예금잔액", "요구불예금잔액",
    ]
    required = ["법인ID", "기준년월", *balance_columns]
    missing = sorted(set(required) - set(source.columns))
    if missing:
        raise ValueError(f"FISIM 필수 컬럼 누락: {missing}")
    work = source[required].copy()
    work["법인ID"] = work["법인ID"].astype("string")
    work["월"] = pd.PeriodIndex(work["기준년월"].astype(str), freq="M")
    work[balance_columns] = work[balance_columns].apply(pd.to_numeric, errors="coerce")
    if work[balance_columns].isna().any().any() or work[balance_columns].lt(0).any().any():
        raise ValueError("FISIM 잔액은 결측이 없는 비음수 숫자여야 합니다.")
    if work.duplicated(["법인ID", "월"]).any():
        raise ValueError("법인ID+월 중복이 있습니다.")
    work["대출잔액_L"] = work[balance_columns[:2]].sum(axis=1)
    work["저축성수신잔액_DS"] = work[balance_columns[2:4]].sum(axis=1)
    work["요구불잔액_DR"] = work["요구불예금잔액"]
    work = work.merge(rates, on="월", how="left", validate="many_to_one")
    work["대출_FISIM_CONTRIB_M"] = work["대출잔액_L"] * work["대출스프레드_월"]
    work["저축성수신_FISIM_CONTRIB_M"] = (
        work["저축성수신잔액_DS"] * work["저축성수신스프레드_월"]
    )
    work["요구불_FISIM_CONTRIB_M"] = work["요구불잔액_DR"] * work["요구불스프레드_월"]
    work["FISIM_CONTRIB_M"] = work[[
        "대출_FISIM_CONTRIB_M", "저축성수신_FISIM_CONTRIB_M",
        "요구불_FISIM_CONTRIB_M",
    ]].sum(axis=1)
    return work
```

- [ ] **Step 4: Add failing CLV, zero-risk, negative-FISIM, and rank tests**

```python
def test_operating_clv_uses_six_prior_year_balances_and_deterministic_rank():
    result = build_operating_clv(source_2025_h2(), cutoff_rates(), scores())
    assert result["예측월수"].eq(6).all()
    assert result.loc[result["법인ID"].eq("ZERO"), "PotentialLoss"].item() == pytest.approx(0)
    assert result.loc[result["defense_value"].gt(0), "defense_rank"].dropna().astype(int).tolist() == [1, 2]
```

- [ ] **Step 5: Implement six-month CLV and defense ranking**

```python
monthly["S_사건미발생확률"] = np.power(
    1 - monthly["risk_probability"], monthly["예측개월차_h"] / 6.0
)
monthly["CLV_Risk_월기여"] = (
    monthly["예측_FISIM_M"] * monthly["S_사건미발생확률"]
    / (1 + monthly["risk_probability"])
)
customer["PotentialLoss"] = customer["CLV_NoRisk"] - customer["CLV_Risk"]
customer["defense_value"] = customer["PotentialLoss"].clip(lower=0)
```

- [ ] **Step 6: Run focused tests**

Run: `conda run -n final pytest tests/test_m12_clv.py -q`

Expected: PASS.

- [ ] **Step 7: Commit the focused calculation module**

```bash
git add src/backend/m12_clv.py tests/test_m12_clv.py
git commit -m "feat: reproduce final M12 CLV calculations"
```

### Task 2: Final artifact preparation and service-table contract

**Files:**
- Modify: `src/backend/prepare_service_database.py`
- Modify: `src/backend/service_builder.py`
- Modify: `tests/test_service_input_preparation.py`
- Modify: `tests/test_service_builder.py`

**Interfaces:**
- Replace `ServiceInputs(source, risk_scores, segment_panel, profitability, shap_local)` with `ServiceInputs(source, operating_scores, clv)`.
- Consume score columns `score_eligible`, `risk_probability`, `SEG__current_segment`, `SEG__transition`, D/A/C/K change fields, and `shap_top{1..3}_{feature,value}`.
- Produce database-shaped tables with explicit CLV fields and exactly 3,341 snapshots for the real artifacts.

- [ ] **Step 1: Replace old fixture assertions with final score and CLV assertions**

```python
assert set(snapshots.columns) >= {
    "risk_probability", "clv_no_risk", "clv_risk",
    "potential_loss", "defense_value", "defense_rank",
}
assert "customer_value_proxy" not in snapshots
assert "crm_priority_score" not in snapshots
```

- [ ] **Step 2: Add a failing eligibility lock test**

```python
def test_operating_scores_filter_to_target_eligible_population():
    inputs = final_inputs_with_one_ineligible_row()
    tables = build_service_tables(inputs)
    assert tables["customer_snapshots"]["corporate_id"].tolist() == ["ELIGIBLE"]
```

- [ ] **Step 3: Run service preparation and builder tests**

Run: `conda run -n final pytest tests/test_service_input_preparation.py tests/test_service_builder.py -q`

Expected: FAIL on the retired input and snapshot contract.

- [ ] **Step 4: Rewrite preparation defaults and generated inputs**

```python
DEFAULT_RISK_SCORES_PATH = Path(
    "src/models/web_m12_intervene_v2_scores_202512_all_3372.csv"
)
DEFAULT_FTP_PATH = Path("outputs/iM뱅크_월별_추정FTP_2023_2025.csv")
DEFAULT_BANK_RATES_PATH = Path("outputs/예대금리차2023~2025_순.csv")
```

The command reads the source and final score CSV, calls Task 1 functions, writes an audit CLV CSV under `outputs/rm_service_inputs`, and passes only final inputs to the loader.

- [ ] **Step 5: Reshape final service tables**

Build customers, risk scores, segments, CLV, weakening signals, SHAP factors, recommendations, snapshots, and monthly summaries from the final artifacts. Preserve existing recommendation and AI-report robustness edits. Generate SHAP rows from the three wide score columns and allow `feature_value` to be null because the final score artifact contains contribution values but not raw SHAP feature values.

- [ ] **Step 6: Run focused service tests**

Run: `conda run -n final pytest tests/test_service_input_preparation.py tests/test_service_builder.py -q`

Expected: PASS.

- [ ] **Step 7: Commit preparation and builder changes**

```bash
git add src/backend/prepare_service_database.py src/backend/service_builder.py tests/test_service_input_preparation.py tests/test_service_builder.py
git commit -m "feat: build service tables from final M12 artifacts"
```

### Task 3: SQLite schema and atomic loader

**Files:**
- Modify: `src/backend/database.py`
- Modify: `src/backend/load_service_database.py`
- Modify: `tests/test_service_database.py`

**Interfaces:**
- `clv_values` table columns: `corporate_id`, `as_of_month`, `clv_no_risk`, `clv_risk`, `potential_loss`, `defense_value`, `defense_rank`.
- `customer_snapshots` repeats the fields required for indexed API reads.
- `monthly_summaries.potential_loss_total` replaces `priority_value_total`.
- `ServiceSourcePaths` contains `source`, `operating_scores`, and `clv`.

- [ ] **Step 1: Write failing schema and load tests**

```python
assert table_columns(connection, "customer_snapshots") == [
    "corporate_id", "as_of_month", "risk_probability", "risk_level",
    "clv_no_risk", "clv_risk", "potential_loss", "defense_value",
    "defense_rank", "segment_name", "weakening_type", "industry",
    "region", "dedicated_yn",
]
```

- [ ] **Step 2: Run database tests and verify failure**

Run: `conda run -n final pytest tests/test_service_database.py -q`

Expected: FAIL because the schema still exposes value-proxy fields.

- [ ] **Step 3: Replace schema and loader allowlists**

Make `defense_rank` nullable, add indexes on `(as_of_month, defense_rank)` and filter fields, and retain atomic temporary-database replacement. Update source manifests to hash the three final input artifacts.

- [ ] **Step 4: Run database tests**

Run: `conda run -n final pytest tests/test_service_database.py -q`

Expected: PASS, including the test that a failed load leaves the existing DB unchanged.

- [ ] **Step 5: Commit database changes**

```bash
git add src/backend/database.py src/backend/load_service_database.py tests/test_service_database.py
git commit -m "feat: store final CLV defense contract"
```

### Task 4: FastAPI and repository contract

**Files:**
- Modify: `src/backend/schemas.py`
- Modify: `src/backend/repository.py`
- Modify: `src/backend/app.py`
- Modify: `tests/test_service_api.py`

**Interfaces:**
- `Customer` fields include `clvRisk: float`, `potentialLoss: float`, `defenseRank: int | None`.
- `Overview` includes `potentialLossTotal: float`.
- Allowed customer sorts: `defense_rank`, `risk`, `clv_risk`, `potential_loss`, `name`.
- Default priority sort: `defense_rank` ascending with nulls last and corporate-ID tie-break.

- [ ] **Step 1: Rewrite API fixtures and expected JSON**

```python
assert response.json()["items"][0] == {
    "id": "A",
    "clvRisk": 80.0,
    "potentialLoss": 20.0,
    "defenseRank": 1,
    # existing identity, risk, segment, weakening, and signal fields
}
assert "valueProxy" not in response.json()["items"][0]
```

- [ ] **Step 2: Run API tests and verify failure**

Run: `conda run -n final pytest tests/test_service_api.py -q`

Expected: FAIL on old response fields and sort names.

- [ ] **Step 3: Update Pydantic schemas and SQL mapping**

Use a null-last expression for ascending defense rank:

```sql
ORDER BY (s.defense_rank IS NULL) ASC,
         s.defense_rank ASC,
         s.corporate_id ASC
```

Retain parameterized filters and allowlisted sort columns. Preserve the repository change that accepts stored SHAP factors regardless of model-name label.

- [ ] **Step 4: Run API tests**

Run: `conda run -n final pytest tests/test_service_api.py -q`

Expected: PASS.

- [ ] **Step 5: Commit API changes**

```bash
git add src/backend/schemas.py src/backend/repository.py src/backend/app.py tests/test_service_api.py
git commit -m "feat: expose CLV risk and potential loss APIs"
```

### Task 5: React CLV and potential-loss UI

**Files:**
- Modify: `src/frontend/rm-insight-copilot/src/pages/PriorityPage.jsx`
- Modify: `src/frontend/rm-insight-copilot/src/pages/OverviewPage.jsx`
- Modify: `src/frontend/rm-insight-copilot/src/pages/DormancyRiskPage.test.jsx`
- Modify: `src/frontend/rm-insight-copilot/src/pages/OverviewPage.test.jsx`
- Create: `src/frontend/rm-insight-copilot/src/pages/PriorityPage.test.jsx`
- Modify: `tests/test_frontend_copy.py`

**Interfaces:**
- Priority page consumes `clvRisk`, `potentialLoss`, `defenseRank`.
- Overview consumes `potentialLossTotal`.
- Required note: `FISIM 기반 향후 6개월 경제적 기여가치 추정치이며 확정 회계손실이 아닙니다.`

- [ ] **Step 1: Add failing frontend tests**

```jsx
expect(await screen.findByText("CLV_Risk")).toBeInTheDocument();
expect(screen.getByText("PotentialLoss")).toBeInTheDocument();
expect(screen.getByText(/확정 회계손실이 아닙니다/)).toBeInTheDocument();
expect(screen.queryByText("고객가치 대리지표")).not.toBeInTheDocument();
```

- [ ] **Step 2: Run focused frontend tests**

Run: `cd src/frontend/rm-insight-copilot && npm test -- --run src/pages/PriorityPage.test.jsx src/pages/OverviewPage.test.jsx src/pages/DormancyRiskPage.test.jsx`

Expected: FAIL on the retired fields and labels.

- [ ] **Step 3: Update priority and overview rendering**

Display Korean-formatted numeric values, use `-` for null defense ranks, and keep existing filter and recommendation navigation behavior. Do not show `CLV_NoRisk`, generic profitability, customer-value proxy, or retired CRM-priority score.

- [ ] **Step 4: Run frontend and copy tests**

Run: `cd src/frontend/rm-insight-copilot && npm test`

Run: `conda run -n final pytest tests/test_frontend_copy.py -q`

Expected: PASS.

- [ ] **Step 5: Commit frontend changes**

```bash
git add src/frontend/rm-insight-copilot/src/pages/PriorityPage.jsx src/frontend/rm-insight-copilot/src/pages/OverviewPage.jsx src/frontend/rm-insight-copilot/src/pages/PriorityPage.test.jsx src/frontend/rm-insight-copilot/src/pages/OverviewPage.test.jsx src/frontend/rm-insight-copilot/src/pages/DormancyRiskPage.test.jsx tests/test_frontend_copy.py
git commit -m "feat: show CLV risk and potential loss priority"
```

### Task 6: Active documentation migration

**Files:**
- Modify: `README.md`
- Modify: `AGENTS.md`
- Modify: `financial_dormancy.md`
- Modify: `y_setting_pipeline.md`
- Modify: `src/models/model.md`
- Modify: `tests/test_persistent_target_documentation.py`

**Interfaces:**
- Active docs identify `Y_INTERVENE_M12_v2` as the deployed target.
- Active docs retain `Y_지속거래약화_3M70` only as historical retrospective evidence.
- Active docs define FISIM CLV and defense priority without customer-value-proxy language.

- [ ] **Step 1: Update documentation assertions first**

```python
for path in ACTIVE_DOCS:
    text = path.read_text(encoding="utf-8")
    assert "Y_INTERVENE_M12_v2" in text
    assert "CLV_Risk" in text
    assert "PotentialLoss" in text
    assert "위험 × 고객가치 대리지표" not in text
```

- [ ] **Step 2: Run documentation tests and verify failure**

Run: `conda run -n final pytest tests/test_persistent_target_documentation.py -q`

Expected: FAIL while the active docs still declare the old modeling gate.

- [ ] **Step 3: Rewrite active documentation consistently**

Record the target locks, model contract, 3,341 operating population, FISIM units, CLV formulas, displayed fields, and interpretation limits from the approved design. Do not delete historical evidence tables; label them as retired or historical.

- [ ] **Step 4: Run documentation tests**

Run: `conda run -n final pytest tests/test_persistent_target_documentation.py -q`

Expected: PASS.

- [ ] **Step 5: Commit documentation changes**

```bash
git add README.md AGENTS.md financial_dormancy.md y_setting_pipeline.md src/models/model.md tests/test_persistent_target_documentation.py
git commit -m "docs: adopt final intervention target and CLV priority"
```

### Task 7: Real-artifact rebuild and full verification

**Files:**
- Generated: `outputs/rm_service_inputs/clv_202512.csv`
- Generated: `outputs/rm_service/rm_service.sqlite`
- Modify only if verification exposes a contract bug: files from Tasks 1-6

**Interfaces:**
- CLI: `conda run -n final python -m src.backend.prepare_service_database`
- Required DB snapshot count: 3,341
- Required cutoff: `2025-12`

- [ ] **Step 1: Run all Python tests**

Run: `conda run -n final pytest -q`

Expected: PASS.

- [ ] **Step 2: Run all frontend tests and production build**

Run: `cd src/frontend/rm-insight-copilot && npm test`

Run: `cd src/frontend/rm-insight-copilot && npm run build`

Expected: PASS and a successful Vite build.

- [ ] **Step 3: Rebuild the service database from real artifacts**

Run: `conda run -n final python -m src.backend.prepare_service_database`

Expected: JSON summary reports cutoff `2025-12` and 3,341 customer snapshots.

- [ ] **Step 4: Audit generated values**

Run: `sqlite3 outputs/rm_service/rm_service.sqlite "SELECT as_of_month, COUNT(*), SUM(defense_value > 0), MIN(defense_rank), MAX(defense_rank), SUM(defense_value) FROM customer_snapshots GROUP BY as_of_month;"`

Expected: one `2025-12` row, 3,341 snapshots, consecutive positive defense ranks, and finite aggregate potential loss.

- [ ] **Step 5: Search for active legacy copy**

Run: `rg -n "customer_value_proxy|valueProxy|crm_priority_score|priorityScore|고객가치 대리지표|CRM 우선순위 점수" README.md AGENTS.md financial_dormancy.md y_setting_pipeline.md src/backend src/frontend/rm-insight-copilot/src tests`

Expected: no active contract references; test names may mention legacy strings only when asserting absence.

- [ ] **Step 6: Review the final diff and user-change preservation**

Run: `git diff --check && git status --short && git diff --stat`

Expected: no whitespace errors, no accidental removal of the pre-existing AI-report/SHAP robustness work, and only intended generated artifacts left untracked or ignored.
