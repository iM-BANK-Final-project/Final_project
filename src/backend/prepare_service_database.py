"""Build final M12 CLV inputs and atomically load the RM service database."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence

import pandas as pd

from src.backend.load_service_database import (
    DEFAULT_DATABASE_PATH,
    LoadSummary,
    ServiceSourcePaths,
    load_service_database,
)
from src.backend.m12_clv import (
    EXPECTED_MONTHS,
    build_monthly_rates,
    build_operating_clv,
)


DEFAULT_SOURCE_PATH = Path("outputs/iM뱅크데이터_거시경제지표포함.csv")
DEFAULT_RISK_SCORES_PATH = Path(
    "src/models/web_m12_intervene_v2_scores_202512_all_3372.csv"
)
DEFAULT_FTP_PATH = Path("outputs/iM뱅크_월별_추정FTP_2023_2025.csv")
DEFAULT_BANK_RATES_PATH = Path("outputs/예대금리차2023~2025_순.csv")
DEFAULT_DERIVED_DIR = Path("outputs/rm_service_inputs")
OPERATING_CUTOFF = "2025-12"
EXPECTED_SOURCE_FIRMS = 3372
EXPECTED_ELIGIBLE_FIRMS = 3341


def _require_columns(
    frame: pd.DataFrame,
    columns: tuple[str, ...],
    label: str,
) -> None:
    missing = sorted(set(columns).difference(frame.columns))
    if missing:
        raise ValueError(f"{label} 필수 컬럼이 없습니다: {missing}")


def _boolean_values(series: pd.Series, label: str) -> pd.Series:
    if pd.api.types.is_bool_dtype(series):
        return series.astype(bool)
    normalized = series.astype("string").str.strip().str.lower().map(
        {"true": True, "false": False, "1": True, "0": False}
    )
    if normalized.isna().any():
        raise ValueError(f"{label}은 true 또는 false여야 합니다.")
    return normalized.astype(bool)


def validate_source_panel(
    source: pd.DataFrame,
    *,
    expected_firms: int = EXPECTED_SOURCE_FIRMS,
) -> None:
    """Validate the complete 2023-01 through 2025-12 customer-month panel."""
    _require_columns(source, ("법인ID", "기준년월"), "원천 패널")
    if source["법인ID"].isna().any():
        raise ValueError("원천 패널 법인ID에 결측이 있습니다.")
    work = source.loc[:, ["법인ID", "기준년월"]].copy()
    work["법인ID"] = work["법인ID"].astype("string")
    try:
        work["월"] = pd.PeriodIndex(work["기준년월"].astype(str), freq="M")
    except ValueError as error:
        raise ValueError("원천 패널 기준년월 형식을 해석할 수 없습니다.") from error
    if work.duplicated(["법인ID", "월"]).any():
        raise ValueError("원천 패널에 법인ID+기준년월 중복이 있습니다.")
    if work["법인ID"].nunique() != expected_firms:
        raise ValueError(
            f"원천 패널 법인은 정확히 {expected_firms:,}개여야 합니다."
        )
    counts = work.groupby("법인ID")["월"].nunique()
    if not counts.eq(36).all():
        raise ValueError("원천 패널은 법인별 완전관측 36개월이어야 합니다.")
    if set(work["월"].unique()) != set(EXPECTED_MONTHS):
        raise ValueError("원천 패널 기간은 2023-01~2025-12의 연속 36개월이어야 합니다.")
    if len(work) != expected_firms * 36:
        raise ValueError("원천 패널 행 수가 법인 수 × 36개월과 일치하지 않습니다.")


def filter_eligible_operating_scores(
    scores: pd.DataFrame,
    *,
    expected_count: int = EXPECTED_ELIGIBLE_FIRMS,
) -> pd.DataFrame:
    """Select and lock the final target-evaluable 2025-12 operating population."""
    required = (
        "법인ID",
        "cutoff_month",
        "score_eligible",
        "risk_probability",
    )
    _require_columns(scores, required, "운영 점수")
    work = scores.copy()
    if work["법인ID"].isna().any():
        raise ValueError("운영 점수 법인ID에 결측이 있습니다.")
    work["법인ID"] = work["법인ID"].astype("string")
    if work["법인ID"].duplicated().any():
        raise ValueError("운영 점수 법인ID가 중복되었습니다.")
    cutoff = pd.to_numeric(work["cutoff_month"], errors="coerce")
    if cutoff.isna().any() or not cutoff.eq(202512).all():
        raise ValueError("운영 점수 기준월은 모두 2025-12여야 합니다.")
    work["score_eligible"] = _boolean_values(work["score_eligible"], "score_eligible")
    work["risk_probability"] = pd.to_numeric(
        work["risk_probability"], errors="coerce"
    )
    if (
        work["risk_probability"].isna().any()
        or not work["risk_probability"].between(0, 1).all()
    ):
        raise ValueError("운영 점수 위험확률은 0과 1 사이여야 합니다.")
    eligible = work.loc[work["score_eligible"]].copy()
    if len(eligible) != expected_count or eligible["법인ID"].nunique() != expected_count:
        raise ValueError(
            f"적격 운영 모집단은 정확히 {expected_count:,}개 법인이어야 합니다."
        )
    return eligible.reset_index(drop=True)


def build_final_clv(
    source: pd.DataFrame,
    ftp: pd.DataFrame,
    bank_rates: pd.DataFrame,
    scores: pd.DataFrame,
    *,
    expected_source_firms: int | None = None,
    expected_count: int = EXPECTED_ELIGIBLE_FIRMS,
) -> pd.DataFrame:
    """Validate final inputs and reproduce the notebook's 2025-12 CLV output."""
    source_firms = (
        source["법인ID"].nunique()
        if expected_source_firms is None
        else expected_source_firms
    )
    validate_source_panel(source, expected_firms=source_firms)
    eligible_scores = filter_eligible_operating_scores(
        scores, expected_count=expected_count
    )
    rates = build_monthly_rates(ftp, bank_rates)
    result = build_operating_clv(
        source,
        rates,
        eligible_scores,
        cutoff=OPERATING_CUTOFF,
    )
    if len(result) != expected_count or result["법인ID"].nunique() != expected_count:
        raise ValueError("CLV 결과가 적격 운영 모집단과 일치하지 않습니다.")
    return result


