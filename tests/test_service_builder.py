import json

import pandas as pd
import pytest

from src.backend.service_builder import (
    ServiceInputs,
    build_recommendations,
    build_customer_value,
    build_service_tables,
    build_weakening_signals,
    classify_weakening_type,
    normalize_month,
    select_common_month,
)
from src.segmentation.relationship_segments import SegmentationConfig


EXPECTED_ACTIONS = {
    "입출금": "자금관리 상담, CMS, 결제성 거래 점검",
    "채널": "디지털채널 온보딩, 이용 장애·불편 확인",
    "카드": "법인카드 이용조건 점검, 한도·혜택 상담",
    "복합 거래활동": "RM 직접 접촉, 관계 회복 상담",
}


def _source_row(customer_id: str, month: object, scale: float) -> dict[str, object]:
    config = SegmentationConfig()
    row: dict[str, object] = {
        "법인ID": customer_id,
        "기준년월": month,
        "업종_대분류": "제조업",
        "사업장_시도": "서울",
        "법인_고객등급": "일반",
        "전담고객여부": "N",
        "상품관계폭": scale,
    }
    row.update({column: scale for column in config.amount_cols})
    return row


def _inputs() -> ServiceInputs:
    source = pd.DataFrame(
        [
            _source_row("A", "202505", 1.0),
            *[
                _source_row("B", month, 2.0)
                for month in pd.period_range("2024-10", "2025-06", freq="M")
            ],
            *[
                _source_row("C", month, 3.0)
                for month in pd.period_range("2024-10", "2025-06", freq="M")
            ],
        ]
    )
    risk = pd.DataFrame(
        {
            "법인ID": ["A", "B", "C", "A"],
            "기준년월": ["2025-05", "202506", "2025-06", "2025-06"],
            "모델": ["LightGBM", "LightGBM", "LightGBM", "XGBoost"],
            "예측확률": [0.2, 0.8, 0.7, 0.99],
        }
    )
    segment = pd.DataFrame(
        {
            "법인ID": ["A", "B", "C"],
            "기준년월": ["202505", "2025-06", pd.Timestamp("2025-06-01")],
            "관계세그먼트": ["저관계", "수신중심", "복합고관계"],
            "거래활동점수": [0.1, 0.6, 0.9],
            "수신관계점수": [0.1, 0.8, 0.9],
            "여신관계점수": [0.1, 0.4, 0.9],
        }
    )
    profitability = pd.DataFrame(
        {
            "법인ID": ["A", "B", "C"],
            "기준월": ["2025-05", "202506", pd.Period("2025-06", freq="M")],
            "V_FTP_12M": [10.0, 20.0, 30.0],
            "V_FTP_12M_방어가치": [1.0, 2.0, 3.0],
        }
    )
    shap = pd.DataFrame(
        {
            "모델": ["LightGBM", "XGBoost"],
            "법인ID": ["B", "B"],
            "기준년월": ["2025-06", "2025-06"],
            "feature": ["x", "ignored"],
            "feature_value": [1.0, 2.0],
            "shap_value": [0.3, 0.4],
            "abs_shap_rank": [1, 1],
        }
    )
    return ServiceInputs(source, risk, segment, profitability, shap)


def _signal_history() -> pd.DataFrame:
    config = SegmentationConfig()
    axis_columns = {
        "입출금": config.activity_cols[:2],
        "채널": config.activity_cols[2:7],
        "카드": config.activity_cols[7:],
    }
    rows = []
    for customer_id, weakened_axis in (("D", "입출금"), ("H", "채널"), ("K", "카드")):
        for offset, month in enumerate(pd.period_range("2025-01", "2025-09", freq="M")):
            row = {
                "법인ID": customer_id,
                "기준년월": str(month),
                **{column: 0.0 for column in config.activity_cols},
            }
            for axis, columns in axis_columns.items():
                row[columns[0]] = 60.0 if axis == weakened_axis and offset >= 6 else 100.0
            rows.append(row)
    return pd.DataFrame(rows)


