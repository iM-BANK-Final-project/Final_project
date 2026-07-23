from pathlib import Path

import pandas as pd
import pytest

from src.backend.prepare_service_database import (
    DEFAULT_BANK_RATES_PATH,
    DEFAULT_FTP_PATH,
    DEFAULT_RISK_SCORES_PATH,
    _write_clv_artifact,
    build_final_clv,
    filter_eligible_operating_scores,
    validate_source_panel,
)


def _minimal_panel() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "법인ID": ["A"] * 36,
            "기준년월": [
                int(month.strftime("%Y%m"))
                for month in pd.period_range("2023-01", "2025-12", freq="M")
            ],
        }
    )


def _source_with_balances() -> pd.DataFrame:
    panel = _minimal_panel()
    panel["여신_운전자금대출잔액"] = 100.0
    panel["여신_시설자금대출잔액"] = 0.0
    panel["거치식예금잔액"] = 0.0
    panel["적립식예금잔액"] = 0.0
    panel["요구불예금잔액"] = 0.0
    return panel


def _ftp() -> pd.DataFrame:
    months = pd.period_range("2023-01", "2025-12", freq="M")
    return pd.DataFrame(
        {
            "month": months.astype(str),
            "monthly_recombined_ytd_rate_decimal": [0.002] * 36,
        }
    )


def _bank_rates() -> pd.DataFrame:
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


def test_default_paths_point_to_final_repository_artifacts():
    assert DEFAULT_RISK_SCORES_PATH == Path(
        "src/models/web_m12_final_scores_202512_all_3372.csv"
    )
    assert DEFAULT_FTP_PATH == Path("outputs/iM뱅크_월별_추정FTP_2023_2025.csv")
    assert DEFAULT_BANK_RATES_PATH == Path("outputs/예대금리차2023~2025_순.csv")


def test_final_164_score_artifact_is_locked_and_filters_to_3341():
    scores = pd.read_csv(
        "src/models/web_m12_final_scores_202512_all_3372.csv",
        dtype={"법인ID": "string"},
        low_memory=False,
    )

    eligible = filter_eligible_operating_scores(scores)

    assert len(eligible) == 3341
    assert eligible["risk_band"].value_counts().to_dict() == {
        "G5_REST": 3006,
        "G4_5_TO_10": 167,
        "G2_1_TO_3": 67,
        "G3_3_TO_5": 67,
        "G1_TOP_1": 34,
    }
    assert eligible["predicted_positive_model_scope"].sum() == 181


def test_final_164_score_artifact_rejects_changed_model_metadata():
    scores = pd.read_csv(
        "src/models/web_m12_final_scores_202512_all_3372.csv",
        dtype={"법인ID": "string"},
        low_memory=False,
    )
    scores.loc[0, "feature_set"] = "UNEXPECTED"

    with pytest.raises(ValueError, match="feature_set"):
        filter_eligible_operating_scores(scores)


def test_validate_source_panel_requires_complete_consecutive_36_months():
    validate_source_panel(_minimal_panel(), expected_firms=1)

    incomplete = _minimal_panel().iloc[:-1]
    with pytest.raises(ValueError, match="36개월"):
        validate_source_panel(incomplete, expected_firms=1)


def test_filter_eligible_operating_scores_enforces_count_and_unique_ids():
    scores = pd.DataFrame(
        {
            "법인ID": ["A", "B", "C"],
            "cutoff_month": [202512] * 3,
            "score_eligible": [True, False, True],
            "risk_probability": [0.8, 0.7, 0.6],
        }
    )

    result = filter_eligible_operating_scores(scores, expected_count=2)

    assert result["법인ID"].tolist() == ["A", "C"]
    with pytest.raises(ValueError, match="적격 운영 모집단"):
        filter_eligible_operating_scores(scores, expected_count=3)

    duplicated = pd.concat([scores, scores.iloc[[0]]], ignore_index=True)
    with pytest.raises(ValueError, match="중복"):
        filter_eligible_operating_scores(duplicated, expected_count=2)


def test_build_final_clv_reproduces_actual_six_month_fisim_formula():
    scores = pd.DataFrame(
        {
            "법인ID": ["A"],
            "cutoff_month": [202512],
            "score_eligible": [True],
            "risk_probability": [0.5],
        }
    )

    result = build_final_clv(
        _source_with_balances(),
        _ftp(),
        _bank_rates(),
        scores,
        expected_count=1,
    )

    assert result.loc[0, "기준월"] == "2025-12"
    assert result.loc[0, "수익성월수"] == 6
    assert result.loc[0, "수익성기간"] == "2025-07~2025-12"
    assert result.loc[0, "CLV_NoRisk"] == pytest.approx(100.0 * 0.038 * 6)
    assert result.loc[0, "CLV_Risk"] == pytest.approx(
        result.loc[0, "CLV_NoRisk"] / 1.5
    )
    assert result.loc[0, "PotentialLoss"] == pytest.approx(
        result.loc[0, "CLV_NoRisk"] - result.loc[0, "CLV_Risk"]
    )


def test_build_final_clv_keeps_source_and_eligible_population_locks_separate():
    source_a = _source_with_balances()
    source_b = source_a.assign(법인ID="B")
    source = pd.concat([source_a, source_b], ignore_index=True)
    scores = pd.DataFrame(
        {
            "법인ID": ["A", "B"],
            "cutoff_month": [202512, 202512],
            "score_eligible": [True, False],
            "risk_probability": [0.0, 0.5],
        }
    )

    result = build_final_clv(
        source,
        _ftp(),
        _bank_rates(),
        scores,
        expected_source_firms=2,
        expected_count=1,
    )

    assert result["법인ID"].tolist() == ["A"]


def test_clv_artifact_preserves_risk_probability_for_strict_join(tmp_path):
    probability = 0.017202704348169298
    frame = pd.DataFrame(
        {
            "법인ID": ["A"],
            "risk_probability": [probability],
            "CLV_Risk": [123.45678901234567],
        }
    )
    path = tmp_path / "clv.csv"

    _write_clv_artifact(frame, path)
    restored = pd.read_csv(path)

    assert restored.loc[0, "risk_probability"] == pytest.approx(
        probability, rel=0, abs=1e-12
    )
