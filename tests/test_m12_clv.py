import numpy as np
import pandas as pd
import pytest

from src.backend.m12_clv import (
    build_monthly_fisim,
    build_monthly_rates,
    build_operating_clv,
)


def _ftp_36_months() -> pd.DataFrame:
    months = pd.period_range("2023-01", "2025-12", freq="M")
    return pd.DataFrame(
        {
            "month": months.astype(str),
            "monthly_recombined_ytd_rate_decimal": [0.002] * len(months),
        }
    )


def _bank_rates_36_months() -> pd.DataFrame:
    month_columns = {
        month.strftime("%Y년%m월"): [4.0, 1.0]
        for month in pd.date_range("2023-01-01", "2025-12-01", freq="MS")
    }
    return pd.DataFrame(
        {
            "은행": ["iM뱅크(구 대구은행)", None],
            "구분": ["기업대출금리", "저축성수신금리"],
            **month_columns,
        }
    )


def _source_row(
    *,
    corporate_id: str = "A",
    month: int = 202512,
    working_loan: float = 100.0,
    facility_loan: float = 50.0,
    fixed_deposit: float = 20.0,
    installment_deposit: float = 10.0,
    demand_deposit: float = 40.0,
) -> dict[str, object]:
    return {
        "법인ID": corporate_id,
        "기준년월": month,
        "여신_운전자금대출잔액": working_loan,
        "여신_시설자금대출잔액": facility_loan,
        "거치식예금잔액": fixed_deposit,
        "적립식예금잔액": installment_deposit,
        "요구불예금잔액": demand_deposit,
    }


def test_monthly_rates_apply_notebook_units_and_demand_deposit_assumption():
    result = build_monthly_rates(_ftp_36_months(), _bank_rates_36_months())

    assert len(result) == 36
    december = result.loc[result["월"].eq(pd.Period("2025-12", freq="M"))].iloc[0]
    assert december["기업대출금리_월_decimal"] == pytest.approx(0.04)
    assert december["저축성수신금리_월_decimal"] == pytest.approx(0.01)
    assert december["FTP_월_decimal"] == pytest.approx(0.002)
    assert december["대출스프레드_월"] == pytest.approx(0.038)
    assert december["저축성수신스프레드_월"] == pytest.approx(-0.008)
    assert december["요구불스프레드_월"] == pytest.approx(0.0019)


def test_monthly_rates_reject_incomplete_ftp_history():
    with pytest.raises(ValueError, match="36개월"):
        build_monthly_rates(_ftp_36_months().iloc[:-1], _bank_rates_36_months())


def test_monthly_fisim_uses_month_end_balances_without_annualization():
    rates = pd.DataFrame(
        {
            "월": [pd.Period("2025-12", freq="M")],
            "대출스프레드_월": [0.04],
            "저축성수신스프레드_월": [0.01],
            "요구불스프레드_월": [0.002],
        }
    )
    source = pd.DataFrame([_source_row()])

    result = build_monthly_fisim(source, rates)

    assert result.loc[0, "대출잔액_L"] == 150.0
    assert result.loc[0, "저축성수신잔액_DS"] == 30.0
    assert result.loc[0, "요구불잔액_DR"] == 40.0
    assert result.loc[0, "FISIM_CONTRIB_M"] == pytest.approx(
        150.0 * 0.04 + 30.0 * 0.01 + 40.0 * 0.002
    )


@pytest.mark.parametrize("invalid", [np.nan, -1.0])
def test_monthly_fisim_rejects_missing_or_negative_balances(invalid):
    source = pd.DataFrame([_source_row(demand_deposit=invalid)])
    rates = pd.DataFrame(
        {
            "월": [pd.Period("2025-12", freq="M")],
            "대출스프레드_월": [0.04],
            "저축성수신스프레드_월": [0.01],
            "요구불스프레드_월": [0.002],
        }
    )

    with pytest.raises(ValueError, match="비음수"):
        build_monthly_fisim(source, rates)


def _forecast_source() -> pd.DataFrame:
    rows = []
    for corporate_id, loan in [("A", 100.0), ("B", 100.0), ("NEG", 0.0), ("ZERO", 200.0)]:
        for month in range(202501, 202507):
            rows.append(
                _source_row(
                    corporate_id=corporate_id,
                    month=month,
                    working_loan=loan,
                    facility_loan=0.0,
                    fixed_deposit=100.0 if corporate_id == "NEG" else 0.0,
                    installment_deposit=0.0,
                    demand_deposit=0.0,
                )
            )
    return pd.DataFrame(rows)


def _cutoff_rates() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "월": [pd.Period("2025-12", freq="M")],
            "대출스프레드_월": [0.01],
            "저축성수신스프레드_월": [-0.01],
            "요구불스프레드_월": [0.002],
        }
    )


def _scores() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "법인ID": ["B", "A", "NEG", "ZERO"],
            "risk_probability": [0.5, 0.5, 0.5, 0.0],
        }
    )


def test_operating_clv_matches_six_month_survival_formula_and_rank_order():
    result = build_operating_clv(
        _forecast_source(), _cutoff_rates(), _scores(), cutoff="2025-12"
    ).set_index("법인ID")

    survival = np.power(1 - 0.5, np.arange(1, 7) / 6.0)
    expected_clv_risk = np.sum(survival / 1.5)
    assert result.loc["A", "CLV_NoRisk"] == pytest.approx(6.0)
    assert result.loc["A", "CLV_Risk"] == pytest.approx(expected_clv_risk)
    assert result.loc["A", "PotentialLoss"] == pytest.approx(6.0 - expected_clv_risk)
    assert result.loc["A", "defense_rank"] == 1
    assert result.loc["B", "defense_rank"] == 2


def test_operating_clv_preserves_negative_value_and_leaves_nondefense_rank_null():
    result = build_operating_clv(
        _forecast_source(), _cutoff_rates(), _scores(), cutoff="2025-12"
    ).set_index("법인ID")

    assert result.loc["NEG", "CLV_NoRisk"] == pytest.approx(-6.0)
    assert result.loc["NEG", "PotentialLoss"] < 0
    assert result.loc["NEG", "defense_value"] == 0
    assert pd.isna(result.loc["NEG", "defense_rank"])
    assert result.loc["ZERO", "PotentialLoss"] == pytest.approx(0)
    assert pd.isna(result.loc["ZERO", "defense_rank"])


def test_operating_clv_requires_exactly_six_reference_months_per_firm():
    incomplete = _forecast_source().loc[
        lambda frame: ~(
            frame["법인ID"].eq("A") & frame["기준년월"].eq(202506)
        )
    ]

    with pytest.raises(ValueError, match="6개월"):
        build_operating_clv(incomplete, _cutoff_rates(), _scores(), cutoff="2025-12")


def test_operating_clv_rejects_probability_outside_unit_interval():
    scores = _scores()
    scores.loc[scores["법인ID"].eq("A"), "risk_probability"] = 1.1

    with pytest.raises(ValueError, match="0과 1"):
        build_operating_clv(_forecast_source(), _cutoff_rates(), scores)
