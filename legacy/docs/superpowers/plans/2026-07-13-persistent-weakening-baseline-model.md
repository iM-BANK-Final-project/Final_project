# Persistent Weakening Baseline Model Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a leakage-safe rolling three-month target, fixed time split, three baseline scorers, and reproducible evaluation outputs for `Y_지속거래약화_3M70`.

**Architecture:** One focused model module converts the existing event-label panel into anchor rows, derives past-only features, enforces the calendar split, fits fixed baselines, and calculates row/event metrics. A thin runner loads raw CSV data through the approved label pipeline and writes auditable outputs. All behavior is developed with synthetic 36-month corporate panels because the real source file is not present in the workspace.

**Tech Stack:** Python 3.10 contract, pandas 2.1.4, NumPy 1.26.4, scikit-learn 1.4.2, unittest

## Global Constraints

- Event target remains `Y_지속거래약화_3M70`.
- Model target is `Y_향후3개월_지속거래약화(t)=1` only when a positive event occurs in `t+1~t+3`.
- Features use month `t` and earlier only; future confirmation fields are forbidden.
- Earliest anchor is `2024-02`; latest fully observable anchor is `2025-06`.
- Train anchors are `2024-02~2024-09`.
- Anchor months `2024-10~2025-03` are label-window purge rows, not training or validation rows.
- Validation anchors are `2025-04~2025-06` and are never used to fit preprocessing or models.
- Current `core_3m_event=1` anchors are excluded.
- Validation is a final time-out holdout; baseline hyperparameters are fixed before evaluation.
- Real-data performance must not be claimed until the source data is supplied and the runner is executed.

---

### Task 1: Rolling target and label-window split

**Files:**
- Create: `src/models/persistent_weakening_baseline.py`
- Create: `tests/test_persistent_weakening_modeling.py`

**Interfaces:**
- Consumes: the monthly panel returned by `build_persistent_weakening_labels`.
- Produces: `build_modeling_targets(label_panel) -> pd.DataFrame` and `split_train_validation(frame) -> tuple[pd.DataFrame, pd.DataFrame]`.

- [ ] **Step 1: Write failing rolling-target tests**

```python
import unittest

import pandas as pd

from src.models.persistent_weakening_baseline import (
    MODEL_TARGET_COL,
    build_modeling_targets,
    split_train_validation,
)


def labeled_panel(event_month="2024-05", event_y=1):
    months = pd.period_range("2023-01", "2025-12", freq="M")
    panel = pd.DataFrame({
        "법인ID": "C1",
        "기준년월": months,
        "핵심거래활동금액": 100.0,
        "입출금활동금액": 40.0,
        "채널활동금액": 40.0,
        "카드활동금액": 20.0,
        "핵심거래_YoY_ratio": 1.0,
        "drop50": False,
        "drop50_연속개월수": 0,
        "core_3m_event": False,
        "Y_지속거래약화_3M70": pd.Series(pd.NA, index=range(36), dtype="Int8"),
        "지속거래약화사건ID": pd.NA,
    })
    event = panel["기준년월"].eq(pd.Period(event_month))
    panel.loc[event, "core_3m_event"] = True
    panel.loc[event, "Y_지속거래약화_3M70"] = event_y
    panel.loc[event, "지속거래약화사건ID"] = f"C1+{event_month}"
    return panel


class RollingTargetTest(unittest.TestCase):
    def test_positive_event_labels_only_previous_three_anchors(self):
        result = build_modeling_targets(labeled_panel("2024-05"))
        positives = result.loc[result[MODEL_TARGET_COL].eq(1), "기준년월"]
        self.assertEqual(positives.astype(str).tolist(), ["2024-02", "2024-03", "2024-04"])

    def test_event_at_t_plus_four_is_not_in_target(self):
        result = build_modeling_targets(labeled_panel("2024-06"))
        february = result["기준년월"].eq(pd.Period("2024-02"))
        self.assertEqual(result.loc[february, MODEL_TARGET_COL].iloc[0], 0)

    def test_current_event_anchor_is_excluded(self):
        result = build_modeling_targets(labeled_panel("2024-05"))
        self.assertNotIn("2024-05", result["기준년월"].astype(str).tolist())

    def test_latest_anchor_is_june_2025(self):
        result = build_modeling_targets(labeled_panel("2024-05"))
        self.assertEqual(str(result["기준년월"].max()), "2025-06")

    def test_split_has_six_month_label_window_purge(self):
        result = build_modeling_targets(labeled_panel("2024-05"))
        train, validation = split_train_validation(result)
        self.assertEqual(str(train["기준년월"].min()), "2024-02")
        self.assertEqual(str(train["기준년월"].max()), "2024-09")
        self.assertEqual(str(validation["기준년월"].min()), "2025-04")
        self.assertEqual(str(validation["기준년월"].max()), "2025-06")
        self.assertLess(train["label_end"].max(), validation["기준년월"].min())
```

