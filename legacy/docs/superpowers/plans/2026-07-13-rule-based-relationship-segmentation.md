# Rule-Based Relationship Segmentation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `segmentation_final_report.md`의 `L30_H70_M15`를 2023년 고정 기준분포와 2024년 사후 안정성 검증까지 재현하는 세그먼트 파이프라인을 구현한다.

**Architecture:** 계산 모듈은 원천 검증, 12개월 관계수준 요약, 고정 percentile scoring, 룰 할당, 안정성 계산을 순수 함수로 제공한다. runner는 원천 CSV를 읽고 2023 reference/assignment/profile과 2024 assignment/profile/stability를 CSV로 저장한다.

**Tech Stack:** Python 3.9, pandas, numpy, scikit-learn, unittest

## Global Constraints

- 세그먼트 fit에는 2023-01~2023-12만 사용한다.
- 2024년은 2023 기준분포를 고정 적용하고 새로 순위를 매기지 않는다.
- 2025년, Y, 업종, 지역, 고객등급, 전담여부는 라벨 생성에 사용하지 않는다.
- 월별 금액 결측을 0으로 대체하지 않는다.
- 최종 룰은 `L30_H70_M15`이며 경계값을 포함한다.
- 테스트를 먼저 작성하고 기대 이유로 실패하는 것을 확인한 뒤 최소 구현한다.

---

### Task 1: Source Validation And Relationship Levels

**Files:**
- Create: `src/segmentation/__init__.py`
- Create: `src/segmentation/relationship_segments.py`
- Create: `tests/test_relationship_segments.py`

**Interfaces:**
- Produces: `SegmentationConfig`, `validate_segmentation_source(frame, config)`, `build_monthly_relationship_axes(frame, config)`, `summarize_relationship_window(monthly, start, end, config)`
- Consumes: 월별 법인 DataFrame과 정확한 12개월 구간

- [ ] **Step 1: Write failing source and axis tests**

```python
class RelationshipLevelTests(unittest.TestCase):
    def test_sums_report_axes_and_uses_median_log_level(self):
        source = make_monthly_source(customer_ids=["A"], years=(2023,))
        source.loc[source["기준년월"].eq(202301), "요구불입금금액"] = 8.0
        monthly = build_monthly_relationship_axes(source)
        levels = summarize_relationship_window(
            monthly,
            "2023-01",
            "2023-12",
        )
        expected = np.median(
            np.log1p(monthly.loc[monthly["법인ID"].eq("A"), "거래활동금액"])
        )
        self.assertAlmostEqual(levels.loc[0, "거래활동관계수준"], expected)

    def test_rejects_missing_negative_duplicate_and_incomplete_source(self):
        source = make_monthly_source(customer_ids=["A"], years=(2023,))
        with self.subTest("missing"):
            broken = source.copy()
            broken.loc[0, "요구불입금금액"] = np.nan
            with self.assertRaisesRegex(ValueError, "결측"):
                build_monthly_relationship_axes(broken)
        with self.subTest("negative"):
            broken = source.copy()
            broken.loc[0, "요구불입금금액"] = -1
            with self.assertRaisesRegex(ValueError, "음수"):
                build_monthly_relationship_axes(broken)
        with self.subTest("duplicate"):
            broken = pd.concat([source, source.iloc[[0]]], ignore_index=True)
            with self.assertRaisesRegex(ValueError, "중복"):
                build_monthly_relationship_axes(broken)
        with self.subTest("incomplete"):
            monthly = build_monthly_relationship_axes(source.iloc[:-1])
            with self.assertRaisesRegex(ValueError, "12개월"):
                summarize_relationship_window(monthly, "2023-01", "2023-12")
```

- [ ] **Step 2: Run focused tests and verify RED**

Run: `python -m unittest tests.test_relationship_segments.RelationshipLevelTests`

Expected: import failure because `src.segmentation.relationship_segments` does not exist.

- [ ] **Step 3: Implement configuration, validation, axes, and window summary**

