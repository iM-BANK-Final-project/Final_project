import sqlite3

import pytest
from fastapi.testclient import TestClient

from src.backend.app import create_app
from src.backend.database import connect_database, initialize_schema
from src.backend.gemini_service import ReportGenerationError
from src.backend.report_pdf import PdfGenerationError
from src.backend.repository import ServiceRepository
from src.backend.schemas import GeminiNarrative


@pytest.fixture
def service_database(tmp_path):
    path = tmp_path / "service.sqlite"
    connection = connect_database(path)
    initialize_schema(connection)
    connection.executescript(
        """
        INSERT INTO customers VALUES
          ('A', '에이기업', '제조업', '서울', '우수', 1),
          ('B', NULL, '도소매', '부산', '일반', 0),
          ('C', '씨기업', '제조업', '서울', '최우수', 1);

        INSERT INTO customer_snapshots VALUES
          ('A', '2025-05', .70, 1, 'G1_TOP_1', '상위 1%', 1, 1, .26479401324821045,
           90, 70, 20, 20, 1,
           '복합고관계형', '입출금', '제조업', '서울', 1),
          ('A', '2025-12', .80, 1, 'G1_TOP_1', '상위 1%', 1, 1, .26479401324821045,
           100, 70, 30, 30, 1,
           '복합고관계형', '복합 거래활동', '제조업', '서울', 1),
          ('B', '2025-12', .40, 3, 'G5_REST', '나머지 90%', 5, 1, .26479401324821045,
           -10, -8, -2, 0, NULL,
           '저거래·저수신형', '채널', '도소매', '부산', 0),
          ('C', '2025-12', .60, 2, 'G3_3_TO_5', '상위 3~5%', 3, 1, .26479401324821045,
           90, 75, 15, 15, 2,
           '거래·수신중심형', '카드', '제조업', '서울', 1);

        INSERT INTO weakening_signals VALUES
          ('A', '2025-12', '입출금', 60, 100, -40, 1),
          ('A', '2025-12', '자동이체', 65, 100, -35, 2),
          ('B', '2025-12', '채널', 70, 100, -30, 1),
          ('C', '2025-12', '카드', 75, 100, -25, 1);

        INSERT INTO recommendations VALUES
          ('A', '2025-12', '복합 거래활동', 'HIGH', '복합 약화', 'RM 직접 접촉',
           '관계 회복 상담', '복합 거래활동 회복을 우선 상담합니다.'),
          ('B', '2025-12', '채널', 'WATCH', '채널 약화', 'RM 전화',
           '디지털채널 점검', '채널 이용 불편을 확인합니다.'),
          ('C', '2025-12', '카드', 'MEDIUM', '카드 약화', 'RM 전화',
           '법인카드 상담', '법인카드 조건을 점검합니다.');

        INSERT INTO shap_factors VALUES
          ('A', '2025-12', 'LightGBM_Isotonic', '요구불_TheilSen_추세', NULL, .30, 1),
          ('A', '2025-12', 'LightGBM_Isotonic', '채널_TheilSen_추세', NULL, -.20, 2),
          ('A', '2025-12', 'LightGBM_Isotonic', 'feature_3', NULL, .18, 3),
          ('A', '2025-12', 'LightGBM_Isotonic', 'feature_4', NULL, -.16, 4),
          ('A', '2025-12', 'LightGBM_Isotonic', 'feature_5', NULL, .14, 5),
          ('A', '2025-12', 'LightGBM_Isotonic', 'feature_6', NULL, -.12, 6),
          ('A', '2025-12', 'LightGBM_Isotonic', 'feature_7', NULL, .10, 7),
          ('A', '2025-12', 'LightGBM_Isotonic', 'feature_8', NULL, -.08, 8),
          ('A', '2025-12', 'LightGBM_Isotonic', 'feature_9', NULL, .06, 9),
          ('A', '2025-12', 'LightGBM_Isotonic', 'feature_10', NULL, -.04, 10),
          ('B', '2025-12', 'XGBoost', '최근3개월_채널', 70, .25, 1);

        INSERT INTO monthly_summaries VALUES
          ('2025-05', 1, .70, 1.0, 20, '{"입출금": 1}'),
          ('2025-12', 3, .60, .3333333333, 45,
           '{"복합 거래활동": 1, "채널": 1, "카드": 1}');

        INSERT INTO risk_trends VALUES
          ('2025-07', 3, .50, 1, .3333333333, 'FS2_R1_DACK_DYNAMIC_LIGHTGBM_ISOTONIC'),
          ('2025-08', 3, .52, 1, .3333333333, 'FS2_R1_DACK_DYNAMIC_LIGHTGBM_ISOTONIC'),
          ('2025-09', 3, .54, 1, .3333333333, 'FS2_R1_DACK_DYNAMIC_LIGHTGBM_ISOTONIC'),
          ('2025-10', 3, .56, 1, .3333333333, 'FS2_R1_DACK_DYNAMIC_LIGHTGBM_ISOTONIC'),
          ('2025-11', 3, .58, 1, .3333333333, 'FS2_R1_DACK_DYNAMIC_LIGHTGBM_ISOTONIC'),
          ('2025-12', 3, .60, 1, .3333333333, 'FS2_R1_DACK_DYNAMIC_LIGHTGBM_ISOTONIC');
        """
    )
    connection.commit()
    connection.close()
    return path