- [ ] **Step 2: Run tests and confirm the model module is missing**

Run: `python -m unittest tests.test_persistent_weakening_modeling.RollingTargetTest -v`

Expected: ERROR with `ModuleNotFoundError` for `persistent_weakening_baseline`.

- [ ] **Step 3: Implement the rolling target and fixed split**

```python
from __future__ import annotations

import pandas as pd

from src.preprocessing.persistent_transaction_weakening_labels import EVENT_ID_COL, TARGET_COL


MODEL_TARGET_COL = "Y_향후3개월_지속거래약화"
FUTURE_EVENT_MONTH_COL = "미래지속거래약화사건월"
FUTURE_EVENT_ID_COL = "미래지속거래약화사건ID"
FIRST_ANCHOR = pd.Period("2024-02", freq="M")
LAST_ANCHOR = pd.Period("2025-06", freq="M")


def build_modeling_targets(label_panel: pd.DataFrame) -> pd.DataFrame:
    panel = label_panel.sort_values(["법인ID", "기준년월"]).copy()
    rows = []
    for customer_id, group in panel.groupby("법인ID", sort=False):
        positive_events = group.loc[group[TARGET_COL].eq(1), ["기준년월", EVENT_ID_COL]]
        for _, anchor in group.iterrows():
            month = anchor["기준년월"]
            if month < FIRST_ANCHOR or month > LAST_ANCHOR or bool(anchor["core_3m_event"]):
                continue
            future = positive_events.loc[
                positive_events["기준년월"].between(month + 1, month + 3)
            ].sort_values("기준년월")
            row = anchor.to_dict()
            row[MODEL_TARGET_COL] = int(not future.empty)
            row["label_end"] = month + 6
            row[FUTURE_EVENT_MONTH_COL] = future.iloc[0]["기준년월"] if not future.empty else pd.NaT
            row[FUTURE_EVENT_ID_COL] = future.iloc[0][EVENT_ID_COL] if not future.empty else pd.NA
            rows.append(row)
    return pd.DataFrame(rows).reset_index(drop=True)


def split_train_validation(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    train = frame.loc[frame["기준년월"].between(pd.Period("2024-02"), pd.Period("2024-09"))].copy()
    validation = frame.loc[frame["기준년월"].between(pd.Period("2025-04"), pd.Period("2025-06"))].copy()
    if train.empty or validation.empty:
        raise ValueError("train 또는 validation 구간이 비어 있습니다.")
    if train["label_end"].max() >= validation["기준년월"].min():
        raise ValueError("train label 관찰창과 validation 기준월이 겹칩니다.")
    return train, validation
```

- [ ] **Step 4: Run rolling-target tests**

Run: `python -m unittest tests.test_persistent_weakening_modeling.RollingTargetTest -v`

Expected: 5 tests, all `ok`.

- [ ] **Step 5: Commit rolling target**

```bash
git add src/models/persistent_weakening_baseline.py tests/test_persistent_weakening_modeling.py
git commit -m "feat: add rolling persistent weakening target"
```

