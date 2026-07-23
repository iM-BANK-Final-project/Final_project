# RM Web Data Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve the existing RM Insight React prototype while replacing mock values with SQLite-backed risk, segment, profitability, recommendation, SHAP, and overview results served by FastAPI.

**Architecture:** A standalone CLI validates existing CSV artifacts, selects the latest common scoring month, builds customer-value and CRM-priority fields, and atomically replaces a local SQLite database. FastAPI performs read-only repository queries; React keeps its current page/component layout and replaces direct `mockData.js` imports with API hooks.

**Tech Stack:** Python 3.10, pandas, stdlib `sqlite3`, FastAPI, Pydantic, pytest, httpx, React 19, Vite 6, Vitest, Testing Library.

## Global Constraints

- Work only in `/private/tmp/Final_project-rm-web-integration` on `codex/rm-web-integration`.
- Preserve the current `App.jsx` page-state navigation, page order, cards, tables, charts, splash screen, CSS design, and `전략 보고서 생성` button.
- Do not implement a click handler or generation API for `전략 보고서 생성`.
- Do not execute model training, segmentation, profitability calculation, or LLM calls in an HTTP request.
- Use `법인ID+기준년월` as the service join key and reject duplicates, invalid months, future-only columns, missing required values, and probabilities outside `[0, 1]`.
- Use the latest month common to risk, segment, source, and profitability inputs unless `--as-of-month` explicitly selects another common month.
- Use only model `LightGBM` from `validation_scores.csv` as the service risk score; never mix model rows.
- Compute customer value as the equal-weight mean of four cohort percentile ranks plus `일반=0.0/우수=0.5/최우수=1.0` and `N=0.0/Y=1.0`.
- Keep `V_FTP_12M` profitability separate from customer value.
- Compute `crm_priority_score = risk_probability * customer_value_proxy`; never label it expected loss or attach a currency unit.
- Use `지속거래약화`, not actual churn, confirmed dormancy, or loss language.
- Never fall back to mock data after an API or database error.
- Bind the local API to `127.0.0.1`, allow only the Vite local origin, and do not commit CSV, SQLite, DB, or secret files.

---

## File Map

### Backend

- `src/backend/database.py`: SQLite connection, schema, transaction, and atomic replacement helpers.
- `src/backend/service_builder.py`: artifact validation, month normalization, value/priority, weakening signals, recommendations, and table DataFrames.
- `src/backend/load_service_database.py`: CLI argument parsing and atomic database load orchestration.
- `src/backend/repository.py`: parameterized read queries and response-shaped dictionaries.
- `src/backend/schemas.py`: FastAPI response models matching the existing frontend field shapes.
- `src/backend/app.py`: FastAPI application, CORS, dependency injection, endpoints, and 404/503 mapping.
- `tests/test_service_database.py`: schema and atomic database tests.
- `tests/test_service_builder.py`: artifact contract, customer value, signals, and recommendation tests.
- `tests/test_service_api.py`: health, overview, filters, customer, priority, recommendation, and report endpoint tests.

### Frontend

- `src/frontend/rm-insight-copilot/src/api/client.js`: relative API client and query serialization.
- `src/frontend/rm-insight-copilot/src/hooks/useApi.js`: request lifecycle and cancellation.
- `src/frontend/rm-insight-copilot/src/components/PageState.jsx`: in-panel loading, empty, and error UI.
- `src/frontend/rm-insight-copilot/src/App.jsx`: shared selected-customer state only; preserve page-state navigation.
- `src/frontend/rm-insight-copilot/src/pages/*.jsx`: replace mock imports and hardcoded controls with API data without layout redesign.
- `src/frontend/rm-insight-copilot/src/components/RiskMeter.jsx`: final target wording.
- `src/frontend/rm-insight-copilot/src/components/MiniTrendChart.jsx`: empty/zero-safe rendering.
- `src/frontend/rm-insight-copilot/src/styles.css`: minimal state styles only.
- `src/frontend/rm-insight-copilot/src/data/mockData.js`: delete after no active imports remain.
- `src/frontend/rm-insight-copilot/src/**/*.test.jsx`: interaction and state tests.

### Runtime documentation

