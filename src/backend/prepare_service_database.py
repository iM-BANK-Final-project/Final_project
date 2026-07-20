"""Derive service inputs from existing CSVs and load the RM SQLite database."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

import numpy as np
import pandas as pd

from src.backend.load_service_database import (
    DEFAULT_DATABASE_PATH,
    LoadSummary,
    ServiceSourcePaths,
    load_service_database,
)
from src.segmentation.relationship_segments import (
    SegmentationConfig,
    build_monthly_relationship_axes,
    build_reference_relationship_levels,
    build_rolling_relationship_features,
    select_complete_segmentation_cohort,
)


DEFAULT_SOURCE_PATH = Path("outputs/iM뱅크데이터_거시경제지표포함.csv")
DEFAULT_RISK_SCORES_PATH = Path(
    "outputs/persistent_weakening_baseline/validation_scores.csv"
)
DEFAULT_BANK_RATES_PATH = Path("outputs/예대금리차2023~2025_순.csv")
DEFAULT_SHAP_LOCAL_PATH = Path(
    "outputs/persistent_weakening_interpretation/shap_local_top_rows.csv"
)
DEFAULT_DERIVED_DIR = Path("outputs/rm_service_inputs")
DEMAND_DEPOSIT_RATE = 0.0001

# src/수익성.ipynb에서 검증한 단독분기 원가성자금 이자율이다.
FTP_RATE_BY_QUARTER = {
    "2023Q1": 0.0272,
    "2023Q2": 0.0272,
    "2023Q3": 0.0272,
    "2023Q4": 0.0272,
    "2024Q1": 0.028,
    "2024Q2": 0.027210722184337,
    "2024Q3": 0.027013851220178,
    "2024Q4": 0.026627565434292,
    "2025Q1": 0.0251,
    "2025Q2": 0.023311321623796,
    "2025Q3": 0.021545482326075,
    "2025Q4": 0.021545482326075,
}

SEGMENT_OUTPUT_COLUMNS = [
    "법인ID",
    "기준년월",
    "관계세그먼트",
    "거래활동점수",
    "수신관계점수",
    "여신관계점수",
]
PROFIT_OUTPUT_COLUMNS = [
    "법인ID",
    "기준월",
    "V_FTP_12M",
    "V_FTP_12M_방어가치",
]
PROFIT_SOURCE_COLUMNS = [
    "법인ID",
    "기준년월",
    "요구불예금잔액",
    "거치식예금잔액",
    "적립식예금잔액",
    "여신_운전자금대출잔액",
    "여신_시설자금대출잔액",
]


def build_service_segment_panel(source: pd.DataFrame) -> pd.DataFrame:
    """Build only the approved rolling relationship features needed by the service."""
    config = SegmentationConfig()
    monthly = build_monthly_relationship_axes(source, config)
    cohort = select_complete_segmentation_cohort(monthly, config)
    reference = build_reference_relationship_levels(cohort, config)
    rolling = build_rolling_relationship_features(cohort, reference, config)
    result = rolling.loc[:, SEGMENT_OUTPUT_COLUMNS].copy()
    result["기준년월"] = result["기준년월"].astype(str)
    return result.reset_index(drop=True)


def _build_bank_rate_month(bank_rates: pd.DataFrame) -> pd.DataFrame:
    required = {"은행", "구분"}
    missing = sorted(required.difference(bank_rates.columns))
    if missing:
        raise ValueError(f"은행 금리 필수 컬럼이 없습니다: {missing}")

    work = bank_rates.copy()
    work["은행"] = work["은행"].ffill()
    month_columns = [
        column
        for column in work.columns
        if column not in required and pd.notna(pd.to_datetime(column, format="%Y년%m월", errors="coerce"))
    ]
    if not month_columns:
        raise ValueError("은행 금리 월별 컬럼이 없습니다.")

    long = work.melt(
        id_vars=["은행", "구분"],
        value_vars=month_columns,
        var_name="월표기",
        value_name="금리_pct",
    )
    long = long.loc[
        long["은행"].astype(str).str.contains("iM뱅크", na=False)
        & long["구분"].isin(["기업대출금리", "저축성수신금리"])
    ].copy()
    long["기준월"] = pd.to_datetime(long["월표기"], format="%Y년%m월", errors="coerce")
    long["금리_pct"] = pd.to_numeric(long["금리_pct"], errors="coerce")
    if long.duplicated(["기준월", "구분"]).any():
        raise ValueError("은행 금리가 기준월·구분별로 중복되었습니다.")

    monthly = (
        long.pivot(index="기준월", columns="구분", values="금리_pct")
        .reset_index()
        .rename_axis(None, axis=1)
    )
    for column in ("기업대출금리", "저축성수신금리"):
        if column not in monthly or monthly[column].isna().any():
            raise ValueError(f"은행 금리 매핑 누락: {column}")
        monthly[column] = monthly[column] / 100
    monthly["분기"] = monthly["기준월"].dt.to_period("Q").astype(str)
    monthly["FTP_원가성자금"] = monthly["분기"].map(FTP_RATE_BY_QUARTER)
    if monthly["FTP_원가성자금"].isna().any():
        missing_quarters = sorted(monthly.loc[monthly["FTP_원가성자금"].isna(), "분기"].unique())
        raise ValueError(f"FTP 금리 매핑 누락: {missing_quarters}")
    return monthly


def build_profitability_panel(
    source: pd.DataFrame,
    bank_rates: pd.DataFrame,
) -> pd.DataFrame:
    """Reproduce the notebook's monthly FTP contribution and complete 12M values."""
    missing = [column for column in PROFIT_SOURCE_COLUMNS if column not in source.columns]
    if missing:
        raise ValueError(f"수익성 원천 필수 컬럼이 없습니다: {missing}")

    work = source.loc[:, PROFIT_SOURCE_COLUMNS].copy()
    work["기준월"] = pd.to_datetime(
        work["기준년월"].astype(str), format="%Y%m", errors="coerce"
    )
    if work["기준월"].isna().any():
        raise ValueError("수익성 기준년월 파싱에 실패했습니다.")
    if work.duplicated(["법인ID", "기준월"]).any():
        raise ValueError("수익성 원천에 법인ID+기준월 중복이 있습니다.")

    balance_columns = PROFIT_SOURCE_COLUMNS[2:]
    balances = work.loc[:, balance_columns].apply(pd.to_numeric, errors="coerce")
    if balances.isna().any().any():
        raise ValueError("수익성 원천 잔액에 결측 또는 비수치 값이 있습니다.")
    if balances.lt(0).any().any():
        raise ValueError("수익성 원천 잔액에 음수가 있습니다.")
    work.loc[:, balance_columns] = balances
    work = work.sort_values(["법인ID", "기준월"]).reset_index(drop=True)

    work["대출잔액_월말"] = work["여신_운전자금대출잔액"] + work["여신_시설자금대출잔액"]
    work["저축성수신잔액_월말"] = work["거치식예금잔액"] + work["적립식예금잔액"]
    work["요구불예금잔액_월말"] = work["요구불예금잔액"]
    for month_end, monthly_average in (
        ("대출잔액_월말", "대출잔액_월평균"),
        ("저축성수신잔액_월말", "저축성수신잔액_월평균"),
        ("요구불예금잔액_월말", "요구불예금잔액_월평균"),
    ):
        previous = work.groupby("법인ID", sort=False)[month_end].shift(1)
        work[monthly_average] = np.where(
            previous.notna(), (previous + work[month_end]) / 2, work[month_end]
        )

    rates = _build_bank_rate_month(bank_rates)
    work = work.merge(
        rates[["기준월", "기업대출금리", "저축성수신금리", "FTP_원가성자금"]],
        on="기준월",
        how="left",
        validate="many_to_one",
    )
    rate_columns = ["기업대출금리", "저축성수신금리", "FTP_원가성자금"]
    if work[rate_columns].isna().any().any():
        missing_months = work.loc[work[rate_columns].isna().any(axis=1), "기준월"].dt.strftime("%Y-%m").unique()
        raise ValueError(f"금리 매핑 누락: {sorted(missing_months.tolist())}")

    annualization = work["기준월"].dt.days_in_month / 365
    work["V_FTP_월"] = (
        work["대출잔액_월평균"] * (work["기업대출금리"] - work["FTP_원가성자금"])
        + work["저축성수신잔액_월평균"] * (work["FTP_원가성자금"] - work["저축성수신금리"])
        + work["요구불예금잔액_월평균"] * (work["FTP_원가성자금"] - DEMAND_DEPOSIT_RATE)
    ) * annualization
    work["V_FTP_12M"] = work.groupby("법인ID", sort=False)["V_FTP_월"].transform(
        lambda values: values.rolling(window=12, min_periods=12).sum()
    )
    work["V_FTP_12M_방어가치"] = work["V_FTP_12M"].clip(lower=0)
    result = work.dropna(subset=["V_FTP_12M"]).copy()
    result["기준월"] = result["기준월"].dt.strftime("%Y-%m")
    return result.loc[:, PROFIT_OUTPUT_COLUMNS].reset_index(drop=True)