@pytest.fixture
def client(service_database):
    repository = ServiceRepository(lambda: connect_database(service_database))
    with TestClient(create_app(repository)) as test_client:
        yield test_client


def generated_narrative() -> GeminiNarrative:
    return GeminiNarrative.model_validate(
        {
            "riskSummary": "조기 점검이 필요합니다.",
            "valueAssessment": "확정 손실이 아닌 시나리오입니다.",
            "weakeningDrivers": "SHAP 예측 기여도를 확인합니다.",
            "contactStrategy": "RM 확인이 필요합니다.",
            "recommendedActions": ["접촉 일정 수립"],
            "caveats": ["해지 확률이 아닙니다."],
        }
    )


@pytest.fixture
def ai_client(service_database):
    repository = ServiceRepository(lambda: connect_database(service_database))
    contexts = []
    rendered_reports = []

    def generate(context):
        contexts.append(context)
        return generated_narrative()

    def render(report):
        rendered_reports.append(report)
        return b"%PDF-1.4\nmock-report"

    with TestClient(
        create_app(repository, report_generator=generate, pdf_renderer=render)
    ) as test_client:
        yield test_client, contexts, rendered_reports


def test_health_reports_available_database(client):
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "available"}


def test_health_reports_missing_database_as_503(tmp_path):
    missing = tmp_path / "missing.sqlite"
    repository = ServiceRepository(lambda: connect_database(missing))

    with TestClient(create_app(repository)) as test_client:
        response = test_client.get("/api/health")

    assert response.status_code == 503


def test_overview_returns_potential_loss_total_and_trend(client):
    response = client.get("/api/overview")

    assert response.status_code == 200
    assert response.json() == {
        "asOfMonth": "2025-12",
        "managedCustomerCount": 3,
        "averageRisk": 60.0,
        "thresholdShare": pytest.approx(33.33333333),
        "potentialLossTotal": 45.0,
        "monthlyTrend": [
            {"month": "2025-07", "risk": 50.0, "thresholdShare": 33.33333333, "thresholdCount": 1, "eligibleCount": 3, "isCurrent": False},
            {"month": "2025-08", "risk": 52.0, "thresholdShare": 33.33333333, "thresholdCount": 1, "eligibleCount": 3, "isCurrent": False},
            {"month": "2025-09", "risk": 54.0, "thresholdShare": 33.33333333, "thresholdCount": 1, "eligibleCount": 3, "isCurrent": False},
            {"month": "2025-10", "risk": 56.0, "thresholdShare": 33.33333333, "thresholdCount": 1, "eligibleCount": 3, "isCurrent": False},
            {"month": "2025-11", "risk": 58.0, "thresholdShare": 33.33333333, "thresholdCount": 1, "eligibleCount": 3, "isCurrent": False},
            {"month": "2025-12", "risk": 60.0, "thresholdShare": 33.33333333, "thresholdCount": 1, "eligibleCount": 3, "isCurrent": True},
        ],
        "signalSummary": [
            {"label": "복합 거래활동", "value": 1},
            {"label": "채널", "value": 1},
            {"label": "카드", "value": 1},
        ],
    }


def test_filter_options_are_distinct_and_frontend_named(client):
    response = client.get("/api/filter-options")

    assert response.status_code == 200
    assert response.json() == {
        "asOfMonth": "2025-12",
        "segments": ["거래·수신중심형", "복합고관계형", "저거래·저수신형"],
        "riskBands": [
            {"value": "G1_TOP_1", "label": "상위 1%", "order": 1},
            {"value": "G3_3_TO_5", "label": "상위 3~5%", "order": 3},
            {"value": "G5_REST", "label": "나머지 90%", "order": 5},
        ],
        "industries": ["도소매", "제조업"],
        "regions": ["부산", "서울"],
        "dedicatedOptions": ["N", "Y"],
        "weakeningTypes": ["복합 거래활동", "채널", "카드"],
    }


