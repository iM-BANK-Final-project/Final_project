import pytest

from src.backend import database
from src.backend.database import connect_database, initialize_schema


EXPECTED_TABLES = {
    "customers",
    "risk_scores",
    "segments",
    "profitability",
    "weakening_signals",
    "shap_factors",
    "recommendations",
    "customer_snapshots",
    "monthly_summaries",
    "import_runs",
}


def test_initialize_schema_creates_service_tables(tmp_path):
    connection = connect_database(tmp_path / "service.sqlite")
    initialize_schema(connection)
    names = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
        if not row[0].startswith("sqlite_")
    }
    connection.close()

    assert names == EXPECTED_TABLES


def test_weakening_signal_allows_unknown_change_rate(tmp_path):
    connection = connect_database(tmp_path / "service.sqlite")
    initialize_schema(connection)
    connection.execute(
        """
        INSERT INTO customers (
            corporate_id, industry, region, customer_grade, dedicated_yn
        ) VALUES ('A', '제조업', '서울', '일반', 0)
        """
    )

    connection.execute(
        """
        INSERT INTO weakening_signals (
            corporate_id, as_of_month, signal_type, current_value,
            comparison_value, change_rate, signal_rank
        ) VALUES ('A', '2025-06', '입출금', 0, 0, NULL, 1)
        """
    )
    connection.close()


def test_atomic_replacement_preserves_existing_database_on_failure(tmp_path):
    target = tmp_path / "service.sqlite"
    target.write_bytes(b"known-good")

    def fail_to_populate(_connection):
        raise ValueError("load failed")

    with pytest.raises(ValueError, match="load failed"):
        database.replace_database_atomically(target, fail_to_populate)

    assert target.read_bytes() == b"known-good"
    assert not target.with_suffix(".sqlite.tmp").exists()
