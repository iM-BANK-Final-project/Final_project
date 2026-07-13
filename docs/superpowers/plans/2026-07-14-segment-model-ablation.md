# Segment Feature Model Ablation Implementation Plan

> **Execution note:** Follow this plan sequentially with test-driven development. Do not alter the approved label, split, LightGBM parameters, or validation rows while comparing feature families.

**Goal:** Add leakage-safe rolling relationship-axis scores and L30_H70_M15 segment features to the existing persistent-weakening LightGBM pipeline, then compare them under one fixed train/validation experiment.

**Architecture:** The segmentation module will turn each corporation-month into three trailing-12-month relationship levels, score them against the fixed 2023 reference distribution, and assign one of six segments. A separate model-ablation module will one-to-one join those features to the existing modeling panel and run fixed LightGBM variants using identical rows, labels, split, and parameters. A CLI runner will reproduce the full experiment and write auditable outputs.

**Tech stack:** Python, pandas, NumPy, LightGBM, scikit-learn, pytest.

---

## Task 1: Build leakage-safe rolling relationship features

**Files:**
- Modify: `src/segmentation/relationship_segments.py`
- Modify: `tests/test_relationship_segments.py`

### Step 1: Write failing rolling-window and reference tests

Add tests that construct two small corporations with at least 14 monthly rows and assert:

- the feature at anchor `t` is the median of `log1p(amount)` from exactly `t-11` through `t`;
- changing `t+1` and later source values does not change features at `t`;
- one corporation's values never affect another corporation's rolling level;
- scores are calculated from the supplied fixed reference rather than re-ranking each anchor month;
- the six dummy columns always sum to one and correspond to the assigned segment.

Run:

```bash
pytest -q tests/test_relationship_segments.py
```

Expected: FAIL because the rolling feature functions and fixed dummy columns do not yet exist.

### Step 2: Implement the minimum rolling feature layer

Add public constants for the three score columns and six normalized dummy columns. Add:

```python
def build_reference_relationship_levels(
    monthly: pd.DataFrame,
    config: SegmentationConfig | None = None,
) -> pd.DataFrame:
    ...

def build_rolling_relationship_features(
    monthly: pd.DataFrame,
    reference: pd.DataFrame,
    config: SegmentationConfig | None = None,
) -> pd.DataFrame:
    ...
```

Implementation requirements:

1. Build the reference levels from the exact `2023-01` to `2023-12` window.
2. Sort by corporation and month before any rolling operation.
3. For each relationship amount axis, compute `log1p` first, then a customer-local 12-month median with `min_periods=12`.
4. Score every complete rolling level with `score_against_reference`.
5. Assign L30_H70_M15 with `assign_l30_h70_m15`.
6. Materialize all six fixed dummy columns, including absent categories.
7. Return only corporation, anchor month, levels, scores, segment, and fixed dummies.

### Step 3: Run the focused tests and commit

Run:

```bash
pytest -q tests/test_relationship_segments.py
git diff --check
```

Expected: PASS.

Commit:

```bash
git add src/segmentation/relationship_segments.py tests/test_relationship_segments.py
git commit -m "feat: build rolling relationship segment features"
```

## Task 2: Add safe panel joining and feature-family contracts

**Files:**
- Create: `src/models/segment_model_ablation.py`
- Create: `tests/test_segment_model_ablation.py`

### Step 1: Write failing join and feature-family tests

Add tests that assert:

- duplicate corporation-anchor keys in either input raise `ValueError`;
- a missing relationship-feature key raises `ValueError` instead of silently dropping or imputing a row;
- row count, row order, target, event ID, and label end are unchanged after joining;
- `Base`, `Segment`, `Axis`, and `Both` return the exact intended feature columns;
- every selected feature is numeric;
- `NoDirect` excludes all `DIRECT_SIGNAL_FEATURES` while leaving other base features unchanged.

Run:

```bash
pytest -q tests/test_segment_model_ablation.py
```

Expected: FAIL because the module does not exist.

### Step 2: Implement strict joining and feature sets

Create constants:

```python
RELATIONSHIP_SCORE_COLUMNS = (
    "거래활동점수",
    "수신관계점수",
    "여신관계점수",
)
SEGMENT_DUMMY_COLUMNS = (...six fixed columns...)
```

Add:

```python
def join_relationship_features(modeling, relationship_features): ...
def build_feature_families(frame): ...
```

The join must validate one-to-one keys, reject missing matches, preserve the left row order, and verify that modeling identity/label columns did not change. Feature-family construction must reuse `model_feature_columns` and `ablation_feature_columns`; it must not rediscover target or split columns by dtype.

### Step 3: Run focused tests and commit

Run:

```bash
pytest -q tests/test_segment_model_ablation.py
git diff --check
```

Expected: PASS.

Commit:

```bash
git add src/models/segment_model_ablation.py tests/test_segment_model_ablation.py
git commit -m "feat: define segment model feature families"
```

## Task 3: Implement fixed LightGBM ablation, selection, and diagnostics

