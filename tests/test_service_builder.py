import pandas as pd
import pytest

from src.backend.service_builder import (
    ServiceInputs,
    build_recommendations,
    build_service_tables,
    build_weakening_signals,
    classify_weakening_type,
    normalize_month,
    select_common_month,
)


SIGNAL_COLUMNS = {
    "입출금": ("요구불입금금액", "요구불출금금액"),
    "자동이체": ("자동이체금액",),
    "채널": (
        "창구거래금액",
        "인터넷뱅킹거래금액",
        "스마트뱅킹거래금액",
        "폰뱅킹거래금액",
        "ATM거래금액",
    ),
    "카드": ("신용카드사용금액", "체크카드사용금액"),
}

EXPECTED_ACTIONS = {
    "입출금": "자금관리 상담, CMS, 결제성 거래 점검",
    "자동이체": "자동이체 등록·해지 내역 점검, 결제성 거래 상담",
    "채널": "디지털채널 온보딩, 이용 장애·불편 확인",
    "카드": "법인카드 이용조건 점검, 한도·혜택 상담",
    "복합 거래활동": "RM 직접 접촉, 관계 회복 상담",
}


def _source() -> pd.DataFrame:
    rows = []
    for customer_id, scale in (("A", 1.0), ("B", 2.0), ("C", 3.0)):
        for offset, month in enumerate(pd.period_range("2025-01", "2025-12", freq="M")):
            row = {
                "법인ID": customer_id,
                "기준년월": int(month.strftime("%Y%m")),
                "업종_대분류": "제조업" if customer_id != "C" else "도매 및 소매업",
                "사업장_시도": "대구" if customer_id != "C" else None,
                "법인_고객등급": "우수",
                "전담고객여부": "Y" if customer_id == "B" else "N",
            }
            for columns in SIGNAL_COLUMNS.values():
                for column in columns:
                    row[column] = scale * (100.0 if offset < 9 else 60.0)
            rows.append(row)
    return pd.DataFrame(rows)


def _operating_scores() -> pd.DataFrame:
    score = {
            "법인ID": ["A", "B", "C"],
            "cutoff_month": [202512, 202512, 202512],
            "score_eligible": [False, True, True],
            "SEG__baseline_segment_2023": ["저거래·저수신형", "복합고관계형", "거래·수신중심형"],
            "SEG__current_segment": ["저거래·저수신형", "저거래·저수신형", "거래·수신중심형"],
            "SEG__transition": [
                "저거래·저수신형 → 저거래·저수신형",
                "복합고관계형 → 저거래·저수신형",
                "거래·수신중심형 → 거래·수신중심형",
            ],
            "CTX__업종_대분류__현재": ["제조업", "제조업", "도매 및 소매업"],
            "CTX__업종_중분류__현재": ["전자", "기계", "도매"],
            "risk_probability": [0.9, 0.8, 0.4],
            "risk_rank_eligible": [pd.NA, 1, 2],
            "risk_band": ["OUT_OF_SCOPE", "G1_TOP_1", "G5_REST"],
            "risk_band_name": ["적격 제외", "상위 1%", "나머지 90%"],
            "risk_band_order": [pd.NA, 1, 5],
            "predicted_positive_model_scope": [pd.NA, 1, 1],
            "threshold": [0.26479401324821045] * 3,
            "target_name": ["Y_INTERVENE_M12_v2"] * 3,
            "feature_set": ["FS_FINAL_164_TUNED"] * 3,
            "feature_count": [164] * 3,
            "calibration_method": ["PLATT"] * 3,
            "probability_status": [
                "VALIDATION_PLATT_LOCKED_SERVICE_REESTIMATION_DEFERRED"
            ] * 3,
            "요구불_최근3대이전9_변화율_pct": [-70.0, -40.0, -20.0],
            "자동이체_최근3대이전9_변화율_pct": [-60.0, -35.0, -10.0],
            "채널_최근3대이전9_변화율_pct": [-50.0, -30.0, -5.0],
            "카드_최근3대이전9_변화율_pct": [-40.0, -25.0, 5.0],
        }
    for rank in range(1, 11):
        score[f"shap_top{rank}_feature"] = [f"feature_{rank}"] * 3
        score[f"shap_top{rank}_value"] = [0.11 - rank / 100] * 3
    return pd.DataFrame(score)