- `environment.yml`: add test-only Python packages needed by the existing test command.
- `src/frontend/rm-insight-copilot/package.json`: add Vitest and Testing Library scripts/dependencies.
- `.env.example`: document `RM_SERVICE_DB_PATH` and `VITE_API_BASE_URL` without secrets.
- `README.md`: exact DB load, API start, frontend start, and verification commands.

---

### Task 1: SQLite schema and atomic replacement

**Files:**
- Create: `src/backend/__init__.py`
- Create: `src/backend/database.py`
- Create: `tests/test_service_database.py`
- Modify: `environment.yml`

**Interfaces:**
- Produces: `connect_database(path: Path) -> sqlite3.Connection`
- Produces: `initialize_schema(connection: sqlite3.Connection) -> None`
- Produces: `replace_database_atomically(target: Path, populate: Callable[[sqlite3.Connection], None]) -> None`

- [ ] **Step 1: Add backend test dependencies and the failing schema test**

Add `pytest` and `httpx` under `environment.yml` pip dependencies. Create a test that opens a temporary DB, calls `initialize_schema`, and asserts the exact table set:

```python
EXPECTED_TABLES = {
    "customers", "risk_scores", "segments", "profitability",
    "weakening_signals", "shap_factors", "recommendations",
    "customer_snapshots", "monthly_summaries", "import_runs",
}

def test_initialize_schema_creates_service_tables(tmp_path):
    connection = connect_database(tmp_path / "service.sqlite")
    initialize_schema(connection)
    names = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
        if not row[0].startswith("sqlite_")
    }
    assert names == EXPECTED_TABLES
```

- [ ] **Step 2: Update the local environment and verify the test fails**

Run:

```bash
conda env update -n final -f environment.yml
conda run -n final python -m pytest tests/test_service_database.py -v
```

Expected: import failure for `src.backend.database`.

- [ ] **Step 3: Implement connection and schema creation**

Use stdlib `sqlite3`, `PRAGMA foreign_keys = ON`, `sqlite3.Row`, and one `SCHEMA_SQL` script. Define all columns and primary keys from the approved design. Store JSON fields as `TEXT`, booleans as checked `INTEGER`, and probabilities/value scores with `CHECK(value BETWEEN 0 AND 1)`. Create indexes for `(as_of_month, risk_level)`, `(as_of_month, segment_name)`, `(as_of_month, crm_priority_rank)`, and filter columns.

Implement atomic replacement as:

```python
def replace_database_atomically(target: Path, populate):
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.unlink(missing_ok=True)
    connection = connect_database(temporary)
    try:
        initialize_schema(connection)
        populate(connection)
        connection.commit()
        connection.close()
        temporary.replace(target)
    except Exception:
        connection.rollback()
        connection.close()
        temporary.unlink(missing_ok=True)
        raise
```

- [ ] **Step 4: Add and pass the atomic-preservation test**

Write a test that seeds `target` with `b"known-good"`, raises `ValueError("load failed")` inside `populate`, and asserts the original bytes remain and `.tmp` is absent.

Run:

```bash
conda run -n final python -m pytest tests/test_service_database.py -v
```

Expected: all database tests pass.

- [ ] **Step 5: Commit Task 1**

```bash
git add environment.yml src/backend/__init__.py src/backend/database.py tests/test_service_database.py
git commit -m "feat: add RM service SQLite schema"
```

---

### Task 2: Artifact contract and customer-value builder

**Files:**
- Create: `src/backend/service_builder.py`
- Create: `tests/test_service_builder.py`

**Interfaces:**
- Produces: `ServiceInputs(source, risk_scores, segment_panel, profitability, shap_local)` dataclass.
- Produces: `normalize_month(series: pd.Series) -> pd.Series`
- Produces: `select_common_month(inputs: ServiceInputs, requested: str | None) -> str`
- Produces: `build_customer_value(source_month: pd.DataFrame) -> pd.DataFrame`
- Produces: `build_service_tables(inputs: ServiceInputs, as_of_month: str | None = None) -> dict[str, pd.DataFrame]`

- [ ] **Step 1: Write failing month, duplicate, and value tests**

Create minimal DataFrames for three customers. Assert:

```python
def test_customer_value_uses_equal_weight_contract():
    source = pd.DataFrame({
        "법인ID": ["A", "B", "C"],
        "수신잔액합계": [0.0, 10.0, 20.0],
        "여신잔액합계": [0.0, 10.0, 20.0],
        "핵심거래활동금액": [0.0, 10.0, 20.0],
        "상품관계폭": [0.0, 10.0, 20.0],
        "법인_고객등급": ["일반", "우수", "최우수"],
        "전담고객여부": ["N", "N", "Y"],
    })
    result = build_customer_value(source).set_index("법인ID")
    assert result.loc["C", "customer_value_proxy"] == pytest.approx(1.0)
    assert result.loc["A", "customer_value_proxy"] == pytest.approx((4 / 3) / 6)
```

Also assert duplicate `법인ID+기준년월`, invalid month, unknown grade, unknown dedicated flag, missing component, negative source amount, and risk probability `1.01` each raise a Korean `ValueError` naming the violated contract.

- [ ] **Step 2: Run tests and confirm missing implementation**

Run:

```bash
conda run -n final python -m pytest tests/test_service_builder.py -v
```

Expected: import failure for `src.backend.service_builder`.

- [ ] **Step 3: Implement input normalization and latest-common-month selection**

Support these exact source contracts:

```text
source CSV: 법인ID, 기준년월, 업종_대분류, 사업장_시도, 법인_고객등급,
            전담고객여부, 상품관계폭, SegmentationConfig.amount_cols
risk CSV: 법인ID, 기준년월, 모델, 예측확률
segment CSV: 법인ID, 기준년월, 관계세그먼트, 거래활동점수, 수신관계점수, 여신관계점수
profitability CSV: 법인ID, 기준월, V_FTP_12M, V_FTP_12M_방어가치
SHAP CSV: 모델, 법인ID, 기준년월, feature, feature_value, shap_value, abs_shap_rank
```

Normalize `YYYYMM`, `YYYY-MM`, timestamps, and pandas periods to `YYYY-MM`. Filter risk and SHAP rows to `모델 == "LightGBM"`. Compute the month intersection from source, filtered risk, segment, and profitability. If `requested` is not in the intersection, raise `ValueError` with the sorted available intersection.

- [ ] **Step 4: Implement source aggregates and value scoring**

Use `SegmentationConfig` to calculate:

```python
source_month["수신잔액합계"] = source_month[list(config.deposit_cols)].sum(axis=1)
source_month["여신잔액합계"] = source_month[list(config.loan_cols)].sum(axis=1)
source_month["핵심거래활동금액"] = source_month[list(config.activity_cols)].sum(axis=1)
```

Use `rank(method="average", pct=True)` for the four numeric components, fixed grade/dedicated maps for the other two, and a row mean across exactly six non-null values. Preserve each component in `value_components_json`. Join risk, segment, source, and profitability with `validate="one_to_one"`; the risk population is the left/base population because it is the scoring risk set.

- [ ] **Step 5: Run and pass contract/value tests**

Run:

```bash
conda run -n final python -m pytest tests/test_service_builder.py -v
```

Expected: month, validation, and value tests pass.

- [ ] **Step 6: Commit Task 2**

```bash
git add src/backend/service_builder.py tests/test_service_builder.py
git commit -m "feat: build validated RM customer snapshots"
```

---

### Task 3: Weakening signals, recommendations, profitability, and report rows

**Files:**
- Modify: `src/backend/service_builder.py`
- Modify: `tests/test_service_builder.py`

**Interfaces:**
- Produces: `build_weakening_signals(history: pd.DataFrame, customer_ids: set[str], as_of_month: str) -> pd.DataFrame`
- Produces: `classify_weakening_type(signals: pd.DataFrame) -> pd.DataFrame`
- Produces: `build_recommendations(snapshots: pd.DataFrame, signals: pd.DataFrame) -> pd.DataFrame`

- [ ] **Step 1: Write failing signal and recommendation tests**

Create nine months of source history for customers whose latest three-month averages are 40% lower than the preceding six-month averages. Assert `recent`, `previous`, and `change_rate=-40.0` for `입출금`, `채널`, and `카드` independently. Assert two axes at or below `-20%` produce `복합 거래활동`; otherwise the most negative axis determines the type.

