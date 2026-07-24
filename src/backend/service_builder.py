"""Validate final M12 artifacts and build RM service snapshot tables."""

from __future__ import annotations

from dataclasses import dataclass
import json
import re

import numpy as np
import pandas as pd


MODEL_NAME = "FS_FINAL_164_TUNED_LIGHTGBM_PLATT"
TREND_MODEL_NAME = MODEL_NAME
MODEL_THRESHOLD = 0.26479401324821045
VALID_GRADES = {"일반", "우수", "최우수"}
VALID_DEDICATED = {"N", "Y"}
SIGNAL_SOURCE_COLUMNS = {
    "입출금": ("요구불입금금액", "요구불출금금액"),
    "자동이체": ("자동이체금액",),
    "채널": (
        "창구거래금액",
        "인터넷뱅킹거래금액",
        "스마트뱅킹거래금액",
        "폰뱅킹거래금액",
        "ATM거래금액",
    ),
    "카드": ("신용카드사용금액", "체크카드사용금액"),
}
SCORE_CHANGE_COLUMNS = {
    "입출금": "요구불_최근3대이전9_변화율_pct",
    "자동이체": "자동이체_최근3대이전9_변화율_pct",
    "채널": "채널_최근3대이전9_변화율_pct",
    "카드": "카드_최근3대이전9_변화율_pct",
}
RECOMMENDED_ACTIONS = {
    "입출금": "자금관리 상담, CMS, 결제성 거래 점검",
    "자동이체": "자동이체 등록·해지 내역 점검, 결제성 거래 상담",
    "채널": "디지털채널 온보딩, 이용 장애·불편 확인",
    "카드": "법인카드 이용조건 점검, 한도·혜택 상담",
    "복합 거래활동": "RM 직접 접촉, 관계 회복 상담",
}
RISK_BAND_PRIORITIES = {
    "G1_TOP_1": "URGENT",
    "G2_1_TO_3": "HIGH",
    "G3_3_TO_5": "MEDIUM_HIGH",
    "G4_5_TO_10": "MEDIUM",
    "G5_REST": "WATCH",
}
CONTACT_STRATEGIES = {
    "URGENT": "RM 최우선 직접 접촉",
    "HIGH": "RM 우선 직접 접촉",
    "MEDIUM_HIGH": "RM 조기 계획 접촉",
    "MEDIUM": "RM 계획 접촉",
    "WATCH": "모니터링 후 필요 시 접촉",
}
SHAP_FACTOR_COUNT = 10
SHAP_SCORE_COLUMNS = tuple(
    column
    for rank in range(1, SHAP_FACTOR_COUNT + 1)
    for column in (f"shap_top{rank}_feature", f"shap_top{rank}_value")
)
OPERATING_SCORE_COLUMNS = (
    "법인ID",
    "cutoff_month",
    "score_eligible",
    "SEG__baseline_segment_2023",
    "SEG__current_segment",
    "SEG__transition",
    "CTX__업종_대분류__현재",
    "CTX__업종_중분류__현재",
    "risk_probability",
    "risk_rank_eligible",
    "risk_band",
    "risk_band_name",
    "risk_band_order",
    "predicted_positive_model_scope",
    "threshold",
    "target_name",
    "feature_set",
    "feature_count",
    "calibration_method",
    "probability_status",
    *SCORE_CHANGE_COLUMNS.values(),
    *SHAP_SCORE_COLUMNS,
)
CLV_COLUMNS = (
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
)
RISK_TREND_COLUMNS = (
    "as_of_month",
    "eligible_count",
    "average_risk",
    "high_risk_count",
    "high_risk_share",
    "model_name",
)


@dataclass
class ServiceInputs:
    """In-memory final artifacts consumed by the service builder."""

    source: pd.DataFrame
    operating_scores: pd.DataFrame
    clv: pd.DataFrame
    risk_trends: pd.DataFrame


def _require_columns(
    frame: pd.DataFrame,
    columns: tuple[str, ...],
    contract_name: str,
) -> None:
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise ValueError(f"{contract_name} 필수 컬럼이 없습니다: {missing}")