def _clv() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "법인ID": ["A", "B", "C"],
            "기준월": ["2025-12"] * 3,
            "risk_probability": [0.9, 0.8, 0.4],
            "CLV_NoRisk": [120.0, 100.0, -10.0],
            "CLV_Risk": [20.0, 70.0, -8.0],
            "PotentialLoss": [100.0, 30.0, -2.0],
            "defense_value": [100.0, 30.0, 0.0],
            "defense_rank": pd.Series([1, 2, pd.NA], dtype="Int64"),
            "수익성월수": [6, 6, 6],
            "수익성기간": ["2025-07~2025-12"] * 3,
            "미래수익성예측사용": [False] * 3,
        }
    )


def _risk_trends() -> pd.DataFrame:
    months = pd.period_range("2025-07", "2025-12", freq="M").astype(str)
    return pd.DataFrame(
        {
            "as_of_month": months,
            "eligible_count": [2] * 6,
            "average_risk": [0.55, 0.54, 0.53, 0.52, 0.51, 0.60],
            "high_risk_count": [2] * 6,
            "high_risk_share": [1.0] * 6,
            "model_name": ["FS_FINAL_164_TUNED_LIGHTGBM_PLATT"] * 6,
        }
    )


def _inputs() -> ServiceInputs:
    return ServiceInputs(_source(), _operating_scores(), _clv(), _risk_trends())


def test_normalize_month_accepts_supported_representations():
    values = pd.Series(
        ["202506", "2025-06", pd.Timestamp("2025-06-17"), pd.Period("2025-06")]
    )

    assert normalize_month(values).tolist() == ["2025-06"] * 4


def test_normalize_month_rejects_invalid_values():
    with pytest.raises(ValueError, match="기준월 형식"):
        normalize_month(pd.Series(["2025-13"]))


def test_select_common_month_uses_final_cutoff():
    assert select_common_month(_inputs(), requested=None) == "2025-12"


def test_select_common_month_rejects_unavailable_request():
    with pytest.raises(ValueError, match="사용 가능 공통 기준월.*2025-12"):
        select_common_month(_inputs(), requested="2025-06")


def test_build_service_tables_filters_ineligible_score_rows_and_removes_proxy_contract():
    tables = build_service_tables(_inputs())

    assert set(tables) == {
        "customers",
        "risk_scores",
        "segments",
        "clv_values",
        "weakening_signals",
        "shap_factors",
        "recommendations",
        "customer_snapshots",
        "monthly_summaries",
        "risk_trends",
    }
    snapshots = tables["customer_snapshots"].set_index("corporate_id")
    assert snapshots.index.tolist() == ["B", "C"]
    assert snapshots.loc["B", "clv_risk"] == 70.0
    assert snapshots.loc["B", "potential_loss"] == 30.0
    assert snapshots.loc["B", "defense_rank"] == 2
    assert snapshots.loc["B", "risk_band"] == "G1_TOP_1"
    assert snapshots.loc["C", "risk_band"] == "G5_REST"
    assert list(tables["risk_scores"].columns) == [
        "corporate_id",
        "as_of_month",
        "model_name",
        "risk_probability",
        "risk_rank",
        "risk_band",
        "risk_band_name",
        "risk_band_order",
        "predicted_positive",
        "threshold",
    ]
    assert pd.isna(snapshots.loc["C", "defense_rank"])
    assert "customer_value_proxy" not in snapshots.columns
    assert "crm_priority_score" not in snapshots.columns
    assert tables["monthly_summaries"].loc[0, "potential_loss_total"] == 30.0
    assert tables["risk_trends"]["as_of_month"].tolist() == [
        "2025-07",
        "2025-08",
        "2025-09",
        "2025-10",
        "2025-11",
        "2025-12",
    ]
    assert tables["risk_trends"].iloc[-1].to_dict() == {
        "as_of_month": "2025-12",
        "eligible_count": 2,
        "average_risk": pytest.approx(0.6),
        "threshold_count": 2,
        "threshold_share": pytest.approx(1.0),
        "model_name": "FS_FINAL_164_TUNED_LIGHTGBM_PLATT",
    }


