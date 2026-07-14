import sqlite3

import pytest
from fastapi.testclient import TestClient

from src.backend.app import create_app
from src.backend.database import connect_database, initialize_schema
from src.backend.repository import ServiceRepository


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
          ('A', '2025-05', .70, '고위험', .60, 100, 30, .42, 2,
           '수신중심', '입출금', '제조업', '서울', 1),
          ('A', '2025-06', .80, '고위험', .75, 110, 35, .60, 1,
           '수신중심', '입출금', '제조업', '서울', 1),
          ('B', '2025-06', .40, '관찰', .50, NULL, NULL, .20, 3,
           '여신중심', '채널', '도소매', '부산', 0),
          ('C', '2025-06', .60, '중위험', .70, 90, 20, .42, 2,
           '복합고관계', '카드', '제조업', '서울', 1);

        INSERT INTO weakening_signals VALUES
          ('A', '2025-06', '입출금', 60, 100, -40, 1),
          ('A', '2025-06', '채널', 80, 100, -20, 2),
          ('B', '2025-06', '채널', 70, 100, -30, 1),
          ('C', '2025-06', '카드', 75, 100, -25, 1);

        INSERT INTO recommendations VALUES
          ('A', '2025-06', '입출금', 'High', '입출금 약화', 'RM 방문',
           '자금관리 상담', '입출금 거래 회복을 우선 상담합니다.'),
          ('B', '2025-06', '채널', 'Watch', '채널 약화', 'RM 전화',
           '디지털채널 점검', '채널 이용 불편을 확인합니다.'),
          ('C', '2025-06', '카드', 'Medium', '카드 약화', 'RM 전화',
           '법인카드 상담', '법인카드 조건을 점검합니다.');

        INSERT INTO shap_factors VALUES
          ('A', '2025-06', 'LightGBM', '최근3개월_입출금', 60, .30, 1),
          ('A', '2025-06', 'LightGBM', '최근3개월_채널', 80, -.20, 2);

        INSERT INTO monthly_summaries VALUES
          ('2025-05', 1, .70, 1.0, .42, '{"입출금": 1}'),
          ('2025-06', 3, .60, .3333333333, 1.22,
           '{"입출금": 1, "채널": 1, "카드": 1}');
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
    assert response.json()["detail"] == "서비스 데이터베이스를 사용할 수 없습니다."


def test_overview_returns_kpis_trend_and_signal_distribution(client):
    response = client.get("/api/overview")

    assert response.status_code == 200
    assert response.json() == {
        "asOfMonth": "2025-06",
        "managedCustomerCount": 3,
        "averageRisk": 60.0,
        "highRiskShare": pytest.approx(33.33333333),
        "priorityValueTotal": 1.22,
        "monthlyTrend": [
            {"month": "2025-05", "risk": 70.0, "managed": 1},
            {"month": "2025-06", "risk": 60.0, "managed": 3},
        ],
        "signalSummary": [
            {"label": "입출금", "value": 1},
            {"label": "채널", "value": 1},
            {"label": "카드", "value": 1},
        ],
    }


def test_overview_accepts_as_of_month(client):
    response = client.get("/api/overview", params={"as_of_month": "2025-05"})

    assert response.status_code == 200
    assert response.json()["asOfMonth"] == "2025-05"
    assert response.json()["monthlyTrend"] == [
        {"month": "2025-05", "risk": 70.0, "managed": 1}
    ]


def test_filter_options_are_distinct_and_frontend_named(client):
    response = client.get("/api/filter-options")

    assert response.status_code == 200
    assert response.json() == {
        "asOfMonth": "2025-06",
        "segments": ["복합고관계", "수신중심", "여신중심"],
        "riskLevels": ["고위험", "관찰", "중위험"],
        "industries": ["도소매", "제조업"],
        "regions": ["부산", "서울"],
        "dedicatedOptions": ["N", "Y"],
        "weakeningTypes": ["입출금", "채널", "카드"],
    }


def test_customers_filters_and_uses_frontend_shape(client):
    response = client.get("/api/customers", params={"segment": "여신중심"})

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert set(("id", "name", "risk", "health", "segment", "signals")) <= set(item)
    assert item["name"] == "B"
    assert item["segment"] == "여신중심"


