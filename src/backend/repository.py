"""Parameterized SQLite reads for the RM insight service."""

from collections.abc import Callable, Iterable
import json
import sqlite3
from typing import Any


class DatabaseUnavailable(RuntimeError):
    """Raised when the service database has not been loaded."""


CUSTOMER_SORT_COLUMNS = {
    "defense_rank": "s.defense_rank",
    "risk": "s.risk_probability",
    "clv_risk": "s.clv_risk",
    "potential_loss": "s.potential_loss",
    "name": "COALESCE(c.corporate_name, c.corporate_id)",
}

PRIORITY_SORT_COLUMNS = dict(CUSTOMER_SORT_COLUMNS)

FILTER_OPTION_COLUMNS = {
    "segments": "segment_name",
    "riskLevels": "risk_level",
    "industries": "industry",
    "regions": "region",
    "dedicatedOptions": "dedicated_yn",
    "weakeningTypes": "weakening_type",
}


class ServiceRepository:
    def __init__(self, connection_factory: Callable[[], sqlite3.Connection]):
        self._connection_factory = connection_factory

    def _connect(self) -> sqlite3.Connection:
        try:
            connection = self._connection_factory()
            connection.row_factory = sqlite3.Row
            return connection
        except (OSError, sqlite3.Error) as error:
            raise DatabaseUnavailable from error

    @staticmethod
    def _missing_schema(error: sqlite3.OperationalError) -> bool:
        return "no such table" in str(error).lower()

    def _read(self, operation: Callable[[sqlite3.Connection], Any]) -> Any:
        connection = self._connect()
        try:
            return operation(connection)
        except sqlite3.OperationalError as error:
            if self._missing_schema(error):
                raise DatabaseUnavailable from error
            raise
        finally:
            connection.close()

    def health(self) -> bool:
        def query(connection: sqlite3.Connection) -> bool:
            connection.execute("SELECT 1 FROM monthly_summaries LIMIT 1").fetchone()
            return True

        return self._read(query)

    def _month(self, connection: sqlite3.Connection, requested: str | None) -> str:
        if requested is not None:
            return requested
        row = connection.execute(
            "SELECT MAX(as_of_month) AS as_of_month FROM monthly_summaries"
        ).fetchone()
        if row is None or row["as_of_month"] is None:
            raise DatabaseUnavailable
        return str(row["as_of_month"])

    def overview(self, as_of_month: str | None = None) -> dict[str, Any] | None:
        def query(connection: sqlite3.Connection) -> dict[str, Any] | None:
            month = self._month(connection, as_of_month)
            summary = connection.execute(
                "SELECT * FROM monthly_summaries WHERE as_of_month = ?", (month,)
            ).fetchone()
            if summary is None:
                return None
            trend = connection.execute(
                """
                SELECT as_of_month, managed_customer_count, average_risk
                FROM monthly_summaries
                WHERE as_of_month <= ?
                ORDER BY as_of_month ASC
                """,
                (month,),
            ).fetchall()
            distribution = json.loads(summary["signal_distribution_json"])
            return {
                "asOfMonth": month,
                "managedCustomerCount": summary["managed_customer_count"],
                "averageRisk": summary["average_risk"] * 100,
                "highRiskShare": summary["high_risk_share"] * 100,
                "potentialLossTotal": summary["potential_loss_total"],
                "monthlyTrend": [
                    {
                        "month": row["as_of_month"],
                        "risk": row["average_risk"] * 100,
                        "managed": row["managed_customer_count"],
                    }
                    for row in trend
                ],
                "signalSummary": [
                    {"label": label, "value": value}
                    for label, value in distribution.items()
                ],
            }

        return self._read(query)

    def filter_options(self, as_of_month: str | None = None) -> dict[str, Any]:
        def query(connection: sqlite3.Connection) -> dict[str, Any]:
            month = self._month(connection, as_of_month)

            def values(option: str) -> list[str]:
                column = FILTER_OPTION_COLUMNS[option]
                rows = connection.execute(
                    f"SELECT DISTINCT {column} AS value FROM customer_snapshots "
                    "WHERE as_of_month = ? ORDER BY value ASC",
                    (month,),
                ).fetchall()
                return [str(row["value"]) for row in rows]

            options = {key: values(key) for key in FILTER_OPTION_COLUMNS}
            options["dedicatedOptions"] = [
                "Y" if value == "1" else "N"
                for value in options["dedicatedOptions"]
            ]
            return {"asOfMonth": month, **options}

        return self._read(query)

    @staticmethod
    def _filters(
        *,
        search: str | None = None,
        segment: str | None = None,
        risk_level: str | None = None,
        industry: str | None = None,
        region: str | None = None,
        dedicated: str | None = None,
        weakening_type: str | None = None,
    ) -> tuple[list[str], list[Any]]:
        clauses: list[str] = []
        parameters: list[Any] = []
        fixed_filters = (
            ("s.segment_name", segment),
            ("s.risk_level", risk_level),
            ("s.industry", industry),
            ("s.region", region),
            ("s.dedicated_yn", None if dedicated is None else int(dedicated == "Y")),
            ("s.weakening_type", weakening_type),
        )
        for column, value in fixed_filters:
            if value is not None:
                clauses.append(f"{column} = ?")
                parameters.append(value)
        if search:
            clauses.append(
                "(c.corporate_id LIKE ? OR COALESCE(c.corporate_name, '') LIKE ?)"
            )
            pattern = f"%{search}%"
            parameters.extend((pattern, pattern))
        return clauses, parameters

    @staticmethod
    def _signals(
        connection: sqlite3.Connection, corporate_ids: Iterable[str], month: str
    ) -> dict[str, list[dict[str, Any]]]:
        identifiers = list(corporate_ids)
        if not identifiers:
            return {}
        placeholders = ", ".join("?" for _ in identifiers)
        rows = connection.execute(
            f"""
            SELECT corporate_id, signal_type, current_value, comparison_value,
                   change_rate
            FROM weakening_signals
            WHERE as_of_month = ? AND corporate_id IN ({placeholders})
            ORDER BY corporate_id, signal_rank, signal_type
            """,
            (month, *identifiers),
        ).fetchall()
        result: dict[str, list[dict[str, Any]]] = {key: [] for key in identifiers}
        for row in rows:
            result[row["corporate_id"]].append(
                {
                    "label": row["signal_type"],
                    "change": row["change_rate"],
                    "recent": row["current_value"],
                    "previous": row["comparison_value"],
                }
            )
        return result

    @staticmethod
    def _customer(row: sqlite3.Row, signals: list[dict[str, Any]]) -> dict[str, Any]:
        risk = row["risk_probability"] * 100
        return {
            "id": row["corporate_id"],
            "name": row["display_name"],
            "industry": row["industry"],
            "region": row["region"],
            "dedicated": "Y" if row["dedicated_yn"] else "N",
            "segment": row["segment_name"],
            "riskLevel": row["risk_level"],
            "risk": risk,
            "health": 100 - risk,
            "clvRisk": row["clv_risk"],
            "potentialLoss": row["potential_loss"],
            "defenseRank": row["defense_rank"],
            "weakeningType": row["weakening_type"],
            "signals": signals,
        }

    def customers(
        self,
        *,
        page: int = 1,
        page_size: int = 50,
        sort_by: str = "defense_rank",
        sort_order: str = "asc",
        as_of_month: str | None = None,
        **filters: Any,
    ) -> dict[str, Any]:
        return self._customer_page(
            page=page,
            page_size=page_size,
            sort_by=sort_by,
            sort_order=sort_order,
            as_of_month=as_of_month,
            sort_columns=CUSTOMER_SORT_COLUMNS,
            filters=filters,
        )

    def priorities(
        self,
        *,
        page: int = 1,
        page_size: int = 50,
        sort_by: str = "defense_rank",
        sort_order: str = "asc",
        as_of_month: str | None = None,
        **filters: Any,
    ) -> dict[str, Any]:
        return self._customer_page(
            page=page,
            page_size=page_size,
            sort_by=sort_by,
            sort_order=sort_order,
            as_of_month=as_of_month,
            sort_columns=PRIORITY_SORT_COLUMNS,
            filters=filters,
        )

    def _customer_page(
        self,
        *,
        page: int,
        page_size: int,
        sort_by: str,
        sort_order: str,
        as_of_month: str | None,
        sort_columns: dict[str, str],
        filters: dict[str, Any],
    ) -> dict[str, Any]:
        if sort_by not in sort_columns or sort_order not in {"asc", "desc"}:
            raise ValueError("허용되지 않은 정렬 조건입니다.")

        def query(connection: sqlite3.Connection) -> dict[str, Any]:
            month = self._month(connection, as_of_month)
            clauses, parameters = self._filters(**filters)
            where = " AND ".join(["s.as_of_month = ?", *clauses])
            query_parameters = [month, *parameters]
            total = connection.execute(
                f"""
                SELECT COUNT(*) AS count
                FROM customer_snapshots s
                JOIN customers c ON c.corporate_id = s.corporate_id
                WHERE {where}
                """,
                query_parameters,
            ).fetchone()["count"]
            sort_column = sort_columns[sort_by]
            if sort_by == "defense_rank":
                order_by = (
                    f"(s.defense_rank IS NULL) ASC, "
                    f"{sort_column} {sort_order.upper()}, s.corporate_id ASC"
                )
            else:
                order_by = (
                    f"{sort_column} {sort_order.upper()}, s.corporate_id ASC"
                )
            rows = connection.execute(
                f"""
                SELECT s.*, COALESCE(c.corporate_name, c.corporate_id) AS display_name
                FROM customer_snapshots s
                JOIN customers c ON c.corporate_id = s.corporate_id
                WHERE {where}
                ORDER BY {order_by}
                LIMIT ? OFFSET ?
                """,
                (*query_parameters, page_size, (page - 1) * page_size),
            ).fetchall()
            signals = self._signals(connection, (row["corporate_id"] for row in rows), month)
            return {
                "items": [
                    self._customer(row, signals[row["corporate_id"]]) for row in rows
                ],
                "page": page,
                "pageSize": page_size,
                "total": total,
            }

        return self._read(query)

    def customer_detail(
        self, corporate_id: str, as_of_month: str | None = None
    ) -> dict[str, Any] | None:
        def query(connection: sqlite3.Connection) -> dict[str, Any] | None:
            month = self._month(connection, as_of_month)
            row = connection.execute(
                """
                SELECT s.*, COALESCE(c.corporate_name, c.corporate_id) AS display_name
                FROM customer_snapshots s
                JOIN customers c ON c.corporate_id = s.corporate_id
                WHERE s.corporate_id = ? AND s.as_of_month = ?
                """,
                (corporate_id, month),
            ).fetchone()
            if row is None:
                return None
            signals = self._signals(connection, [corporate_id], month)
            return self._customer(row, signals[corporate_id])

        return self._read(query)

    def recommendations(
        self,
        *,
        page: int = 1,
        page_size: int = 50,
        segment: str | None = None,
        weakening_type: str | None = None,
        risk_level: str | None = None,
        as_of_month: str | None = None,
    ) -> dict[str, Any]:
        def query(connection: sqlite3.Connection) -> dict[str, Any]:
            month = self._month(connection, as_of_month)
            clauses, parameters = self._filters(
                segment=segment,
                weakening_type=weakening_type,
                risk_level=risk_level,
            )
            where = " AND ".join(["s.as_of_month = ?", *clauses])
            query_parameters = [month, *parameters]
            joins = """
                FROM recommendations r
                JOIN customer_snapshots s
                  ON s.corporate_id = r.corporate_id AND s.as_of_month = r.as_of_month
                JOIN customers c ON c.corporate_id = r.corporate_id
            """
            total = connection.execute(
                f"SELECT COUNT(*) AS count {joins} WHERE {where}", query_parameters
            ).fetchone()["count"]
            rows = connection.execute(
                f"""
                SELECT r.*, s.segment_name,
                       COALESCE(c.corporate_name, c.corporate_id) AS display_name
                {joins}
                WHERE {where}
                ORDER BY (s.defense_rank IS NULL) ASC,
                         s.defense_rank ASC,
                         s.corporate_id ASC
                LIMIT ? OFFSET ?
                """,
                (*query_parameters, page_size, (page - 1) * page_size),
            ).fetchall()
            return {
                "items": [self._recommendation(row) for row in rows],
                "page": page,
                "pageSize": page_size,
                "total": total,
            }

        return self._read(query)

    @staticmethod
    def _recommendation(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["corporate_id"],
            "name": row["display_name"],
            "segment": row["segment_name"],
            "weakeningType": row["weakening_type"],
            "priority": row["priority_level"],
            "reason": row["reason"],
            "contact": row["contact_strategy"],
            "action": row["recommended_action"],
            "summary": row["strategy_summary"],
        }

    def report(
        self, corporate_id: str, as_of_month: str | None = None
    ) -> dict[str, Any] | None:
        def query(connection: sqlite3.Connection) -> dict[str, Any] | None:
            month = self._month(connection, as_of_month)
            customer_row = connection.execute(
                """
                SELECT s.*, COALESCE(c.corporate_name, c.corporate_id) AS display_name
                FROM customer_snapshots s
                JOIN customers c ON c.corporate_id = s.corporate_id
                WHERE s.corporate_id = ? AND s.as_of_month = ?
                """,
                (corporate_id, month),
            ).fetchone()
            if customer_row is None:
                return None
            recommendation_row = connection.execute(
                """
                SELECT r.*, s.segment_name,
                       COALESCE(c.corporate_name, c.corporate_id) AS display_name
                FROM recommendations r
                JOIN customer_snapshots s
                  ON s.corporate_id = r.corporate_id AND s.as_of_month = r.as_of_month
                JOIN customers c ON c.corporate_id = r.corporate_id
                WHERE r.corporate_id = ? AND r.as_of_month = ?
                """,
                (corporate_id, month),
            ).fetchone()
            if recommendation_row is None:
                return None
            signals = self._signals(connection, [corporate_id], month)
            shap_rows = connection.execute(
                """
                SELECT feature_name, feature_value, shap_value, abs_shap_rank
                FROM shap_factors
                WHERE corporate_id = ? AND as_of_month = ?
                ORDER BY abs_shap_rank ASC, model_name ASC
                """,
                (corporate_id, month),
            ).fetchall()
            factors = [
                {
                    "feature": row["feature_name"],
                    "featureValue": row["feature_value"],
                    "impact": row["shap_value"],
                    "rank": row["abs_shap_rank"],
                }
                for row in shap_rows
            ]
            return {
                "customer": self._customer(customer_row, signals[corporate_id]),
                "recommendation": self._recommendation(recommendation_row),
                "strategySummary": recommendation_row["strategy_summary"],
                "shapAvailable": bool(factors),
                "shapFactors": factors,
            }

        return self._read(query)
