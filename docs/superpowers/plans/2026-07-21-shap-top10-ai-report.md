# AI Report SHAP Top 10 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Export, store, return, and display all ten highest-absolute-impact local SHAP factors for each of the 3,341 eligible customers, with a small `주요 SHAP Value (상위 10개)` title above the list.

**Architecture:** Expand the final operating-score notebook from three to ten local SHAP columns, then make the service builder validate and normalize those columns into ten database rows per customer. Keep the existing report API shape and rendering component; remove no data client-side and add only the requested section heading.

**Tech Stack:** Jupyter/nbformat, Python 3.10, pandas, NumPy, LightGBM, SQLite, FastAPI/Pydantic, pytest, React 19, Vitest/Testing Library

## Global Constraints

- Rank local model contributions by descending absolute SHAP value and export ranks 1 through 10.
- Preserve the final LightGBM model, Isotonic calibration, 56-feature set, risk probabilities, and `score_eligible` values.
- Expose only the same 3,341 eligible customers.
- Persist exactly 10 SHAP rows per eligible customer and 33,410 rows in the real database.
- Display all ten factors at once without slicing, pagination, collapsing, or a “more” control.
- Place `주요 SHAP Value (상위 10개)` immediately above the SHAP list.
- Do not calculate SHAP in an API or browser request.
- Preserve unrelated user changes in `src/models/persistent_weakening_interpretation.py` and `tests/test_persistent_weakening_interpretation.py`.

---

### Task 1: Final notebook Top 10 score contract

**Files:**
- Modify: `src/models/web_202512_m12_final_model.ipynb`
- Modify: `src/수익성F(y선정포함).ipynb`
- Create: `tests/test_web_m12_notebook_contract.py`

**Interfaces:**
- Produces: score columns `shap_top{rank}_feature` and `shap_top{rank}_value` for every `rank` in `1..10`.
- Preserves: `risk_probability`, `score_eligible`, and the existing operating score row order and count.

- [ ] **Step 1: Write the failing notebook-source contract test**

```python
import json
from pathlib import Path


NOTEBOOK = Path("src/models/web_202512_m12_final_model.ipynb")


def notebook_code() -> str:
    payload = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    return "\n".join(
        "".join(cell.get("source", []))
        for cell in payload["cells"]
        if cell.get("cell_type") == "code"
    )


def test_final_web_notebook_exports_local_shap_top10():
    source = notebook_code()
    assert "add_local_shap_top10" in source
    assert "[:, :10]" in source
    assert "range(10)" in source
    assert "add_local_shap_top3" not in source
```

- [ ] **Step 2: Run the contract test and verify RED**

Run: `conda run -n final python -m pytest tests/test_web_m12_notebook_contract.py -q`

Expected: FAIL because the notebook still defines `add_local_shap_top3`, selects `:3`, and loops over `range(3)`.

- [ ] **Step 3: Update the notebook code cell with minimal JSON churn**

Use an `apply_patch` edit limited to the source strings that define and invoke the helper:

```python
def add_local_shap_top10(frame: pd.DataFrame, result: pd.DataFrame, bundle: dict) -> pd.DataFrame:
    model_pipeline = bundle['pipeline']
    feature_names = bundle['features']
    transformed = model_pipeline.named_steps['preprocessor'].transform(frame[feature_names])
    contributions = model_pipeline.named_steps['model'].predict(
        transformed, pred_contrib=True
    )
    contributions = np.asarray(contributions)[:, :len(feature_names)]
    top_index = np.argsort(-np.abs(contributions), axis=1)[:, :10]
    for rank in range(10):
        index = top_index[:, rank]
        result[f'shap_top{rank + 1}_feature'] = [feature_names[i] for i in index]
        result[f'shap_top{rank + 1}_value'] = contributions[np.arange(len(frame)), index]
    return result
```

Call `add_local_shap_top10(frame, result, bundle)` from `score_all_firms_202512`.

