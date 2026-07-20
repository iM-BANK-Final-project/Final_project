from pathlib import Path

import pandas as pd
import pytest

from src.backend.prepare_service_database import (
    build_profitability_panel,
    build_service_segment_panel,
)
from src.segmentation.relationship_segments import SegmentationConfig


def _segmentation_source() -> pd.DataFrame:
    config = SegmentationConfig()
    rows = []
    for customer_id, scale in (("A", 1.0), ("B", 2.0), ("C", 3.0)):
        for month in pd.period_range("2023-01", "2025-12", freq="M"):
            row = {
                "법인ID": customer_id,
                "기준년월": int(month.strftime("%Y%m")),
            }
            row.update({column: scale for column in config.amount_cols})
            rows.append(row)
    return pd.DataFrame(rows)


def _bank_rates_2023() -> pd.DataFrame:
    months = [f"2023년{month:02d}월" for month in range(1, 13)]
    return pd.DataFrame(
        [
            {"은행": "iM뱅크(구 대구은행)", "구분": "기업대출금리", **dict.fromkeys(months, 5.0)},
            {"은행": None, "구분": "저축성수신금리", **dict.fromkeys(months, 2.0)},
        ]
    )


def _profitability_source() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "법인ID": ["A"] * 12,
            "기준년월": [int(month.strftime("%Y%m")) for month in pd.period_range("2023-01", "2023-12", freq="M")],
            "요구불예금잔액": [20.0] * 12,
            "거치식예금잔액": [30.0] * 12,
            "적립식예금잔액": [20.0] * 12,
            "여신_운전자금대출잔액": [70.0] * 12,
            "여신_시설자금대출잔액": [30.0] * 12,
        }
    )


def test_build_service_segment_panel_derives_required_loader_columns():
    result = build_service_segment_panel(_segmentation_source())

    assert list(result.columns) == [
        "법인ID",
        "기준년월",
        "관계세그먼트",
        "거래활동점수",
        "수신관계점수",
        "여신관계점수",
    ]
    assert result["기준년월"].min() == "2023-12"
    assert result["기준년월"].max() == "2025-12"
    assert len(result) == 3 * 25


def test_build_profitability_panel_matches_notebook_ftp_contract():
    result = build_profitability_panel(_profitability_source(), _bank_rates_2023())

    assert list(result.columns) == [
        "법인ID",
        "기준월",
        "V_FTP_12M",
        "V_FTP_12M_방어가치",
    ]
    assert result["기준월"].tolist() == ["2023-12"]
    assert result.loc[0, "V_FTP_12M"] == pytest.approx(3.182)
    assert result.loc[0, "V_FTP_12M_방어가치"] == pytest.approx(3.182)


def test_build_profitability_panel_rejects_missing_monthly_rates():
    incomplete_rates = _bank_rates_2023().drop(columns="2023년12월")

    with pytest.raises(ValueError, match="금리 매핑 누락"):
        build_profitability_panel(_profitability_source(), incomplete_rates)