def test_customers_expose_only_final_public_value_fields(client):
    response = client.get(
        "/api/customers",
        params={"sort_by": "risk", "sort_order": "desc", "page_size": 1},
    )

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item == {
        "id": "A",
        "name": "에이기업",
        "industry": "제조업",
        "region": "서울",
        "dedicated": "Y",
        "segment": "복합고관계형",
        "riskBand": "G1_TOP_1",
        "riskBandName": "상위 1%",
        "riskBandOrder": 1,
        "riskRank": 1,
        "predictedPositive": True,
        "threshold": pytest.approx(26.479401324821045),
        "risk": 80.0,
        "health": 20.0,
        "clvRisk": 70.0,
        "potentialLoss": 30.0,
        "defenseRank": 1,
        "weakeningType": "복합 거래활동",
        "signals": [
            {"label": "입출금", "change": -40.0, "recent": 60.0, "previous": 100.0},
            {"label": "자동이체", "change": -35.0, "recent": 65.0, "previous": 100.0},
        ],
    }
    assert not {
        "valueProxy",
        "profitability",
        "priorityScore",
        "priorityRank",
        "defenseValue",
    } & set(item)


@pytest.mark.parametrize(
    ("query", "expected_id"),
    [
        ({"search": "에이"}, "A"),
        ({"search": "B"}, "B"),
        ({"segment": "복합고관계형"}, "A"),
        ({"risk_band": "G3_3_TO_5"}, "C"),
        ({"industry": "도소매"}, "B"),
        ({"region": "부산"}, "B"),
        ({"dedicated": "N"}, "B"),
    ],
)
def test_customers_support_search_and_every_filter(client, query, expected_id):
    response = client.get("/api/customers", params=query)

    assert response.status_code == 200
    assert [item["id"] for item in response.json()["items"]] == [expected_id]


def test_priorities_default_to_defense_rank_with_nulls_last(client):
    response = client.get("/api/priorities")

    assert response.status_code == 200
    assert [item["id"] for item in response.json()["items"]] == ["A", "C", "B"]
    assert response.json()["items"][-1]["defenseRank"] is None


def test_priorities_support_final_sort_fields(client):
    by_loss = client.get(
        "/api/priorities",
        params={"sort_by": "potential_loss", "sort_order": "desc"},
    )
    by_clv = client.get(
        "/api/priorities",
        params={"sort_by": "clv_risk", "sort_order": "asc"},
    )

    assert [item["id"] for item in by_loss.json()["items"]] == ["A", "C", "B"]
    assert [item["id"] for item in by_clv.json()["items"]] == ["B", "A", "C"]


def test_recommendations_support_filters_and_defense_order(client):
    response = client.get("/api/recommendations", params={"weakening_type": "카드"})

    assert response.status_code == 200
    assert [item["id"] for item in response.json()["items"]] == ["C"]


def test_recommendations_support_risk_band_filter(client):
    response = client.get(
        "/api/recommendations", params={"risk_band": "G3_3_TO_5"}
    )

    assert response.status_code == 200
    assert [item["id"] for item in response.json()["items"]] == ["C"]


def test_report_returns_nullable_feature_values_and_all_stored_models(client):
    a_response = client.get("/api/reports/A")
    b_response = client.get("/api/reports/B")

    assert a_response.status_code == 200
    assert a_response.json()["shapFactors"][0] == {
        "feature": "요구불_TheilSen_추세",
        "featureValue": None,
        "impact": 0.3,
        "rank": 1,
    }
    assert len(a_response.json()["shapFactors"]) == 10
    assert [
        factor["rank"] for factor in a_response.json()["shapFactors"]
    ] == list(range(1, 11))
    assert b_response.status_code == 200
    assert b_response.json()["shapFactors"] == [
        {
            "feature": "최근3개월_채널",
            "featureValue": 70.0,
            "impact": 0.25,
            "rank": 1,
        }
    ]


