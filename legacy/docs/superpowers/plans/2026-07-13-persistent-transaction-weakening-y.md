# Persistent Transaction Weakening Y Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the active five-axis dormancy target with a tested `Y_지속거래약화_3M70` event-label pipeline and align all active project documentation with that target.

**Architecture:** A pure pandas label module validates the 36-month cohort, derives the three core activity aggregates, detects first-completion months of three consecutive YoY drops, and confirms persistence using disjoint 12-month baseline and 3-month future windows. A thin CLI handles file discovery and CSV outputs. Model training is explicitly gated until a separate rolling prediction target is approved.

**Tech Stack:** Python 3.10, pandas, NumPy, unittest, argparse, Markdown

## Global Constraints

- Final target is `Y_지속거래약화_3M70`.
- `핵심거래활동금액 = 입출금활동금액 + 채널활동금액 + 카드활동금액`.
- `drop50` requires YoY ratio strictly less than `0.50` for three consecutive months.
- Persistence requires future-three-month average divided by pre-event-twelve-month average strictly less than `0.70`.
- Missing customer-months and missing source amounts must never be silently converted to zero.
- The old `Y_핵심관계약화_3개월` and its performance metrics must not be presented as current results.
- Future-three-month confirmation data must never be exposed as a model feature.

---

### Task 1: Core activity and cohort contract

**Files:**
- Create: `src/preprocessing/__init__.py`
- Create: `src/preprocessing/persistent_transaction_weakening_labels.py`
- Create: `tests/test_persistent_transaction_weakening_labels.py`

**Interfaces:**
- Consumes: a `pandas.DataFrame` with `법인ID`, `기준년월`, and nine raw activity amount columns.
- Produces: `LabelConfig`, `validate_complete_cohort(frame, config) -> pd.DataFrame`, and `build_core_activity(frame, config) -> pd.DataFrame`.

- [ ] **Step 1: Write failing tests for source aggregation and validation**

```python
import unittest

import numpy as np
import pandas as pd

from src.preprocessing.persistent_transaction_weakening_labels import (
    LabelConfig,
    build_core_activity,
    validate_complete_cohort,
)


RAW_COLUMNS = {
    "요구불입금금액": 1.0,
    "요구불출금금액": 2.0,
    "창구거래금액": 3.0,
    "인터넷뱅킹거래금액": 4.0,
    "스마트뱅킹거래금액": 5.0,
    "폰뱅킹거래금액": 6.0,
    "ATM거래금액": 7.0,
    "신용카드사용금액": 8.0,
    "체크카드사용금액": 9.0,
}


def complete_frame(customer="C1"):
    months = pd.period_range("2023-01", "2025-12", freq="M")
    return pd.DataFrame([
        {"법인ID": customer, "기준년월": int(month.strftime("%Y%m")), **RAW_COLUMNS}
        for month in months
    ])


class CoreActivityContractTest(unittest.TestCase):
    def test_aggregates_flow_channel_card_and_core(self):
        result = build_core_activity(complete_frame(), LabelConfig())
        row = result.iloc[0]
        self.assertEqual(row["입출금활동금액"], 3.0)
        self.assertEqual(row["채널활동금액"], 25.0)
        self.assertEqual(row["카드활동금액"], 17.0)
        self.assertEqual(row["핵심거래활동금액"], 45.0)

    def test_missing_component_keeps_core_activity_missing(self):
        frame = complete_frame()
        frame.loc[0, "ATM거래금액"] = np.nan
        result = build_core_activity(frame, LabelConfig())
        self.assertTrue(pd.isna(result.loc[0, "핵심거래활동금액"]))

    def test_rejects_duplicate_customer_month(self):
        frame = pd.concat([complete_frame(), complete_frame().iloc[[0]]])
        with self.assertRaisesRegex(ValueError, "중복"):
            validate_complete_cohort(frame, LabelConfig())

    def test_rejects_incomplete_month_sequence(self):
        with self.assertRaisesRegex(ValueError, "36개월"):
            validate_complete_cohort(complete_frame().iloc[:-1], LabelConfig())
```

- [ ] **Step 2: Run the tests and verify the import fails**

Run: `python -m unittest tests.test_persistent_transaction_weakening_labels.CoreActivityContractTest -v`