def normalize_month(series: pd.Series) -> pd.Series:
    """Normalize supported monthly representations to ``YYYY-MM`` strings."""
    text = series.astype("string").str.strip()
    compact = text.str.fullmatch(r"\d{6}").fillna(False)
    text = text.mask(compact, text.str.slice(0, 4) + "-" + text.str.slice(4, 6))
    parsed = pd.to_datetime(text, errors="coerce", format="mixed")
    normalized = parsed.dt.to_period("M").astype("string")
    invalid = normalized.isna()
    if invalid.any():
        examples = series.loc[invalid].head(5).tolist()
        raise ValueError(f"기준월 형식 위반: YYYY-MM으로 변환할 수 없습니다: {examples}")
    return normalized


def _normalize_boolean(series: pd.Series, label: str) -> pd.Series:
    if pd.api.types.is_bool_dtype(series):
        return series.astype(bool)
    normalized = series.astype("string").str.strip().str.lower().map(
        {
            "true": True,
            "false": False,
            "1": True,
            "0": False,
            "1.0": True,
            "0.0": False,
        }
    )
    if normalized.isna().any():
        raise ValueError(f"{label}은 true 또는 false여야 합니다.")
    return normalized.astype(bool)


def _normalized_inputs(inputs: ServiceInputs) -> ServiceInputs:
    source_columns = (
        "법인ID",
        "기준년월",
        "업종_대분류",
        "사업장_시도",
        "법인_고객등급",
        "전담고객여부",
        *sum(SIGNAL_SOURCE_COLUMNS.values(), ()),
    )
    _require_columns(inputs.source, source_columns, "원천 데이터")
    _require_columns(inputs.operating_scores, OPERATING_SCORE_COLUMNS, "운영 점수")
    _require_columns(inputs.clv, CLV_COLUMNS, "CLV")
    _require_columns(inputs.risk_trends, RISK_TREND_COLUMNS, "월별 위험 추세")

    source = inputs.source.copy()
    scores = inputs.operating_scores.copy()
    clv = inputs.clv.copy()
    risk_trends = inputs.risk_trends.copy()
    for frame, label in ((source, "원천"), (scores, "운영 점수"), (clv, "CLV")):
        if frame["법인ID"].isna().any():
            raise ValueError(f"{label} 법인ID에 결측이 있습니다.")
        frame["법인ID"] = frame["법인ID"].astype("string")

    source["기준년월"] = normalize_month(source["기준년월"])
    source["사업장_시도"] = source["사업장_시도"].fillna("미상")
    scores["cutoff_month"] = normalize_month(scores["cutoff_month"])
    scores["score_eligible"] = _normalize_boolean(
        scores["score_eligible"], "score_eligible"
    )
    clv["기준월"] = normalize_month(clv["기준월"])
    clv["미래수익성예측사용"] = _normalize_boolean(
        clv["미래수익성예측사용"], "미래수익성예측사용"
    )
    risk_trends["as_of_month"] = normalize_month(risk_trends["as_of_month"])
    return ServiceInputs(source, scores, clv, risk_trends)


