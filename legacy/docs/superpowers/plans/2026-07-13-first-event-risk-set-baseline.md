# First-Event Risk-Set Baseline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 최초 양성 지속거래약화 사건이 발생한 법인의 사건월 이후 기준월을 모델링 위험집단에서 제외하고 기존 3개 베이스라인 성과를 재산출한다.

**Architecture:** `build_modeling_targets` 내에서 법인별 `Y_지속거래약화_3M70=1`인 최초 양성 사건월을 찾고, 기준월이 그 사건월 이상인 행을 생성하지 않는다. 라벨과 feature 정의, 시간 분할, 모델 설정은 변경하지 않고 원천 CSV로 기존 베이스라인만 재실행한다.

**Tech Stack:** Python 3.9, pandas, scikit-learn, unittest

## Global Constraints

- Y는 `Y_지속거래약화_3M70`와 `Y_향후3개월_지속거래약화`의 현재 정의를 유지한다.
- 위험집단은 최초 양성 사건월 직전까지다. 사건월과 이후 기준월은 제외한다.
- Train, purge, validation 구간과 54개 feature는 변경하지 않는다.
- Prevalence, CurrentSignalRule, LogisticRegression만 재실행한다.

---

### Task 1: 최초 양성 사건 위험집단 보정

**Files:**
- Modify: `src/models/persistent_weakening_baseline.py`
- Test: `tests/test_persistent_weakening_modeling.py`

**Interfaces:**
- Consumes: `build_modeling_targets(label_panel: pd.DataFrame) -> pd.DataFrame`
- Produces: 최초 양성 사건월 미만의 기준월만 포함한 모델링 패널

- [x] **Step 1: 실패 테스트 작성**

  최초 양성 사건월이 `2024-05`인 법인의 `2024-05` 및 이후 기준월이 결과에 없고, 사건 전 `2024-02~04`는 남는지 검증한다.

- [x] **Step 2: RED 확인**

  Run: `python -m unittest tests.test_persistent_weakening_modeling.RollingTargetTest.test_excludes_positive_event_month_and_all_later_anchors`

  Expected: FAIL because 사건 이후 기준월이 현재 결과에 남아 있다.

- [x] **Step 3: 최소 구현**

  법인별 최초 `TARGET_COL == 1` 사건월을 구하고 `anchor_month >= first_positive_event_month`인 행을 `build_modeling_targets` 순회에서 건너뛴다.

- [x] **Step 4: GREEN 및 회귀 확인**

  Run: `python -m unittest tests.test_persistent_weakening_modeling`

  Expected: all modeling tests pass.

### Task 2: 실데이터 베이스라인 재산출

**Files:**
- Regenerate: `outputs/persistent_weakening_baseline/modeling_panel.csv`
- Regenerate: `outputs/persistent_weakening_baseline/validation_scores.csv`
- Regenerate: `outputs/persistent_weakening_baseline/validation_metrics.csv`
- Regenerate: `outputs/persistent_weakening_baseline/validation_lift.csv`
- Regenerate: `outputs/persistent_weakening_baseline/segment_diagnostics.csv`

**Interfaces:**
- Consumes: `run_baseline(input_path: Path, output_dir: Path) -> dict[str, Path]`
- Produces: 보정된 위험집단의 3개 베이스라인 점수와 평가표

- [x] **Step 1: 전체 회귀 검증**

  Run: `python -m unittest discover -s tests`

  Expected: all tests pass.

- [x] **Step 2: 원천 CSV 재실행**

  Run: `python -m src.models.run_persistent_weakening_baseline --input '<원천 CSV 절대경로>' --output-dir outputs/persistent_weakening_baseline`

  Expected: five output CSV files are regenerated.

- [x] **Step 3: 결과 검증**

  완전관측 법인 3,372개와 최초 양성 사건 516개를 재확인하고, Train/Validation 행수·양성률·고유 사건 수와 모델별 PR-AUC, Top-K 지표를 이전 결과와 비교한다.

- [x] **Step 4: 최종 검증**

  Run: `git diff --check && python -m compileall -q src tests && python -m unittest discover -s tests`

  Expected: exit code 0 and all tests pass.