```python
@dataclass(frozen=True)
class SegmentationConfig:
    customer_id_col: str = "법인ID"
    month_col: str = "기준년월"
    activity_cols: tuple[str, ...] = (
        "요구불입금금액", "요구불출금금액", "창구거래금액",
        "인터넷뱅킹거래금액", "스마트뱅킹거래금액",
        "폰뱅킹거래금액", "ATM거래금액",
        "신용카드사용금액", "체크카드사용금액",
    )
    deposit_cols: tuple[str, ...] = (
        "요구불예금잔액", "거치식예금잔액", "적립식예금잔액",
        "수익증권잔액", "신탁잔액", "퇴직연금잔액",
    )
    loan_cols: tuple[str, ...] = (
        "여신_운전자금대출잔액",
        "여신_시설자금대출잔액",
    )

def build_monthly_relationship_axes(frame, config=None):
    config = config or SegmentationConfig()
    work = validate_segmentation_source(frame, config)
    for output, columns in config.axis_columns.items():
        work[output] = work.loc[:, columns].sum(axis=1, min_count=len(columns))
    return work

def summarize_relationship_window(monthly, start, end, config=None):
    config = config or SegmentationConfig()
    start_period = pd.Period(start, freq="M")
    end_period = pd.Period(end, freq="M")
    expected = pd.period_range(start_period, end_period, freq="M")
    if len(expected) != 12:
        raise ValueError("관계수준 요약 구간은 정확히 12개월이어야 합니다.")
    work = monthly.loc[monthly[config.month_col].between(start_period, end_period)].copy()
    counts = work.groupby(config.customer_id_col)[config.month_col].nunique()
    if not counts.eq(12).all():
        raise ValueError("법인별 12개월이 모두 필요합니다.")
    for amount_col, level_col in config.amount_level_pairs:
        work[level_col] = np.log1p(work[amount_col])
    return work.groupby(config.customer_id_col, as_index=False)[config.level_columns].median()
```

- [ ] **Step 4: Run focused tests and verify GREEN**

Run: `python -m unittest tests.test_relationship_segments.RelationshipLevelTests`

Expected: all tests in `RelationshipLevelTests` pass.

- [ ] **Step 5: Commit the tested relationship-level layer**

```bash
git add src/segmentation/__init__.py src/segmentation/relationship_segments.py tests/test_relationship_segments.py
git commit -m "feat: build relationship segmentation axes"
```

---

### Task 2: Frozen Percentiles And L30_H70_M15

**Files:**
- Modify: `src/segmentation/relationship_segments.py`
- Modify: `tests/test_relationship_segments.py`

**Interfaces:**
- Consumes: 법인별 관계수준 DataFrame
- Produces: `fit_reference_scores(levels, config)`, `score_against_reference(levels, reference, config)`, `assign_l30_h70_m15(scored, config)`, `build_segment_profile(assignments)`

- [ ] **Step 1: Write failing percentile and rule tests**

```python
class SegmentRuleTests(unittest.TestCase):
    def test_reference_scores_use_average_percentile_for_ties(self):
        levels = level_frame(activity=[0, 0, 10, 20], deposit=[0, 1, 2, 3], loan=[0, 1, 2, 3])
        scored, reference = fit_reference_scores(levels)
        self.assertEqual(scored["거래활동점수"].tolist(), [0.375, 0.375, 0.75, 1.0])
        rescored = score_against_reference(levels, reference)
        pd.testing.assert_series_equal(
            scored["거래활동점수"],
            rescored["거래활동점수"],
            check_names=False,
        )

    def test_future_scores_use_frozen_reference_distribution(self):
        reference_levels = level_frame(activity=[1, 2, 3, 4], deposit=[1, 2, 3, 4], loan=[1, 2, 3, 4])
        _, reference = fit_reference_scores(reference_levels)
        future = level_frame(activity=[0, 2.5, 5], deposit=[0, 2.5, 5], loan=[0, 2.5, 5])
        scored = score_against_reference(future, reference)
        self.assertEqual(scored["거래활동점수"].tolist(), [0.0, 0.5, 1.0])

    def test_assigns_all_six_segments_with_priority_and_inclusive_edges(self):
        scored = score_frame([
            (0.30, 0.30, 0.30),
            (0.85, 0.70, 0.10),
            (0.65, 0.40, 0.20),
            (0.20, 0.55, 0.40),
            (0.20, 0.35, 0.50),
            (0.50, 0.40, 0.35),
        ])
        result = assign_l30_h70_m15(scored)
        self.assertEqual(result["관계세그먼트"].tolist(), [
            "저관계",
            "복합고관계",
            "거래활동중심",
            "수신중심",
            "여신중심",
            "균형·중간관계",
        ])
```

