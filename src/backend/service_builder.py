"""Validate analytical artifacts and build RM service snapshot tables."""

from __future__ import annotations

from dataclasses import dataclass
import json
import re

import pandas as pd

from src.segmentation.relationship_segments import SegmentationConfig


MODEL_NAME = "LightGBM"
GRADE_SCORES = {"일반": 0.0, "우수": 0.5, "최우수": 1.0}
DEDICATED_SCORES = {"N": 0.0, "Y": 1.0}
VALUE_NUMERIC_COLUMNS = (
    "수신잔액합계",
    "여신잔액합계",
    "핵심거래활동금액",
    "상품관계폭",
)
VALUE_SCORE_COLUMNS = (
    "수신점수",
    "여신점수",
    "거래성금액점수",
    "상품관계폭점수",
    "고객등급점수",
    "전담점수",
)


@dataclass
class ServiceInputs:
    """In-memory analytical artifacts consumed by the service builder."""

    source: pd.DataFrame
    risk_scores: pd.DataFrame
    segment_panel: pd.DataFrame
    profitability: pd.DataFrame
    shap_local: pd.DataFrame


def _require_columns(
    frame: pd.DataFrame,
    columns: tuple[str, ...],
    contract_name: str,
) -> None:
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise ValueError(f"{contract_name} 필수 컬럼이 없습니다: {missing}")


def _normalize_month_value(value: object) -> str | None:
    if pd.isna(value):
        return None
    if isinstance(value, pd.Period):
        return str(value.asfreq("M"))
    if isinstance(value, pd.Timestamp):
        return str(value.to_period("M"))

    text = str(value).strip()
    if re.fullmatch(r"\d{6}", text):
        text = f"{text[:4]}-{text[4:]}"
    try:
        parsed = pd.to_datetime(text, errors="raise")
    except (TypeError, ValueError):
        return None
    return str(parsed.to_period("M"))


def normalize_month(series: pd.Series) -> pd.Series:
    """Normalize supported monthly representations to ``YYYY-MM`` strings."""
    normalized = series.map(_normalize_month_value)
    invalid = normalized.isna()
    if invalid.any():
        examples = series.loc[invalid].head(5).tolist()
        raise ValueError(f"기준월 형식 위반: YYYY-MM으로 변환할 수 없습니다: {examples}")
    return normalized.astype("string")


def _normalized_inputs(inputs: ServiceInputs) -> ServiceInputs:
    config = SegmentationConfig()
    source_columns = (
        "법인ID",
        "기준년월",
        "업종_대분류",
        "사업장_시도",
        "법인_고객등급",
        "전담고객여부",
        "상품관계폭",
        *config.amount_cols,
    )
    _require_columns(inputs.source, source_columns, "원천 데이터")
    _require_columns(
        inputs.risk_scores,
        ("법인ID", "기준년월", "모델", "예측확률"),
        "위험점수",
    )
    _require_columns(
        inputs.segment_panel,
        (
            "법인ID",
            "기준년월",
            "관계세그먼트",
            "거래활동점수",
            "수신관계점수",
            "여신관계점수",
        ),
        "세그먼트",
    )
    _require_columns(
        inputs.profitability,
        ("법인ID", "기준월", "V_FTP_12M", "V_FTP_12M_방어가치"),
        "수익성",
    )
    _require_columns(
        inputs.shap_local,
        (
            "모델",
            "법인ID",
            "기준년월",
            "feature",
            "feature_value",
            "shap_value",
            "abs_shap_rank",
        ),
        "SHAP",
    )

    source = inputs.source.copy()
    risk = inputs.risk_scores.loc[inputs.risk_scores["모델"].eq(MODEL_NAME)].copy()
    segment = inputs.segment_panel.copy()
    profitability = inputs.profitability.copy()
    shap = inputs.shap_local.loc[inputs.shap_local["모델"].eq(MODEL_NAME)].copy()
    source["기준년월"] = normalize_month(source["기준년월"])
    risk["기준년월"] = normalize_month(risk["기준년월"])
    segment["기준년월"] = normalize_month(segment["기준년월"])
    profitability["기준월"] = normalize_month(profitability["기준월"])
    shap["기준년월"] = normalize_month(shap["기준년월"])
    return ServiceInputs(source, risk, segment, profitability, shap)


