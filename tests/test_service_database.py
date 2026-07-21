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


EXPECTED_TABLES = {
    "customers",
    "risk_scores",
    "segments",
    "clv_values",
    "weakening_signals",
    "shap_factors",
    "recommendations",
    "customer_snapshots",
    "monthly_summaries",
    "import_runs",
}


def _table_columns(connection, table_name):
    return [row[1] for row in connection.execute(f"PRAGMA table_info({table_name})")]


def test_dataframe_append_stays_in_callers_transaction_and_rolls_back(tmp_path):
    connection = connect_database(tmp_path / "service.sqlite")
    initialize_schema(connection)
    connection.execute("BEGIN")
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
    connection.close()


def _source_frame() -> pd.DataFrame:
    rows = []
    for offset, month in enumerate(pd.period_range("2025-01", "2025-12", freq="M")):
        rows.append(
            {
                "법인ID": "A",
                "기준년월": str(month),
                "업종_대분류": "제조업",
                "사업장_시도": "서울",
                "법인_고객등급": "우수",
                "전담고객여부": "Y",
                "요구불입금금액": 100.0 if offset < 9 else 60.0,
                "요구불출금금액": 0.0,
                "자동이체금액": 100.0 if offset < 9 else 60.0,
                "창구거래금액": 100.0 if offset < 9 else 60.0,
                "인터넷뱅킹거래금액": 0.0,
                "스마트뱅킹거래금액": 0.0,
                "폰뱅킹거래금액": 0.0,
                "ATM거래금액": 0.0,
                "신용카드사용금액": 100.0 if offset < 9 else 60.0,
                "체크카드사용금액": 0.0,
            }
        )
    return pd.DataFrame(rows)


def _score_frame() -> pd.DataFrame:
    score = {
            "법인ID": ["A"],
            "cutoff_month": [202512],
            "score_eligible": [True],
            "SEG__baseline_segment_2023": ["복합고관계형"],
            "SEG__current_segment": ["저거래·저수신형"],
            "SEG__transition": ["복합고관계형 → 저거래·저수신형"],
            "CTX__업종_대분류__현재": ["제조업"],
            "CTX__업종_중분류__현재": ["기계"],
            "risk_probability": [0.8],
            "요구불_최근3대이전9_변화율_pct": [-40.0],
            "자동이체_최근3대이전9_변화율_pct": [-35.0],
            "채널_최근3대이전9_변화율_pct": [-30.0],
            "카드_최근3대이전9_변화율_pct": [-25.0],
        }
    for rank in range(1, 11):
        score[f"shap_top{rank}_feature"] = [f"feature_{rank}"]
        score[f"shap_top{rank}_value"] = [0.11 - rank / 100]
    return pd.DataFrame(score)


def _clv_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "법인ID": ["A"],
            "기준월": ["2025-12"],
            "risk_probability": [0.8],
            "CLV_NoRisk": [100.0],
            "CLV_Risk": [70.0],
            "PotentialLoss": [30.0],
            "defense_value": [30.0],
            "defense_rank": pd.Series([1], dtype="Int64"),
            "예측월수": [6],
        }
    )


def _write_service_source_csvs(directory: Path) -> ServiceSourcePaths:
    frames = {
        "source": _source_frame(),
        "operating_scores": _score_frame(),
        "clv": _clv_frame(),
    }
    paths = {}
    for name, frame in frames.items():
        path = directory / f"{name}.csv"
        frame.to_csv(path, index=False)
        paths[name] = path
    return ServiceSourcePaths(**paths)


def test_initialize_schema_creates_final_clv_tables_and_columns(tmp_path):
    connection = connect_database(tmp_path / "service.sqlite")
    initialize_schema(connection)
    names = {
        row[0]
        for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        if not row[0].startswith("sqlite_")
    }

    assert names == EXPECTED_TABLES
    assert _table_columns(connection, "clv_values") == [
        "corporate_id",
        "as_of_month",
        "clv_no_risk",
        "clv_risk",
        "potential_loss",
        "defense_value",
        "defense_rank",
    ]
    assert _table_columns(connection, "customer_snapshots") == [
        "corporate_id",
        "as_of_month",
        "risk_probability",
        "risk_level",
        "clv_no_risk",
        "clv_risk",
        "potential_loss",
        "defense_value",
        "defense_rank",
        "segment_name",
        "weakening_type",
        "industry",
        "region",
        "dedicated_yn",
    ]
    assert "potential_loss_total" in _table_columns(connection, "monthly_summaries")
    connection.close()


def test_schema_allows_null_defense_rank_and_shap_feature_value(tmp_path):
    connection = connect_database(tmp_path / "service.sqlite")
    initialize_schema(connection)
    connection.execute(
        "INSERT INTO customers VALUES ('A', NULL, '제조업', '서울', '일반', 0)"
    )
    connection.execute(
        "INSERT INTO shap_factors VALUES "
        "('A', '2025-12', 'LightGBM', 'feature', NULL, .2, 1)"
    )
    connection.execute(
        "INSERT INTO customer_snapshots VALUES "
        "('A', '2025-12', .1, 'WATCH', -10, -8, -2, 0, NULL, "
        "'저거래·저수신형', '카드', '제조업', '서울', 0)"
    )
    connection.commit()
    assert connection.execute(
        "SELECT defense_rank FROM customer_snapshots WHERE corporate_id='A'"
    ).fetchone()[0] is None
    connection.close()


def test_load_service_database_builds_atomic_completed_snapshot(tmp_path):
    paths = _write_service_source_csvs(tmp_path)
    db_path = tmp_path / "service.sqlite"

    summary = load_service_database(paths, db_path, as_of_month=None)

    assert summary.status == "COMPLETED"
    assert summary.as_of_month == "2025-12"
    with connect_database(db_path) as connection:
        snapshot = connection.execute(
            "SELECT clv_risk, potential_loss, defense_rank "
            "FROM customer_snapshots WHERE corporate_id='A'"
        ).fetchone()
        shap_ranks = [
            row[0]
            for row in connection.execute(
                "SELECT abs_shap_rank FROM shap_factors "
                "WHERE corporate_id='A' ORDER BY abs_shap_rank"
            )
        ]
    assert snapshot["clv_risk"] == 70.0
    assert snapshot["potential_loss"] == 30.0
    assert snapshot["defense_rank"] == 1
    assert shap_ranks == list(range(1, 11))


def test_load_service_database_records_hashes_paths_and_row_counts(tmp_path):
    paths = _write_service_source_csvs(tmp_path)
    db_path = tmp_path / "service.sqlite"

    summary = load_service_database(paths, db_path, as_of_month="2025-12")

    with connect_database(db_path) as connection:
        import_run = connection.execute(
            "SELECT * FROM import_runs WHERE run_id = ?", (summary.run_id,)
        ).fetchone()
    manifest = json.loads(import_run["source_manifest_json"])
    row_counts = json.loads(import_run["row_counts_json"])
    assert import_run["status"] == "COMPLETED"
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
            "--operating-scores",
            str(paths.operating_scores),
            "--clv",
            str(paths.clv),
            "--database",
            str(db_path),
            "--as-of-month",
            "2025-12",
        ]
    )

    assert exit_code != 0
    assert "insert failed" in capsys.readouterr().err
    assert db_path.read_bytes() == b"known-good"
    assert not db_path.with_suffix(".sqlite.tmp").exists()


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