Expected: ERROR with `ModuleNotFoundError` for `persistent_transaction_weakening_labels`.

- [ ] **Step 3: Implement configuration, cohort validation, and aggregation**

```python
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class LabelConfig:
    customer_id_col: str = "법인ID"
    month_col: str = "기준년월"
    expected_months: int = 36
    flow_cols: tuple[str, ...] = ("요구불입금금액", "요구불출금금액")
    channel_cols: tuple[str, ...] = (
        "창구거래금액", "인터넷뱅킹거래금액", "스마트뱅킹거래금액",
        "폰뱅킹거래금액", "ATM거래금액",
    )
    card_cols: tuple[str, ...] = ("신용카드사용금액", "체크카드사용금액")

    @property
    def amount_cols(self) -> tuple[str, ...]:
        return self.flow_cols + self.channel_cols + self.card_cols


def _require_columns(frame: pd.DataFrame, columns: tuple[str, ...]) -> None:
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise ValueError(f"필수 컬럼이 없습니다: {missing}")


def validate_complete_cohort(frame: pd.DataFrame, config: LabelConfig) -> pd.DataFrame:
    _require_columns(frame, (config.customer_id_col, config.month_col, *config.amount_cols))
    work = frame.copy()
    parsed = pd.to_datetime(work[config.month_col].astype(str), format="%Y%m", errors="coerce")
    if parsed.isna().any():
        examples = work.loc[parsed.isna(), config.month_col].head(5).tolist()
        raise ValueError(f"기준년월 파싱 실패: {examples}")
    work[config.month_col] = parsed.dt.to_period("M")
    duplicated = work.duplicated([config.customer_id_col, config.month_col], keep=False)
    if duplicated.any():
        raise ValueError("법인×월 중복이 있습니다.")
    bad = []
    for customer_id, group in work.groupby(config.customer_id_col, sort=False):
        months = group[config.month_col].sort_values()
        expected = pd.period_range(months.iloc[0], periods=config.expected_months, freq="M")
        if len(months) != config.expected_months or not months.reset_index(drop=True).equals(pd.Series(expected)):
            bad.append(customer_id)
    if bad:
        raise ValueError(f"정확한 연속 36개월 조건을 충족하지 않은 법인 수: {len(bad)}")
    amounts = work.loc[:, config.amount_cols].apply(pd.to_numeric, errors="coerce")
    if amounts.lt(0).any().any():
        raise ValueError("음수 거래금액이 있습니다.")
    work.loc[:, config.amount_cols] = amounts
    return work.sort_values([config.customer_id_col, config.month_col]).reset_index(drop=True)


def build_core_activity(frame: pd.DataFrame, config: LabelConfig | None = None) -> pd.DataFrame:
    config = config or LabelConfig()
    work = validate_complete_cohort(frame, config)
    work["입출금활동금액"] = work.loc[:, config.flow_cols].sum(axis=1, min_count=len(config.flow_cols))
    work["채널활동금액"] = work.loc[:, config.channel_cols].sum(axis=1, min_count=len(config.channel_cols))
    work["카드활동금액"] = work.loc[:, config.card_cols].sum(axis=1, min_count=len(config.card_cols))
    work["핵심거래활동금액"] = work[["입출금활동금액", "채널활동금액", "카드활동금액"]].sum(axis=1, min_count=3)
    return work
```

- [ ] **Step 4: Run the contract tests and verify they pass**

Run: `python -m unittest tests.test_persistent_transaction_weakening_labels.CoreActivityContractTest -v`

Expected: 4 tests, all `ok`.

- [ ] **Step 5: Commit the core contract**

```bash
git add src/preprocessing/__init__.py src/preprocessing/persistent_transaction_weakening_labels.py tests/test_persistent_transaction_weakening_labels.py
git commit -m "feat: add persistent weakening activity contract"
```

### Task 2: YoY, consecutive event, and persistence label

**Files:**
- Modify: `src/preprocessing/persistent_transaction_weakening_labels.py`
- Modify: `tests/test_persistent_transaction_weakening_labels.py`