def test_build_service_tables_rejects_trend_that_does_not_reconcile_with_december():
    inputs = _inputs()
    inputs.risk_trends.loc[5, "average_risk"] = 0.61

    with pytest.raises(ValueError, match="12월 운영 점수와 일치"):
        build_service_tables(inputs)


def test_build_service_tables_uses_final_segments_shap_and_four_axis_signals():
    tables = build_service_tables(_inputs())

    segments = tables["segments"].set_index("corporate_id")
    assert segments.loc["B", "segment_name"] == "저거래·저수신형"
    assert segments.loc["B", "segment_transition"] == "복합고관계형 → 저거래·저수신형"
    shap = tables["shap_factors"]
    assert len(shap) == 20
    assert shap.groupby("corporate_id")["abs_shap_rank"].apply(list).tolist() == [
        list(range(1, 11)),
        list(range(1, 11)),
    ]
    assert shap["feature_value"].isna().all()
    assert set(tables["weakening_signals"]["signal_type"]) == {
        "입출금",
        "자동이체",
        "채널",
        "카드",
    }
    score_change = tables["weakening_signals"].set_index(
        ["corporate_id", "signal_type"]
    ).loc[("B", "자동이체"), "change_rate"]
    assert score_change == -35.0


def test_build_service_tables_rejects_duplicate_source_month():
    inputs = _inputs()
    inputs.source.loc[len(inputs.source)] = inputs.source.iloc[-1]

    with pytest.raises(ValueError, match=r"법인ID\+기준년월 중복"):
        build_service_tables(inputs)


def test_build_service_tables_requires_all_shap_top10_columns():
    inputs = _inputs()
    inputs.operating_scores = inputs.operating_scores.drop(
        columns="shap_top10_value"
    )

    with pytest.raises(ValueError, match="shap_top10_value"):
        build_service_tables(inputs)


def test_build_service_tables_rejects_invalid_probability():
    inputs = _inputs()
    inputs.operating_scores.loc[1, "risk_probability"] = 1.01

    with pytest.raises(ValueError, match="0과 1"):
        build_service_tables(inputs)


def test_build_service_tables_rejects_changed_final_model_contract():
    inputs = _inputs()
    inputs.operating_scores["feature_set"] = "UNEXPECTED"

    with pytest.raises(ValueError, match="feature_set"):
        build_service_tables(inputs)


def test_build_service_tables_rejects_clv_risk_mismatch():
    inputs = _inputs()
    inputs.clv.loc[inputs.clv["법인ID"].eq("B"), "risk_probability"] = 0.7

    with pytest.raises(ValueError, match="위험확률 불일치"):
        build_service_tables(inputs)


def test_build_service_tables_rejects_invalid_current_customer_category():
    inputs = _inputs()
    inputs.source.loc[
        inputs.source["법인ID"].eq("B") & inputs.source["기준년월"].eq(202512),
        "전담고객여부",
    ] = "UNKNOWN"

    with pytest.raises(ValueError, match="전담고객여부"):
        build_service_tables(inputs)