Make both notebooks repository-runnable instead of using the original machine path. In `수익성F(y선정포함).ipynb`, set the source to `Path.cwd() / "outputs/iM뱅크데이터_거시경제지표포함.csv"`, `BASE_DIR = Path.cwd() / "outputs"`, `OUTPUT_DIR = BASE_DIR / "수익성F_outputs"`, and `MODEL_DIR = BASE_DIR / "수익성F_models"`. In the web notebook, set the same output/model directories and set `WEB_SCORE_PATH = Path.cwd() / "src/models/web_m12_intervene_v2_scores_202512_all_3372.csv"`.

- [ ] **Step 4: Validate notebook structure and contract GREEN**

Run:

```bash
conda run -n final python -c "import nbformat; nbformat.read('src/models/web_202512_m12_final_model.ipynb', as_version=4); print('valid notebook')"
conda run -n final python -m pytest tests/test_web_m12_notebook_contract.py -q
```

Expected: notebook parses successfully and the test passes.

- [ ] **Step 5: Commit the notebook contract**

```bash
git add src/models/web_202512_m12_final_model.ipynb 'src/수익성F(y선정포함).ipynb' \
  tests/test_web_m12_notebook_contract.py
git commit -m "feat: export operating SHAP top 10"
```

### Task 2: Service builder Top 10 validation and expansion

**Files:**
- Modify: `src/backend/service_builder.py`
- Modify: `tests/test_service_builder.py`
- Modify: `tests/test_service_database.py`

**Interfaces:**
- Consumes: all `shap_top1_*` through `shap_top10_*` score columns.
- Produces: ten `shap_factors` rows per eligible customer with ranks `1..10`.

- [ ] **Step 1: Add a shared Top 10 fixture shape and failing assertions**

In both service fixture builders, retain their current non-SHAP fixture dictionaries and then generate the twenty SHAP columns instead of hand-writing three pairs:

```python
for rank in range(1, 11):
    score[f"shap_top{rank}_feature"] = [f"feature_{rank}"] * row_count
    score[f"shap_top{rank}_value"] = [0.11 - rank / 100] * row_count
return pd.DataFrame(score)
```

Update the builder assertion:

```python
shap = tables["shap_factors"]
assert len(shap) == 20
assert shap.groupby("corporate_id")["abs_shap_rank"].apply(list).tolist() == [
    list(range(1, 11)),
    list(range(1, 11)),
]
```

Add a missing-column rejection test:

```python
def test_build_service_tables_requires_all_shap_top10_columns():
    inputs = _inputs()
    inputs.operating_scores = inputs.operating_scores.drop(columns="shap_top10_value")
    with pytest.raises(ValueError, match="shap_top10_value"):
        build_service_tables(inputs)
```

- [ ] **Step 2: Run focused tests and verify RED**

Run: `conda run -n final python -m pytest tests/test_service_builder.py tests/test_service_database.py -q`

Expected: FAIL because the builder only requires and expands ranks 1 through 3.

- [ ] **Step 3: Implement a single Top 10 constant and validation**

In `service_builder.py`:

```python
SHAP_FACTOR_COUNT = 10
SHAP_SCORE_COLUMNS = tuple(
    column
    for rank in range(1, SHAP_FACTOR_COUNT + 1)
    for column in (f"shap_top{rank}_feature", f"shap_top{rank}_value")
)

OPERATING_SCORE_COLUMNS = (
    "법인ID",
    "cutoff_month",
    "score_eligible",
    "SEG__baseline_segment_2023",
    "SEG__current_segment",
    "SEG__transition",
    "CTX__업종_대분류__현재",
    "CTX__업종_중분류__현재",
    "risk_probability",
    *SCORE_CHANGE_COLUMNS.values(),
    *SHAP_SCORE_COLUMNS,
)
```

Validate every SHAP value using `pd.to_numeric(..., errors="coerce")` and `np.isfinite`; reject blank feature names. Change `_build_shap_table` to `for rank in range(1, SHAP_FACTOR_COUNT + 1)` and assert each customer produces ranks `1..10`.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run: `conda run -n final python -m pytest tests/test_service_builder.py tests/test_service_database.py -q`

Expected: PASS.

- [ ] **Step 5: Commit the service contract**