**Interfaces:**
- Consumes: validated output from `build_core_activity`.
- Produces: `build_persistent_weakening_labels(frame, config=None) -> tuple[pd.DataFrame, pd.DataFrame]`.

- [ ] **Step 1: Add failing behavioral tests**

```python
from src.preprocessing.persistent_transaction_weakening_labels import build_persistent_weakening_labels


def activity_frame(core_values):
    frame = complete_frame()
    weights = {column: value / 9 for column, value in RAW_COLUMNS.items()}
    for index, core in enumerate(core_values):
        for column, weight in weights.items():
            frame.loc[index, column] = core * weight / sum(weights.values())
    return frame


class PersistentWeakeningLabelTest(unittest.TestCase):
    def test_marks_only_first_completion_month_and_confirms_below_point_seven(self):
        values = [100.0] * 36
        values[12:18] = [49.0, 49.0, 49.0, 40.0, 40.0, 40.0]
        panel, events = build_persistent_weakening_labels(activity_frame(values))
        event = events.iloc[0]
        self.assertEqual(str(event["기준년월"]), "2024-03")
        self.assertAlmostEqual(event["future3_to_baseline"], 0.4)
        self.assertEqual(event["Y_지속거래약화_3M70"], 1)
        self.assertEqual(panel["core_3m_event"].sum(), 1)

    def test_ratio_equal_half_is_not_drop50(self):
        values = [100.0] * 36
        values[12:15] = [49.0, 50.0, 49.0]
        panel, events = build_persistent_weakening_labels(activity_frame(values))
        self.assertFalse(panel.loc[panel["기준년월"].eq(pd.Period("2024-02")), "drop50"].iloc[0])
        self.assertTrue(events.empty)

    def test_ratio_equal_point_seven_is_negative(self):
        values = [100.0] * 36
        values[12:15] = [49.0, 49.0, 49.0]
        values[15:18] = [70.0, 70.0, 70.0]
        _, events = build_persistent_weakening_labels(activity_frame(values))
        self.assertEqual(events.iloc[0]["Y_지속거래약화_3M70"], 0)

    def test_insufficient_future_window_keeps_y_missing(self):
        values = [100.0] * 36
        values[33:36] = [49.0, 49.0, 49.0]
        _, events = build_persistent_weakening_labels(activity_frame(values))
        self.assertTrue(pd.isna(events.iloc[0]["Y_지속거래약화_3M70"]))
```

- [ ] **Step 2: Run the label tests and verify the missing function failure**

Run: `python -m unittest tests.test_persistent_transaction_weakening_labels.PersistentWeakeningLabelTest -v`

Expected: ERROR because `build_persistent_weakening_labels` is not defined.

- [ ] **Step 3: Implement the minimal label pipeline**

```python
import numpy as np


TARGET_COL = "Y_지속거래약화_3M70"
EVENT_ID_COL = "지속거래약화사건ID"


def _consecutive_true_count(series: pd.Series) -> pd.Series:
    result = []
    count = 0
    for value in series:
        if value is True or value == True:
            count += 1
        else:
            count = 0
        result.append(count)
    return pd.Series(result, index=series.index, dtype="int64")


def build_persistent_weakening_labels(
    frame: pd.DataFrame,
    config: LabelConfig | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    config = config or LabelConfig()
    panel = build_core_activity(frame, config)
    customer = panel[config.customer_id_col]
    core = panel["핵심거래활동금액"]
    prior = core.groupby(customer, sort=False).shift(12)
    panel["핵심거래_YoY_ratio"] = core.div(prior.where(prior.gt(0)))
    panel["drop50"] = panel["핵심거래_YoY_ratio"].lt(0.50).astype("boolean")
    panel.loc[panel["핵심거래_YoY_ratio"].isna(), "drop50"] = pd.NA
    panel["drop50_연속개월수"] = panel.groupby(config.customer_id_col, group_keys=False)["drop50"].apply(_consecutive_true_count)
    panel["core_3m_event"] = panel["drop50_연속개월수"].eq(3)
    grouped_core = core.groupby(customer, sort=False)
    panel["이벤트이전12개월평균"] = grouped_core.transform(lambda s: s.shift(1).rolling(12, min_periods=12).mean())
    panel["이벤트이후3개월평균"] = grouped_core.transform(lambda s: s.shift(-1).rolling(3, min_periods=3).mean().shift(-2))
    panel["future3_to_baseline"] = panel["이벤트이후3개월평균"].div(panel["이벤트이전12개월평균"].where(panel["이벤트이전12개월평균"].gt(0)))
    panel[TARGET_COL] = pd.Series(pd.NA, index=panel.index, dtype="Int8")
    decidable = panel["core_3m_event"] & panel["future3_to_baseline"].notna()
    panel.loc[decidable, TARGET_COL] = panel.loc[decidable, "future3_to_baseline"].lt(0.70).astype("int8")
    panel[EVENT_ID_COL] = pd.NA
    panel.loc[panel["core_3m_event"], EVENT_ID_COL] = (
        panel.loc[panel["core_3m_event"], config.customer_id_col].astype(str)
        + "+"
        + panel.loc[panel["core_3m_event"], config.month_col].astype(str)
    )
    events = panel.loc[panel["core_3m_event"]].copy().reset_index(drop=True)
    return panel, events
```