### Task 2: Past-only feature engineering and leakage guards

**Files:**
- Modify: `src/models/persistent_weakening_baseline.py`
- Modify: `tests/test_persistent_weakening_modeling.py`

**Interfaces:**
- Consumes: event-label monthly panel plus the anchor keys created by `build_modeling_targets`.
- Produces: `build_modeling_features(label_panel) -> pd.DataFrame` and `model_feature_columns(frame) -> list[str]`.

- [ ] **Step 1: Write failing feature-cutoff tests**

```python
from src.models.persistent_weakening_baseline import build_modeling_features, model_feature_columns


class PastOnlyFeatureTest(unittest.TestCase):
    def test_changing_future_values_does_not_change_anchor_features(self):
        original = labeled_panel("2024-05")
        changed = original.copy()
        changed.loc[changed["기준년월"].gt(pd.Period("2024-02")), "핵심거래활동금액"] = 999999.0
        before = build_modeling_features(original).set_index(["법인ID", "기준년월"]).loc[("C1", pd.Period("2024-02"))]
        after = build_modeling_features(changed).set_index(["법인ID", "기준년월"]).loc[("C1", pd.Period("2024-02"))]
        pd.testing.assert_series_equal(before, after)

    def test_forbidden_columns_are_not_model_features(self):
        features = build_modeling_features(labeled_panel("2024-05"))
        selected = model_feature_columns(features)
        forbidden = {"Y_지속거래약화_3M70", MODEL_TARGET_COL, "이벤트이후3개월평균", "future3_to_baseline", FUTURE_EVENT_ID_COL}
        self.assertTrue(forbidden.isdisjoint(selected))
```

- [ ] **Step 2: Run tests and confirm missing functions**

Run: `python -m unittest tests.test_persistent_weakening_modeling.PastOnlyFeatureTest -v`

Expected: ERROR because `build_modeling_features` is not defined.

- [ ] **Step 3: Implement deterministic past-only rolling features**

```python
import numpy as np


FEATURE_AXES = ("핵심거래활동금액", "입출금활동금액", "채널활동금액", "카드활동금액")
FORBIDDEN_FEATURES = {
    TARGET_COL, MODEL_TARGET_COL, "이벤트이후3개월평균", "future3_to_baseline",
    FUTURE_EVENT_MONTH_COL, FUTURE_EVENT_ID_COL, EVENT_ID_COL, "label_end",
}


def _slope(values: pd.Series) -> float:
    clean = values.dropna().to_numpy(dtype=float)
    return float(np.polyfit(np.arange(len(clean)), clean, 1)[0]) if len(clean) >= 2 else np.nan


def build_modeling_features(label_panel: pd.DataFrame) -> pd.DataFrame:
    monthly = label_panel.sort_values(["법인ID", "기준년월"]).copy()
    engineered = monthly[["법인ID", "기준년월"]].copy()
    for axis in FEATURE_AXES:
        values = pd.to_numeric(monthly[axis], errors="coerce")
        grouped = values.groupby(monthly["법인ID"], sort=False)
        engineered[f"log1p_현재값_{axis}"] = np.log1p(values)
        engineered[f"1개월변화율_{axis}"] = grouped.pct_change(fill_method=None).replace([np.inf, -np.inf], np.nan)
        engineered[f"YoY_ratio_{axis}"] = values.div(grouped.shift(12).where(grouped.shift(12).gt(0)))
        for window in (3, 6):
            mean = grouped.transform(lambda s, w=window: s.rolling(w, min_periods=w).mean())
            std = grouped.transform(lambda s, w=window: s.rolling(w, min_periods=w).std())
            active = grouped.transform(lambda s, w=window: s.gt(0).rolling(w, min_periods=w).mean())
            engineered[f"log1p_최근{window}개월평균_{axis}"] = np.log1p(mean)
            engineered[f"log1p_최근{window}개월표준편차_{axis}"] = np.log1p(std)
            engineered[f"최근{window}개월활성률_{axis}"] = active
        previous6 = grouped.transform(lambda s: s.shift(3).rolling(6, min_periods=6).mean())
        recent3 = grouped.transform(lambda s: s.rolling(3, min_periods=3).mean())
        engineered[f"최근3개월_이전6개월비율_{axis}"] = recent3.div(previous6.where(previous6.gt(0)))
        for window in (3, 6, 12):
            engineered[f"최근{window}개월기울기_{axis}"] = grouped.transform(lambda s, w=window: s.rolling(w, min_periods=w).apply(_slope, raw=False))
    engineered["현재drop50"] = monthly["drop50"].astype("Float64")
    engineered["현재drop50연속개월수"] = monthly["drop50_연속개월수"]
    targets = build_modeling_targets(label_panel)
    return targets.merge(engineered, on=["법인ID", "기준년월"], how="left", validate="one_to_one")


def model_feature_columns(frame: pd.DataFrame) -> list[str]:
    identifiers = {"법인ID", "기준년월", "core_3m_event", "drop50", "drop50_연속개월수", "핵심거래_YoY_ratio"}
    return [column for column in frame.columns if column not in FORBIDDEN_FEATURES | identifiers and pd.api.types.is_numeric_dtype(frame[column])]
```