Assert the approved recommendation table exactly:

```python
EXPECTED_ACTIONS = {
    "입출금": "자금관리 상담, CMS, 결제성 거래 점검",
    "채널": "디지털채널 온보딩, 이용 장애·불편 확인",
    "카드": "법인카드 이용조건 점검, 한도·혜택 상담",
    "복합 거래활동": "RM 직접 접촉, 관계 회복 상담",
}
```

- [ ] **Step 2: Run focused tests and verify failures**

Run:

```bash
conda run -n final python -m pytest tests/test_service_builder.py -k "signal or recommendation" -v
```

Expected: missing function failures.

- [ ] **Step 3: Implement historical signal calculation**

For each customer and axis, use months `t-8..t-3` as previous six and `t-2..t` as recent three. Require all nine months and non-null, non-negative input amounts. Define `change_rate` as `(recent / previous - 1) * 100`; when `previous == 0`, store `change_rate` as null rather than inventing a percentage. Round display values to two decimals and rank non-null changes ascending per customer.

- [ ] **Step 4: Implement weakening type and deterministic recommendation copy**

Use the `-20%` multiple-axis threshold described in Step 1. Set priority level from probability (`HIGH >= .75`, `MEDIUM >= .60`, otherwise `WATCH`). Build `reason`, `contact_strategy`, `recommended_action`, and `strategy_summary` from risk, segment, signal, and the approved action table. Do not call an LLM or describe the text as LLM-generated.

- [ ] **Step 5: Add profitability and SHAP behavior tests**

Assert `V_FTP_12M` maps only to `profitability_value`, `V_FTP_12M_방어가치` maps only to `defense_value`, neither changes `customer_value_proxy`, and absent SHAP produces an empty list rather than fake factors.

- [ ] **Step 6: Run builder tests and commit**

Run:

```bash
conda run -n final python -m pytest tests/test_service_builder.py -v
```

Expected: all builder tests pass.

```bash
git add src/backend/service_builder.py tests/test_service_builder.py
git commit -m "feat: derive RM signals and recommendations"
```

---

### Task 4: Atomic database loader CLI

**Files:**
- Create: `src/backend/load_service_database.py`
- Modify: `tests/test_service_database.py`
- Modify: `.env.example`

**Interfaces:**
- Consumes: `build_service_tables(...)` and `replace_database_atomically(...)`.
- Produces: `load_service_database(paths: ServiceSourcePaths, database_path: Path, as_of_month: str | None) -> LoadSummary`
- Produces CLI module `python -m src.backend.load_service_database`.

- [ ] **Step 1: Write a failing end-to-end load test**

Write fixture CSVs to `tmp_path`, call `load_service_database`, and assert:

```python
assert summary.status == "COMPLETED"
assert summary.as_of_month == "2025-06"
with connect_database(db_path) as connection:
    snapshot = connection.execute(
        "SELECT risk_probability, customer_value_proxy, crm_priority_score "
        "FROM customer_snapshots WHERE corporate_id='A'"
    ).fetchone()
assert snapshot["crm_priority_score"] == pytest.approx(
    snapshot["risk_probability"] * snapshot["customer_value_proxy"]
)
```

- [ ] **Step 2: Run the test and verify loader import failure**

Run:

```bash
conda run -n final python -m pytest tests/test_service_database.py -k load -v
```

Expected: import failure for `load_service_database`.

- [ ] **Step 3: Implement table insertion and CLI arguments**

Define exact arguments:

```text
--source
--risk-scores
--segment-panel
--profitability
--shap-local
--database (default outputs/rm_service/rm_service.sqlite)
--as-of-month (optional YYYY-MM)
```

Use `DataFrame.to_sql(..., if_exists="append", index=False)` only inside the temporary DB transaction. Insert `import_runs` as `RUNNING`, then update to `COMPLETED` with source paths, SHA-256 hashes, row counts, and selected month. On failure, print the exception to stderr, return non-zero, and preserve the previous target DB through `replace_database_atomically`.

- [ ] **Step 4: Document local environment variables**

Add:

```dotenv
RM_SERVICE_DB_PATH=outputs/rm_service/rm_service.sqlite
VITE_API_BASE_URL=http://127.0.0.1:8000
```

