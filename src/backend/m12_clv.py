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
    """Build risk-adjusted CLV from the trailing six actual FISIM months."""
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
    profitability_months = pd.period_range(cutoff_period - 5, cutoff_period, freq="M")
    monthly_fisim = build_monthly_fisim(source, rates)
    monthly = monthly_fisim.loc[
        monthly_fisim["법인ID"].isin(score_work["법인ID"])
        & monthly_fisim["월"].isin(profitability_months),
        ["법인ID", "월", "FISIM_CONTRIB_M"],
    ].copy()
    month_counts = monthly.groupby("법인ID")["월"].nunique()
    if (
        len(monthly) != len(score_work) * 6
        or len(month_counts) != len(score_work)
        or not month_counts.eq(6).all()
    ):
        raise ValueError("각 운영 법인은 최근 실제 FISIM 6개월을 모두 가져야 합니다.")

    monthly = monthly.merge(
        score_work,
        on="법인ID",
        how="inner",
        validate="many_to_one",
    )
    customer = (
        monthly.groupby("법인ID", as_index=False)
        .agg(
            CLV_NoRisk=("FISIM_CONTRIB_M", "sum"),
            수익성월수=("월", "size"),
        )
        .merge(score_work, on="법인ID", how="left", validate="one_to_one")
    )
    if not customer["수익성월수"].eq(6).all():
        raise ValueError("각 운영 법인의 실제 FISIM 수익성은 정확히 6개월이어야 합니다.")
    customer["기준월"] = str(cutoff_period)
    customer["수익성기간"] = (
        f"{profitability_months.min()}~{profitability_months.max()}"
    )
    customer["미래수익성예측사용"] = False
    customer["CLV_Risk"] = customer["CLV_NoRisk"] / (
        1 + customer["risk_probability"]
    )
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
            "수익성월수",
            "수익성기간",
            "미래수익성예측사용",
        ]
    ].sort_values(
        ["defense_rank", "법인ID"], na_position="last", kind="mergesort"
    ).reset_index(drop=True)
