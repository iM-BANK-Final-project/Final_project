"""Atomically load validated analytical artifacts into the RM service database."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
from typing import Sequence
from uuid import uuid4

import pandas as pd

from src.backend.database import replace_database_atomically
from src.backend.service_builder import ServiceInputs, build_service_tables


DEFAULT_DATABASE_PATH = Path("outputs/rm_service/rm_service.sqlite")
SERVICE_TABLE_COLUMNS = {
    "customers": (
        "corporate_id",
        "corporate_name",
        "industry",
        "region",
        "customer_grade",
        "dedicated_yn",
    ),
    "risk_scores": (
        "corporate_id",
        "as_of_month",
        "model_name",
        "risk_probability",
        "risk_level",
    ),
    "segments": (
        "corporate_id",
        "as_of_month",
        "segment_name",
        "activity_score",
        "deposit_score",
        "loan_score",
    ),
    "profitability": (
        "corporate_id",
        "as_of_month",
        "profitability_value",
        "defense_value",
        "customer_value_proxy",
        "value_components_json",
    ),
    "weakening_signals": (
        "corporate_id",
        "as_of_month",
        "signal_type",
        "current_value",
        "comparison_value",
        "change_rate",
        "signal_rank",
    ),
    "shap_factors": (
        "corporate_id",
        "as_of_month",
        "model_name",
        "feature_name",
        "feature_value",
        "shap_value",
        "abs_shap_rank",
    ),
    "recommendations": (
        "corporate_id",
        "as_of_month",
        "weakening_type",
        "priority_level",
        "reason",
        "contact_strategy",
        "recommended_action",
        "strategy_summary",
    ),
    "customer_snapshots": (
        "corporate_id",
        "as_of_month",
        "risk_probability",
        "risk_level",
        "customer_value_proxy",
        "profitability_value",
        "defense_value",
        "crm_priority_score",
        "crm_priority_rank",
        "segment_name",
        "weakening_type",
        "industry",
        "region",
        "dedicated_yn",
    ),
}


@dataclass(frozen=True)
class ServiceSourcePaths:
    """CSV artifact paths required to build a service snapshot."""

    source: Path
    risk_scores: Path
    segment_panel: Path
    profitability: Path
    shap_local: Path


@dataclass(frozen=True)
class LoadSummary:
    """Audit summary for one successful database replacement."""

    run_id: str
    status: str
    as_of_month: str
    row_counts: dict[str, int]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _source_manifest(paths: ServiceSourcePaths) -> dict[str, dict[str, str]]:
    return {
        name: {"path": str(path), "sha256": _sha256(path)}
        for name, path in vars(paths).items()
    }


def _read_inputs(paths: ServiceSourcePaths) -> ServiceInputs:
    return ServiceInputs(
        source=pd.read_csv(paths.source),
        risk_scores=pd.read_csv(paths.risk_scores),
        segment_panel=pd.read_csv(paths.segment_panel),
        profitability=pd.read_csv(paths.profitability),
        shap_local=pd.read_csv(paths.shap_local),
    )


def _sqlite_value(value: object) -> object:
    if pd.isna(value):
        return None
    item = getattr(value, "item", None)
    return item() if item is not None else value


def _append_dataframe(
    connection: sqlite3.Connection,
    table_name: str,
    frame: pd.DataFrame,
) -> None:
    """Append a known service table without committing the caller's transaction."""
    expected_columns = SERVICE_TABLE_COLUMNS.get(table_name)
    if expected_columns is None:
        raise ValueError(f"허용되지 않은 서비스 테이블입니다: {table_name}")
    actual_columns = tuple(frame.columns)
    if actual_columns != expected_columns:
        raise ValueError(
            f"{table_name} 컬럼 계약 위반: "
            f"expected={expected_columns}, actual={actual_columns}"
        )
    quoted_table = f'"{table_name}"'
    quoted_columns = ", ".join(f'"{column}"' for column in expected_columns)
    placeholders = ", ".join("?" for _ in expected_columns)
    statement = (
        f"INSERT INTO {quoted_table} ({quoted_columns}) VALUES ({placeholders})"
    )
    rows = (
        tuple(_sqlite_value(value) for value in row)
        for row in frame.itertuples(index=False, name=None)
    )
    connection.executemany(statement, rows)


def load_service_database(
    paths: ServiceSourcePaths,
    database_path: Path,
    as_of_month: str | None,
) -> LoadSummary:
    """Build and atomically replace the RM service database from CSV artifacts."""
    manifest = _source_manifest(paths)
    tables = build_service_tables(_read_inputs(paths), as_of_month=as_of_month)
    selected_months = tables["customer_snapshots"]["as_of_month"].unique().tolist()
    if len(selected_months) != 1:
        raise ValueError("고객 스냅샷은 정확히 하나의 기준월을 포함해야 합니다.")
    selected_month = str(selected_months[0])
    row_counts = {name: len(frame) for name, frame in tables.items()}
    run_id = uuid4().hex
    started_at = datetime.now(timezone.utc).isoformat()

    def populate(connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            INSERT INTO import_runs (
                run_id, started_at, status, as_of_month,
                source_manifest_json, row_counts_json
            ) VALUES (?, ?, 'RUNNING', ?, ?, ?)
            """,
            (
                run_id,
                started_at,
                selected_month,
                json.dumps({}, sort_keys=True),
                json.dumps({}, sort_keys=True),
            ),
        )
        for table_name, frame in tables.items():
            _append_dataframe(connection, table_name, frame)
        connection.execute(
            """
            UPDATE import_runs
            SET completed_at = ?, status = 'COMPLETED', as_of_month = ?,
                source_manifest_json = ?, row_counts_json = ?
            WHERE run_id = ?
            """,
            (
                datetime.now(timezone.utc).isoformat(),
                selected_month,
                json.dumps(manifest, ensure_ascii=False, sort_keys=True),
                json.dumps(row_counts, sort_keys=True),
                run_id,
            ),
        )

    replace_database_atomically(Path(database_path), populate)
    return LoadSummary(run_id, "COMPLETED", selected_month, row_counts)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="RM 분석 산출물을 검증해 SQLite 서비스 DB로 원자적 적재합니다."
    )
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--risk-scores", required=True, type=Path)
    parser.add_argument("--segment-panel", required=True, type=Path)
    parser.add_argument("--profitability", required=True, type=Path)
    parser.add_argument("--shap-local", required=True, type=Path)
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE_PATH)
    parser.add_argument("--as-of-month")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the database loader CLI and return a process exit code."""
    args = _parser().parse_args(argv)
    paths = ServiceSourcePaths(
        source=args.source,
        risk_scores=args.risk_scores,
        segment_panel=args.segment_panel,
        profitability=args.profitability,
        shap_local=args.shap_local,
    )
    try:
        summary = load_service_database(paths, args.database, args.as_of_month)
    except Exception as error:
        print(error, file=sys.stderr)
        return 1
    print(json.dumps(vars(summary), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