Keep both non-secret and ensure actual `.env` remains ignored.

- [ ] **Step 5: Pass loader tests and commit**

Run:

```bash
conda run -n final python -m pytest tests/test_service_database.py tests/test_service_builder.py -v
```

Expected: all tests pass.

```bash
git add src/backend/load_service_database.py tests/test_service_database.py .env.example
git commit -m "feat: load RM artifacts into SQLite"
```

---

### Task 5: Repository and FastAPI read endpoints

**Files:**
- Create: `src/backend/schemas.py`
- Create: `src/backend/repository.py`
- Create: `src/backend/app.py`
- Create: `tests/test_service_api.py`

**Interfaces:**
- Produces: `ServiceRepository(connection_factory)` methods `overview`, `filter_options`, `customers`, `customer_detail`, `priorities`, `recommendations`, and `report`.
- Produces: FastAPI application `src.backend.app:app`.
- Produces: camelCase JSON matching existing frontend fields (`id`, `name`, `risk`, `health`, `valueProxy`, `priorityScore`, `weakeningType`, `signals`).

- [ ] **Step 1: Write failing API contract tests**

Use `fastapi.testclient.TestClient` with a seeded temporary SQLite DB. Assert:

```python
def test_customers_filters_and_uses_frontend_shape(client):
    response = client.get("/api/customers", params={"segment": "여신중심"})
    assert response.status_code == 200
    item = response.json()["items"][0]
    assert set(("id", "name", "risk", "health", "segment", "signals")) <= set(item)
    assert item["segment"] == "여신중심"

def test_missing_customer_is_404(client):
    response = client.get("/api/customers/UNKNOWN")
    assert response.status_code == 404
```

Cover health with and without DB, overview, filter options, search, every filter, priority rank order, recommendation filters, report with SHAP, report without SHAP, maximum page size, and rejected sort fields.

- [ ] **Step 2: Run API tests and verify import failures**

Run:

```bash
conda run -n final python -m pytest tests/test_service_api.py -v
```

Expected: imports for repository/app fail.

- [ ] **Step 3: Implement response models and repository queries**

Use Pydantic models with the frontend field names as the public contract. Use SQL placeholders for every value; build filter clauses only from fixed column maps. Default `page=1`, `page_size=50`, maximum `page_size=200`. Default priority sort is `crm_priority_rank ASC`. Return source `corporate_id` as the name when `corporate_name` is null.

- [ ] **Step 4: Implement FastAPI endpoints and local-only CORS**

Create endpoints from the design. Map missing database to HTTP 503, unknown customer to 404, invalid filter/sort to 422, and unexpected query errors to a logged 500 without exposing SQL. Configure CORS only for `http://127.0.0.1:5173` and `http://localhost:5173`.

- [ ] **Step 5: Pass backend tests and commit**

Run:

```bash
conda run -n final python -m pytest tests/test_service_database.py tests/test_service_builder.py tests/test_service_api.py -v
```

Expected: all backend service tests pass.

```bash
git add src/backend/schemas.py src/backend/repository.py src/backend/app.py tests/test_service_api.py
git commit -m "feat: serve RM insights through FastAPI"
```

---

### Task 6: Frontend API foundation without layout changes

**Files:**
- Create: `src/frontend/rm-insight-copilot/src/api/client.js`
- Create: `src/frontend/rm-insight-copilot/src/hooks/useApi.js`
- Create: `src/frontend/rm-insight-copilot/src/components/PageState.jsx`
- Create: `src/frontend/rm-insight-copilot/src/api/client.test.js`
- Modify: `src/frontend/rm-insight-copilot/package.json`
- Modify: `src/frontend/rm-insight-copilot/vite.config.js`
- Modify: `src/frontend/rm-insight-copilot/src/styles.css`

**Interfaces:**
- Produces: `apiGet(path: string, params?: Record<string, unknown>, signal?: AbortSignal): Promise<unknown>`.
- Produces: `useApi(path: string, params?: object) -> {data, loading, error, retry}`.
- Produces: `LoadingState`, `EmptyState`, and `ErrorState` components.

- [ ] **Step 1: Add frontend test tooling and failing client tests**

