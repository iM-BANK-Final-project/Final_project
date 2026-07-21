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
                "feature": feature,
                "featureValue": None,
                "impact": (
                    0
                    if rank == 7
                    else -rank / 100 if rank in {2, 3, 4, 6, 8, 10} else rank / 100
                ),
                "rank": rank,
            }
            for rank, feature in enumerate(
                [
                    "핵심거래_수준",
                    "수신자산_수준",
                    "여신관계_수준",
                    "수신상품_활성폭",
                    "여신세부상품_활성폭",
                    "채널_활성폭",
                    "관계영역_활성폭",
                    "요구불_최근3대직전3_로그차이",
                    "자동이체_TheilSen_추세",
                    "카드_현재월대직전6_로그차이",
                ],
                start=1,
            )
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
    assert '"featureSet": "FS2_R1_DACK_DYNAMIC"' in call["contents"]
    assert '"featureCount": 56' in call["contents"]
    assert '"rank": 10' in call["contents"]
    assert '"groupedSignals"' in call["contents"]
    assert "같은 그룹의 유사 피처는 하나의 종합 신호" in call["contents"]
    assert "모든 원시 Top 10 항목을 권위 있는 입력 근거로 검토하세요" in call["contents"]
    assert "각 피처를 개별적으로 모두 언급할 필요는 없습니다" in call["contents"]
    assert "일부만 선택하거나 생략하지 마세요" not in call["contents"]
    assert "업종·지역·고객등급·전담여부는 모델 피처가 아닙니다" in call["contents"]
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


def test_generate_strategy_report_adds_canonical_limitations_once():
    client = fake_client(parsed=valid_narrative())

    result = generate_strategy_report(report_context(), client=client)

    assert (
        result.caveats.count(
            "Y는 실제 해지·부도·확정 휴면이 아닌 지속거래약화 proxy 예측입니다."
        )
        == 1
    )
    assert "해지 확률이 아닙니다." not in result.caveats
    assert "지속거래약화 가능성이 아닙니다." not in result.caveats
    assert (
        result.caveats.count(
            "SHAP은 인과관계나 확률 변화량이 아닌 모델 예측 기여도입니다."
        )
        == 1
    )
    assert (
        result.caveats.count(
            "CLV_Risk와 PotentialLoss는 확정 손실액이 아닌 시나리오 추정치입니다."
        )
        == 1
    )


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


def test_generate_strategy_report_allows_feature_value_without_protective_claim():
    payload = valid_narrative()
    payload["weakeningDrivers"] = "핵심거래_수준은 최근 낮은 수준입니다."

    result = generate_strategy_report(report_context(), client=fake_client(parsed=payload))

    assert result.weakeningDrivers == "핵심거래_수준은 최근 낮은 수준입니다."


def test_generate_strategy_report_allows_correct_mixed_direction_clauses():
    payload = valid_narrative()
    payload["weakeningDrivers"] = (
        "여신관계_수준은 위험점수를 낮춘 요인이나 핵심거래_수준은 리스크를 높인 요인입니다."
    )

    result = generate_strategy_report(report_context(), client=fake_client(parsed=payload))

    assert result.weakeningDrivers == payload["weakeningDrivers"]


@pytest.mark.parametrize(
    "drivers",
    [
        "여신관계_수준은 리스크를 증가시킨 요인입니다.",
        "핵심거래_수준은 위험도를 낮춘 보호 요인입니다.",
        "위험점수를 높인 요인은 여신관계_수준입니다.",
    ],
)
def test_generate_strategy_report_rejects_alternate_conflicting_direction_wording(drivers):
    payload = valid_narrative()
    payload["weakeningDrivers"] = drivers

    with pytest.raises(ReportGenerationError):
        generate_strategy_report(report_context(), client=fake_client(parsed=payload))


@pytest.mark.parametrize(
    "drivers",
    [
        "관계영역_활성폭은 위험도를 높인 요인입니다.",
        "관계영역_활성폭은 리스크를 낮춘 보호 요인입니다.",
    ],
)
def test_generate_strategy_report_rejects_neutral_feature_direction_claims(drivers):
    payload = valid_narrative()
    payload["weakeningDrivers"] = drivers

    with pytest.raises(ReportGenerationError):
        generate_strategy_report(report_context(), client=fake_client(parsed=payload))


def test_generate_strategy_report_allows_independent_risk_percentage_with_shap_description():
    payload = valid_narrative()
    payload["weakeningDrivers"] = (
        "지속거래약화 가능성은 80%이며 SHAP은 모델 예측 기여도입니다."
    )

    result = generate_strategy_report(report_context(), client=fake_client(parsed=payload))

    assert result.weakeningDrivers == payload["weakeningDrivers"]


@pytest.mark.parametrize(
    "drivers",
    [
        "SHAP 0.31이므로 위험도는 3%p 증가했습니다.",
        "SHAP 값 때문에 리스크가 10bp 상승했습니다.",
        "SHAP 0.2만큼 위험점수가 높아졌습니다.",
    ],
)
def test_generate_strategy_report_rejects_shap_linked_probability_changes(drivers):
    payload = valid_narrative()
    payload["weakeningDrivers"] = drivers

    with pytest.raises(ReportGenerationError):
        generate_strategy_report(report_context(), client=fake_client(parsed=payload))


def test_generate_strategy_report_replaces_overlapping_caveats_with_canonical_set():
    payload = valid_narrative()
    payload["caveats"] = [
        "Y는 실제 해지·부도·확정 휴면이 아닌 지속거래약화 proxy 예측입니다.",
        "SHAP은 인과관계나 확률 변화량이 아닌 모델 예측 기여도입니다.",
        "CLV_Risk와 PotentialLoss는 확정 손실액이 아닌 시나리오 추정치입니다.",
        "RM 검토가 필요합니다.",
        "접촉 전 최신 거래를 확인하세요.",
        "정량 근거를 함께 검토하세요.",
    ]

    result = generate_strategy_report(report_context(), client=fake_client(parsed=payload))

    assert len(result.caveats) == 6
    assert result.caveats[:3] == [
        "RM 검토가 필요합니다.",
        "접촉 전 최신 거래를 확인하세요.",
        "정량 근거를 함께 검토하세요.",
    ]
    assert result.caveats[-3:] == [
        "Y는 실제 해지·부도·확정 휴면이 아닌 지속거래약화 proxy 예측입니다.",
        "SHAP은 인과관계나 확률 변화량이 아닌 모델 예측 기여도입니다.",
        "CLV_Risk와 PotentialLoss는 확정 손실액이 아닌 시나리오 추정치입니다.",
    ]
    assert result.valueAssessment == "확정 손실이 아닌 시나리오입니다."