@pytest.mark.parametrize(
    ("query", "expected_id"),
    [
        ({"search": "에이"}, "A"),
        ({"search": "B"}, "B"),
        ({"segment": "수신중심"}, "A"),
        ({"risk_level": "중위험"}, "C"),
        ({"industry": "도소매"}, "B"),
        ({"region": "부산"}, "B"),
        ({"dedicated": "N"}, "B"),
    ],
)
def test_customers_supports_search_and_every_filter(client, query, expected_id):
    response = client.get("/api/customers", params=query)

    assert response.status_code == 200
    assert [item["id"] for item in response.json()["items"]] == [expected_id]


def test_customers_paginates_and_exposes_scores(client):
    response = client.get(
        "/api/customers",
        params={"page": 2, "page_size": 1, "sort_by": "risk", "sort_order": "desc"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["page"] == 2
    assert body["pageSize"] == 1
    assert body["total"] == 3
    assert body["items"][0] == {
        "id": "C",
        "name": "씨기업",
        "industry": "제조업",
        "region": "서울",
        "dedicated": "Y",
        "segment": "복합고관계",
        "riskLevel": "중위험",
        "risk": 60.0,
        "health": 40.0,
        "valueProxy": 0.7,
        "priorityScore": 0.42,
        "priorityRank": 2,
        "weakeningType": "카드",
        "profitability": 90.0,
        "defenseValue": 20.0,
        "signals": [
            {"label": "카드", "change": -25.0, "recent": 75.0, "previous": 100.0}
        ],
    }


def test_customer_detail_returns_frontend_shape(client):
    response = client.get("/api/customers/A")

    assert response.status_code == 200
    assert response.json()["id"] == "A"
    assert response.json()["signals"][0]["label"] == "입출금"


def test_missing_customer_is_404(client):
    response = client.get("/api/customers/UNKNOWN")

    assert response.status_code == 404


def test_priorities_default_to_rank_order_and_support_all_filters(client):
    response = client.get("/api/priorities")

    assert response.status_code == 200
    assert [item["id"] for item in response.json()["items"]] == ["A", "C", "B"]
    cases = {
        "industry": ("도소매", "B"),
        "region": ("부산", "B"),
        "dedicated": ("N", "B"),
        "weakening_type": ("카드", "C"),
        "segment": ("수신중심", "A"),
    }
    for field, (value, expected_id) in cases.items():
        filtered = client.get("/api/priorities", params={field: value})
        assert filtered.status_code == 200
        assert [item["id"] for item in filtered.json()["items"]] == [expected_id]


def test_recommendations_support_segment_and_weakening_filters(client):
    by_segment = client.get("/api/recommendations", params={"segment": "여신중심"})
    by_type = client.get("/api/recommendations", params={"weakening_type": "카드"})

    assert by_segment.status_code == 200
    assert by_segment.json()["items"] == [
        {
            "id": "B",
            "name": "B",
            "segment": "여신중심",
            "weakeningType": "채널",
            "priority": "Watch",
            "reason": "채널 약화",
            "contact": "RM 전화",
            "action": "디지털채널 점검",
            "summary": "채널 이용 불편을 확인합니다.",
        }
    ]
    assert [item["id"] for item in by_type.json()["items"]] == ["C"]


def test_report_returns_stored_shap_signals_and_recommendation(client):
    response = client.get("/api/reports/A")

    assert response.status_code == 200
    body = response.json()
    assert body["customer"]["id"] == "A"
    assert body["strategySummary"] == "입출금 거래 회복을 우선 상담합니다."
    assert body["shapAvailable"] is True
    assert body["shapFactors"] == [
        {
            "feature": "최근3개월_입출금",
            "featureValue": 60.0,
            "impact": 0.3,
            "rank": 1,
        },
        {
            "feature": "최근3개월_채널",
            "featureValue": 80.0,
            "impact": -0.2,
            "rank": 2,
        },
    ]


def test_report_without_shap_preserves_risk_result(client):
    response = client.get("/api/reports/B")

    assert response.status_code == 200
    assert response.json()["customer"]["risk"] == 40.0
    assert response.json()["shapAvailable"] is False
    assert response.json()["shapFactors"] == []


def test_missing_report_is_404(client):
    response = client.get("/api/reports/UNKNOWN")

    assert response.status_code == 404


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


def test_requested_month_without_snapshot_is_404(client):
    response = client.get("/api/customers/A", params={"as_of_month": "2024-01"})

    assert response.status_code == 404


def test_rejects_malformed_month_and_dedicated_filters(client):
    malformed_month = client.get("/api/overview", params={"as_of_month": "202506"})
    invalid_dedicated = client.get("/api/customers", params={"dedicated": "maybe"})

    assert malformed_month.status_code == 422
    assert invalid_dedicated.status_code == 422
