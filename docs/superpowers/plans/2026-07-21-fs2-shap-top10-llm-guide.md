# FS2 SHAP Top 10 LLM Guide Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Align the AI strategy report guide, Gemini prompt, and narrative postprocessing with the 56-feature `FS2_R1_DACK_DYNAMIC` model and its customer-level Local SHAP Top 10.

**Architecture:** Add a focused SHAP report-rules module that owns the 56-feature contract, feature-to-RM translations, Top 10 validation, and grouped summaries. `gemini_service.py` will enrich the authoritative context with that deterministic evidence before generation and will validate/normalize the returned narrative without changing the existing API, UI, or PDF schema.

**Tech Stack:** Python 3.10, Pydantic v2, FastAPI, google-genai, pytest, Markdown

## Global Constraints

- The model feature set is exactly `FS2_R1_DACK_DYNAMIC`: 16 R1 features plus 40 D/A/C/K dynamic features.
- Industry, region, customer grade, and dedicated-RM fields are context only and are not model features.
- Preserve every available Local SHAP Top 10 item in rank order in the Gemini evidence, API response, UI, and PDF table.
- Combine related features only in narrative guidance and grouped summaries; never delete or rewrite the authoritative SHAP rows.
- Positive SHAP means risk-up, negative SHAP means risk-down, and zero means neutral.
- SHAP is raw-margin model contribution, not probability change or causality.
- `CLV_Risk` and `PotentialLoss` are scenario metrics, not confirmed accounting losses.
- Keep the existing `GeminiNarrative` and `GeneratedReport` public response schemas.
- Preserve unrelated user changes in the dirty worktree.

---

### Task 1: Deterministic FS2 feature and SHAP Top 10 rules

**Files:**
- Create: `src/backend/shap_report_rules.py`
- Create: `tests/test_shap_report_rules.py`

**Interfaces:**
- Produces: `FS2_FEATURES: tuple[str, ...]` containing exactly 56 unique names.
- Produces: `prepare_shap_report_evidence(shap_factors: list[dict]) -> dict`.
- Returned evidence contains `featureSet`, `localShapTop10`, and `groupedSignals`.

- [ ] **Step 1: Write failing tests for the 56-feature contract and old categorical rejection**

```python
import pytest

from src.backend.shap_report_rules import FS2_FEATURES, prepare_shap_report_evidence


def factor(feature, impact, rank, feature_value=None):
    return {
        "feature": feature,
        "featureValue": feature_value,
        "impact": impact,
        "rank": rank,
    }


def test_fs2_contract_has_16_base_and_40_dynamic_features():
    assert len(FS2_FEATURES) == 56
    assert len(set(FS2_FEATURES)) == 56
    assert "핵심거래_수준" in FS2_FEATURES
    assert "카드_현재월대직전6_로그차이" in FS2_FEATURES
    assert not any(name.startswith("CAT_") for name in FS2_FEATURES)


def test_prepare_shap_evidence_rejects_retired_categorical_feature():
    with pytest.raises(ValueError, match="FS2_R1_DACK_DYNAMIC"):
        prepare_shap_report_evidence([factor("CAT_사업장_시도_서울", 0.3, 1)])
```

- [ ] **Step 2: Run tests and verify RED**

Run: `conda run -n final python -m pytest tests/test_shap_report_rules.py -q`

Expected: FAIL because `src.backend.shap_report_rules` does not exist.

- [ ] **Step 3: Implement the exact 56-feature registry and feature translation**