- [ ] **Step 4: Run modeling tests**

Run: `python -m unittest tests.test_persistent_weakening_modeling -v`

Expected: 7 tests, all `ok`.

- [ ] **Step 5: Commit feature engineering**

```bash
git add src/models/persistent_weakening_baseline.py tests/test_persistent_weakening_modeling.py
git commit -m "feat: add leakage-safe weakening features"
```

### Task 3: Baseline scoring and evaluation

**Files:**
- Modify: `src/models/persistent_weakening_baseline.py`
- Modify: `tests/test_persistent_weakening_modeling.py`

**Interfaces:**
- Consumes: train and validation feature frames.
- Produces: `fit_and_score_baselines(train, validation) -> tuple[pd.DataFrame, pd.DataFrame]` and `evaluate_scored_rows(scored) -> pd.DataFrame`.

- [ ] **Step 1: Write failing baseline and metric tests**

```python
from src.models.persistent_weakening_baseline import evaluate_scored_rows, fit_and_score_baselines


class BaselineEvaluationTest(unittest.TestCase):
    def test_top_half_metrics_and_event_recall(self):
        scored = pd.DataFrame({
            "법인ID": ["A", "B", "C", "D"],
            "기준년월": [pd.Period("2025-04")] * 4,
            MODEL_TARGET_COL: [1, 0, 1, 0],
            FUTURE_EVENT_ID_COL: ["A+2025-05", pd.NA, "C+2025-06", pd.NA],
            "모델": "rule",
            "예측확률": [0.9, 0.8, 0.7, 0.1],
        })
        metrics = evaluate_scored_rows(scored, top_fractions=(0.5,))
        row = metrics.iloc[0]
        self.assertEqual(row["Recall_at_K"], 0.5)
        self.assertEqual(row["Precision_at_K"], 0.5)
        self.assertEqual(row["Lift_at_K"], 1.0)
        self.assertEqual(row["사건Recall_at_K"], 0.5)

    def test_three_baselines_return_same_validation_rows(self):
        frame = build_modeling_features(pd.concat([labeled_panel("2024-05"), labeled_panel("2025-05").assign(법인ID="C2")], ignore_index=True))
        train, validation = split_train_validation(frame)
        scores, metrics = fit_and_score_baselines(train, validation)
        self.assertEqual(set(scores["모델"]), {"Prevalence", "CurrentSignalRule", "LogisticRegression"})
        self.assertEqual(scores.groupby("모델").size().nunique(), 1)
        self.assertEqual(set(metrics["모델"]), set(scores["모델"]))
```

- [ ] **Step 2: Run tests and confirm missing evaluation functions**

Run: `python -m unittest tests.test_persistent_weakening_modeling.BaselineEvaluationTest -v`