def test_normalize_month_accepts_supported_representations():
    values = pd.Series(
        ["202506", "2025-06", pd.Timestamp("2025-06-17"), pd.Period("2025-06")]
    )

    assert normalize_month(values).tolist() == ["2025-06"] * 4


def test_normalize_month_rejects_invalid_values():
    with pytest.raises(ValueError, match="기준월 형식"):
        normalize_month(pd.Series(["2025-13"]))


def test_select_common_month_uses_latest_lightgbm_intersection():
    assert select_common_month(_inputs(), requested=None) == "2025-06"


def test_select_common_month_rejects_unavailable_request_with_available_months():
    with pytest.raises(ValueError, match=r"공통 기준월.*\['2025-05', '2025-06'\]"):
        select_common_month(_inputs(), requested="2025-04")


def test_customer_value_uses_equal_weight_contract():
    source = pd.DataFrame(
        {
            "법인ID": ["A", "B", "C"],
            "수신잔액합계": [0.0, 10.0, 20.0],
            "여신잔액합계": [0.0, 10.0, 20.0],
            "핵심거래활동금액": [0.0, 10.0, 20.0],
            "상품관계폭": [0.0, 10.0, 20.0],
            "법인_고객등급": ["일반", "우수", "최우수"],
            "전담고객여부": ["N", "N", "Y"],
        }
    )

    result = build_customer_value(source).set_index("법인ID")

    assert result.loc["C", "customer_value_proxy"] == pytest.approx(1.0)
    assert result.loc["A", "customer_value_proxy"] == pytest.approx((4 / 3) / 6)
    components = json.loads(result.loc["B", "value_components_json"])
    assert set(components) == {
        "수신점수",
        "여신점수",
        "거래성금액점수",
        "상품관계폭점수",
        "고객등급점수",
        "전담점수",
    }


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda frame: frame.assign(법인_고객등급="미정"), "고객등급"),
        (lambda frame: frame.assign(전담고객여부="UNKNOWN"), "전담고객여부"),
        (lambda frame: frame.drop(columns="상품관계폭"), "필수 구성요소"),
        (lambda frame: frame.assign(수신잔액합계=-1), "원천 금액.*음수"),
    ],
)
def test_customer_value_rejects_contract_violations(mutation, message):
    valid = pd.DataFrame(
        {
            "법인ID": ["A"],
            "수신잔액합계": [1.0],
            "여신잔액합계": [1.0],
            "핵심거래활동금액": [1.0],
            "상품관계폭": [1.0],
            "법인_고객등급": ["일반"],
            "전담고객여부": ["N"],
        }
    )

    with pytest.raises(ValueError, match=message):
        build_customer_value(mutation(valid))


def test_build_service_tables_rejects_duplicate_customer_month():
    inputs = _inputs()
    inputs.source.loc[len(inputs.source)] = inputs.source.iloc[-1]

    with pytest.raises(ValueError, match=r"법인ID\+기준년월 중복"):
        build_service_tables(inputs)


def test_build_service_tables_rejects_invalid_risk_probability():
    inputs = _inputs()
    inputs.risk_scores.loc[1, "예측확률"] = 1.01

    with pytest.raises(ValueError, match="예측확률.*0과 1"):
        build_service_tables(inputs)


@pytest.mark.parametrize(
    ("column", "invalid_value", "message"),
    [
        ("법인_고객등급", "미정", "고객등급 허용값 위반"),
        ("전담고객여부", "UNKNOWN", "전담고객여부 허용값 위반"),
    ],
)
def test_build_service_tables_rejects_invalid_category_in_earlier_source_month(
    column,
    invalid_value,
    message,
):
    inputs = _inputs()
    inputs.source.loc[inputs.source["법인ID"].eq("A"), column] = invalid_value

    with pytest.raises(ValueError, match=message):
        build_service_tables(inputs)