def test_generate_report_combines_authoritative_metrics_and_top10(ai_client):
    client, contexts, _rendered_reports = ai_client

    response = client.post(
        "/api/reports/A/generate", params={"as_of_month": "2025-12"}
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["corporateId"] == "A"
    assert payload["customerName"] == "에이기업"
    assert payload["asOfMonth"] == "2025-12"
    assert payload["metrics"] == {
        "risk": 80.0,
        "clvRisk": 70.0,
        "potentialLoss": 30.0,
    }
    assert len(payload["shapFactors"]) == 10
    assert payload["riskSummary"] == "조기 점검이 필요합니다."
    assert contexts[0]["customer"]["id"] == "A"


def test_pdf_endpoint_revalidates_report_and_returns_download(ai_client):
    client, _contexts, rendered_reports = ai_client
    report = client.post(
        "/api/reports/A/generate", params={"as_of_month": "2025-12"}
    ).json()

    response = client.post("/api/reports/A/pdf", json=report)

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert "filename*=UTF-8''" in response.headers["content-disposition"]
    assert response.content.startswith(b"%PDF-")
    assert rendered_reports[0].corporateId == "A"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("corporateId", "B"),
        ("customerName", "변조기업"),
        ("asOfMonth", "2025-05"),
        ("metrics", {"risk": 79.0, "clvRisk": 70.0, "potentialLoss": 30.0}),
    ],
)
def test_pdf_endpoint_rejects_tampered_authoritative_evidence(ai_client, field, value):
    client, _contexts, _rendered_reports = ai_client
    report = client.post(
        "/api/reports/A/generate", params={"as_of_month": "2025-12"}
    ).json()
    report[field] = value

    response = client.post("/api/reports/A/pdf", json=report)

    assert response.status_code == 400
    assert response.json() == {"detail": "보고서 근거 데이터가 현재 고객 데이터와 다릅니다."}


def test_generate_report_returns_404_for_unknown_customer(ai_client):
    client, _contexts, _rendered_reports = ai_client

    response = client.post("/api/reports/UNKNOWN/generate")

    assert response.status_code == 404


def test_generate_report_redacts_provider_failure(service_database):
    repository = ServiceRepository(lambda: connect_database(service_database))

    def fail(_context):
        raise ReportGenerationError("secret provider failure")

    with TestClient(
        create_app(repository, report_generator=fail), raise_server_exceptions=False
    ) as client:
        response = client.post("/api/reports/A/generate")

    assert response.status_code == 502
    assert response.json() == {"detail": "AI 보고서 생성에 실패했습니다."}
    assert "secret" not in response.text


def test_pdf_endpoint_returns_safe_failure(service_database):
    repository = ServiceRepository(lambda: connect_database(service_database))

    def fail(_report):
        raise PdfGenerationError("secret font path")

    with TestClient(
        create_app(
            repository,
            report_generator=lambda _context: generated_narrative(),
            pdf_renderer=fail,
        ),
        raise_server_exceptions=False,
    ) as client:
        report = client.post("/api/reports/A/generate").json()
        response = client.post("/api/reports/A/pdf", json=report)

    assert response.status_code == 500
    assert response.json() == {"detail": "PDF 보고서 생성에 실패했습니다."}
    assert "secret" not in response.text


def test_pdf_endpoint_rejects_invalid_schema(ai_client):
    client, _contexts, _rendered_reports = ai_client

    response = client.post("/api/reports/A/pdf", json={"corporateId": "A"})

    assert response.status_code == 422


def test_cors_preflight_allows_report_post(ai_client):
    client, _contexts, _rendered_reports = ai_client

    response = client.options(
        "/api/reports/A/generate",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
        },
    )

    assert response.status_code == 200
    assert "POST" in response.headers["access-control-allow-methods"]


def test_missing_customer_and_report_are_404(client):
    assert client.get("/api/customers/UNKNOWN").status_code == 404
    assert client.get("/api/reports/UNKNOWN").status_code == 404


@pytest.mark.parametrize(
    ("path", "params"),
    [
        ("/api/customers", {"page_size": 201}),
        ("/api/priorities", {"page_size": 201}),
        ("/api/recommendations", {"page_size": 201}),
        ("/api/customers", {"sort_by": "corporate_id; DROP TABLE customers"}),
        ("/api/priorities", {"sort_by": "unknown"}),
    ],
)
def test_rejects_oversized_pages_and_non_allowlisted_sort_fields(client, path, params):
    response = client.get(path, params=params)

    assert response.status_code == 422


def test_rejects_malformed_month_and_dedicated_filters(client):
    assert client.get("/api/overview", params={"as_of_month": "202512"}).status_code == 422
    assert client.get("/api/customers", params={"dedicated": "maybe"}).status_code == 422


def test_unexpected_error_is_logged_and_redacted(caplog):
    class FailingRepository:
        def overview(self, _as_of_month):
            raise RuntimeError("secret SQL detail")

    with TestClient(
        create_app(FailingRepository()), raise_server_exceptions=False
    ) as failing_client:
        response = failing_client.get("/api/overview")

    assert response.status_code == 500
    assert "secret SQL detail" not in response.text
    assert any("Unexpected RM service error" in record.message for record in caplog.records)


def test_missing_schema_is_503(tmp_path):
    empty = tmp_path / "empty.sqlite"
    sqlite3.connect(empty).close()
    repository = ServiceRepository(lambda: connect_database(empty))

    with TestClient(create_app(repository)) as empty_client:
        response = empty_client.get("/api/health")

    assert response.status_code == 503