Add scripts `"test": "vitest run"` and dev dependencies `vitest`, `jsdom`, `@testing-library/react`, and `@testing-library/jest-dom`. Test that undefined/empty params are omitted, Korean values are URL-encoded, non-2xx JSON errors become `ApiError`, and abort errors are not converted into visible failures.

- [ ] **Step 2: Install packages and verify tests fail**

Run:

```bash
npm install
npm test -- src/api/client.test.js
```

Expected: import failure for `src/api/client.js`.

- [ ] **Step 3: Implement API client, hook, and state components**

Use `VITE_API_BASE_URL` when present and relative paths otherwise. `useApi` must abort stale requests in cleanup and expose `retry` through an incrementing request key. Page state components render inside existing panel/card containers; add only `.page-state`, `.page-error`, and `.page-empty` styles.

- [ ] **Step 4: Configure the Vite local proxy and pass tests**

Set `/api` proxy target to `http://127.0.0.1:8000` without changing React plugins. Run:

```bash
npm test -- src/api/client.test.js
npm run build
```

Expected: tests and production build pass.

- [ ] **Step 5: Commit Task 6**

```bash
git add src/frontend/rm-insight-copilot/package.json src/frontend/rm-insight-copilot/package-lock.json src/frontend/rm-insight-copilot/vite.config.js src/frontend/rm-insight-copilot/src/api src/frontend/rm-insight-copilot/src/hooks src/frontend/rm-insight-copilot/src/components/PageState.jsx src/frontend/rm-insight-copilot/src/styles.css
git commit -m "feat: add RM frontend API state layer"
```

---

### Task 7: Connect Overview and persistent-weakening pages

**Files:**
- Modify: `src/frontend/rm-insight-copilot/src/pages/OverviewPage.jsx`
- Modify: `src/frontend/rm-insight-copilot/src/pages/DormancyRiskPage.jsx`
- Modify: `src/frontend/rm-insight-copilot/src/components/RiskMeter.jsx`
- Modify: `src/frontend/rm-insight-copilot/src/components/MiniTrendChart.jsx`
- Create: `src/frontend/rm-insight-copilot/src/pages/OverviewPage.test.jsx`
- Create: `src/frontend/rm-insight-copilot/src/pages/DormancyRiskPage.test.jsx`

**Interfaces:**
- Consumes: `GET /api/overview`, `GET /api/filter-options`, and `GET /api/customers`.
- Preserves: current hero, KPI, two-column, filter bar, and customer-card DOM structure/classes.

- [ ] **Step 1: Write failing page tests**

Mock `apiGet`. For Overview assert real KPI values and top customer render, both existing navigation buttons still call `onPageChange`, and loading/error states do not render mock customer names. For Risk assert search, segment, and risk controls issue expected params and returned cards populate `RiskMeter` and `SignalBars`.

- [ ] **Step 2: Run focused tests and confirm mock-based failures**

Run:

```bash
npm test -- src/pages/OverviewPage.test.jsx src/pages/DormancyRiskPage.test.jsx
```

Expected: assertions fail because pages still import `mockData.js`.

- [ ] **Step 3: Replace mock imports with hooks while preserving markup classes**

Keep the same sections and child components. Format API decimals only at display boundaries. Change copy to `지속거래약화 예측`, `지속거래약화 위험`, and `CRM 우선순위 점수`. Populate select options from `/api/filter-options`. Debounce search by 250 ms; select changes update immediately.

- [ ] **Step 4: Make trend chart empty/zero-safe**

Return `null` for empty data and use a denominator of `1` when every value is zero so inline heights never become `NaN%`.

- [ ] **Step 5: Pass page tests/build and commit**

Run:

```bash
npm test -- src/pages/OverviewPage.test.jsx src/pages/DormancyRiskPage.test.jsx
npm run build
```

Expected: tests and build pass.

```bash
git add src/frontend/rm-insight-copilot/src/pages/OverviewPage.jsx src/frontend/rm-insight-copilot/src/pages/DormancyRiskPage.jsx src/frontend/rm-insight-copilot/src/pages/*.test.jsx src/frontend/rm-insight-copilot/src/components/RiskMeter.jsx src/frontend/rm-insight-copilot/src/components/MiniTrendChart.jsx
git commit -m "feat: connect RM risk dashboard data"
```

---