def _validated_risk_trends(
    frame: pd.DataFrame,
    scores_month: pd.DataFrame,
    month: str,
) -> pd.DataFrame:
    """Validate the fixed-model six-month aggregate and reconcile its current month."""
    trend = frame.loc[:, RISK_TREND_COLUMNS].copy()
    if trend["as_of_month"].duplicated().any():
        raise ValueError("월별 위험 추세 기준월이 중복되었습니다.")
    trend = trend.sort_values("as_of_month").reset_index(drop=True)
    expected_months = pd.period_range(
        pd.Period(month, freq="M") - 5,
        pd.Period(month, freq="M"),
        freq="M",
    ).astype(str).tolist()
    if trend["as_of_month"].tolist() != expected_months:
        raise ValueError(f"월별 위험 추세는 {expected_months[0]}~{month} 6개월이어야 합니다.")
    if not trend["model_name"].eq(TREND_MODEL_NAME).all():
        raise ValueError(f"월별 위험 추세 모델은 {TREND_MODEL_NAME}이어야 합니다.")

    numeric_columns = (
        "eligible_count",
        "average_risk",
        "high_risk_count",
        "high_risk_share",
    )
    trend = _numeric_contract(trend, numeric_columns, "월별 위험 추세")
    if not trend["average_risk"].between(0, 1).all() or not trend[
        "high_risk_share"
    ].between(0, 1).all():
        raise ValueError("월별 위험 추세 비율은 0과 1 사이여야 합니다.")
    counts = trend[["eligible_count", "high_risk_count"]]
    if (counts < 0).any().any() or not np.equal(counts, np.floor(counts)).all().all():
        raise ValueError("월별 위험 추세 고객 수는 0 이상의 정수여야 합니다.")
    if (trend["high_risk_count"] > trend["eligible_count"]).any():
        raise ValueError("월별 고위험 고객 수는 적격 고객 수를 초과할 수 없습니다.")
    calculated_share = trend["high_risk_count"] / trend["eligible_count"]
    if not np.allclose(calculated_share, trend["high_risk_share"], rtol=0, atol=1e-12):
        raise ValueError("월별 위험 추세 고위험 비중과 고객 수가 일치하지 않습니다.")

    current = trend.iloc[-1]
    threshold = pd.to_numeric(scores_month["threshold"], errors="coerce")
    if threshold.isna().any() or not np.allclose(
        threshold, MODEL_THRESHOLD, rtol=0, atol=1e-12
    ):
        raise ValueError("월별 위험 추세의 운영 임계값이 최종 모델과 일치하지 않습니다.")
    expected = {
        "eligible_count": len(scores_month),
        "average_risk": float(scores_month["risk_probability"].mean()),
        "high_risk_count": int(
            _normalize_boolean(
                scores_month["predicted_positive_model_scope"],
                "predicted_positive_model_scope",
            ).sum()
        ),
    }
    expected["high_risk_share"] = expected["high_risk_count"] / expected["eligible_count"]
    matches = (
        int(current["eligible_count"]) == expected["eligible_count"]
        and int(current["high_risk_count"]) == expected["high_risk_count"]
        and np.isclose(current["average_risk"], expected["average_risk"], rtol=0, atol=1e-12)
        and np.isclose(current["high_risk_share"], expected["high_risk_share"], rtol=0, atol=1e-12)
    )
    if not matches:
        raise ValueError("월별 위험 추세 12월 값이 12월 운영 점수와 일치하지 않습니다.")
    trend[["eligible_count", "high_risk_count"]] = trend[
        ["eligible_count", "high_risk_count"]
    ].astype(int)
    return trend.rename(
        columns={
            "high_risk_count": "threshold_count",
            "high_risk_share": "threshold_share",
        }
    )


def _common_months(inputs: ServiceInputs) -> list[str]:
    return sorted(
        set(inputs.source["기준년월"])
        & set(inputs.operating_scores["cutoff_month"])
        & set(inputs.clv["기준월"])
    )


def select_common_month(inputs: ServiceInputs, requested: str | None) -> str:
    """Select the final common artifact month, or validate an explicit month."""
    normalized = _normalized_inputs(inputs)
    available = _common_months(normalized)
    if not available:
        raise ValueError("운영 점수·원천·CLV 데이터에 공통 기준월이 없습니다.")
    if requested is None:
        return available[-1]
    requested_month = normalize_month(pd.Series([requested])).iloc[0]
    if requested_month not in available:
        raise ValueError(
            f"요청한 공통 기준월 {requested_month}을 사용할 수 없습니다. "
            f"사용 가능 공통 기준월: {available}"
        )
    return requested_month


def _validate_unique(frame: pd.DataFrame, month_column: str, contract: str) -> None:
    if frame.duplicated(["법인ID", month_column], keep=False).any():
        raise ValueError(f"{contract} 법인ID+기준년월 중복이 있습니다.")


