# Direct-Signal Ablation And Fixed LightGBM Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 직접 약화 신호 3개 feature의 영향을 ablation으로 측정하고, 튜닝하지 않은 고정 LightGBM을 동일한 전체/제거 feature 세트에서 비교한다.

**Architecture:** 기존 feature 생성과 시간 분할은 변경하지 않는다. `model_feature_columns`의 결과에서 `현재drop50`, `현재drop50연속개월수`, `YoY_ratio_핵심거래활동금액`만 제외한 ablation feature 목록을 별도로 만든다. Logistic Regression과 고정 LightGBM을 각 feature 세트에 fit하고 기존 validation 행과 지표에서 비교한다.

**Tech Stack:** Python 3.9, pandas, scikit-learn, LightGBM 4.6.0, unittest

## Global Constraints

- Train `2024-02~2024-09`, purge `2024-10~2025-03`, validation `2025-04~2025-06`을 유지한다.
- 최초 양성 사건월과 이후 기준월을 제외한 현재 위험집단을 유지한다.
- FLAML과 validation 기반 하이퍼파라미터 탐색은 하지 않는다.
- 모든 모델은 동일 validation 행을 점수화한다.

---

### Task 1: Ablation Feature Contract

**Files:**
- Modify: `src/models/persistent_weakening_baseline.py`
- Test: `tests/test_persistent_weakening_modeling.py`

**Interfaces:**
- Produces: `ablation_feature_columns(frame: pd.DataFrame) -> list[str]`
- Removes exactly: `현재drop50`, `현재drop50연속개월수`, `YoY_ratio_핵심거래활동금액`

- [x] **Step 1: 제거 목록을 검증하는 실패 테스트를 작성한다.**
- [x] **Step 2: 테스트가 함수 미정의로 실패함을 확인한다.**
- [x] **Step 3: 기존 feature 목록에서 상수 3개만 제외하는 최소 구현을 추가한다.**
- [x] **Step 4: 모델링 테스트로 GREEN을 확인한다.**

### Task 2: Fixed Logistic And LightGBM Variants

**Files:**
- Modify: `src/models/persistent_weakening_baseline.py`
- Modify: `environment.yml`
- Test: `tests/test_persistent_weakening_modeling.py`

**Interfaces:**
- Produces model names: `LogisticRegression`, `LogisticRegression_NoDirect`, `LightGBM`, `LightGBM_NoDirect`
- LightGBM fixed configuration: `n_estimators=300`, `learning_rate=0.03`, `num_leaves=15`, `max_depth=5`, `min_child_samples=100`, `subsample=0.8`, `colsample_bytree=0.8`, `reg_alpha=0.1`, `reg_lambda=1.0`, `class_weight='balanced'`, `random_state=42`, `n_jobs=1`

- [x] **Step 1: 6개 모델 이름과 동일 validation 행 수를 요구하는 실패 테스트를 작성한다.**
- [x] **Step 2: 기존 3개 모델만 반환해 실패함을 확인한다.**
- [x] **Step 3: 두 Logistic과 두 LightGBM을 각 feature 세트에 fit하고 점수를 추가한다.**
- [x] **Step 4: `environment.yml`에 `lightgbm=4.6.0`을 추가한다.**
- [x] **Step 5: 모델링 및 전체 회귀 테스트를 통과한다.**

### Task 3: Real-Data Rerun And Documentation

**Files:**
- Regenerate: `outputs/persistent_weakening_baseline/*.csv`
- Modify: `src/models/model.md`
- Modify: `financial_dormancy.md`

- [x] **Step 1: 원천 CSV로 전체 베이스라인을 재실행한다.**
- [x] **Step 2: 사건 이후 행 0건과 최초 양성 사건 516개를 재확인한다.**
- [x] **Step 3: 6개 모델의 PR-AUC, Top-K, Lead 1·2·3, 현재 무감소 Recall을 비교한다.**
- [x] **Step 4: 실제 결과와 고정 LightGBM 설정을 모델 문서에 기록한다.**
- [x] **Step 5: `git diff --check`, `compileall`, 전체 `unittest`로 최종 검증한다.**
