"""Final M12 FISIM profitability and six-month CLV calculations."""

from __future__ import annotations

import re

import numpy as np
import pandas as pd


DEMAND_DEPOSIT_RATE_MONTHLY_DECIMAL = 0.0001
EXPECTED_MONTHS = pd.period_range("2023-01", "2025-12", freq="M")
BALANCE_COLUMNS = [
    "여신_운전자금대출잔액",
    "여신_시설자금대출잔액",
    "거치식예금잔액",
    "적립식예금잔액",
    "요구불예금잔액",
]
RATE_COLUMNS = [
    "대출스프레드_월",
    "저축성수신스프레드_월",
    "요구불스프레드_월",
]


def _require_columns(frame: pd.DataFrame, columns: list[str], label: str) -> None:
    missing = sorted(set(columns).difference(frame.columns))
    if missing:
        raise ValueError(f"{label} 필수 컬럼 누락: {missing}")


def _numeric_nonnegative(frame: pd.DataFrame, columns: list[str], label: str) -> None:
    frame[columns] = frame[columns].apply(pd.to_numeric, errors="coerce")
    if frame[columns].isna().any().any():
        raise ValueError(f"{label} 값은 결측이 없는 비음수 숫자여야 합니다.")
    if frame[columns].lt(0).any().any():
        raise ValueError(f"{label} 값은 결측이 없는 비음수 숫자여야 합니다.")


def build_monthly_rates(
    ftp: pd.DataFrame,
    bank_rates: pd.DataFrame,
) -> pd.DataFrame:
    """Normalize the final notebook's monthly FTP and bank-rate inputs."""
    ftp_rate_column = "monthly_recombined_ytd_rate_decimal"
    _require_columns(ftp, ["month", ftp_rate_column], "FTP")
    ftp_work = ftp.loc[:, ["month", ftp_rate_column]].copy()
    try:
        ftp_work["월"] = pd.PeriodIndex(ftp_work["month"].astype(str), freq="M")
    except ValueError as error:
        raise ValueError("FTP 월 형식을 해석할 수 없습니다.") from error
    ftp_work["FTP_월_decimal"] = pd.to_numeric(
        ftp_work[ftp_rate_column], errors="coerce"
    )
    if ftp_work["FTP_월_decimal"].isna().any():
        raise ValueError("FTP 월 소수 값에 결측 또는 비수치가 있습니다.")
    if (
        len(ftp_work) != 36
        or not ftp_work["월"].is_unique
        or set(ftp_work["월"]) != set(EXPECTED_MONTHS)
    ):
        raise ValueError("FTP는 2023-01~2025-12의 고유한 36개월이어야 합니다.")
    if not ftp_work["FTP_월_decimal"].between(0, 0.02).all():
        raise ValueError("FTP 월 소수 값이 허용 범위를 벗어났습니다.")

    _require_columns(bank_rates, ["은행", "구분"], "예대금리")
    rate_work = bank_rates.copy()
    rate_work["은행"] = rate_work["은행"].ffill()
    month_columns = [
        column
        for column in rate_work.columns
        if re.fullmatch(r"\d{4}년\d{2}월", str(column))
    ]
    if len(month_columns) != 36:
        raise ValueError("예대금리는 2023-01~2025-12의 36개월 열이어야 합니다.")
    selected = rate_work.loc[
        rate_work["은행"].astype(str).str.contains("iM뱅크", na=False)
        & rate_work["구분"].isin(["기업대출금리", "저축성수신금리"]),
        ["구분", *month_columns],
    ].copy()
    if selected["구분"].value_counts().to_dict() != {
        "기업대출금리": 1,
        "저축성수신금리": 1,
    }:
        raise ValueError("iM뱅크 기업대출·저축성수신 금리는 각각 한 행이어야 합니다.")

    long = selected.melt(
        id_vars="구분",
        var_name="금리기준월",
        value_name="월율_pct",
    )
    parts = long["금리기준월"].str.extract(
        r"(?P<year>\d{4})년(?P<month>\d{2})월"
    )
    long["월"] = pd.PeriodIndex(parts["year"] + "-" + parts["month"], freq="M")
    long["월율_pct"] = pd.to_numeric(long["월율_pct"], errors="coerce")
    if long["월율_pct"].isna().any():
        raise ValueError("예대금리에 결측 또는 비수치 값이 있습니다.")
    rate_pivot = (
        long.pivot(index="월", columns="구분", values="월율_pct")
        .reset_index()
        .rename_axis(columns=None)
    )
    result = ftp_work.loc[:, ["월", "FTP_월_decimal"]].merge(
        rate_pivot,
        on="월",
        how="inner",
        validate="one_to_one",
    )
    if len(result) != 36:
        raise ValueError("FTP와 예대금리의 공통 월이 36개월이 아닙니다.")

    result["기업대출금리_월_decimal"] = result["기업대출금리"] / 100
    result["저축성수신금리_월_decimal"] = result["저축성수신금리"] / 100
    result["요구불금리_월_decimal"] = DEMAND_DEPOSIT_RATE_MONTHLY_DECIMAL
    result["대출스프레드_월"] = (
        result["기업대출금리_월_decimal"] - result["FTP_월_decimal"]
    )
    result["저축성수신스프레드_월"] = (
        result["FTP_월_decimal"] - result["저축성수신금리_월_decimal"]
    )
    result["요구불스프레드_월"] = (
        result["FTP_월_decimal"] - result["요구불금리_월_decimal"]
    )
    return result.sort_values("월").reset_index(drop=True)