def _numeric_contract(
    frame: pd.DataFrame,
    columns: tuple[str, ...],
    contract: str,
    *,
    probability: bool = False,
) -> pd.DataFrame:
    numeric = frame.loc[:, columns].apply(pd.to_numeric, errors="coerce")
    if numeric.isna().any().any():
        invalid = numeric.columns[numeric.isna().any()].tolist()
        raise ValueError(f"{contract} 숫자 또는 결측 계약 위반: {invalid}")
    if probability and not (
        numeric.ge(0).all().all() and numeric.le(1).all().all()
    ):
        raise ValueError(f"{contract} 예측확률은 0과 1 사이여야 합니다.")
    result = frame.copy()
    result.loc[:, columns] = numeric
    return result


def build_weakening_signals(
    history: pd.DataFrame,
    customer_ids: set[str],
    as_of_month: str,
) -> pd.DataFrame:
    """Compare recent three-month activity with the preceding nine months."""
    required = ("법인ID", "기준년월", *sum(SIGNAL_SOURCE_COLUMNS.values(), ()))
    _require_columns(history, required, "약화 신호 원천 데이터")
    month = normalize_month(pd.Series([as_of_month])).iloc[0]
    expected_months = pd.period_range(
        pd.Period(month, freq="M") - 11,
        pd.Period(month, freq="M"),
        freq="M",
    ).astype(str)

    work = history.loc[history["법인ID"].astype(str).isin(customer_ids)].copy()
    work["법인ID"] = work["법인ID"].astype(str)
    work["기준년월"] = normalize_month(work["기준년월"])
    work = work.loc[work["기준년월"].isin(expected_months)].copy()
    if work.duplicated(["법인ID", "기준년월"], keep=False).any():
        raise ValueError("약화 신호 원천 데이터에 법인ID+기준년월 중복이 있습니다.")
    expected_index = pd.MultiIndex.from_product(
        [sorted(customer_ids), expected_months], names=["법인ID", "기준년월"]
    )
    actual_index = pd.MultiIndex.from_frame(work[["법인ID", "기준년월"]])
    if not expected_index.isin(actual_index).all():
        raise ValueError("약화 신호 계산에는 고객별 연속 12개월 이력이 필요합니다.")

    source_columns = sum(SIGNAL_SOURCE_COLUMNS.values(), ())
    numeric = work.loc[:, source_columns].apply(pd.to_numeric, errors="coerce")
    if numeric.isna().any().any():
        invalid = numeric.columns[numeric.isna().any()].tolist()
        raise ValueError(f"약화 신호 원천 금액에 결측이 있습니다: {invalid}")
    if numeric.lt(0).any().any():
        raise ValueError("약화 신호 원천 금액에 음수가 있습니다.")
    work.loc[:, source_columns] = numeric

    rows: list[dict[str, object]] = []
    for customer_id, customer in work.groupby("법인ID", sort=True):
        customer = customer.sort_values("기준년월")
        for signal_type, columns in SIGNAL_SOURCE_COLUMNS.items():
            monthly = customer.loc[:, columns].sum(axis=1)
            previous = float(monthly.iloc[:9].mean())
            recent = float(monthly.iloc[9:].mean())
            change_rate = None if previous == 0 else (recent / previous - 1) * 100
            rows.append(
                {
                    "corporate_id": customer_id,
                    "as_of_month": month,
                    "signal_type": signal_type,
                    "current_value": round(recent, 2),
                    "comparison_value": round(previous, 2),
                    "change_rate": None if change_rate is None else round(change_rate, 2),
                }
            )
    signals = pd.DataFrame(rows)
    signals["signal_rank"] = signals.groupby("corporate_id")["change_rate"].rank(
        method="min", ascending=True, na_option="bottom"
    ).astype(int)
    return signals


def classify_weakening_type(signals: pd.DataFrame) -> pd.DataFrame:
    """Classify each customer as a single or multi-axis weakening type."""
    required = ("corporate_id", "as_of_month", "signal_type", "change_rate")
    _require_columns(signals, required, "약화 신호")
    rows: list[dict[str, str]] = []
    for (customer_id, month), customer in signals.groupby(
        ["corporate_id", "as_of_month"], sort=False
    ):
        comparable = customer.loc[customer["change_rate"].notna()].copy()
        if comparable["change_rate"].le(-20.0).sum() >= 2:
            weakening_type = "복합 거래활동"
        elif comparable.empty:
            weakening_type = "미분류"
        else:
            weakening_type = comparable.sort_values(
                ["change_rate", "signal_type"], kind="stable"
            ).iloc[0]["signal_type"]
        rows.append(
            {
                "corporate_id": customer_id,
                "as_of_month": month,
                "weakening_type": weakening_type,
            }
        )
    return pd.DataFrame(rows)