def _common_months(inputs: ServiceInputs) -> list[str]:
    month_sets = (
        set(inputs.source["기준년월"]),
        set(inputs.risk_scores["기준년월"]),
        set(inputs.segment_panel["기준년월"]),
        set(inputs.profitability["기준월"]),
    )
    return sorted(set.intersection(*month_sets))


def select_common_month(inputs: ServiceInputs, requested: str | None) -> str:
    """Select the latest common artifact month, or validate an explicit month."""
    normalized = _normalized_inputs(inputs)
    available = _common_months(normalized)
    if not available:
        raise ValueError("위험·세그먼트·원천·수익성 데이터에 공통 기준월이 없습니다.")
    if requested is None:
        return available[-1]
    requested_month = normalize_month(pd.Series([requested])).iloc[0]
    if requested_month not in available:
        raise ValueError(
            f"요청한 공통 기준월 {requested_month}을 사용할 수 없습니다. "
            f"사용 가능 공통 기준월: {available}"
        )
    return requested_month


def build_customer_value(source_month: pd.DataFrame) -> pd.DataFrame:
    """Build the approved six-component equal-weight customer-value proxy."""
    required = (
        "법인ID",
        *VALUE_NUMERIC_COLUMNS,
        "법인_고객등급",
        "전담고객여부",
    )
    missing = [column for column in required if column not in source_month.columns]
    if missing:
        raise ValueError(f"고객가치 필수 구성요소가 없습니다: {missing}")

    work = source_month.copy()
    numeric = work.loc[:, VALUE_NUMERIC_COLUMNS].apply(pd.to_numeric, errors="coerce")
    if numeric.isna().any().any():
        columns = numeric.columns[numeric.isna().any()].tolist()
        raise ValueError(f"고객가치 원천 금액 또는 상품관계폭에 결측이 있습니다: {columns}")
    if numeric.lt(0).any().any():
        raise ValueError("고객가치 원천 금액 또는 상품관계폭에 음수가 있습니다.")
    work.loc[:, VALUE_NUMERIC_COLUMNS] = numeric

    unknown_grades = sorted(set(work["법인_고객등급"].dropna()) - GRADE_SCORES.keys())
    if work["법인_고객등급"].isna().any() or unknown_grades:
        raise ValueError(f"고객등급 허용값 위반: {unknown_grades}")
    unknown_flags = sorted(set(work["전담고객여부"].dropna()) - DEDICATED_SCORES.keys())
    if work["전담고객여부"].isna().any() or unknown_flags:
        raise ValueError(f"전담고객여부 허용값 위반: {unknown_flags}")

    for source_column, score_column in zip(
        VALUE_NUMERIC_COLUMNS,
        VALUE_SCORE_COLUMNS[:4],
    ):
        work[score_column] = work[source_column].rank(method="average", pct=True)
    work["고객등급점수"] = work["법인_고객등급"].map(GRADE_SCORES)
    work["전담점수"] = work["전담고객여부"].map(DEDICATED_SCORES)
    if work.loc[:, VALUE_SCORE_COLUMNS].isna().any().any():
        raise ValueError("고객가치 여섯 구성요소에 결측이 있습니다.")

    work["customer_value_proxy"] = work.loc[:, VALUE_SCORE_COLUMNS].mean(axis=1)
    work["value_components_json"] = work.loc[:, VALUE_SCORE_COLUMNS].apply(
        lambda row: json.dumps(
            {column: float(row[column]) for column in VALUE_SCORE_COLUMNS},
            ensure_ascii=False,
            sort_keys=True,
        ),
        axis=1,
    )
    return work