```python
R1_FEATURES = (
    "핵심거래_수준", "수신자산_수준", "여신관계_수준",
    "수신상품_활성폭", "여신세부상품_활성폭", "채널_활성폭",
    "관계영역_활성폭", "수신_요구불대기타_로그균형",
    "여신_운전대시설_로그균형", "핵심거래_입출금대채널_평균비중",
    "채널_비대면대창구_로그균형", "수신좌수_강도",
    "여신부모좌수_강도", "신용카드개수_강도",
    "자동이체건수_강도", "카드_활성률",
)
AXES = ("요구불", "자동이체", "채널", "카드")
DYNAMIC_SUFFIXES = (
    "최근3대직전3_로그차이", "최근3대이전9_로그차이",
    "H2대H1_로그차이", "로그변동성", "TheilSen_추세",
    "최근3대이전9_활성률차이", "월간50퍼감소횟수",
    "월간감소율", "최대연속비활성개월", "현재월대직전6_로그차이",
)
FS2_FEATURES = R1_FEATURES + tuple(
    f"{axis}_{suffix}" for axis in AXES for suffix in DYNAMIC_SUFFIXES
)
```

Add explicit base-feature group mappings, dynamic-axis mappings, and suffix meanings from the approved design. Reject names outside `FS2_FEATURES`; do not infer arbitrary prefixes.

- [ ] **Step 4: Write failing tests for Top 10 validation, direction, shares, and grouping**

```python
def test_prepare_shap_evidence_preserves_all_items_and_groups_same_axis():
    factors = [
        factor("요구불_TheilSen_추세", 0.6, 1, -0.2),
        factor("요구불_최근3대이전9_로그차이", 0.3, 2, -0.4),
        factor("여신관계_수준", -0.1, 3, 2.0),
    ]
    result = prepare_shap_report_evidence(factors)

    assert [item["rank"] for item in result["localShapTop10"]] == [1, 2, 3]
    assert [item["direction"] for item in result["localShapTop10"]] == [
        "risk_up", "risk_up", "risk_down"
    ]
    assert sum(item["top10AbsShare"] for item in result["localShapTop10"]) == pytest.approx(1)
    demand = next(group for group in result["groupedSignals"] if group["group"] == "입출금 활동")
    assert demand["includedRanks"] == [1, 2]
    assert demand["signedShap"] == pytest.approx(0.9)
    assert demand["representativeFeatures"] == [
        "요구불_TheilSen_추세", "요구불_최근3대이전9_로그차이"
    ]


@pytest.mark.parametrize("mutation", ["gap", "duplicate", "too_many", "nonfinite"])
def test_prepare_shap_evidence_rejects_invalid_top10(mutation):
    factors = [factor("핵심거래_수준", 0.2, 1)]
    if mutation == "gap":
        factors.append(factor("수신자산_수준", 0.1, 3))
    elif mutation == "duplicate":
        factors.append(factor("수신자산_수준", 0.1, 1))
    elif mutation == "too_many":
        factors = [factor(FS2_FEATURES[index], 0.01, index + 1) for index in range(11)]
    else:
        factors[0]["impact"] = float("inf")
    with pytest.raises(ValueError):
        prepare_shap_report_evidence(factors)
```

- [ ] **Step 5: Run tests and verify RED**

Run: `conda run -n final python -m pytest tests/test_shap_report_rules.py -q`

Expected: feature registry tests pass; evidence tests FAIL because preprocessing is incomplete.

- [ ] **Step 6: Implement minimal Top 10 preprocessing and grouped summaries**

Validate 1–10 items, continuous ranks, finite impacts, and valid FS2 names. Return every original field plus `group`, `direction`, `meaning`, and `top10AbsShare`. Group in first-rank order and return `signedShap`, `absoluteShap`, `top10AbsShare`, `direction`, `includedRanks`, and at most two `representativeFeatures`. Mark a group `mixed` when it contains both positive and negative impacts.

- [ ] **Step 7: Run focused tests and verify GREEN**

Run: `conda run -n final python -m pytest tests/test_shap_report_rules.py -q`

Expected: PASS.

- [ ] **Step 8: Commit the deterministic rules**

```bash
git add src/backend/shap_report_rules.py tests/test_shap_report_rules.py
git commit -m "feat: add FS2 SHAP report rules"
```

### Task 2: Gemini prompt enrichment and narrative safety postprocessing