def test_build_service_tables_uses_risk_population_and_contract_names():
    tables = build_service_tables(_inputs())

    assert set(tables) == {
        "customers",
        "risk_scores",
        "segments",
        "profitability",
        "weakening_signals",
        "shap_factors",
        "recommendations",
        "customer_snapshots",
    }
    snapshots = tables["customer_snapshots"].set_index("corporate_id")
    assert snapshots.index.tolist() == ["B", "C"]
    assert snapshots.loc["B", "crm_priority_score"] == pytest.approx(
        snapshots.loc["B", "risk_probability"]
        * snapshots.loc["B", "customer_value_proxy"]
    )
    assert tables["shap_factors"]["model_name"].tolist() == ["LightGBM"]
    assert set(snapshots["weakening_type"]) == {"입출금"}
    assert len(tables["weakening_signals"]) == 6
    assert len(tables["recommendations"]) == 2


def test_profitability_fields_remain_separate_from_customer_value_proxy():
    inputs = _inputs()
    original_tables = build_service_tables(inputs)
    original_snapshots = original_tables["customer_snapshots"].set_index("corporate_id")

    inputs.profitability.loc[inputs.profitability["법인ID"].eq("B"), "V_FTP_12M"] = 9999
    inputs.profitability.loc[
        inputs.profitability["법인ID"].eq("B"), "V_FTP_12M_방어가치"
    ] = 7777
    changed_tables = build_service_tables(inputs)
    changed_snapshots = changed_tables["customer_snapshots"].set_index("corporate_id")
    profitability = changed_tables["profitability"].set_index("corporate_id")

    assert profitability.loc["B", "profitability_value"] == 9999
    assert profitability.loc["B", "defense_value"] == 7777
    assert changed_snapshots.loc["B", "profitability_value"] == 9999
    assert changed_snapshots.loc["B", "defense_value"] == 7777
    assert changed_snapshots.loc["B", "customer_value_proxy"] == pytest.approx(
        original_snapshots.loc["B", "customer_value_proxy"]
    )


def test_absent_shap_produces_empty_factor_records():
    inputs = _inputs()
    inputs.shap_local = inputs.shap_local.iloc[0:0].copy()

    tables = build_service_tables(inputs)

    assert tables["shap_factors"].to_dict("records") == []


def test_weakening_signal_uses_previous_six_and_recent_three_for_each_axis():
    signals = build_weakening_signals(
        _signal_history(), {"D", "H", "K"}, "2025-09"
    ).set_index(["corporate_id", "signal_type"])

    for customer_id, signal_type in (("D", "입출금"), ("H", "채널"), ("K", "카드")):
        signal = signals.loc[(customer_id, signal_type)]
        assert signal["current_value"] == 60.0
        assert signal["comparison_value"] == 100.0
        assert signal["change_rate"] == -40.0
        assert signal["signal_rank"] == 1


def test_weakening_signal_rejects_incomplete_null_and_negative_nine_month_history():
    history = _signal_history()
    incomplete = history.loc[
        ~(
            history["법인ID"].eq("D")
            & history["기준년월"].eq("2025-01")
        )
    ]
    with pytest.raises(ValueError, match="9개월"):
        build_weakening_signals(incomplete, {"D"}, "2025-09")

    missing = history.copy()
    missing.loc[missing.index[0], "요구불입금금액"] = None
    with pytest.raises(ValueError, match="결측"):
        build_weakening_signals(missing, {"D"}, "2025-09")

    negative = history.copy()
    negative.loc[negative.index[0], "요구불입금금액"] = -1
    with pytest.raises(ValueError, match="음수"):
        build_weakening_signals(negative, {"D"}, "2025-09")


def test_weakening_signal_leaves_zero_comparison_change_null_and_ranks_it_last():
    history = _signal_history().loc[lambda frame: frame["법인ID"].eq("D")].copy()
    config = SegmentationConfig()
    history.loc[history["기준년월"].le("2025-06"), config.activity_cols[:2]] = 0.0

    signals = build_weakening_signals(history, {"D"}, "2025-09")
    deposit_signal = signals.loc[signals["signal_type"].eq("입출금")].iloc[0]

    assert pd.isna(deposit_signal["change_rate"])
    assert deposit_signal["signal_rank"] == 3
    assert signals.loc[signals["change_rate"].notna(), "signal_rank"].tolist() == [1, 1]