def _validate_unique(frame: pd.DataFrame, month_column: str, contract: str) -> None:
    if frame.duplicated(["법인ID", month_column], keep=False).any():
        raise ValueError(f"{contract} 법인ID+기준년월 중복이 있습니다.")


def _numeric_contract(
    frame: pd.DataFrame,
    columns: tuple[str, ...],
    contract: str,
    *,
    non_negative: bool = False,
    probability: bool = False,
) -> pd.DataFrame:
    numeric = frame.loc[:, columns].apply(pd.to_numeric, errors="coerce")
    if numeric.isna().any().any():
        invalid = numeric.columns[numeric.isna().any()].tolist()
        raise ValueError(f"{contract} 숫자 또는 결측 계약 위반: {invalid}")
    if non_negative and numeric.lt(0).any().any():
        raise ValueError(f"{contract} 원천 금액에 음수가 있습니다.")
    within_probability_range = numeric.ge(0).all().all() and numeric.le(1).all().all()
    if probability and not within_probability_range:
        raise ValueError(f"{contract} 예측확률은 0과 1 사이여야 합니다.")
    result = frame.copy()
    result.loc[:, columns] = numeric
    return result


def _risk_level(probability: pd.Series) -> pd.Series:
    return pd.Series(
        pd.cut(
            probability,
            bins=[-float("inf"), 0.60, 0.75, float("inf")],
            labels=["WATCH", "MEDIUM", "HIGH"],
            right=False,
        ),
        index=probability.index,
    ).astype("string")