**Files:**
- Modify: `src/backend/gemini_service.py`
- Modify: `tests/test_gemini_service.py`

**Interfaces:**
- Consumes: `prepare_shap_report_evidence(context["shapFactors"])`.
- Produces: `build_strategy_report_prompt(context)` containing raw Top 10 plus grouped evidence.
- Produces: `postprocess_strategy_narrative(narrative, shap_evidence) -> GeminiNarrative`.

- [ ] **Step 1: Replace synthetic test features with valid FS2 Top 10 and add failing prompt assertions**

Use ten real features in `report_context()` and assert that the call contents contain:

```python
assert '"featureSet": "FS2_R1_DACK_DYNAMIC"' in call["contents"]
assert '"featureCount": 56' in call["contents"]
assert '"rank": 10' in call["contents"]
assert '"groupedSignals"' in call["contents"]
assert "같은 그룹의 유사 피처는 하나의 종합 신호" in call["contents"]
assert "업종·지역·고객등급·전담여부는 모델 피처가 아닙니다" in call["contents"]
```

- [ ] **Step 2: Run the prompt test and verify RED**

Run: `conda run -n final python -m pytest tests/test_gemini_service.py::test_generate_strategy_report_uses_evidence_and_validates_narrative -q`

Expected: FAIL because the prompt does not yet contain FS2 metadata or grouped signals.

- [ ] **Step 3: Enrich a copied context and update the prompt rules**

In `build_strategy_report_prompt`, copy the context, calculate `shapAnalysis`, and serialize the enriched copy:

```python
enriched = deepcopy(context)
enriched["shapAnalysis"] = prepare_shap_report_evidence(enriched["shapFactors"])
evidence = json.dumps(enriched, ensure_ascii=False, allow_nan=False, indent=2)
```

State that all Top 10 items are authoritative, grouped signals prevent repetitive prose, the 56-feature model excludes customer-context categories, raw SHAP is not probability or causality, and absent feature values cannot be guessed.

- [ ] **Step 4: Run the prompt test and verify GREEN**

Run: `conda run -n final python -m pytest tests/test_gemini_service.py::test_generate_strategy_report_uses_evidence_and_validates_narrative -q`

Expected: PASS.

- [ ] **Step 5: Write failing postprocessing tests**

```python
def test_generate_strategy_report_adds_canonical_limitations_once():
    client = fake_client(parsed=valid_narrative())
    result = generate_strategy_report(report_context(), client=client)
    assert result.caveats.count("Y는 실제 해지·부도·확정 휴면이 아닌 지속거래약화 proxy 예측입니다.") == 1
    assert result.caveats.count("SHAP은 인과관계나 확률 변화량이 아닌 모델 예측 기여도입니다.") == 1
    assert result.caveats.count("CLV_Risk와 PotentialLoss는 확정 손실액이 아닌 시나리오 추정치입니다.") == 1


@pytest.mark.parametrize(
    "drivers",
    [
        "SHAP 0.31이므로 위험확률이 31% 증가했습니다.",
        "여신관계_수준은 SHAP이 음수지만 위험점수를 높인 요인입니다.",
    ],
)
def test_generate_strategy_report_rejects_unsafe_shap_claims(drivers):
    payload = valid_narrative()
    payload["weakeningDrivers"] = drivers
    with pytest.raises(ReportGenerationError):
        generate_strategy_report(report_context(), client=fake_client(parsed=payload))
```

- [ ] **Step 6: Run postprocessing tests and verify RED**

Run: `conda run -n final python -m pytest tests/test_gemini_service.py -q`

Expected: FAIL because canonical caveats and unsafe-claim validation are not implemented.

- [ ] **Step 7: Implement bounded narrative postprocessing**

Validate all narrative fields for a SHAP-to-percentage claim. When an exact risk-down feature name appears in a sentence with risk-up wording, or a risk-up feature appears with protective wording, reject it. Normalize fixed event-probability terms such as `해지 확률` to `지속거래약화 가능성`. Replace semantically overlapping limitation entries with the three canonical caveats, preserve up to three unrelated caveats, and return a newly validated `GeminiNarrative` with no more than six caveats.