def build_monthly_fisim(
    source: pd.DataFrame,
    rates: pd.DataFrame,
) -> pd.DataFrame:
    """Calculate direct monthly FISIM contribution from month-end balances."""
    required = ["법인ID", "기준년월", *BALANCE_COLUMNS]
    _require_columns(source, required, "FISIM 원천")
    _require_columns(rates, ["월", *RATE_COLUMNS], "FISIM 금리")
    work = source.loc[:, required].copy()
    if work["법인ID"].isna().any():
        raise ValueError("법인ID에 결측이 있습니다.")
    work["법인ID"] = work["법인ID"].astype("string")
    try:
        work["월"] = pd.PeriodIndex(work["기준년월"].astype(str), freq="M")
    except ValueError as error:
        raise ValueError("기준년월 형식을 해석할 수 없습니다.") from error
    if work.duplicated(["법인ID", "월"]).any():
        raise ValueError("FISIM 원천에 법인ID+월 중복이 있습니다.")
    _numeric_nonnegative(work, BALANCE_COLUMNS, "FISIM 잔액")

    work["대출잔액_L"] = work[BALANCE_COLUMNS[:2]].sum(axis=1)
    work["저축성수신잔액_DS"] = work[BALANCE_COLUMNS[2:4]].sum(axis=1)
    work["요구불잔액_DR"] = work["요구불예금잔액"]
    work = work.merge(
        rates.loc[:, ["월", *RATE_COLUMNS]],
        on="월",
        how="left",
        validate="many_to_one",
    )
    if work[RATE_COLUMNS].isna().any().any():
        missing_months = sorted(work.loc[work[RATE_COLUMNS].isna().any(axis=1), "월"].astype(str).unique())
        raise ValueError(f"FISIM 금리 매핑 누락: {missing_months}")

    work["대출_FISIM_CONTRIB_M"] = work["대출잔액_L"] * work["대출스프레드_월"]
    work["저축성수신_FISIM_CONTRIB_M"] = (
        work["저축성수신잔액_DS"] * work["저축성수신스프레드_월"]
    )
    work["요구불_FISIM_CONTRIB_M"] = (
        work["요구불잔액_DR"] * work["요구불스프레드_월"]
    )
    contribution_columns = [
        "대출_FISIM_CONTRIB_M",
        "저축성수신_FISIM_CONTRIB_M",
        "요구불_FISIM_CONTRIB_M",
    ]
    work["FISIM_CONTRIB_M"] = work[contribution_columns].sum(axis=1)
    return work.sort_values(["법인ID", "월"]).reset_index(drop=True)