def build_service_tables(
    inputs: ServiceInputs,
    as_of_month: str | None = None,
) -> dict[str, pd.DataFrame]:
    """Validate and join artifacts into database-shaped service tables."""
    normalized = _normalized_inputs(inputs)
    available = _common_months(normalized)
    if not available:
        raise ValueError("위험·세그먼트·원천·수익성 데이터에 공통 기준월이 없습니다.")
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
    risk = normalized.risk_scores
    segment = normalized.segment_panel
    profitability = normalized.profitability
    shap = normalized.shap_local
    _validate_unique(source, "기준년월", "원천 데이터")
    _validate_unique(risk, "기준년월", "위험점수")
    _validate_unique(segment, "기준년월", "세그먼트")
    _validate_unique(profitability, "기준월", "수익성")

    config = SegmentationConfig()
    source = _numeric_contract(
        source,
        ("상품관계폭", *config.amount_cols),
        "원천 데이터",
        non_negative=True,
    )
    risk = _numeric_contract(risk, ("예측확률",), "위험점수", probability=True)
    segment = _numeric_contract(
        segment,
        ("거래활동점수", "수신관계점수", "여신관계점수"),
        "세그먼트 점수",
        probability=True,
    )

    source_month = source.loc[source["기준년월"].eq(month)].copy()
    source_month["수신잔액합계"] = source_month.loc[:, config.deposit_cols].sum(axis=1)
    source_month["여신잔액합계"] = source_month.loc[:, config.loan_cols].sum(axis=1)
    source_month["핵심거래활동금액"] = source_month.loc[:, config.activity_cols].sum(axis=1)
    value = build_customer_value(source_month)

    risk_month = risk.loc[risk["기준년월"].eq(month)].copy()
    segment_month = segment.loc[segment["기준년월"].eq(month)].copy()
    profitability_month = profitability.loc[profitability["기준월"].eq(month)].copy()
    joined = risk_month.merge(
        segment_month,
        on=["법인ID", "기준년월"],
        how="left",
        validate="one_to_one",
    ).merge(
        value,
        on=["법인ID", "기준년월"],
        how="left",
        validate="one_to_one",
    ).merge(
        profitability_month,
        left_on=["법인ID", "기준년월"],
        right_on=["법인ID", "기준월"],
        how="left",
        validate="one_to_one",
    )
    required_joined = (
        "관계세그먼트",
        "customer_value_proxy",
        "value_components_json",
    )
    if joined.loc[:, required_joined].isna().any().any():
        raise ValueError("위험점수 모집단의 세그먼트 또는 고객가치 결합 계약 위반입니다.")

    joined["dedicated_yn"] = joined["전담고객여부"].map({"N": 0, "Y": 1})
    joined["risk_level"] = _risk_level(joined["예측확률"])
    joined["crm_priority_score"] = (
        joined["예측확률"] * joined["customer_value_proxy"]
    )
    joined["crm_priority_rank"] = joined["crm_priority_score"].rank(
        method="min", ascending=False
    ).astype(int)

    customers = joined.loc[
        :,
        [
            "법인ID",
            "업종_대분류",
            "사업장_시도",
            "법인_고객등급",
            "dedicated_yn",
        ],
    ].rename(
        columns={
            "법인ID": "corporate_id",
            "업종_대분류": "industry",
            "사업장_시도": "region",
            "법인_고객등급": "customer_grade",
        }
    )
    customers.insert(1, "corporate_name", customers["corporate_id"])

    risk_table = joined.loc[:, ["법인ID", "기준년월", "모델", "예측확률", "risk_level"]].rename(
        columns={
            "법인ID": "corporate_id",
            "기준년월": "as_of_month",
            "모델": "model_name",
            "예측확률": "risk_probability",
        }
    )
    segments = joined.loc[
        :,
        [
            "법인ID",
            "기준년월",
            "관계세그먼트",
            "거래활동점수",
            "수신관계점수",
            "여신관계점수",
        ],
    ].rename(
        columns={
            "법인ID": "corporate_id",
            "기준년월": "as_of_month",
            "관계세그먼트": "segment_name",
            "거래활동점수": "activity_score",
            "수신관계점수": "deposit_score",
            "여신관계점수": "loan_score",
        }
    )
    profitability_table = joined.loc[
        :,
        [
            "법인ID",
            "기준년월",
            "V_FTP_12M",
            "V_FTP_12M_방어가치",
            "customer_value_proxy",
            "value_components_json",
        ],
    ].rename(
        columns={
            "법인ID": "corporate_id",
            "기준년월": "as_of_month",
            "V_FTP_12M": "profitability_value",
            "V_FTP_12M_방어가치": "defense_value",
        }
    )

    risk_ids = set(risk_month["법인ID"])
    shap_table = shap.loc[
        shap["기준년월"].eq(month) & shap["법인ID"].isin(risk_ids),
        [
            "법인ID",
            "기준년월",
            "모델",
            "feature",
            "feature_value",
            "shap_value",
            "abs_shap_rank",
        ],
    ].rename(
        columns={
            "법인ID": "corporate_id",
            "기준년월": "as_of_month",
            "모델": "model_name",
            "feature": "feature_name",
        }
    )

    snapshots = joined.loc[
        :,
        [
            "법인ID",
            "기준년월",
            "예측확률",
            "risk_level",
            "customer_value_proxy",
            "V_FTP_12M",
            "V_FTP_12M_방어가치",
            "crm_priority_score",
            "crm_priority_rank",
            "관계세그먼트",
            "업종_대분류",
            "사업장_시도",
            "dedicated_yn",
        ],
    ].rename(
        columns={
            "법인ID": "corporate_id",
            "기준년월": "as_of_month",
            "예측확률": "risk_probability",
            "V_FTP_12M": "profitability_value",
            "V_FTP_12M_방어가치": "defense_value",
            "관계세그먼트": "segment_name",
            "업종_대분류": "industry",
            "사업장_시도": "region",
        }
    )
    snapshots.insert(10, "weakening_type", "미분류")
    return {
        "customers": customers.reset_index(drop=True),
        "risk_scores": risk_table.reset_index(drop=True),
        "segments": segments.reset_index(drop=True),
        "profitability": profitability_table.reset_index(drop=True),
        "shap_factors": shap_table.reset_index(drop=True),
        "customer_snapshots": snapshots.reset_index(drop=True),
    }