Expected: ERROR because baseline functions are not defined.

- [ ] **Step 3: Implement fixed baselines and ranking metrics**

```python
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


def evaluate_scored_rows(scored: pd.DataFrame, top_fractions=(0.05, 0.10, 0.20)) -> pd.DataFrame:
    rows = []
    for model_name, group in scored.groupby("모델", sort=False):
        positives = int(group[MODEL_TARGET_COL].sum())
        base_rate = group[MODEL_TARGET_COL].mean()
        total_events = group[FUTURE_EVENT_ID_COL].dropna().nunique()
        for fraction in top_fractions:
            count = max(1, int(np.ceil(len(group) * fraction)))
            top = group.nlargest(count, "예측확률")
            captured = int(top[MODEL_TARGET_COL].sum())
            captured_events = top[FUTURE_EVENT_ID_COL].dropna().nunique()
            precision = captured / count
            rows.append({
                "모델": model_name,
                "K": fraction,
                "PR_AUC": average_precision_score(group[MODEL_TARGET_COL], group["예측확률"]) if positives else np.nan,
                "Recall_at_K": captured / positives if positives else np.nan,
                "Precision_at_K": precision,
                "Lift_at_K": precision / base_rate if base_rate else np.nan,
                "사건Recall_at_K": captured_events / total_events if total_events else np.nan,
            })
    return pd.DataFrame(rows)


def fit_and_score_baselines(train: pd.DataFrame, validation: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    if train[MODEL_TARGET_COL].nunique() < 2:
        raise ValueError("train에 양성과 음성이 모두 필요합니다.")
    feature_columns = model_feature_columns(train)
    outputs = []
    base = validation[["법인ID", "기준년월", MODEL_TARGET_COL, FUTURE_EVENT_ID_COL]].copy()
    prevalence = base.copy()
    prevalence["모델"] = "Prevalence"
    prevalence["예측확률"] = train[MODEL_TARGET_COL].mean()
    outputs.append(prevalence)
    rule = base.copy()
    yoy = validation["핵심거래_YoY_ratio"].fillna(1.0)
    rule["모델"] = "CurrentSignalRule"
    rule["예측확률"] = 2 * validation["drop50_연속개월수"].clip(upper=2) + yoy.lt(0.70).astype(int) + (1 - yoy).clip(lower=0)
    outputs.append(rule)
    pipeline = Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("scaler", StandardScaler()),
        ("model", LogisticRegression(C=1.0, class_weight="balanced", max_iter=1000, random_state=42)),
    ])
    pipeline.fit(train[feature_columns], train[MODEL_TARGET_COL].astype(int))
    logistic = base.copy()
    logistic["모델"] = "LogisticRegression"
    logistic["예측확률"] = pipeline.predict_proba(validation[feature_columns])[:, 1]
    outputs.append(logistic)
    scores = pd.concat(outputs, ignore_index=True)
    return scores, evaluate_scored_rows(scores)
```

- [ ] **Step 4: Run all modeling tests**

Run: `python -m unittest tests.test_persistent_weakening_modeling -v`

Expected: 9 tests, all `ok`. The two-customer fixture provides a 2024 train positive, train negatives, a 2025 validation positive, and validation negatives.

- [ ] **Step 5: Commit baselines**

```bash
git add src/models/persistent_weakening_baseline.py tests/test_persistent_weakening_modeling.py
git commit -m "feat: add persistent weakening baselines"
```

### Task 4: Runner, outputs, and complete verification

**Files:**
- Create: `src/models/run_persistent_weakening_baseline.py`
- Modify: `tests/test_persistent_weakening_modeling.py`
- Modify: `src/models/model.md`

**Interfaces:**
- Consumes: raw 36-month corporate CSV via `--input`.
- Produces: modeling panel, validation scores, and validation metrics under `--output-dir`.

- [ ] **Step 1: Write a failing runner output test**