**Files:**
- Modify: `src/models/segment_model_ablation.py`
- Modify: `tests/test_segment_model_ablation.py`

### Step 1: Write failing experiment-contract tests

Use small deterministic frames and monkeypatch the model builder where appropriate. Assert:

- all variants receive the same train and validation row keys;
- model fitting uses `build_fixed_lightgbm` for every variant;
- model names and feature counts are recorded;
- the K=10% selection order is PR-AUC, event recall, row recall, then fewer added features;
- if `Base` wins, a duplicate `NoDirect_Best` is not generated;
- if Segment, Axis, or Both wins, `NoDirect_Best` adds exactly that feature family to the NoDirect base;
- diagnostics report validation counts, positives, average score, top-decile share, capture rate, precision, and lift for all six segments with zero-filled absent categories.

Run:

```bash
pytest -q tests/test_segment_model_ablation.py
```

Expected: FAIL on the new experiment functions.

### Step 2: Implement the fixed comparison experiment

Add:

```python
def fit_and_score_segment_ablation(train, validation): ...
def select_best_feature_addition(metrics, feature_families): ...
def build_segment_diagnostics(scores): ...
```

Run phase 1 variants `LightGBM_Base`, `LightGBM_Segment`, `LightGBM_Axis`, and `LightGBM_Both`. Select the best at K=0.10 using the documented deterministic tie-break. Then run `LightGBM_NoDirect` and, only when a non-base addition wins, `LightGBM_NoDirect_Best`. Return validation scores, metrics, and a feature-selection table containing each model's feature family, feature count, added feature count, and selection status.

All probability scoring must happen only on the validation frame. Never use validation labels for fitting, preprocessing, imputation, or threshold construction.

### Step 3: Run model tests and commit

Run:

```bash
pytest -q tests/test_segment_model_ablation.py tests/test_persistent_weakening_modeling.py
git diff --check
```

Expected: PASS.

Commit:

```bash
git add src/models/segment_model_ablation.py tests/test_segment_model_ablation.py
git commit -m "feat: compare relationship segment model variants"
```

## Task 4: Add the reproducible CLI runner and output validation

**Files:**
- Create: `src/models/run_segment_model_ablation.py`
- Modify: `tests/test_segment_model_ablation.py`
- Modify: `src/models/model.md`

### Step 1: Write failing runner and output tests

Add tests for:

- the source `usecols` union includes every label and segmentation source column once;
- the selected 36-month cohort is identical for the label and relationship pipelines;
- the runner invokes the approved train/purge/validation split;
- output writing requires and produces `modeling_panel`, `validation_scores`, `validation_metrics`, `validation_lift`, `segment_diagnostics`, and `feature_selection`;
- CSV output paths and encodings are stable.

Run:

```bash
pytest -q tests/test_segment_model_ablation.py
```

Expected: FAIL because the runner and required output contract do not exist.

### Step 2: Implement the end-to-end runner

The runner must:

1. Read the de-duplicated union of `LabelConfig.amount_cols` and `SegmentationConfig.amount_cols`.
2. Select the exact 2023-01 to 2025-12 complete cohort once.
3. Build the approved persistent-weakening labels and existing modeling features without changing them.
4. Build 2023 reference levels and trailing-12-month relationship features.
5. Strictly join on corporation and anchor month.
6. Apply `split_train_validation` unchanged.
7. Run the fixed model comparison and write all six auditable outputs.

Update `src/models/model.md` with feature timing, experiment variants, selection caveat, and command example. State explicitly that choosing the best variant on this validation window is exploratory and requires a later untouched time interval before a final generalization claim.

### Step 3: Run focused and full automated tests

Run:

```bash
pytest -q tests/test_segment_model_ablation.py
pytest -q
git diff --check
```

Expected: all tests PASS and no whitespace errors.

### Step 4: Run on the actual project CSV and validate artifacts

Run:

```bash
python -m src.models.run_segment_model_ablation \
  --input "/Users/gggyyu/Desktop/(아이엠뱅크) 2026 교육용 데이터/(iM뱅크) 2026 교육용 법인 익명데이터.csv" \
  --output-dir outputs/segment_model_ablation
```

Then verify:

- complete cohort count remains 3,372;
- train and validation month ranges match the approved split;
- train `label_end` ends before validation starts;
- joining does not change row count or target prevalence;
- relationship scores stay in `[0, 1]`;
- each row has exactly one segment dummy;
- no probabilities, labels, or metrics contain unexpected nulls;
- model score rows are identical across all generated variants;
- metrics and diagnostic aggregates reconcile to raw validation rows.

### Step 5: Final verification commit

Commit:

```bash
git add src/models/run_segment_model_ablation.py src/models/model.md tests/test_segment_model_ablation.py
git commit -m "feat: run leakage-safe segment model ablation"
```

Run one final clean verification:

```bash
pytest -q
git status --short
git log --oneline -5
```

Do not merge or push until the user reviews the implementation and actual-data results.