def test_weakening_type_uses_multi_axis_threshold_then_most_negative_axis():
    signals = pd.DataFrame(
        [
            ("A", "2025-09", "입출금", -25.0),
            ("A", "2025-09", "채널", -20.0),
            ("A", "2025-09", "카드", -10.0),
            ("B", "2025-09", "입출금", -10.0),
            ("B", "2025-09", "채널", -30.0),
            ("B", "2025-09", "카드", -5.0),
            ("C", "2025-09", "입출금", 5.0),
            ("C", "2025-09", "채널", -1.0),
            ("C", "2025-09", "카드", -10.0),
        ],
        columns=["corporate_id", "as_of_month", "signal_type", "change_rate"],
    )

    result = classify_weakening_type(signals).set_index("corporate_id")

    assert result["weakening_type"].to_dict() == {
        "A": "복합 거래활동",
        "B": "채널",
        "C": "카드",
    }


def test_weakening_type_marks_all_null_axis_changes_unclassified():
    signals = pd.DataFrame(
        [
            ("A", "2025-09", signal_type, None)
            for signal_type in ("입출금", "채널", "카드")
        ],
        columns=["corporate_id", "as_of_month", "signal_type", "change_rate"],
    )

    result = classify_weakening_type(signals)

    assert result.loc[0, "weakening_type"] == "미분류"


def test_recommendation_uses_approved_actions_and_deterministic_context_copy():
    snapshots = pd.DataFrame(
        {
            "corporate_id": ["A", "B", "C", "D"],
            "as_of_month": ["2025-09"] * 4,
            "risk_probability": [0.75, 0.60, 0.59, 0.90],
            "segment_name": ["수신중심", "거래활동중심", "저관계", "복합고관계"],
        }
    )
    signals = pd.DataFrame(
        [
            (customer_id, "2025-09", signal_type, change_rate)
            for customer_id, signal_type, change_rate in (
                ("A", "입출금", -30.0),
                ("B", "채널", -30.0),
                ("C", "카드", -30.0),
                ("D", "입출금", -30.0),
                ("D", "채널", -25.0),
            )
        ],
        columns=["corporate_id", "as_of_month", "signal_type", "change_rate"],
    )

    recommendations = build_recommendations(snapshots, signals).set_index("corporate_id")

    assert recommendations["recommended_action"].to_dict() == {
        "A": EXPECTED_ACTIONS["입출금"],
        "B": EXPECTED_ACTIONS["채널"],
        "C": EXPECTED_ACTIONS["카드"],
        "D": EXPECTED_ACTIONS["복합 거래활동"],
    }
    assert recommendations["priority_level"].to_dict() == {
        "A": "HIGH",
        "B": "MEDIUM",
        "C": "WATCH",
        "D": "HIGH",
    }
    for customer_id, row in recommendations.iterrows():
        assert row["weakening_type"] in row["reason"]
        assert snapshots.set_index("corporate_id").loc[customer_id, "segment_name"] in row["strategy_summary"]
        assert row["recommended_action"] in row["strategy_summary"]


def test_recommendation_uses_transparent_fallback_when_all_changes_are_null():
    snapshots = pd.DataFrame(
        {
            "corporate_id": ["A"],
            "as_of_month": ["2025-09"],
            "risk_probability": [0.80],
            "segment_name": ["저관계"],
        }
    )
    signals = pd.DataFrame(
        [
            ("A", "2025-09", signal_type, None)
            for signal_type in ("입출금", "채널", "카드")
        ],
        columns=["corporate_id", "as_of_month", "signal_type", "change_rate"],
    )

    recommendation = build_recommendations(snapshots, signals).iloc[0]

    assert recommendation["weakening_type"] == "미분류"
    assert recommendation["contact_strategy"] == "RM 확인"
    assert recommendation["recommended_action"] == "거래이력 확인 후 RM 판단"
    assert "비교 분모를 산출할 수 없어" in recommendation["reason"]
    assert "약화 원인을 판단하지 않았습니다" in recommendation["reason"]
    assert "비교 분모를 산출할 수 없어" in recommendation["strategy_summary"]
    assert "약화 원인을 판단하지 않았습니다" in recommendation["strategy_summary"]