def test_weakening_signal_uses_previous_nine_and_recent_three_for_four_axes():
    signals = build_weakening_signals(_source(), {"B"}, "2025-12").set_index(
        "signal_type"
    )

    assert set(signals.index) == {"입출금", "자동이체", "채널", "카드"}
    for signal_type in signals.index:
        assert signals.loc[signal_type, "current_value"] == 120.0 * len(
            SIGNAL_COLUMNS[signal_type]
        )
        assert signals.loc[signal_type, "comparison_value"] == 200.0 * len(
            SIGNAL_COLUMNS[signal_type]
        )
        assert signals.loc[signal_type, "change_rate"] == -40.0


def test_weakening_signal_rejects_incomplete_twelve_month_history():
    incomplete = _source().loc[
        lambda frame: ~(
            frame["법인ID"].eq("B") & frame["기준년월"].eq(202501)
        )
    ]

    with pytest.raises(ValueError, match="12개월"):
        build_weakening_signals(incomplete, {"B"}, "2025-12")


def test_weakening_type_uses_multi_axis_threshold_then_most_negative_axis():
    signals = pd.DataFrame(
        [
            ("A", "2025-12", "입출금", -25.0),
            ("A", "2025-12", "자동이체", -20.0),
            ("A", "2025-12", "채널", -10.0),
            ("B", "2025-12", "입출금", -10.0),
            ("B", "2025-12", "채널", -30.0),
        ],
        columns=["corporate_id", "as_of_month", "signal_type", "change_rate"],
    )

    result = classify_weakening_type(signals).set_index("corporate_id")

    assert result["weakening_type"].to_dict() == {
        "A": "복합 거래활동",
        "B": "채널",
    }


def test_recommendation_uses_approved_actions_and_context_copy():
    snapshots = pd.DataFrame(
        {
            "corporate_id": ["A", "B", "C", "D", "E"],
            "as_of_month": ["2025-12"] * 5,
            "risk_probability": [0.75, 0.60, 0.59, 0.90, 0.61],
            "risk_band": [
                "G1_TOP_1",
                "G2_1_TO_3",
                "G3_3_TO_5",
                "G4_5_TO_10",
                "G5_REST",
            ],
            "segment_name": ["수신중심", "거래활동중심", "저관계", "복합고관계", "저관계"],
        }
    )
    signals = pd.DataFrame(
        [
            ("A", "입출금", -30.0),
            ("B", "채널", -30.0),
            ("C", "카드", -30.0),
            ("D", "입출금", -30.0),
            ("D", "채널", -25.0),
            ("E", "자동이체", -30.0),
        ],
        columns=["corporate_id", "signal_type", "change_rate"],
    )
    signals["as_of_month"] = "2025-12"

    recommendations = build_recommendations(snapshots, signals).set_index("corporate_id")

    assert recommendations["recommended_action"].to_dict() == {
        "A": EXPECTED_ACTIONS["입출금"],
        "B": EXPECTED_ACTIONS["채널"],
        "C": EXPECTED_ACTIONS["카드"],
        "D": EXPECTED_ACTIONS["복합 거래활동"],
        "E": EXPECTED_ACTIONS["자동이체"],
    }


def test_recommendation_uses_transparent_fallback_when_all_changes_are_null():
    snapshots = pd.DataFrame(
        {
            "corporate_id": ["A"],
            "as_of_month": ["2025-12"],
            "risk_probability": [0.80],
            "risk_band": ["G1_TOP_1"],
            "segment_name": ["저관계"],
        }
    )
    signals = pd.DataFrame(
        [("A", "2025-12", signal_type, None) for signal_type in SIGNAL_COLUMNS],
        columns=["corporate_id", "as_of_month", "signal_type", "change_rate"],
    )

    recommendation = build_recommendations(snapshots, signals).iloc[0]

    assert recommendation["weakening_type"] == "미분류"
    assert recommendation["contact_strategy"] == "RM 확인"
    assert recommendation["recommended_action"] == "거래이력 확인 후 RM 판단"
    assert "약화 원인을 판단하지 않았습니다" in recommendation["strategy_summary"]
