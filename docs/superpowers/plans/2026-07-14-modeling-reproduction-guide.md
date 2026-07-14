# Modeling Reproduction Guide Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create one Korean Markdown guide that explains and reproduces the complete persistent-weakening modeling work completed so far.

**Architecture:** Build an evidence-backed technical guide from the approved Y documents, current preprocessing/modeling/segmentation code, automated tests, and saved real-data metrics. Keep the final event contract separate from the exploratory rolling target and make every command, file path, sample count, model feature family, and limitation auditable.

**Tech Stack:** Markdown, Python CLI commands, pandas/LightGBM/scikit-learn implementation references, pytest verification.

## Global Constraints

- Create only `docs/modeling_with_segment.md` as the reader-facing deliverable.
- Treat `Y_지속거래약화_3M70` as the approved event label.
- Label `Y_향후3개월_지속거래약화` and all reported model performance as exploratory until the rolling target and time policy are re-approved.
- Do not claim that hyperparameter tuning was performed.
- Do not present small segment-feature differences as a proven generalization improvement.
- Preserve exact code paths, commands, model parameters, row counts, and metrics from inspected artifacts.

---

### Task 1: Write and verify the modeling reproduction guide

**Files:**
- Create: `docs/modeling_with_segment.md`
- Reference: `financial_dormancy.md`
- Reference: `y_setting_pipeline.md`
- Reference: `docs/superpowers/specs/2026-07-13-persistent-transaction-weakening-y-design.md`
- Reference: `src/models/model.md`
- Reference: `src/preprocessing/persistent_transaction_weakening_labels.py`
- Reference: `src/models/persistent_weakening_baseline.py`
- Reference: `src/models/segment_model_ablation.py`
- Reference: `src/segmentation/relationship_segments.py`
- Test: `tests/test_persistent_transaction_weakening_labels.py`
- Test: `tests/test_persistent_weakening_modeling.py`
- Test: `tests/test_segment_model_ablation.py`

**Interfaces:**
- Consumes: approved design documents, executable Python modules, real-data CSV outputs, pytest contracts.
- Produces: `docs/modeling_with_segment.md`, a standalone implementation and interpretation guide.

- [ ] **Step 1: Reconcile definitions, implementation, and saved metrics**

Run:

```bash
rg -n "Y_지속거래약화|Y_향후3개월|TRAIN_START|VALIDATION_START|DIRECT_SIGNAL_FEATURES|build_fixed_lightgbm" \
  financial_dormancy.md y_setting_pipeline.md src tests
```

Expected: the approved event contract, exploratory rolling target, time split constants, direct-signal columns, and fixed model builder are all traceable to active files.

- [ ] **Step 2: Write the complete guide**

Create `docs/modeling_with_segment.md` with these reader-facing sections:

```text
1. 한눈에 보는 현재 상태
2. 전체 데이터 흐름
3. 데이터와 코호트 계약
4. 최종 이벤트 Y
5. 탐색 rolling 예측 target
6. 누수 방지와 시간 분할
7. feature engineering
8. baseline과 NoDirect ablation
9. 관계 세그먼트와 관계축
10. Base/Segment/Axis/Both 비교
11. 고정 하이퍼파라미터
12. 평가 지표와 실데이터 결과
13. feature importance와 SHAP
14. 코드·실행 명령·산출물
15. 재현 및 누수 검증 체크리스트
16. 해석 제한과 다음 순서
```

Include exact formulas, boundary examples, a Mermaid data-flow diagram, parameter tables, result tables, commands, expected counts, and a final implementation checklist.

- [ ] **Step 3: Verify internal consistency and paths**

Run:

```bash
rg -n "TBD|TODO|FIXME|0.2959|75.5%" docs/modeling_with_segment.md
git diff --check
/opt/anaconda3/envs/ml/bin/python -m pytest -q
```

Expected: the placeholder/stale-metric scan returns no matches, `git diff --check` exits 0, and all project tests pass.

- [ ] **Step 4: Audit every documented implementation path**

Run:

```bash
/opt/anaconda3/envs/ml/bin/python -c 'from pathlib import Path; import re; text=Path("docs/modeling_with_segment.md").read_text(); paths=sorted(set(re.findall(r"`((?:src|tests|docs)/[^`]+)`", text))); missing=[p for p in paths if not Path(p).exists()]; print({"documented_paths": len(paths), "missing": missing}); raise SystemExit(bool(missing))'
```

Expected: `missing` is an empty list.

- [ ] **Step 5: Commit the guide**

```bash
git add docs/modeling_with_segment.md docs/superpowers/plans/2026-07-14-modeling-reproduction-guide.md
git commit -m "docs: add end-to-end modeling reproduction guide"
```
