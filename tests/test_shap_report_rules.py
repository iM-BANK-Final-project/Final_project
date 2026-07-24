import pytest

from src.backend.shap_report_rules import (
    FEATURE_COUNT,
    FEATURE_SET,
    prepare_shap_report_evidence,
)


def factor(feature, impact, rank, feature_value=None):
    return {
        "feature": feature,
        "featureValue": feature_value,
        "impact": impact,
        "rank": rank,
    }


def test_final_contract_reports_164_feature_set():
    assert FEATURE_SET == "FS_FINAL_164_TUNED"
    assert FEATURE_COUNT == 164


@pytest.mark.parametrize(
    "feature",
    ["CTX__업종_대분류__현재", "SEG__current_segment", "UNKNOWN__feature"],
)
def test_prepare_shap_evidence_rejects_context_segment_and_unknown_feature(feature):
    with pytest.raises(ValueError, match="FS_FINAL_164_TUNED"):
        prepare_shap_report_evidence([factor(feature, 0.3, 1)])


def test_prepare_shap_evidence_reports_exact_feature_count():
    result = prepare_shap_report_evidence([factor("핵심거래_수준", 0.2, 1)])

    assert result["featureCount"] == 164


def test_prepare_shap_evidence_preserves_all_items_and_groups_same_axis():
    factors = [
        factor("DACK__D__TheilSen추세", 0.6, 1, -0.2),
        factor("EXP_DIFF__D__d1_all_mean", 0.3, 2, -0.4),
        factor("여신관계_수준", -0.1, 3, 2.0),
    ]
    result = prepare_shap_report_evidence(factors)

    assert [item["rank"] for item in result["localShapTop10"]] == [1, 2, 3]
    assert [item["direction"] for item in result["localShapTop10"]] == [
        "risk_up",
        "risk_up",
        "risk_down",
    ]
    assert sum(item["top10AbsShare"] for item in result["localShapTop10"]) == pytest.approx(1)
    demand = next(group for group in result["groupedSignals"] if group["group"] == "입출금 활동")
    assert demand["includedRanks"] == [1, 2]
    assert demand["signedShap"] == pytest.approx(0.9)
    assert demand["representativeFeatures"] == [
        "DACK__D__TheilSen추세",
        "EXP_DIFF__D__d1_all_mean",
    ]


@pytest.mark.parametrize("mutation", ["gap", "duplicate", "too_many", "nonfinite"])
def test_prepare_shap_evidence_rejects_invalid_top10(mutation):
    factors = [factor("핵심거래_수준", 0.2, 1)]
    if mutation == "gap":
        factors.append(factor("수신자산_수준", 0.1, 3))
    elif mutation == "duplicate":
        factors.append(factor("수신자산_수준", 0.1, 1))
    elif mutation == "too_many":
        factors = [
            factor(f"EXP_CROSS__signal_{index}", 0.01, index + 1)
            for index in range(11)
        ]
    else:
        factors[0]["impact"] = float("inf")
    with pytest.raises(ValueError):
        prepare_shap_report_evidence(factors)


def test_prepare_shap_evidence_sorts_ranks_preserves_fields_and_marks_mixed_groups():
    factors = [
        {
            **factor("DACK__D__TheilSen추세", -0.2, 2),
            "source": "stored-shap",
        },
        factor("EXP_PATH__D__recent3_vs_prior9_peak", 0.4, 1),
    ]

    result = prepare_shap_report_evidence(factors)

    assert [item["rank"] for item in result["localShapTop10"]] == [1, 2]
    assert result["localShapTop10"][1]["source"] == "stored-shap"
    assert result["groupedSignals"] == [
        {
            "group": "입출금 활동",
            "signedShap": pytest.approx(0.2),
            "absoluteShap": pytest.approx(0.6),
            "top10AbsShare": pytest.approx(1),
            "direction": "mixed",
            "includedRanks": [1, 2],
            "representativeFeatures": [
                "EXP_PATH__D__recent3_vs_prior9_peak",
                "DACK__D__TheilSen추세",
            ],
        }
    ]


def test_prepare_shap_evidence_handles_zero_impact_without_invalid_shares():
    result = prepare_shap_report_evidence([factor("핵심거래_수준", 0, 1)])

    assert result["localShapTop10"][0]["direction"] == "neutral"
    assert result["localShapTop10"][0]["top10AbsShare"] == 0
    assert result["groupedSignals"][0]["direction"] == "neutral"
    assert result["groupedSignals"][0]["top10AbsShare"] == 0


def test_prepare_shap_evidence_rejects_overflowing_finite_aggregates():
    factors = [
        factor("핵심거래_수준", 1e308, 1),
        factor("수신자산_수준", 1e308, 2),
    ]

    with pytest.raises(ValueError, match="aggregate"):
        prepare_shap_report_evidence(factors)