def build_recommendations(
    snapshots: pd.DataFrame,
    signals: pd.DataFrame,
) -> pd.DataFrame:
    """Build deterministic RM copy from validated risk, segment, and signals."""
    required = (
        "corporate_id",
        "as_of_month",
        "risk_probability",
        "risk_band",
        "segment_name",
    )
    _require_columns(snapshots, required, "고객 스냅샷")
    classified = classify_weakening_type(signals)
    recommendations = snapshots.loc[:, required].merge(
        classified,
        on=["corporate_id", "as_of_month"],
        how="left",
        validate="one_to_one",
    )
    if recommendations["weakening_type"].isna().any():
        raise ValueError("고객 스냅샷의 약화 신호 분류가 없습니다.")
    probabilities = pd.to_numeric(recommendations["risk_probability"], errors="coerce")
    if probabilities.isna().any() or probabilities.lt(0).any() or probabilities.gt(1).any():
        raise ValueError("고객 스냅샷 예측확률은 0과 1 사이여야 합니다.")
    recommendations["priority_level"] = recommendations["risk_band"].map(
        RISK_BAND_PRIORITIES
    )
    if recommendations["priority_level"].isna().any():
        raise ValueError("고객 스냅샷 risk_band 허용값 위반이 있습니다.")
    recommendations["recommended_action"] = recommendations["weakening_type"].map(
        RECOMMENDED_ACTIONS
    )
    recommendations["contact_strategy"] = recommendations["priority_level"].map(
        CONTACT_STRATEGIES
    )
    recommendations["reason"] = recommendations.apply(
        lambda row: (
            f"{row['weakening_type']} 신호와 향후 6개월 지속거래약화 가능성 "
            f"{row['risk_probability']:.1%}를 고려한 조기관리 대상"
        ),
        axis=1,
    )
    recommendations["strategy_summary"] = recommendations.apply(
        lambda row: (
            f"{row['segment_name']} 세그먼트의 {row['priority_level']} 관리 대상입니다. "
            f"{row['recommended_action']}을 우선 검토합니다."
        ),
        axis=1,
    )
    unclassified = recommendations["weakening_type"].eq("미분류")
    recommendations.loc[unclassified, "contact_strategy"] = "RM 확인"
    recommendations.loc[unclassified, "recommended_action"] = "거래이력 확인 후 RM 판단"
    recommendations.loc[unclassified, "reason"] = (
        "비교 분모를 산출할 수 없어 약화 원인을 판단하지 않았습니다."
    )
    recommendations.loc[unclassified, "strategy_summary"] = recommendations.loc[
        unclassified, "segment_name"
    ].map(
        lambda segment: (
            f"{segment} 세그먼트이나 비교 분모를 산출할 수 없어 "
            "약화 원인을 판단하지 않았습니다. 거래이력 확인 후 RM 판단이 필요합니다."
        )
    )
    return recommendations.loc[
        :,
        [
            "corporate_id",
            "as_of_month",
            "weakening_type",
            "priority_level",
            "reason",
            "contact_strategy",
            "recommended_action",
            "strategy_summary",
        ],
    ]


def _apply_score_changes(
    signals: pd.DataFrame,
    scores: pd.DataFrame,
) -> pd.DataFrame:
    lookup: dict[tuple[str, str], float] = {}
    for row in scores.itertuples(index=False):
        customer_id = str(getattr(row, "법인ID"))
        row_values = scores.loc[scores["법인ID"].eq(customer_id)].iloc[0]
        for signal_type, column in SCORE_CHANGE_COLUMNS.items():
            lookup[(customer_id, signal_type)] = float(row_values[column])
    result = signals.copy()
    result["change_rate"] = [
        lookup[(row.corporate_id, row.signal_type)]
        for row in result.itertuples(index=False)
    ]
    result["signal_rank"] = result.groupby("corporate_id")["change_rate"].rank(
        method="min", ascending=True, na_option="bottom"
    ).astype(int)
    return result


