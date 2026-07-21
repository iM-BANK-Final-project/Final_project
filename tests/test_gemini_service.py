from types import SimpleNamespace

import pytest

from src.backend.gemini_service import (
    ReportGenerationError,
    generate_strategy_report,
)


def report_context() -> dict:
    return {
        "customer": {
            "id": "A",
            "name": "에이기업",
            "risk": 80.0,
            "clvRisk": 70.0,
            "potentialLoss": 30.0,
            "signals": [
                {"label": "입출금", "change": -40.0, "recent": 60.0, "previous": 100.0}
            ],
        },
        "recommendation": {
            "contact": "RM 직접 접촉",
            "action": "관계 회복 상담",
            "reason": "복합 약화",
        },
        "strategySummary": "복합 거래활동 회복을 우선 상담합니다.",
        "shapFactors": [
            {
                "feature": f"feature_{rank}",
                "featureValue": None,
                "impact": rank / 100,
                "rank": rank,
            }
            for rank in range(1, 11)
        ],
    }


def valid_narrative() -> dict:
    return {
        "riskSummary": "조기 점검이 필요합니다.",
        "valueAssessment": "확정 손실이 아닌 시나리오입니다.",
        "weakeningDrivers": "SHAP 예측 기여도를 확인합니다.",
        "contactStrategy": "RM 확인이 필요합니다.",
        "recommendedActions": ["접촉 일정 수립"],
        "caveats": ["해지 확률이 아닙니다."],
    }


class FakeModels:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls = []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.response


def fake_client(*, parsed=None, text=None, error=None):
    response = None if error else SimpleNamespace(parsed=parsed, text=text)
    return SimpleNamespace(models=FakeModels(response=response, error=error))


def test_generate_strategy_report_uses_evidence_and_validates_narrative():
    client = fake_client(parsed=valid_narrative())

    result = generate_strategy_report(report_context(), client=client)

    assert result.riskSummary == "조기 점검이 필요합니다."
    call = client.models.calls[0]
    assert call["model"]
    assert "feature_10" in call["contents"]
    assert "PotentialLoss" in call["contents"]
    assert "SHAP은 인과관계가 아닙니다" in call["contents"]
    assert "확정 손실액이 아닙니다" in call["contents"]
    assert call["config"].response_mime_type == "application/json"
    assert call["config"].temperature == 0.2


def test_generate_strategy_report_accepts_json_text_fallback():
    import json

    client = fake_client(parsed=None, text=json.dumps(valid_narrative(), ensure_ascii=False))

    result = generate_strategy_report(report_context(), client=client)

    assert result.contactStrategy == "RM 확인이 필요합니다."


@pytest.mark.parametrize(
    "client",
    [
        fake_client(parsed=None, text=""),
        fake_client(parsed={"riskSummary": "누락"}),
        fake_client(error=RuntimeError("secret provider detail")),
    ],
)
def test_generate_strategy_report_redacts_invalid_or_failed_provider_response(client):
    with pytest.raises(ReportGenerationError, match="AI 보고서 생성에 실패했습니다") as error:
        generate_strategy_report(report_context(), client=client)

    assert "secret provider detail" not in str(error.value)


def test_generate_strategy_report_falls_back_from_vertex_to_api_key(monkeypatch):
    from src.backend import gemini_service

    primary = fake_client(error=RuntimeError("vertex unavailable"))
    fallback = fake_client(parsed=valid_narrative())
    calls = []

    def make_client(force_api_key=False):
        calls.append(force_api_key)
        return fallback if force_api_key else primary

    monkeypatch.setattr(gemini_service, "_make_client", make_client)
    monkeypatch.setattr(gemini_service, "_vertex_enabled", lambda: True)
    monkeypatch.setattr(gemini_service, "GEMINI_API_KEY", "configured")

    result = generate_strategy_report(report_context())

    assert result.riskSummary
    assert calls == [False, True]
