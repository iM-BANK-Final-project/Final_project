# LightGBM Feature Importance And SHAP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 고정 `LightGBM`과 `LightGBM_NoDirect`의 feature importance와 Validation TreeSHAP을 재현 가능한 표·차트로 산출한다.

**Architecture:** 기존 `modeling_panel.csv`을 읽어 현재 시간 분할과 고정 LightGBM 설정을 재사용한다. 두 모델을 Train에만 fit하고 Validation에서 gain/split importance, mean absolute SHAP, mean signed SHAP, beeswarm, 상위 위험 행 local SHAP을 산출한다.

**Tech Stack:** Python 3.9, pandas, numpy, LightGBM 4.6.0, SHAP 0.49.1, matplotlib, unittest

## Global Constraints

- 대상 모델은 `LightGBM`, `LightGBM_NoDirect`만 포함한다.
- Validation은 모델 fit과 파라미터 선택에 사용하지 않는다.
- SHAP은 Validation 8,839행 전체에서 산출한다.
- 업종·지역·등급 안정성은 범위에서 제외한다.

---

### Task 1: Interpretation Tables

**Files:**
- Create: `src/models/persistent_weakening_interpretation.py`
- Test: `tests/test_persistent_weakening_interpretation.py`

- [x] **Step 1:** 두 feature 세트와 두 고정 LightGBM fit 계약을 실패 테스트로 작성한다.
- [x] **Step 2:** gain/split 중요도와 정규화 합 1을 검증하는 테스트를 작성한다.
- [x] **Step 3:** mean absolute SHAP, signed SHAP, local top contribution 계약을 검증한다.
- [x] **Step 4:** 최소 구현으로 테스트를 통과한다.

### Task 2: Runner And Charts

**Files:**
- Create: `src/models/run_persistent_weakening_interpretation.py`
- Modify: `environment.yml`
- Test: `tests/test_persistent_weakening_interpretation.py`

- [x] **Step 1:** 산출물 파일 계약 테스트를 작성하고 RED를 확인한다.
- [x] **Step 2:** `feature_importance.csv`, `shap_global_importance.csv`, `shap_local_top_rows.csv`를 저장한다.
- [x] **Step 3:** gain 상위 15개 비교 차트와 모델별 SHAP beeswarm을 저장한다.
- [x] **Step 4:** `shap==0.49.1`을 환경 의존성에 기록한다.

### Task 3: Real-Data Run And QA

**Files:**
- Create: `outputs/persistent_weakening_interpretation/*`
- Modify: `src/models/model.md`

- [x] **Step 1:** 보정된 `modeling_panel.csv`로 해석 runner를 실행한다.
- [x] **Step 2:** 두 모델의 상위 feature와 SHAP 방향성을 검토한다.
- [x] **Step 3:** PNG를 실제로 렌더링해 라벨·한글·레이아웃을 시각 검증한다.
- [x] **Step 4:** `git diff --check`, `compileall`, 전체 `unittest`를 통과한다.