def _build_shap_table(scores: pd.DataFrame, month: str) -> pd.DataFrame:
    feature_columns = [
        f"shap_top{rank}_feature" for rank in range(1, SHAP_FACTOR_COUNT + 1)
    ]
    value_columns = [
        f"shap_top{rank}_value" for rank in range(1, SHAP_FACTOR_COUNT + 1)
    ]
    feature_names = scores.loc[:, feature_columns].astype("string").apply(
        lambda column: column.str.strip()
    )
    if feature_names.isna().any().any() or feature_names.eq("").any().any():
        raise ValueError("운영 점수 SHAP feature 이름에 결측 또는 빈 문자열이 있습니다.")
    shap_values = scores.loc[:, value_columns].apply(pd.to_numeric, errors="coerce")
    if shap_values.isna().any().any() or not np.isfinite(
        shap_values.to_numpy(dtype=float)
    ).all():
        raise ValueError("운영 점수 SHAP value는 유한한 숫자여야 합니다.")

    rows = []
    normalized_scores = scores.copy()
    normalized_scores.loc[:, feature_columns] = feature_names
    normalized_scores.loc[:, value_columns] = shap_values
    for score in normalized_scores.itertuples(index=False):
        for rank in range(1, SHAP_FACTOR_COUNT + 1):
            rows.append(
                {
                    "corporate_id": str(getattr(score, "법인ID")),
                    "as_of_month": month,
                    "model_name": MODEL_NAME,
                    "feature_name": getattr(score, f"shap_top{rank}_feature"),
                    "feature_value": np.nan,
                    "shap_value": float(getattr(score, f"shap_top{rank}_value")),
                    "abs_shap_rank": rank,
                }
            )
    result = pd.DataFrame(rows)
    expected_ranks = list(range(1, SHAP_FACTOR_COUNT + 1))
    ranks_by_customer = result.groupby("corporate_id")["abs_shap_rank"].apply(list)
    if not ranks_by_customer.apply(lambda ranks: ranks == expected_ranks).all():
        raise ValueError("운영 점수 SHAP 순위는 고객별 1~10이어야 합니다.")
    return result


