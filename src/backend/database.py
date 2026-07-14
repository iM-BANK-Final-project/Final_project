"""SQLite connection, schema, and replacement helpers for the RM service."""

from collections.abc import Callable
from contextlib import suppress
from pathlib import Path
import sqlite3


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS customers (
    corporate_id TEXT PRIMARY KEY,
    corporate_name TEXT,
    industry TEXT NOT NULL,
    region TEXT NOT NULL,
    customer_grade TEXT NOT NULL,
    dedicated_yn INTEGER NOT NULL CHECK (dedicated_yn IN (0, 1))
);

CREATE TABLE IF NOT EXISTS risk_scores (
    corporate_id TEXT NOT NULL,
    as_of_month TEXT NOT NULL,
    model_name TEXT NOT NULL,
    risk_probability REAL NOT NULL CHECK (risk_probability BETWEEN 0 AND 1),
    risk_level TEXT NOT NULL,
    PRIMARY KEY (corporate_id, as_of_month, model_name),
    FOREIGN KEY (corporate_id) REFERENCES customers (corporate_id)
);

CREATE TABLE IF NOT EXISTS segments (
    corporate_id TEXT NOT NULL,
    as_of_month TEXT NOT NULL,
    segment_name TEXT NOT NULL,
    activity_score REAL NOT NULL CHECK (activity_score BETWEEN 0 AND 1),
    deposit_score REAL NOT NULL CHECK (deposit_score BETWEEN 0 AND 1),
    loan_score REAL NOT NULL CHECK (loan_score BETWEEN 0 AND 1),
    PRIMARY KEY (corporate_id, as_of_month),
    FOREIGN KEY (corporate_id) REFERENCES customers (corporate_id)
);

CREATE TABLE IF NOT EXISTS profitability (
    corporate_id TEXT NOT NULL,
    as_of_month TEXT NOT NULL,
    profitability_value REAL,
    defense_value REAL,
    customer_value_proxy REAL NOT NULL CHECK (customer_value_proxy BETWEEN 0 AND 1),
    value_components_json TEXT NOT NULL,
    PRIMARY KEY (corporate_id, as_of_month),
    FOREIGN KEY (corporate_id) REFERENCES customers (corporate_id)
);

CREATE TABLE IF NOT EXISTS weakening_signals (
    corporate_id TEXT NOT NULL,
    as_of_month TEXT NOT NULL,
    signal_type TEXT NOT NULL,
    current_value REAL NOT NULL,
    comparison_value REAL NOT NULL,
    change_rate REAL,
    signal_rank INTEGER NOT NULL,
    PRIMARY KEY (corporate_id, as_of_month, signal_type),
    FOREIGN KEY (corporate_id) REFERENCES customers (corporate_id)
);

CREATE TABLE IF NOT EXISTS shap_factors (
    corporate_id TEXT NOT NULL,
    as_of_month TEXT NOT NULL,
    model_name TEXT NOT NULL,
    feature_name TEXT NOT NULL,
    feature_value REAL NOT NULL,
    shap_value REAL NOT NULL,
    abs_shap_rank INTEGER NOT NULL,
    PRIMARY KEY (corporate_id, as_of_month, model_name, abs_shap_rank),
    FOREIGN KEY (corporate_id) REFERENCES customers (corporate_id)
);

CREATE TABLE IF NOT EXISTS recommendations (
    corporate_id TEXT NOT NULL,
    as_of_month TEXT NOT NULL,
    weakening_type TEXT NOT NULL,
    priority_level TEXT NOT NULL,
    reason TEXT NOT NULL,
    contact_strategy TEXT NOT NULL,
    recommended_action TEXT NOT NULL,
    strategy_summary TEXT NOT NULL,
    PRIMARY KEY (corporate_id, as_of_month),
    FOREIGN KEY (corporate_id) REFERENCES customers (corporate_id)
);

CREATE TABLE IF NOT EXISTS customer_snapshots (
    corporate_id TEXT NOT NULL,
    as_of_month TEXT NOT NULL,
    risk_probability REAL NOT NULL CHECK (risk_probability BETWEEN 0 AND 1),
    risk_level TEXT NOT NULL,
    customer_value_proxy REAL NOT NULL CHECK (customer_value_proxy BETWEEN 0 AND 1),
    profitability_value REAL,
    defense_value REAL,
    crm_priority_score REAL NOT NULL CHECK (crm_priority_score BETWEEN 0 AND 1),
    crm_priority_rank INTEGER NOT NULL,
    segment_name TEXT NOT NULL,
    weakening_type TEXT NOT NULL,
    industry TEXT NOT NULL,
    region TEXT NOT NULL,
    dedicated_yn INTEGER NOT NULL CHECK (dedicated_yn IN (0, 1)),
    PRIMARY KEY (corporate_id, as_of_month),
    FOREIGN KEY (corporate_id) REFERENCES customers (corporate_id)
);

CREATE TABLE IF NOT EXISTS monthly_summaries (
    as_of_month TEXT PRIMARY KEY,
    managed_customer_count INTEGER NOT NULL,
    average_risk REAL NOT NULL CHECK (average_risk BETWEEN 0 AND 1),
    high_risk_share REAL NOT NULL CHECK (high_risk_share BETWEEN 0 AND 1),
    priority_value_total REAL NOT NULL,
    signal_distribution_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS import_runs (
    run_id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    status TEXT NOT NULL,
    as_of_month TEXT NOT NULL,
    source_manifest_json TEXT NOT NULL,
    row_counts_json TEXT NOT NULL,
    error_message TEXT
);

CREATE INDEX IF NOT EXISTS idx_risk_scores_month_level
    ON risk_scores (as_of_month, risk_level);
CREATE INDEX IF NOT EXISTS idx_segments_month_name
    ON segments (as_of_month, segment_name);
CREATE INDEX IF NOT EXISTS idx_snapshots_month_priority_rank
    ON customer_snapshots (as_of_month, crm_priority_rank);
CREATE INDEX IF NOT EXISTS idx_snapshots_month_risk_level
    ON customer_snapshots (as_of_month, risk_level);
CREATE INDEX IF NOT EXISTS idx_snapshots_month_segment_name
    ON customer_snapshots (as_of_month, segment_name);
CREATE INDEX IF NOT EXISTS idx_snapshots_month_industry
    ON customer_snapshots (as_of_month, industry);
CREATE INDEX IF NOT EXISTS idx_snapshots_month_region
    ON customer_snapshots (as_of_month, region);
CREATE INDEX IF NOT EXISTS idx_snapshots_month_dedicated
    ON customer_snapshots (as_of_month, dedicated_yn);
CREATE INDEX IF NOT EXISTS idx_snapshots_month_weakening_type
    ON customer_snapshots (as_of_month, weakening_type);
"""


def connect_database(path: Path) -> sqlite3.Connection:
    """Open a SQLite database with the service's required connection settings."""
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize_schema(connection: sqlite3.Connection) -> None:
    """Create all service tables and indexes when they do not already exist."""
    connection.executescript(SCHEMA_SQL)


def replace_database_atomically(
    target: Path,
    populate: Callable[[sqlite3.Connection], None],
) -> None:
    """Populate a temporary database and replace target only after success."""
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.unlink(missing_ok=True)
    connection = connect_database(temporary)
    try:
        initialize_schema(connection)
        populate(connection)
        connection.commit()
        connection.close()
        temporary.replace(target)
    except Exception:
        with suppress(Exception):
            connection.rollback()
        with suppress(Exception):
            connection.close()
        with suppress(Exception):
            temporary.unlink(missing_ok=True)
        raise