- [ ] **Step 4: Run all label tests**

Run: `python -m unittest tests.test_persistent_transaction_weakening_labels -v`

Expected: 8 tests, all `ok`.

- [ ] **Step 5: Commit event labeling**

```bash
git add src/preprocessing/persistent_transaction_weakening_labels.py tests/test_persistent_transaction_weakening_labels.py
git commit -m "feat: label persistent transaction weakening events"
```

### Task 3: Label CLI and output contract

**Files:**
- Create: `src/preprocessing/run_persistent_transaction_weakening_labels.py`
- Modify: `tests/test_persistent_transaction_weakening_labels.py`

**Interfaces:**
- Consumes: CSV path supplied with `--input`.
- Produces: `persistent_transaction_weakening_panel.csv` and `persistent_transaction_weakening_events.csv` in `--output-dir`.

- [ ] **Step 1: Write a failing CLI output test**

```python
import tempfile
from pathlib import Path

from src.preprocessing.run_persistent_transaction_weakening_labels import run_label_pipeline


class LabelRunnerTest(unittest.TestCase):
    def test_writes_panel_and_event_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path = root / "input.csv"
            complete_frame().to_csv(input_path, index=False)
            panel_path, events_path = run_label_pipeline(input_path, root / "outputs")
            self.assertTrue(panel_path.exists())
            self.assertTrue(events_path.exists())
```

- [ ] **Step 2: Run the test and verify the runner import fails**

Run: `python -m unittest tests.test_persistent_transaction_weakening_labels.LabelRunnerTest -v`

Expected: ERROR with `ModuleNotFoundError` for the runner module.

- [ ] **Step 3: Implement the runner**

```python
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from src.preprocessing.persistent_transaction_weakening_labels import build_persistent_weakening_labels


def run_label_pipeline(input_path: Path, output_dir: Path) -> tuple[Path, Path]:
    source = pd.read_csv(input_path)
    panel, events = build_persistent_weakening_labels(source)
    output_dir.mkdir(parents=True, exist_ok=True)
    panel_path = output_dir / "persistent_transaction_weakening_panel.csv"
    events_path = output_dir / "persistent_transaction_weakening_events.csv"
    panel.to_csv(panel_path, index=False, encoding="utf-8-sig")
    events.to_csv(events_path, index=False, encoding="utf-8-sig")
    return panel_path, events_path


def main() -> None:
    parser = argparse.ArgumentParser(description="지속거래약화 3M70 이벤트 라벨 생성")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output-dir", default=Path("outputs/persistent_transaction_weakening_labels"), type=Path)
    args = parser.parse_args()
    panel_path, events_path = run_label_pipeline(args.input, args.output_dir)
    print(f"saved: {panel_path}")
    print(f"saved: {events_path}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run all label tests**

Run: `python -m unittest tests.test_persistent_transaction_weakening_labels -v`

Expected: 9 tests, all `ok`.

- [ ] **Step 5: Commit the CLI**

```bash
git add src/preprocessing/run_persistent_transaction_weakening_labels.py tests/test_persistent_transaction_weakening_labels.py
git commit -m "feat: add persistent weakening label runner"
```

### Task 4: Replace active documentation and gate stale model execution

**Files:**
- Modify: `financial_dormancy.md`
- Modify: `README.md`
- Modify: `AGENTS.md`
- Modify: `src/models/model.md`
- Modify: `src/models/run_financial_dormancy_model.py`
- Create: `tests/test_persistent_target_documentation.py`

**Interfaces:**
- Consumes: the approved label contract and label module constants.
- Produces: one consistent active target definition; stale model runner exits with an explicit migration message.

- [ ] **Step 1: Write failing documentation and runner-gate tests**

```python
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ACTIVE_DOCS = [ROOT / "financial_dormancy.md", ROOT / "README.md", ROOT / "AGENTS.md", ROOT / "src/models/model.md"]