def prepare_and_load_service_database(
    *,
    source_path: Path,
    bank_rates_path: Path,
    risk_scores_path: Path,
    shap_local_path: Path,
    derived_dir: Path,
    database_path: Path,
    as_of_month: str | None = None,
) -> LoadSummary:
    """Create missing derived CSVs, then atomically build the service database."""
    source = pd.read_csv(source_path)
    bank_rates = pd.read_csv(bank_rates_path)
    segment_panel = build_service_segment_panel(source)
    profitability = build_profitability_panel(source, bank_rates)

    derived_dir.mkdir(parents=True, exist_ok=True)
    segment_path = derived_dir / "segment_panel.csv"
    profitability_path = derived_dir / "profitability.csv"
    segment_panel.to_csv(segment_path, index=False, encoding="utf-8-sig")
    profitability.to_csv(profitability_path, index=False, encoding="utf-8-sig")

    return load_service_database(
        ServiceSourcePaths(
            source=source_path,
            risk_scores=risk_scores_path,
            segment_panel=segment_path,
            profitability=profitability_path,
            shap_local=shap_local_path,
        ),
        database_path,
        as_of_month,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="기존 분석 CSV에서 RM 서비스 입력을 파생하고 SQLite DB를 적재합니다."
    )
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE_PATH)
    parser.add_argument("--bank-rates", type=Path, default=DEFAULT_BANK_RATES_PATH)
    parser.add_argument("--risk-scores", type=Path, default=DEFAULT_RISK_SCORES_PATH)
    parser.add_argument("--shap-local", type=Path, default=DEFAULT_SHAP_LOCAL_PATH)
    parser.add_argument("--derived-dir", type=Path, default=DEFAULT_DERIVED_DIR)
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE_PATH)
    parser.add_argument("--as-of-month")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        summary = prepare_and_load_service_database(
            source_path=args.source,
            bank_rates_path=args.bank_rates,
            risk_scores_path=args.risk_scores,
            shap_local_path=args.shap_local,
            derived_dir=args.derived_dir,
            database_path=args.database,
            as_of_month=args.as_of_month,
        )
    except Exception as error:
        print(error)
        return 1
    print(json.dumps(vars(summary), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
