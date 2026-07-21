from copy import deepcopy

import pytest
from pydantic import ValidationError

from src.backend.schemas import GeneratedReport


def valid_generated_report_payload() -> dict:
    return {
        "corporateId": "A",
        "customerName": "에이기업",
        "asOfMonth": "2025-12",
        "generatedAt": "2026-07-21T13:00:00+09:00",
        "metrics": {"risk": 80.0, "clvRisk": 70.0, "potentialLoss": 30.0},
        "shapFactors": [
            {
                "feature": f"feature_{rank}",
                "featureValue": None,
                "impact": rank / 100,
                "rank": rank,
            }
            for rank in range(1, 11)
        ],
        "riskSummary": "지속거래약화 가능성이 높아 조기 점검이 필요합니다.",
        "valueAssessment": "위험 반영 고객가치와 잠재손실 시나리오를 함께 붅니다.",
        "weakeningDrivers": "SHAP 기여도를 기준으로 주요 변화를 확인합니다.",
        "contactStrategy": "RM이 거래 변화의 배경을 우선 확인합니다.",
        "recommendedActions": ["접촉 일정 수립"],
        "caveats": ["확정 손실액이 아닙니다."],
    }


def test_generated_report_accepts_bounded_complete_payload():
    report = GeneratedReport.model_validate(valid_generated_report_payload())

    assert report.corporateId == "A"
    assert len(report.shapFactors) == 10
    assert report.generatedAt.isoformat() == "2026-07-21T13:00:00+09:00"


@pytest.mark.parametrize(
    "mutation",
    [
        "empty_summary",
        "too_many_actions",
        "too_many_caveats",
        "too_many_shap",
        "duplicate_shap_rank",
        "bad_month",
        "out_of_range_risk",
        "nonfinite_metric",
    ],
)
def test_generated_report_rejects_invalid_payload(mutation):
    payload = deepcopy(valid_generated_report_payload())
    if mutation == "empty_summary":
        payload["riskSummary"] = " "
    elif mutation == "too_many_actions":
        payload["recommendedActions"] = ["조치"] * 9
    elif mutation == "too_many_caveats":
        payload["caveats"] = ["유의"] * 7
    elif mutation == "too_many_shap":
        payload["shapFactors"].append(
            {"feature": "feature_11", "featureValue": None, "impact": 0.01, "rank": 11}
        )
    elif mutation == "duplicate_shap_rank":
        payload["shapFactors"][1]["rank"] = 1
    elif mutation == "bad_month":
        payload["asOfMonth"] = "202512"
    elif mutation == "out_of_range_risk":
        payload["metrics"]["risk"] = 100.1
    else:
        payload["metrics"]["potentialLoss"] = float("inf")

    with pytest.raises(ValidationError):
        GeneratedReport.model_validate(payload)