class PersistentTargetDocumentationTest(unittest.TestCase):
    def test_active_docs_name_the_new_final_target(self):
        for path in ACTIVE_DOCS:
            text = path.read_text(encoding="utf-8")
            self.assertIn("Y_지속거래약화_3M70", text, path)

    def test_active_docs_do_not_present_old_target_as_current(self):
        for path in ACTIVE_DOCS:
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("모델 학습용 y는 `Y_핵심관계약화_3개월`", text, path)

    def test_active_docs_do_not_claim_stale_performance(self):
        for path in ACTIVE_DOCS:
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("0.2959", text, path)
            self.assertNotIn("75.5%", text, path)
```

- [ ] **Step 2: Run the documentation tests and verify they fail on stale content**

Run: `python -m unittest tests.test_persistent_target_documentation -v`

Expected: FAIL because active documents still name the old target and stale performance.

- [ ] **Step 3: Rewrite active target sections and gate the old runner**

Update every active document to state the exact core activity formula, strict `<0.50` and `<0.70` boundaries, event-month definition, proxy limitation, and the fact that model performance is pending retraining. Replace the body of `main()` in `src/models/run_financial_dormancy_model.py` with:

```python
def main() -> None:
    raise SystemExit(
        "기존 Y_핵심관계약화_3개월 모델 실행은 중단되었습니다. "
        "먼저 src.preprocessing.run_persistent_transaction_weakening_labels로 "
        "Y_지속거래약화_3M70 이벤트 라벨을 생성하세요. "
        "rolling 예측 target 승인 후 모델을 재학습해야 합니다."
    )
```

- [ ] **Step 4: Run documentation and existing copy tests**

Run: `python -m unittest tests.test_persistent_target_documentation tests.test_frontend_copy -v`

Expected: all tests `ok`.

- [ ] **Step 5: Commit the active-document migration**

```bash
git add financial_dormancy.md README.md AGENTS.md src/models/model.md src/models/run_financial_dormancy_model.py tests/test_persistent_target_documentation.py
git commit -m "docs: switch project to persistent weakening target"
```

### Task 5: Full verification and stale-reference audit

**Files:**
- Modify if required: files touched in Tasks 1-4 only

**Interfaces:**
- Consumes: completed label pipeline and migrated documentation.
- Produces: verified implementation with an explicit list of historical-only references.

- [ ] **Step 1: Run the complete unit-test suite**

Run: `python -m unittest discover -s tests -v`

Expected: all tests pass with no errors or failures.

- [ ] **Step 2: Run syntax compilation**

Run: `python -m compileall -q src tests`

Expected: exit code 0 and no output.

- [ ] **Step 3: Audit active references**

Run: `rg -n "Y_핵심관계약화_3개월|0\.2959|75\.5%|3축 이상 50%" financial_dormancy.md README.md AGENTS.md src tests`

Expected: no current-target or current-performance claims; any retained occurrence must be explicitly labeled historical or migration-only.

- [ ] **Step 4: Review the final diff for scope and whitespace errors**

Run: `git diff --check`

Expected: no output.

Run: `git status --short`

Expected: only the user’s pre-existing unrelated changes plus files deliberately changed by this plan.

- [ ] **Step 5: Commit verification fixes only if Step 1-4 required changes**

```bash
git add src/preprocessing tests financial_dormancy.md README.md AGENTS.md src/models/model.md src/models/run_financial_dormancy_model.py
git commit -m "test: verify persistent weakening target migration"
```