def build_service_tables(
    inputs: ServiceInputs,
    as_of_month: str | None = None,
) -> dict[str, pd.DataFrame]:
    """Validate and join final artifacts into database-shaped service tables."""
    normalized = _normalized_inputs(inputs)
    available = _common_months(normalized)
    if not available:
        raise ValueError("운영 점수·원천·CLV 데이터에 공통 기준월이 없습니다.")
    if as_of_month is None:
        month = available[-1]
    else:
        month = normalize_month(pd.Series([as_of_month])).iloc[0]
        if month not in available:
            raise ValueError(
                f"요청한 공통 기준월 {month}을 사용할 수 없습니다. "
                f"사용 가능 공통 기준월: {available}"
            )

    source = normalized.source
    scores = normalized.operating_scores
    clv = normalized.clv
    risk_trends = normalized.risk_trends
    _validate_unique(source, "기준년월", "원천 데이터")
    _validate_unique(scores, "cutoff_month", "운영 점수")
    _validate_unique(clv, "기준월", "CLV")
    scores = _numeric_contract(scores, ("risk_probability",), "운영 점수", probability=True)
    scores = _numeric_contract(scores, tuple(SCORE_CHANGE_COLUMNS.values()), "약화 변화율")
    clv = _numeric_contract(
        clv,
        (
            "risk_probability",
            "CLV_NoRisk",
            "CLV_Risk",
            "PotentialLoss",
            "defense_value",
            "수익성월수",
        ),
        "CLV",
    )

    scores_month = scores.loc[
        scores["cutoff_month"].eq(month) & scores["score_eligible"]
    ].copy()
    model_contract = {
        "target_name": "Y_INTERVENE_M12_v2",
        "feature_set": "FS_FINAL_164_TUNED",
        "feature_count": 164,
        "calibration_method": "PLATT",
        "probability_status": "VALIDATION_PLATT_LOCKED_SERVICE_REESTIMATION_DEFERRED",
    }
    for column, expected in model_contract.items():
        if not scores_month[column].eq(expected).all():
            raise ValueError(f"운영 점수 {column}은 {expected!r}로 고정되어야 합니다.")
    risk_trends = _validated_risk_trends(risk_trends, scores_month, month)
    clv_month = clv.loc[clv["기준월"].eq(month)].copy()
    source_month = source.loc[source["기준년월"].eq(month)].copy()
    joined = (
        scores_month.merge(
            clv_month,
            on="법인ID",
            how="left",
            validate="one_to_one",
            suffixes=("", "_clv"),
        )
        .merge(
            source_month[
                [
                    "법인ID",
                    "업종_대분류",
                    "사업장_시도",
                    "법인_고객등급",
                    "전담고객여부",
                ]
            ],
            on="법인ID",
            how="left",
            validate="one_to_one",
        )
    )
    required_joined = [
        "CLV_NoRisk",
        "CLV_Risk",
        "PotentialLoss",
        "defense_value",
        "SEG__current_segment",
        "법인_고객등급",
        "전담고객여부",
    ]
    if joined[required_joined].isna().any().any():
        raise ValueError("적격 운영 점수의 CLV·세그먼트·고객속성 결합 계약 위반입니다.")
    if not np.allclose(
        joined["risk_probability"].to_numpy(float),
        joined["risk_probability_clv"].to_numpy(float),
        rtol=0,
        atol=1e-12,
    ):
        raise ValueError("운영 점수와 CLV의 위험확률 불일치가 있습니다.")
    if not joined["수익성월수"].eq(6).all():
        raise ValueError("CLV 실제 수익성월수는 정확히 6개월이어야 합니다.")
    expected_period = (
        pd.Period(month, freq="M") - 5
    ).strftime("%Y-%m") + f"~{month}"
    if not joined["수익성기간"].eq(expected_period).all():
        raise ValueError(f"CLV 수익성기간은 {expected_period}여야 합니다.")
    if joined["미래수익성예측사용"].any():
        raise ValueError("CLV는 미래 수익성 예측값을 사용할 수 없습니다.")
    if not joined["법인_고객등급"].isin(VALID_GRADES).all():
        raise ValueError("고객등급 허용값 위반이 있습니다.")
    if not joined["전담고객여부"].isin(VALID_DEDICATED).all():
        raise ValueError("전담고객여부 허용값 위반이 있습니다.")
    joined["dedicated_yn"] = joined["전담고객여부"].map({"N": 0, "Y": 1})
    numeric_score_columns = (
        "risk_rank_eligible",
        "risk_band_order",
        "threshold",
    )
    joined = _numeric_contract(joined, numeric_score_columns, "최종 위험 밴드")
    if not joined["risk_band"].isin(RISK_BAND_PRIORITIES).all():
        raise ValueError("운영 점수 risk_band 허용값 위반이 있습니다.")
    if not np.allclose(joined["threshold"], MODEL_THRESHOLD, rtol=0, atol=1e-12):
        raise ValueError("운영 점수 threshold가 최종 모델 임계값과 일치하지 않습니다.")
    joined["predicted_positive_model_scope"] = _normalize_boolean(
        joined["predicted_positive_model_scope"],
        "predicted_positive_model_scope",
    )

    customers = joined[
        [
            "법인ID",
            "CTX__업종_대분류__현재",
            "사업장_시도",
            "법인_고객등급",
            "dedicated_yn",
        ]
    ].rename(
        columns={
            "법인ID": "corporate_id",
            "CTX__업종_대분류__현재": "industry",
            "사업장_시도": "region",
            "법인_고객등급": "customer_grade",
        }
    )
    customers.insert(1, "corporate_name", customers["corporate_id"])

    risk_table = joined[
        [
            "법인ID",
            "risk_probability",
            "risk_rank_eligible",
            "risk_band",
            "risk_band_name",
            "risk_band_order",
            "predicted_positive_model_scope",
            "threshold",
        ]
    ].rename(
        columns={
            "법인ID": "corporate_id",
            "risk_rank_eligible": "risk_rank",
            "predicted_positive_model_scope": "predicted_positive",
        }
    )
    risk_table.insert(1, "as_of_month", month)
    risk_table.insert(2, "model_name", MODEL_NAME)

    segments = joined[
        [
            "법인ID",
            "SEG__baseline_segment_2023",
            "SEG__current_segment",
            "SEG__transition",
        ]
    ].rename(
        columns={
            "법인ID": "corporate_id",
            "SEG__baseline_segment_2023": "baseline_segment_name",
            "SEG__current_segment": "segment_name",
            "SEG__transition": "segment_transition",
        }
    )
    segments.insert(1, "as_of_month", month)

    clv_values = joined[
        [
            "법인ID",
            "CLV_NoRisk",
            "CLV_Risk",
            "PotentialLoss",
            "defense_value",
            "defense_rank",
        ]
    ].rename(
        columns={
            "법인ID": "corporate_id",
            "CLV_NoRisk": "clv_no_risk",
            "CLV_Risk": "clv_risk",
            "PotentialLoss": "potential_loss",
        }
    )
    clv_values.insert(1, "as_of_month", month)

    risk_ids = set(scores_month["법인ID"].astype(str))
    weakening_signals = build_weakening_signals(source, risk_ids, month)
    weakening_signals = _apply_score_changes(weakening_signals, scores_month)
    shap_table = _build_shap_table(scores_month, month)

    snapshots = joined[
        [
            "법인ID",
            "risk_probability",
            "risk_rank_eligible",
            "risk_band",
            "risk_band_name",
            "risk_band_order",
            "predicted_positive_model_scope",
            "threshold",
            "CLV_NoRisk",
            "CLV_Risk",
            "PotentialLoss",
            "defense_value",
            "defense_rank",
            "SEG__current_segment",
            "CTX__업종_대분류__현재",
            "사업장_시도",
            "dedicated_yn",
        ]
    ].rename(
        columns={
            "법인ID": "corporate_id",
            "risk_rank_eligible": "risk_rank",
            "predicted_positive_model_scope": "predicted_positive",
            "CLV_NoRisk": "clv_no_risk",
            "CLV_Risk": "clv_risk",
            "PotentialLoss": "potential_loss",
            "SEG__current_segment": "segment_name",
            "CTX__업종_대분류__현재": "industry",
            "사업장_시도": "region",
        }
    )
    snapshots.insert(1, "as_of_month", month)
    weakening_types = classify_weakening_type(weakening_signals)
    snapshots = snapshots.merge(
        weakening_types,
        on=["corporate_id", "as_of_month"],
        how="left",
        validate="one_to_one",
    )
    if snapshots["weakening_type"].isna().any():
        raise ValueError("적격 운영 모집단의 약화 신호 분류가 없습니다.")
    weakening_type = snapshots.pop("weakening_type")
    snapshots.insert(15, "weakening_type", weakening_type)
    recommendations = build_recommendations(snapshots, weakening_signals)

    signal_distribution = snapshots["weakening_type"].value_counts().sort_index()
    monthly_summaries = pd.DataFrame(
        [
            {
                "as_of_month": month,
                "managed_customer_count": int(len(snapshots)),
                "average_risk": float(snapshots["risk_probability"].mean()),
                "threshold_share": float(snapshots["predicted_positive"].mean()),
                "potential_loss_total": float(snapshots["defense_value"].sum()),
                "signal_distribution_json": json.dumps(
                    {
                        str(label): int(value)
                        for label, value in signal_distribution.items()
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
            }
        ]
    )
    return {
        "customers": customers.reset_index(drop=True),
        "risk_scores": risk_table.reset_index(drop=True),
        "segments": segments.reset_index(drop=True),
        "clv_values": clv_values.reset_index(drop=True),
        "weakening_signals": weakening_signals.reset_index(drop=True),
        "shap_factors": shap_table.reset_index(drop=True),
        "recommendations": recommendations.reset_index(drop=True),
        "customer_snapshots": snapshots.reset_index(drop=True),
        "monthly_summaries": monthly_summaries,
        "risk_trends": risk_trends,
    }
