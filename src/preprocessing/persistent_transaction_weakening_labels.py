from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class LabelConfig:
    customer_id_col: str = "법인ID"
    month_col: str = "기준년월"
    expected_months: int = 36
    flow_cols: tuple[str, ...] = ("요구불입금금액", "요구불출금금액")
    channel_cols: tuple[str, ...] = (
        "창구거래금액",
        "인터넷뱅킹거래금액",
        "스마트뱅킹거래금액",
        "폰뱅킹거래금액",
        "ATM거래금액",
    )
    card_cols: tuple[str, ...] = ("신용카드사용금액", "체크카드사용금액")

    @property
    def amount_cols(self) -> tuple[str, ...]:
        return self.flow_cols + self.channel_cols + self.card_cols


def _require_columns(frame: pd.DataFrame, columns: tuple[str, ...]) -> None:
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise ValueError(f"필수 컬럼이 없습니다: {missing}")


def validate_complete_cohort(
    frame: pd.DataFrame,
    config: LabelConfig,
) -> pd.DataFrame:
    _require_columns(
        frame,
        (config.customer_id_col, config.month_col, *config.amount_cols),
    )
    work = frame.copy()
    parsed = pd.to_datetime(
        work[config.month_col].astype(str),
        format="%Y%m",
        errors="coerce",
    )
    if parsed.isna().any():
        examples = work.loc[parsed.isna(), config.month_col].head(5).tolist()
        raise ValueError(f"기준년월 파싱 실패: {examples}")
    work[config.month_col] = parsed.dt.to_period("M")

    duplicated = work.duplicated(
        [config.customer_id_col, config.month_col],
        keep=False,
    )
    if duplicated.any():
        examples = (
            work.loc[duplicated, [config.customer_id_col, config.month_col]]
            .head(5)
            .astype(str)
            .to_dict("records")
        )
        raise ValueError(f"법인×월 중복이 있습니다: {examples}")

    invalid_customers = []
    for customer_id, group in work.groupby(config.customer_id_col, sort=False):
        months = group[config.month_col].sort_values().reset_index(drop=True)
        if months.empty:
            invalid_customers.append(customer_id)
            continue
        expected = pd.Series(
            pd.period_range(
                months.iloc[0],
                periods=config.expected_months,
                freq="M",
            )
        )
        if len(months) != config.expected_months or not months.equals(expected):
            invalid_customers.append(customer_id)
    if invalid_customers:
        raise ValueError(
            "정확한 연속 36개월 조건을 충족하지 않은 법인 수: "
            f"{len(invalid_customers)}"
        )

    amounts = work.loc[:, config.amount_cols].apply(pd.to_numeric, errors="coerce")
    if amounts.lt(0).any().any():
        raise ValueError("음수 거래금액이 있습니다.")
    work.loc[:, config.amount_cols] = amounts
    return work.sort_values(
        [config.customer_id_col, config.month_col]
    ).reset_index(drop=True)


def build_core_activity(
    frame: pd.DataFrame,
    config: LabelConfig | None = None,
) -> pd.DataFrame:
    config = config or LabelConfig()
    work = validate_complete_cohort(frame, config)
    work["입출금활동금액"] = work.loc[:, config.flow_cols].sum(
        axis=1,
        min_count=len(config.flow_cols),
    )
    work["채널활동금액"] = work.loc[:, config.channel_cols].sum(
        axis=1,
        min_count=len(config.channel_cols),
    )
    work["카드활동금액"] = work.loc[:, config.card_cols].sum(
        axis=1,
        min_count=len(config.card_cols),
    )
    work["핵심거래활동금액"] = work[
        ["입출금활동금액", "채널활동금액", "카드활동금액"]
    ].sum(axis=1, min_count=3)
    return work