def prepare_and_load_service_database(
    *,
    source_path: Path,
    operating_scores_path: Path,
    ftp_path: Path,
    bank_rates_path: Path,
    derived_dir: Path,
    database_path: Path,
    as_of_month: str | None = None,
) -> LoadSummary:
    """Create the final CLV artifact, then atomically rebuild the service DB."""
    source = pd.read_csv(source_path, dtype={"법인ID": "string"}, low_memory=False)
    scores = pd.read_csv(
        operating_scores_path,
        dtype={"법인ID": "string"},
        low_memory=False,
    )
    ftp = pd.read_csv(ftp_path)
    bank_rates = pd.read_csv(bank_rates_path)
    clv = build_final_clv(
        source,
        ftp,
        bank_rates,
        scores,
        expected_source_firms=EXPECTED_SOURCE_FIRMS,
        expected_count=EXPECTED_ELIGIBLE_FIRMS,
    )

    derived_dir.mkdir(parents=True, exist_ok=True)
    clv_path = derived_dir / "clv_202512.csv"
    clv.to_csv(clv_path, index=False, encoding="utf-8-sig", float_format="%.10f")
    return load_service_database(
        ServiceSourcePaths(
            source=source_path,
            operating_scores=operating_scores_path,
            clv=clv_path,
        ),
        database_path,
        as_of_month or OPERATING_CUTOFF,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="최종 M12 위험점수와 FISIM CLV로 RM 서비스 DB를 생성합니다."
    )
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE_PATH)
    parser.add_argument(
        "--operating-scores", type=Path, default=DEFAULT_RISK_SCORES_PATH
    )
    parser.add_argument("--ftp", type=Path, default=DEFAULT_FTP_PATH)
    parser.add_argument("--bank-rates", type=Path, default=DEFAULT_BANK_RATES_PATH)
    parser.add_argument("--derived-dir", type=Path, default=DEFAULT_DERIVED_DIR)
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE_PATH)
    parser.add_argument("--as-of-month", default=OPERATING_CUTOFF)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        summary = prepare_and_load_service_database(
            source_path=args.source,
            operating_scores_path=args.operating_scores,
            ftp_path=args.ftp,
            bank_rates_path=args.bank_rates,
            derived_dir=args.derived_dir,
            database_path=args.database,
            as_of_month=args.as_of_month,
        )
    except Exception as error:
        print(error, file=sys.stderr)
        return 1
    print(json.dumps(vars(summary), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