### Task 8: Connect priority and recommendation flow

**Files:**
- Modify: `src/frontend/rm-insight-copilot/src/App.jsx`
- Modify: `src/frontend/rm-insight-copilot/src/pages/PriorityPage.jsx`
- Modify: `src/frontend/rm-insight-copilot/src/pages/RecommendationsPage.jsx`
- Create: `src/frontend/rm-insight-copilot/src/pages/PriorityRecommendations.test.jsx`

**Interfaces:**
- App produces: `selectedCustomerId: string | null` and `onRecommendationOpen(corporateId: string)`.
- Consumes: `GET /api/priorities` and `GET /api/recommendations`.
- Preserves: current table and recommendation-card classes/layout.

- [ ] **Step 1: Write failing priority/recommendation tests**

Assert all five required filters (`industry`, `region`, `dedicated`, `weakening_type`, `segment`) are sent, priority rows retain server order, the column heading is `CRM 우선순위 점수`, no currency suffix is rendered, and clicking `추천 보기` calls `onRecommendationOpen("A")`. Assert selected customer recommendation appears first.

- [ ] **Step 2: Run tests and verify current static behavior fails**

Run:

```bash
npm test -- src/pages/PriorityRecommendations.test.jsx
```

Expected: failures because current filters are uncontrolled and button has no handler.

- [ ] **Step 3: Add selected-customer state without adding a router**

In `App.jsx`, keep `activePage`; add `selectedCustomerId`. Implement:

```javascript
const openRecommendation = (corporateId) => {
  setSelectedCustomerId(corporateId);
  setActivePage("recommendations");
};
```

Pass only the props required by Priority, Recommendations, and AI Report pages.

- [ ] **Step 4: Connect server filters and results**

Use controlled selects populated by filter options. Render `customer.valueProxy`, optional `customer.profitability`, and `customer.priorityScore` as distinct fields. Do not render `expectedLoss`. Preserve table/card DOM structure and current badges.

- [ ] **Step 5: Pass tests/build and commit**

Run:

```bash
npm test -- src/pages/PriorityRecommendations.test.jsx
npm run build
```

Expected: tests and build pass.

```bash
git add src/frontend/rm-insight-copilot/src/App.jsx src/frontend/rm-insight-copilot/src/pages/PriorityPage.jsx src/frontend/rm-insight-copilot/src/pages/RecommendationsPage.jsx src/frontend/rm-insight-copilot/src/pages/PriorityRecommendations.test.jsx
git commit -m "feat: connect CRM priority and recommendations"
```

---

### Task 9: Connect saved AI report results and retain unimplemented button

**Files:**
- Modify: `src/frontend/rm-insight-copilot/src/pages/AiReportPage.jsx`
- Create: `src/frontend/rm-insight-copilot/src/pages/AiReportPage.test.jsx`

**Interfaces:**
- Consumes: `selectedCustomerId`, `/api/filter-options`, and `GET /api/reports/{corporate_id}`.
- Preserves: report controls, beeswarm, report card, waterfall, report note, and `전략 보고서 생성` button.

- [ ] **Step 1: Write failing report-page tests**

Assert selecting customer B requests `/api/reports/B`, stored SHAP factors and strategy summary render, empty SHAP renders `설명값 미산출`, and the button exists with text `전략 보고서 생성`. Install a fetch/API mock and assert clicking the button causes zero POST requests and does not change the displayed report.

- [ ] **Step 2: Run the test and verify mock-data failure**

Run:

```bash
npm test -- src/pages/AiReportPage.test.jsx
```

Expected: failure because the page imports `customers` and `shapFactors` from mock data.

- [ ] **Step 3: Replace report mock values with stored API results**

Keep the button markup with no `onClick`. Fetch when selected ID changes. Render the API `strategySummary`, `signals`, and customer-specific SHAP factors. Keep the note explicit: this view reads stored validated scores and explanations and does not recalculate the model.

- [ ] **Step 4: Pass report tests/build and commit**

Run:

```bash
npm test -- src/pages/AiReportPage.test.jsx
npm run build
```

Expected: tests and build pass.

```bash
git add src/frontend/rm-insight-copilot/src/pages/AiReportPage.jsx src/frontend/rm-insight-copilot/src/pages/AiReportPage.test.jsx
git commit -m "feat: display stored RM report insights"
```