def build_operating_clv(
    source: pd.DataFrame,
    rates: pd.DataFrame,
    scores: pd.DataFrame,
    cutoff: str = "2025-12",
) -> pd.DataFrame:
    """Build final six-month CLV and deterministic defense priority."""
    _require_columns(scores, ["법인ID", "risk_probability"], "운영 점수")
    score_work = scores.loc[:, ["법인ID", "risk_probability"]].copy()
    if score_work["법인ID"].isna().any():
        raise ValueError("운영 점수 법인ID에 결측이 있습니다.")
    score_work["법인ID"] = score_work["법인ID"].astype("string")
    if score_work["법인ID"].duplicated().any():
        raise ValueError("운영 점수 법인ID가 중복되었습니다.")
    score_work["risk_probability"] = pd.to_numeric(
        score_work["risk_probability"], errors="coerce"
    )
    if (
        score_work["risk_probability"].isna().any()
        or not score_work["risk_probability"].between(0, 1).all()
    ):
        raise ValueError("risk_probability는 0과 1 사이의 숫자여야 합니다.")

    cutoff_period = pd.Period(cutoff, freq="M")
    _require_columns(rates, ["월", *RATE_COLUMNS], "CLV 금리")
    cutoff_rates = rates.loc[rates["월"].eq(cutoff_period), RATE_COLUMNS]
    if len(cutoff_rates) != 1 or cutoff_rates.isna().any().any():
        raise ValueError(f"기준월 {cutoff}의 CLV 금리는 정확히 한 행이어야 합니다.")
    rate_row = cutoff_rates.iloc[0]

    required_source = ["법인ID", "기준년월", *BALANCE_COLUMNS]
    _require_columns(source, required_source, "CLV 원천")
    source_work = source.loc[:, required_source].copy()
    if source_work["법인ID"].isna().any():
        raise ValueError("CLV 원천 법인ID에 결측이 있습니다.")
    source_work["법인ID"] = source_work["법인ID"].astype("string")
    try:
        source_work["월"] = pd.PeriodIndex(
            source_work["기준년월"].astype(str), freq="M"
        )
    except ValueError as error:
        raise ValueError("CLV 원천 기준년월 형식을 해석할 수 없습니다.") from error
    if source_work.duplicated(["법인ID", "월"]).any():
        raise ValueError("CLV 원천에 법인ID+월 중복이 있습니다.")
    _numeric_nonnegative(source_work, BALANCE_COLUMNS, "CLV 잔액")
    source_work["대출잔액_L"] = source_work[BALANCE_COLUMNS[:2]].sum(axis=1)
    source_work["저축성수신잔액_DS"] = source_work[BALANCE_COLUMNS[2:4]].sum(axis=1)
    source_work["요구불잔액_DR"] = source_work["요구불예금잔액"]

    forecast_parts: list[pd.DataFrame] = []
    for horizon in range(1, 7):
        forecast_month = cutoff_period + horizon
        reference_month = forecast_month - 12
        balances = source_work.loc[
            source_work["월"].eq(reference_month)
            & source_work["법인ID"].isin(score_work["법인ID"]),
            ["법인ID", "대출잔액_L", "저축성수신잔액_DS", "요구불잔액_DR"],
        ].copy()
        if len(balances) != len(score_work) or not balances["법인ID"].is_unique:
            raise ValueError("각 운영 법인은 CLV 잔액 참조월 6개월을 모두 가져야 합니다.")
        balances["예측개월차_h"] = horizon
        balances["예측_FISIM_M"] = (
            balances["대출잔액_L"] * rate_row["대출스프레드_월"]
            + balances["저축성수신잔액_DS"] * rate_row["저축성수신스프레드_월"]
            + balances["요구불잔액_DR"] * rate_row["요구불스프레드_월"]
        )
        forecast_parts.append(balances)

    monthly = pd.concat(forecast_parts, ignore_index=True).merge(
        score_work,
        on="법인ID",
        how="inner",
        validate="many_to_one",
    )
    monthly["S_사건미발생확률"] = np.power(
        1 - monthly["risk_probability"], monthly["예측개월차_h"] / 6.0
    )
    monthly["CLV_NoRisk_월기여"] = monthly["예측_FISIM_M"]
    monthly["CLV_Risk_월기여"] = (
        monthly["예측_FISIM_M"] * monthly["S_사건미발생확률"]
        / (1 + monthly["risk_probability"])
    )
    customer = (
        monthly.groupby("법인ID", as_index=False)
        .agg(
            CLV_NoRisk=("CLV_NoRisk_월기여", "sum"),
            CLV_Risk=("CLV_Risk_월기여", "sum"),
            예측월수=("예측개월차_h", "size"),
        )
        .merge(score_work, on="법인ID", how="left", validate="one_to_one")
    )
    if not customer["예측월수"].eq(6).all():
        raise ValueError("각 운영 법인의 CLV 예측은 정확히 6개월이어야 합니다.")
    customer["기준월"] = str(cutoff_period)
    customer["PotentialLoss"] = customer["CLV_NoRisk"] - customer["CLV_Risk"]
    customer["defense_value"] = customer["PotentialLoss"].clip(lower=0)
    if not np.isfinite(
        customer[["CLV_NoRisk", "CLV_Risk", "PotentialLoss", "defense_value"]]
        .to_numpy(dtype=float)
    ).all():
        raise ValueError("CLV 또는 PotentialLoss에 유한하지 않은 값이 있습니다.")

    customer["defense_rank"] = pd.Series(pd.NA, index=customer.index, dtype="Int64")
    eligible = customer.loc[customer["defense_value"].gt(0)].sort_values(
        ["defense_value", "risk_probability", "CLV_NoRisk", "법인ID"],
        ascending=[False, False, False, True],
        kind="mergesort",
    )
    customer.loc[eligible.index, "defense_rank"] = np.arange(1, len(eligible) + 1)
    return customer[
        [
            "법인ID",
            "기준월",
            "risk_probability",
            "CLV_NoRisk",
            "CLV_Risk",
            "PotentialLoss",
            "defense_value",
            "defense_rank",
            "예측월수",
        ]
    ].sort_values(
        ["defense_rank", "법인ID"], na_position="last", kind="mergesort"
    ).reset_index(drop=True)