```python
import tempfile
from pathlib import Path

from src.models.run_persistent_weakening_baseline import OUTPUT_FILENAMES, write_baseline_outputs


class BaselineRunnerTest(unittest.TestCase):
    def test_writes_all_output_contract_files(self):
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory)
            frames = {name: pd.DataFrame({"value": [1]}) for name in OUTPUT_FILENAMES}
            paths = write_baseline_outputs(frames, output_dir)
            self.assertEqual(set(paths), set(OUTPUT_FILENAMES))
            self.assertTrue(all(path.exists() for path in paths.values()))
```

- [ ] **Step 2: Run runner test and confirm import failure**

Run: `python -m unittest tests.test_persistent_weakening_modeling.BaselineRunnerTest -v`

Expected: ERROR with `ModuleNotFoundError` for the runner.

- [ ] **Step 3: Implement CLI and output writer**

```python
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from src.models.persistent_weakening_baseline import build_modeling_features, fit_and_score_baselines, split_train_validation
from src.preprocessing.persistent_transaction_weakening_labels import build_persistent_weakening_labels


OUTPUT_FILENAMES = {
    "modeling_panel": "modeling_panel.csv",
    "validation_scores": "validation_scores.csv",
    "validation_metrics": "validation_metrics.csv",
}


def write_baseline_outputs(frames: dict[str, pd.DataFrame], output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {}
    for name, filename in OUTPUT_FILENAMES.items():
        path = output_dir / filename
        frames[name].to_csv(path, index=False, encoding="utf-8-sig")
        paths[name] = path
    return paths


def run_baseline(input_path: Path, output_dir: Path) -> dict[str, Path]:
    source = pd.read_csv(input_path)
    labels, _ = build_persistent_weakening_labels(source)
    modeling = build_modeling_features(labels)
    train, validation = split_train_validation(modeling)
    scores, metrics = fit_and_score_baselines(train, validation)
    return write_baseline_outputs({
        "modeling_panel": modeling,
        "validation_scores": scores,
        "validation_metrics": metrics,
    }, output_dir)


def main() -> None:
    parser = argparse.ArgumentParser(description="지속거래약화 baseline 모델 실행")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output-dir", default=Path("outputs/persistent_weakening_baseline"), type=Path)
    args = parser.parse_args()
    for name, path in run_baseline(args.input, args.output_dir).items():
        print(f"{name}: {path}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Update the modeling status document**

Replace the execution gate in `src/models/model.md` with this exact status block. Do not insert synthetic-test metrics as project performance.

````markdown
## Baseline Modeling Status

```text
모델링 Y = Y_향후3개월_지속거래약화
Train anchors = 2024-02~2024-09
Label-window purge = 2024-10~2025-03
Validation anchors = 2025-04~2025-06
실제 데이터 성능 = 미측정
```

비교 모델은 Train 양성률, CurrentSignalRule, 고정 설정 Logistic Regression이다. validation은 전처리·모델 fit에 사용하지 않는다. `이벤트이후3개월평균`, `future3_to_baseline`, 이벤트 Y, 미래 사건월·사건ID는 feature에서 제외한다.

```bash
python -m src.models.run_persistent_weakening_baseline \
  --input /path/to/corporate_monthly.csv \
  --output-dir outputs/persistent_weakening_baseline
```
````

- [ ] **Step 5: Run complete verification**

Run: `python -m unittest discover -s tests -v`

Expected: all tests pass with zero failures.

Run: `python -m compileall -q src tests`

Expected: exit code 0 and no output.

Run: `git diff --check`

Expected: no output.

Run: `rg -n "이벤트이후3개월평균|future3_to_baseline|Y_지속거래약화_3M70" src/models/persistent_weakening_baseline.py`

Expected: occurrences only in `FORBIDDEN_FEATURES`, imported target constants, or target construction logic; none in selected feature definitions.

- [ ] **Step 6: Commit runner and documentation**

```bash
git add src/models/run_persistent_weakening_baseline.py src/models/model.md tests/test_persistent_weakening_modeling.py
git commit -m "feat: add persistent weakening baseline runner"
```
