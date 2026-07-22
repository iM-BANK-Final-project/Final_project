# Historical FISIM CLV Service Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve the 3,341 eligible customers and 2025-12 risk scores while replacing forecast CLV with trailing-six-month actual FISIM risk adjustment.

**Architecture:** `build_operating_clv` will aggregate already-normalized monthly FISIM for `c-5..c`, merge immutable operating scores, and calculate the new value fields before applying the existing deterministic rank. Service preparation, the canonical notebook, UI copy, and source-of-truth documentation will use the same contract.

**Tech Stack:** Python 3.10, pandas, NumPy, pytest, React/Vitest, Jupyter nbformat

## Global Constraints

- Keep exactly 3,341 `score_eligible=True` customers and their 2025-12 `risk_probability` values.
- Use 2025-07 through 2025-12 actual FISIM at the current operating cutoff.
- Do not use future balance forecasts or survival weighting.
- Preserve negative FISIM; rank only positive `defense_value`.
- Keep public API field names unchanged.

---

### Task 1: Actual-FISIM CLV calculation

**Files:**
- Modify: `tests/test_m12_clv.py`
- Modify: `src/backend/m12_clv.py`

**Interfaces:**
- Consumes: `build_monthly_fisim(source, rates)` and operating scores with `법인ID`, `risk_probability`
- Produces: `build_operating_clv(source, rates, scores, cutoff)` with `수익성월수=6`

- [ ] Replace the survival-formula test with expectations for `CLV_Risk=P_actual/(1+p)` and actual months `c-5..c`.
- [ ] Run `pytest tests/test_m12_clv.py -q` and confirm the new expectations fail against the forecast implementation.
- [ ] Change `build_operating_clv` to aggregate six actual monthly FISIM rows per eligible customer, validate completeness, and preserve ranking rules.
- [ ] Run `pytest tests/test_m12_clv.py -q` and confirm it passes.

### Task 2: Service input contract

**Files:**
- Modify: `tests/test_service_input_preparation.py`
- Modify: `tests/test_service_builder.py`
- Modify: `tests/test_service_database.py`
- Modify: `src/backend/service_builder.py`
- Modify: `src/backend/prepare_service_database.py`

**Interfaces:**
- Consumes: CLV artifact containing `수익성월수`
- Produces: unchanged service DB/API value fields

- [ ] Update tests to require `수익성월수=6` and the latest formula.
- [ ] Run the focused service tests and confirm the schema expectation fails.
- [ ] Replace the internal `예측월수` contract with `수익성월수` and update descriptions.
- [ ] Run the focused service tests and confirm they pass.

### Task 3: Canonical notebook and explanations

**Files:**
- Modify: `src/수익성F(y선정포함).ipynb`
- Modify: `src/frontend/rm-insight-copilot/src/pages/PriorityPage.jsx`
- Modify: `src/frontend/rm-insight-copilot/src/pages/PriorityPage.test.jsx`
- Modify: `src/backend/gemini_service.py`
- Modify: `src/backend/report_pdf.py`

**Interfaces:**
- Consumes: the approved design formula and existing API values
- Produces: notebook calculation and user-facing copy aligned to actual 2025-07~12 FISIM

- [ ] Add or update copy tests so the previous future-value wording fails.
- [ ] Update notebook sections 11-14 without changing the model/risk population, and update UI/report wording.
- [ ] Run notebook structural tests plus focused frontend/backend report tests.

### Task 4: Source-of-truth documentation and end-to-end verification

**Files:**
- Modify: `AGENTS.md`
- Modify: `README.md`
- Modify: `financial_dormancy.md`
- Modify: `src/models/model.md`
- Modify: `docs/superpowers/specs/2026-07-21-m12-model-clv-service-integration-design.md`

**Interfaces:**
- Consumes: verified implementation contract
- Produces: consistent repository guidance

- [ ] Replace forecast/survival CLV definitions with the actual trailing-six-month formula.
- [ ] Run documentation contract tests.
- [ ] Run the complete backend test suite and frontend test/build commands.
- [ ] Run service preparation against repository artifacts and verify 3,341 unique customers, unchanged score reconciliation, cutoff 2025-12, and six actual profitability months.
- [ ] Review `git diff --check`, staged diff, and branch status before handing off.
