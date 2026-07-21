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


def test_prepare_shap_evidence_preserves_all_items_and_groups_same_axis():
    factors = [
        factor("요구불_TheilSen_추세", 0.6, 1, -0.2),
        factor("요구불_최근3대이전9_로그차이", 0.3, 2, -0.4),
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
        "요구불_TheilSen_추세",
        "요구불_최근3대이전9_로그차이",
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


def test_prepare_shap_evidence_sorts_ranks_preserves_fields_and_marks_mixed_groups():
    factors = [
        {
            **factor("요구불_TheilSen_추세", -0.2, 2),
            "source": "stored-shap",
        },
        factor("요구불_최근3대직전3_로그차이", 0.4, 1),
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
                "요구불_최근3대직전3_로그차이",
                "요구불_TheilSen_추세",
            ],
        }
    ]


def test_prepare_shap_evidence_handles_zero_impact_without_invalid_shares():
    result = prepare_shap_report_evidence([factor("핵심거래_수준", 0, 1)])

    assert result["localShapTop10"][0]["direction"] == "neutral"
    assert result["localShapTop10"][0]["top10AbsShare"] == 0
    assert result["groupedSignals"][0]["direction"] == "neutral"
    assert result["groupedSignals"][0]["top10AbsShare"] == 0
