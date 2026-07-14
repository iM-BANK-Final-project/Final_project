import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

from src.backend import database
from src.backend.database import connect_database, initialize_schema
from src.backend.load_service_database import (
    ServiceSourcePaths,
    _append_dataframe,
    load_service_database,
    main as load_main,
)
from src.segmentation.relationship_segments import SegmentationConfig


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


def test_dataframe_append_stays_in_callers_transaction_and_rolls_back(tmp_path):
    connection = connect_database(tmp_path / "service.sqlite")
    initialize_schema(connection)
    connection.execute("BEGIN")
    connection.execute(
        """
        INSERT INTO import_runs (
            run_id, started_at, status, as_of_month,
            source_manifest_json, row_counts_json
        ) VALUES ('run-1', '2026-07-14T00:00:00+00:00', 'RUNNING',
                  '2025-06', '{}', '{}')
        """
    )
    frame = pd.DataFrame(
        {
            "corporate_id": ["A"],
            "corporate_name": [pd.NA],
            "industry": ["제조업"],
            "region": ["서울"],
            "customer_grade": ["일반"],
            "dedicated_yn": [1],
        }
    )

    _append_dataframe(connection, "customers", frame)

    assert connection.in_transaction is True
    inserted = connection.execute(
        "SELECT corporate_name, dedicated_yn FROM customers WHERE corporate_id='A'"
    ).fetchone()
    assert inserted["corporate_name"] is None
    assert inserted["dedicated_yn"] == 1
    connection.rollback()
    assert connection.execute("SELECT COUNT(*) FROM customers").fetchone()[0] == 0
    assert connection.execute("SELECT COUNT(*) FROM import_runs").fetchone()[0] == 0
    connection.close()


def _write_service_source_csvs(directory: Path) -> ServiceSourcePaths:
    config = SegmentationConfig()
    source_rows = []
    for month_index, month in enumerate(
        pd.period_range("2024-10", "2025-06", freq="M"), start=1
    ):
        row = {
            "법인ID": "A",
            "기준년월": str(month),
            "업종_대분류": "제조업",
            "사업장_시도": "서울",
            "법인_고객등급": "우수",
            "전담고객여부": "Y",
            "상품관계폭": 3,
        }
        row.update({column: float(month_index) for column in config.amount_cols})
        source_rows.append(row)

    frames = {
        "source": pd.DataFrame(source_rows),
        "risk_scores": pd.DataFrame(
            {
                "법인ID": ["A"],
                "기준년월": ["2025-06"],
                "모델": ["LightGBM"],
                "예측확률": [0.8],
            }
        ),
        "segment_panel": pd.DataFrame(
            {
                "법인ID": ["A"],
                "기준년월": ["2025-06"],
                "관계세그먼트": ["복합고관계"],
                "거래활동점수": [0.9],
                "수신관계점수": [0.8],
                "여신관계점수": [0.7],
            }
        ),
        "profitability": pd.DataFrame(
            {
                "법인ID": ["A"],
                "기준월": ["2025-06"],
                "V_FTP_12M": [100.0],
                "V_FTP_12M_방어가치": [30.0],
            }
        ),
        "shap_local": pd.DataFrame(
            {
                "모델": ["LightGBM"],
                "법인ID": ["A"],
                "기준년월": ["2025-06"],
                "feature": ["최근3개월_입출금"],
                "feature_value": [9.0],
                "shap_value": [0.2],
                "abs_shap_rank": [1],
            }
        ),
    }
    paths = {}
    for name, frame in frames.items():
        path = directory / f"{name}.csv"
        frame.to_csv(path, index=False)
        paths[name] = path
    return ServiceSourcePaths(**paths)


def test_load_service_database_builds_atomic_completed_snapshot(tmp_path):
    paths = _write_service_source_csvs(tmp_path)
    db_path = tmp_path / "service.sqlite"

    summary = load_service_database(paths, db_path, as_of_month=None)

    assert summary.status == "COMPLETED"
    assert summary.as_of_month == "2025-06"
    with connect_database(db_path) as connection:
        snapshot = connection.execute(
            "SELECT risk_probability, customer_value_proxy, crm_priority_score "
            "FROM customer_snapshots WHERE corporate_id='A'"
        ).fetchone()
    assert snapshot["crm_priority_score"] == pytest.approx(
        snapshot["risk_probability"] * snapshot["customer_value_proxy"]
    )


def test_load_service_database_records_hashes_paths_and_row_counts(tmp_path):
    paths = _write_service_source_csvs(tmp_path)
    db_path = tmp_path / "service.sqlite"

    summary = load_service_database(paths, db_path, as_of_month="2025-06")

    with connect_database(db_path) as connection:
        import_run = connection.execute(
            "SELECT * FROM import_runs WHERE run_id = ?", (summary.run_id,)
        ).fetchone()
    manifest = json.loads(import_run["source_manifest_json"])
    row_counts = json.loads(import_run["row_counts_json"])
    assert import_run["status"] == "COMPLETED"
    assert import_run["completed_at"] is not None
    assert import_run["error_message"] is None
    assert row_counts == summary.row_counts
    for source_name, source_path in vars(paths).items():
        assert manifest[source_name]["path"] == str(source_path)
        assert manifest[source_name]["sha256"] == hashlib.sha256(
            source_path.read_bytes()
        ).hexdigest()


def test_load_cli_failure_returns_nonzero_and_preserves_previous_database(
    tmp_path, monkeypatch, capsys
):
    paths = _write_service_source_csvs(tmp_path)
    db_path = tmp_path / "service.sqlite"
    db_path.write_bytes(b"known-good")

    def fail_during_insert(*_args, **_kwargs):
        raise RuntimeError("insert failed")

    monkeypatch.setattr(
        "src.backend.load_service_database._append_dataframe", fail_during_insert
    )
    exit_code = load_main(
        [
            "--source",
            str(paths.source),
            "--risk-scores",
            str(paths.risk_scores),
            "--segment-panel",
            str(paths.segment_panel),
            "--profitability",
            str(paths.profitability),
            "--shap-local",
            str(paths.shap_local),
            "--database",
            str(db_path),
            "--as-of-month",
            "2025-06",
        ]
    )

    assert exit_code != 0
    assert "insert failed" in capsys.readouterr().err
    assert db_path.read_bytes() == b"known-good"
    assert not db_path.with_suffix(".sqlite.tmp").exists()


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


def test_atomic_replacement_preserves_swap_error_and_cleans_temporary(
    tmp_path, monkeypatch
):
    target = tmp_path / "service.sqlite"
    temporary = target.with_suffix(".sqlite.tmp")
    target.write_bytes(b"known-good")
    swap_error = OSError("swap failed")

    def fail_replace(path, destination):
        assert path == temporary
        assert destination == target
        raise swap_error

    monkeypatch.setattr(database.Path, "replace", fail_replace)

    with pytest.raises(OSError, match="swap failed") as raised:
        database.replace_database_atomically(target, lambda _connection: None)

    assert raised.value is swap_error
    assert target.read_bytes() == b"known-good"
    assert not temporary.exists()