- [ ] **Step 2: Run rule tests and verify RED**

Run: `python -m unittest tests.test_relationship_segments.SegmentRuleTests`

Expected: import failure for the new scoring and assignment functions.

- [ ] **Step 3: Implement frozen scoring and rule priority**

```python
def fit_reference_scores(levels, config=None):
    scored = levels.copy()
    for level_col, score_col in config.level_score_pairs:
        scored[score_col] = scored[level_col].rank(method="average", pct=True)
    reference = levels[[config.customer_id_col, *config.level_columns]].copy()
    return scored, reference

def assign_l30_h70_m15(scored, config=None):
    config = config or SegmentationConfig()
    result = scored.copy()
    scores = result.loc[:, config.score_columns]
    low = scores.le(config.low_cut).all(axis=1)
    high = scores.ge(config.high_cut).sum(axis=1).ge(2)
    ordered = np.sort(scores.to_numpy(float), axis=1)
    dominant = ordered[:, -1] - ordered[:, -2] >= config.dominance_margin
    labels = np.full(len(result), "균형·중간관계", dtype=object)
    labels[low.to_numpy()] = "저관계"
    labels[(~low & high).to_numpy()] = "복합고관계"
    remaining = ~(low | high) & dominant
    winners = scores.idxmax(axis=1).map({
        "거래활동점수": "거래활동중심",
        "수신관계점수": "수신중심",
        "여신관계점수": "여신중심",
    })
    labels[remaining.to_numpy()] = winners.loc[remaining]
    result["관계세그먼트"] = labels
    return result
```

- [ ] **Step 4: Run rule tests and full suite**

Run: `python -m unittest tests.test_relationship_segments.SegmentRuleTests`

Expected: all rule tests pass.

Run: `python -m unittest discover -s tests`

Expected: the full suite passes.

- [ ] **Step 5: Commit the tested scoring layer**

```bash
git add src/segmentation/relationship_segments.py tests/test_relationship_segments.py
git commit -m "feat: assign frozen relationship segments"
```

---

### Task 3: Stability Metrics And Runner

**Files:**
- Modify: `src/segmentation/relationship_segments.py`
- Create: `src/segmentation/run_relationship_segments.py`
- Modify: `tests/test_relationship_segments.py`

**Interfaces:**
- Consumes: 2023 reference assignments, 2024 assignments, input CSV path
- Produces: `build_segment_stability(reference_assignments, comparison_assignments)`, `run_relationship_segmentation(input_path, output_dir)` and six CSV artifacts

- [ ] **Step 1: Write failing stability and runner contract tests**

```python
class RunnerTests(unittest.TestCase):
    def test_stability_contains_overall_and_segment_metrics(self):
        reference = assignment_frame(["저관계", "저관계", "수신중심", "수신중심"])
        comparison = assignment_frame(["저관계", "수신중심", "수신중심", "수신중심"])
        stability = build_segment_stability(reference, comparison)
        overall = stability.loc[stability["구분"].eq("전체")].iloc[0]
        self.assertEqual(overall["동일세그먼트유지율"], 0.75)
        self.assertIn("ARI", stability.columns)

    def test_runner_writes_six_auditable_csv_files(self):
        source = make_monthly_source(customer_ids=["A", "B", "C"], years=(2023, 2024, 2025))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path = root / "source.csv"
            source.to_csv(input_path, index=False)
            paths = run_relationship_segmentation(input_path, root / "outputs")
            self.assertEqual(len(paths), 6)
            self.assertTrue(all(path.exists() for path in paths.values()))
```