---

### Task 10: Remove active mock dependency, enforce copy, document runtime, and verify end to end

**Files:**
- Delete: `src/frontend/rm-insight-copilot/src/data/mockData.js`
- Modify: `src/frontend/rm-insight-copilot/src/components/TopNav.jsx`
- Modify: `tests/test_frontend_copy.py`
- Modify: `README.md`
- Modify: `src/frontend/rm-insight-copilot/src/styles.css` only if final state classes need alignment.

**Interfaces:**
- Produces: fully documented local workflow and no active frontend mock imports.

- [ ] **Step 1: Strengthen the copy/mock guard test**

Update the Python copy test to assert active JSX contains `지속거래약화 예측`, `지속거래약화 위험`, and `CRM 우선순위 점수`; excludes `금융관계 휴면화 예측`, `휴면위험`, and `기대손실`; and no JS/JSX file imports `data/mockData`.

- [ ] **Step 2: Run the guard and confirm remaining violations**

Run:

```bash
conda run -n final python -m pytest tests/test_frontend_copy.py -v
```

Expected: fail until remaining nav/copy and mock file references are removed.

- [ ] **Step 3: Correct nav copy and delete unused mock data**

Change only labels/text; preserve nav IDs, icons, classes, and order. Delete `mockData.js` after `rg -n "mockData" src/frontend/rm-insight-copilot/src` returns only the guard test expectation or no active import.

- [ ] **Step 4: Add exact local run documentation**

Document these commands with real artifact paths and explain that profitability CSV is exported from `df_profit` with `법인ID`, `기준월`, `V_FTP_12M`, and `V_FTP_12M_방어가치`:

```bash
conda run -n final python -m src.backend.load_service_database \
  --source /path/to/iM뱅크데이터_거시경제지표포함.csv \
  --risk-scores outputs/persistent_weakening_baseline/validation_scores.csv \
  --segment-panel outputs/segment_model_ablation/segment_modeling_panel.csv \
  --profitability /path/to/법인월별_FTP수익성.csv \
  --shap-local outputs/persistent_weakening_interpretation/shap_local_top_rows.csv \
  --database outputs/rm_service/rm_service.sqlite

RM_SERVICE_DB_PATH=outputs/rm_service/rm_service.sqlite \
  conda run -n final uvicorn src.backend.app:app --host 127.0.0.1 --port 8000

cd src/frontend/rm-insight-copilot
npm run dev
```

- [ ] **Step 5: Run the complete automated verification**

Run:

```bash
conda run -n final python -m pytest -q
cd src/frontend/rm-insight-copilot
npm test
npm run build
```

Expected: all Python tests pass; all Vitest tests pass; Vite build succeeds.

- [ ] **Step 6: Run local API smoke checks against a fixture or real loaded DB**

Start the API and verify:

```bash
curl -fsS http://127.0.0.1:8000/api/health
curl -fsS http://127.0.0.1:8000/api/overview
curl -fsS 'http://127.0.0.1:8000/api/priorities?page_size=1'
```

Expected: health is `ok`, overview contains `asOfMonth`, and priority output contains one item with `priorityScore` and no `expectedLoss`.

- [ ] **Step 7: Perform visual preservation check**

Open Overview, 지속거래약화 예측, CRM 우선순위, 맞춤 추천, and AI 리포트 at desktop width. Confirm current nav, hero, cards, table, recommendation cards, report controls, beeswarm, waterfall, splash, colors, spacing, and responsive behavior remain recognizable; confirm loading, empty, and API-error states stay inside the existing page shell.

- [ ] **Step 8: Commit final integration**

```bash
git add README.md tests/test_frontend_copy.py src/frontend/rm-insight-copilot/src
git commit -m "feat: complete RM web data integration"
```

---

## Final Verification Gate

Before claiming completion, use `superpowers:verification-before-completion` and record fresh output for:

```bash
git status --short
conda run -n final python -m pytest -q
cd src/frontend/rm-insight-copilot && npm test && npm run build
```

The work is complete only when the worktree contains no unintended files, all automated checks pass, and the five existing pages display stored service results without importing `mockData.js`.