Call the postprocessor only after provider JSON has passed `GeminiNarrative.model_validate`.

- [ ] **Step 8: Run Gemini tests and verify GREEN**

Run: `conda run -n final python -m pytest tests/test_gemini_service.py -q`

Expected: PASS.

- [ ] **Step 9: Commit Gemini integration**

```bash
git add src/backend/gemini_service.py tests/test_gemini_service.py
git commit -m "feat: ground Gemini reports in FS2 SHAP top 10"
```

### Task 3: Rewrite the operational guide and verify end-to-end contracts

**Files:**
- Modify: `src/SHAP_LLM_REPORT_GUIDE.md`
- Modify: `tests/test_persistent_target_documentation.py`
- Verify: `src/backend/app.py`
- Verify: `src/backend/report_pdf.py`
- Verify: `src/frontend/rm-insight-copilot/src/pages/AiReportPage.jsx`

**Interfaces:**
- Documents: the same 56-feature and Top 10 behavior enforced by `shap_report_rules.py`.
- Preserves: existing generated-report API and all-ten-factor UI/PDF rendering.

- [ ] **Step 1: Add failing documentation contract assertions**

```python
def test_shap_llm_guide_matches_fs2_top10_contract():
    text = Path("src/SHAP_LLM_REPORT_GUIDE.md").read_text(encoding="utf-8")
    assert "FS2_R1_DACK_DYNAMIC" in text
    assert "총 56개" in text
    assert "Local SHAP Top 10" in text
    assert "Top 10 원본" in text
    assert "업종·지역·고객등급·전담여부는 모델 입력이 아니다" in text
    assert "FS1_CAT" not in text
    assert "89개" not in text
    assert "CAT_*" not in text
```

- [ ] **Step 2: Run the documentation test and verify RED**

Run: `conda run -n final python -m pytest tests/test_persistent_target_documentation.py -q`

Expected: FAIL because the guide still describes `FS1_CAT`, 89 variables, and categorical SHAP rules.

- [ ] **Step 3: Rewrite the guide to the implemented contract**

Update the model structure, variable groups, exact Korean dynamic suffix dictionary, preprocessing, prompt JSON example, postprocessing, evaluation checks, and implementation flow. Remove the retired categorical-feature collision section and all claims that the operating model has 89 features. Explicitly distinguish `top10AbsShare` from full-model contribution share and probability change.

- [ ] **Step 4: Run documentation and backend report tests**

Run:

```bash
conda run -n final python -m pytest \
  tests/test_persistent_target_documentation.py \
  tests/test_shap_report_rules.py \
  tests/test_gemini_service.py \
  tests/test_ai_report_schemas.py \
  tests/test_service_api.py \
  tests/test_report_pdf.py -q
```

Expected: PASS.

- [ ] **Step 5: Run the full backend suite and frontend AI report regression**

Run:

```bash
conda run -n final python -m pytest tests -q
cd src/frontend/rm-insight-copilot && npm test -- --run src/pages/AiReportPage.test.jsx
```

Expected: all Python tests pass; the AI report page test confirms the title and all ten SHAP rows remain expanded.

- [ ] **Step 6: Inspect the final diff for scope and stale model terms**

Run:

```bash
git diff --check
rg -n "FS1_CAT|89개|CAT_" src/SHAP_LLM_REPORT_GUIDE.md src/backend/gemini_service.py src/backend/shap_report_rules.py
git status --short
```

Expected: `git diff --check` succeeds; the stale-term search returns no matches; unrelated dirty files remain untouched.

- [ ] **Step 7: Commit guide and contract tests**

```bash
git add src/SHAP_LLM_REPORT_GUIDE.md tests/test_persistent_target_documentation.py
git commit -m "docs: align SHAP LLM guide with FS2 model"
```