- [ ] **Step 2: Run runner tests and verify RED**

Run: `python -m unittest tests.test_relationship_segments.RunnerTests`

Expected: import failure for stability and runner functions.

- [ ] **Step 3: Implement stability metrics and thin runner**

```python
def run_relationship_segmentation(input_path: Path, output_dir: Path) -> dict[str, Path]:
    config = SegmentationConfig()
    source = pd.read_csv(input_path, usecols=config.required_columns)
    monthly = build_monthly_relationship_axes(source, config)
    levels_2023 = summarize_relationship_window(monthly, "2023-01", "2023-12", config)
    scored_2023, reference = fit_reference_scores(levels_2023, config)
    assigned_2023 = assign_l30_h70_m15(scored_2023, config)
    levels_2024 = summarize_relationship_window(monthly, "2024-01", "2024-12", config)
    assigned_2024 = assign_l30_h70_m15(score_against_reference(levels_2024, reference, config), config)
    tables = {
        "reference_2023": reference,
        "assignments_2023": assigned_2023,
        "profile_2023": build_segment_profile(assigned_2023),
        "assignments_2024": assigned_2024,
        "profile_2024": build_segment_profile(assigned_2024),
        "stability_2023_2024": build_segment_stability(assigned_2023, assigned_2024),
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {}
    for name, table in tables.items():
        path = output_dir / f"relationship_segment_{name}.csv"
        table.to_csv(path, index=False, encoding="utf-8-sig")
        paths[name] = path
    return paths
```

- [ ] **Step 4: Run runner tests and full suite**

Run: `python -m unittest tests.test_relationship_segments.RunnerTests`

Expected: all runner tests pass.

Run: `python -m unittest discover -s tests`

Expected: the full suite passes.

- [ ] **Step 5: Commit the runner**

```bash
git add src/segmentation/relationship_segments.py src/segmentation/run_relationship_segments.py tests/test_relationship_segments.py
git commit -m "feat: add relationship segmentation runner"
```

---

### Task 4: Real-Data Reproduction And Documentation

**Files:**
- Create: `outputs/relationship_segments/*`
- Modify: `README.md`
- Modify: `segmentation_final_report.md`

**Interfaces:**
- Consumes: 실제 2026 교육용 법인 익명 CSV
- Produces: 보고서 기대값과의 재현 차이표 및 재실행 명령

- [ ] **Step 1: Run the segmentation pipeline on the real source**

Run:

```bash
python -m src.segmentation.run_relationship_segments \
  --input "/Users/gggyyu/Desktop/(아이엠뱅크) 2026 교육용 데이터/(iM뱅크) 2026 교육용 법인 익명데이터.csv" \
  --output-dir outputs/relationship_segments
```

Expected: six CSV artifacts are created for 3,372 customers.

- [ ] **Step 2: Compare locked report counts and stability values**

Run: a read-only pandas assertion script that checks customer count, six segment labels, profile shares summing to one, and reports absolute differences from the locked counts and 2024 metrics.

Expected: exact matches are recorded as reproduced; mismatches trigger a calculation audit before any documentation claim.

- [ ] **Step 3: Document the reproducible runner and actual results**

Add the exact CLI, output paths, percentile tie contract, actual 2023 segment counts, and actual 2024 stability metrics to `segmentation_final_report.md` and link the runner from `README.md`.

- [ ] **Step 4: Verify the finished implementation**

Run: `git diff --check`

Expected: no output.

Run: `python -m compileall -q src tests`

Expected: exit code 0.

Run: `python -m unittest discover -s tests`

Expected: all tests pass.

- [ ] **Step 5: Commit verified reproduction and docs**

```bash
git add README.md segmentation_final_report.md docs/superpowers/plans/2026-07-13-rule-based-relationship-segmentation.md
git commit -m "docs: record relationship segment reproduction"
```