```bash
git add src/backend/service_builder.py tests/test_service_builder.py tests/test_service_database.py
git commit -m "feat: persist ten local SHAP factors"
```

### Task 3: Report API ordering and ten-factor response

**Files:**
- Modify: `tests/test_service_api.py`
- Verify: `src/backend/repository.py`
- Verify: `src/backend/schemas.py`

**Interfaces:**
- Consumes: ten stored SHAP rows for a selected customer.
- Produces: `shapFactors` list ordered by `rank` from 1 through 10.

- [ ] **Step 1: Expand the API database fixture and add a failing response assertion**

Insert ten factors for the report customer and assert:

```python
payload = client.get("/api/reports/A").json()
assert len(payload["shapFactors"]) == 10
assert [factor["rank"] for factor in payload["shapFactors"]] == list(range(1, 11))
```

- [ ] **Step 2: Run the API report test**

Run: `conda run -n final python -m pytest tests/test_service_api.py -q`

Expected: PASS if the existing repository query already returns every stored row ordered by `abs_shap_rank`; otherwise FAIL at the ten-rank assertion.

- [ ] **Step 3: Apply only the minimal repository change if RED**

The query must remain unbounded and ordered:

```sql
SELECT feature_name, feature_value, shap_value, abs_shap_rank
FROM shap_factors
WHERE corporate_id = ? AND as_of_month = ?
ORDER BY abs_shap_rank ASC, model_name ASC
```

Do not add `LIMIT` or list slicing.

- [ ] **Step 4: Run API tests and commit**

Run: `conda run -n final python -m pytest tests/test_service_api.py -q`

Expected: PASS.

```bash
git add tests/test_service_api.py src/backend/repository.py
git commit -m "test: lock report SHAP top 10 response"
```

If `repository.py` requires no change, stage only the test.

### Task 4: AI report heading and ten visible factors

**Files:**
- Modify: `src/frontend/rm-insight-copilot/src/pages/AiReportPage.jsx`
- Modify: `src/frontend/rm-insight-copilot/src/pages/AiReportPage.test.jsx`
- Modify: `src/frontend/rm-insight-copilot/src/styles.css`

**Interfaces:**
- Consumes: all `report.shapFactors` returned by the API.
- Produces: small heading plus ten always-visible existing SHAP rows.

- [ ] **Step 1: Write the failing UI test**

Create ten factors in the report mock:

```javascript
const shapFactors = Array.from({ length: 10 }, (_, index) => ({
  feature: `feature_${index + 1}`,
  value: null,
  impact: (10 - index) / 100,
  rank: index + 1
}));
```

Assert:

```javascript
expect(await screen.findByText("주요 SHAP Value (상위 10개)")).toBeInTheDocument();
expect(screen.getAllByTestId("shap-factor")).toHaveLength(10);
expect(screen.queryByRole("button", { name: /더 보기/ })).not.toBeInTheDocument();
```

- [ ] **Step 2: Run the focused Vitest and verify RED**

Run: `npm test -- --run src/pages/AiReportPage.test.jsx`

Working directory: `src/frontend/rm-insight-copilot`

Expected: FAIL because the heading and factor test IDs are absent.

- [ ] **Step 3: Add the heading without truncating the list**

Render the heading immediately before the list:

```jsx
{!reportState.loading && !reportState.error && shapFactors.length > 0 && (
  <section className="shap-section" aria-labelledby="shap-section-title">
    <small id="shap-section-title" className="shap-section-title">
      주요 SHAP Value (상위 10개)
    </small>
    <div className="beeswarm">
      {shapFactors.map((factor) => (
        <div className="bee-row" data-testid="shap-factor" key={`${factor.rank}-${factor.feature}`}>
          <span>{factor.feature}</span>
          <div>
            <i style={{ left: `${Math.min(Math.max(50 + factor.impact * 100, 8), 92)}%` }} />
          </div>
          <strong>{impactFormatter.format(factor.impact)}</strong>
        </div>
      ))}
    </div>
  </section>
)}
```

Add compact typography only:

```css
.shap-section-title {
  display: block;
  margin-bottom: 0.75rem;
  color: var(--muted);
  font-size: var(--text-sm);
  font-weight: var(--weight-bold);
}
```

- [ ] **Step 4: Run focused and full frontend tests**

Run:

```bash
npm test -- --run src/pages/AiReportPage.test.jsx
npm test -- --run
```

Working directory: `src/frontend/rm-insight-copilot`

Expected: PASS with ten visible factors.

- [ ] **Step 5: Commit the UI**

```bash
git add src/frontend/rm-insight-copilot/src/pages/AiReportPage.jsx \
  src/frontend/rm-insight-copilot/src/pages/AiReportPage.test.jsx \
  src/frontend/rm-insight-copilot/src/styles.css
git commit -m "feat: show ten SHAP factors in AI reports"
```

### Task 5: Regenerate artifacts and verify the real service

**Files:**
- Regenerate: `src/models/web_m12_intervene_v2_scores_202512_all_3372.csv`
- Regenerate (ignored artifact): `outputs/rm_service_inputs/clv_202512.csv`
- Regenerate (ignored artifact): `outputs/rm_service/rm_service.sqlite`

**Interfaces:**
- Consumes: the locked operating model, calibrator, 56-feature registry, and 2025-12 operating features.
- Produces: 3,372 score rows containing Top 10 columns and a 3,341-customer database containing 33,410 SHAP rows.

- [ ] **Step 1: Locate the locked regeneration inputs**

Required files:

```text
model_m12_intervene_v2_feature_sets.csv
model_m12_intervene_v2_operating_features_202512.csv
model_m12_intervene_v2_operating_pipeline_202512.joblib
model_m12_intervene_v2_operating_calibrator_202512.joblib
```

The files are currently absent. Generate them from the repository-local source by executing `src/수익성F(y선정포함).ipynb` after Task 1 path normalization. If execution fails, report the exact cell, exception, and missing dependency or input as the artifact blocker. Do not derive ranks 4 through 10 from the existing Top 3 CSV.

- [ ] **Step 2: Execute the profitability and final score notebooks top-to-bottom**

Run from the directory matching its repository-relative input configuration:

```bash
conda run -n final python -m jupyter nbconvert \
  --execute --to notebook --inplace \
  'src/수익성F(y선정포함).ipynb'
conda run -n final python -m jupyter nbconvert \
  --execute --to notebook --inplace \
  src/models/web_202512_m12_final_model.ipynb
```

Expected: exit 0, 3,372 score rows, unchanged risk probabilities, and twenty Top 10 SHAP columns.

- [ ] **Step 3: Rebuild the service database**

Run: `conda run -n final python -m src.backend.prepare_service_database`

Expected: completed load with 3,341 customers and 33,410 `shap_factors` rows.

- [ ] **Step 4: Audit the real artifacts**

Run:

```bash
conda run -n final python -c "import pandas as pd, sqlite3; s=pd.read_csv('src/models/web_m12_intervene_v2_scores_202512_all_3372.csv'); assert len(s)==3372; assert all(f'shap_top{i}_feature' in s for i in range(1,11)); c=sqlite3.connect('outputs/rm_service/rm_service.sqlite'); assert c.execute('select count(*) from customers').fetchone()[0]==3341; assert c.execute('select count(*) from shap_factors').fetchone()[0]==33410; assert c.execute('select min(n),max(n) from (select corporate_id,count(*) n from shap_factors group by corporate_id)').fetchone()==(10,10); print('top10 audit passed')"
```

Expected: `top10 audit passed`.

- [ ] **Step 5: Run full verification**

Run:

```bash
conda run -n final python -m pytest -q
cd src/frontend/rm-insight-copilot
npm test -- --run
npm run build
```

Expected: every command exits 0.

- [ ] **Step 6: Commit regenerated tracked artifacts if available**

```bash
git add src/models/web_m12_intervene_v2_scores_202512_all_3372.csv
git commit -m "data: regenerate operating SHAP top 10 scores"
```

Do not stage unrelated pre-existing edits or ignored generated database files.
