import json

import pandas as pd
import pytest

from src.backend.service_builder import (
    ServiceInputs,
    build_customer_value,
    build_service_tables,
    normalize_month,
    select_common_month,
)
from src.segmentation.relationship_segments import SegmentationConfig


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
            _source_row("B", pd.Timestamp("2025-06-20"), 2.0),
            _source_row("C", pd.Period("2025-06", freq="M"), 3.0),
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


def test_build_service_tables_uses_risk_population_and_contract_names():
    tables = build_service_tables(_inputs())

    assert set(tables) == {
        "customers",
        "risk_scores",
        "segments",
        "profitability",
        "shap_factors",
        "customer_snapshots",
    }
    snapshots = tables["customer_snapshots"].set_index("corporate_id")
    assert snapshots.index.tolist() == ["B", "C"]
    assert snapshots.loc["B", "crm_priority_score"] == pytest.approx(
        snapshots.loc["B", "risk_probability"]
        * snapshots.loc["B", "customer_value_proxy"]
    )
    assert tables["shap_factors"]["model_name"].tolist() == ["LightGBM"]
