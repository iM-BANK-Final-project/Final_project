from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.metrics import adjusted_rand_score


SEGMENT_ORDER = (
    "저관계",
    "균형·중간관계",
    "거래활동중심",
    "수신중심",
    "여신중심",
    "복합고관계",
)
SEGMENT_DUMMY_MAP = {
    segment: f"segment_{segment.replace('·', '')}"
    for segment in SEGMENT_ORDER
}
SEGMENT_DUMMY_COLUMNS = tuple(SEGMENT_DUMMY_MAP.values())


@dataclass(frozen=True)
class SegmentationConfig:
    customer_id_col: str = "법인ID"
    month_col: str = "기준년월"
    activity_cols: tuple[str, ...] = (
        "요구불입금금액",
        "요구불출금금액",
        "창구거래금액",
        "인터넷뱅킹거래금액",
        "스마트뱅킹거래금액",
        "폰뱅킹거래금액",
        "ATM거래금액",
        "신용카드사용금액",
        "체크카드사용금액",
    )
    deposit_cols: tuple[str, ...] = (
        "요구불예금잔액",
        "거치식예금잔액",
        "적립식예금잔액",
        "수익증권잔액",
        "신탁잔액",
        "퇴직연금잔액",
    )
    loan_cols: tuple[str, ...] = (
        "여신_운전자금대출잔액",
        "여신_시설자금대출잔액",
    )
    low_cut: float = 0.30
    high_cut: float = 0.70
    dominance_margin: float = 0.15

    @property
    def amount_cols(self) -> tuple[str, ...]:
        return self.activity_cols + self.deposit_cols + self.loan_cols

    @property
    def required_columns(self) -> tuple[str, ...]:
        return (self.customer_id_col, self.month_col, *self.amount_cols)

    @property
    def axis_columns(self) -> dict[str, tuple[str, ...]]:
        return {
            "거래활동금액": self.activity_cols,
            "수신관계금액": self.deposit_cols,
            "여신관계금액": self.loan_cols,
        }

    @property
    def amount_level_pairs(self) -> tuple[tuple[str, str], ...]:
        return (
            ("거래활동금액", "거래활동관계수준"),
            ("수신관계금액", "수신관계수준"),
            ("여신관계금액", "여신관계수준"),
        )

    @property
    def level_columns(self) -> tuple[str, ...]:
        return tuple(level for _, level in self.amount_level_pairs)

    @property
    def score_columns(self) -> tuple[str, ...]:
        return ("거래활동점수", "수신관계점수", "여신관계점수")

    @property
    def level_score_pairs(self) -> tuple[tuple[str, str], ...]:
        return tuple(zip(self.level_columns, self.score_columns))


def _require_columns(frame: pd.DataFrame, columns: tuple[str, ...]) -> None:
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise ValueError(f"필수 컬럼이 없습니다: {missing}")


def validate_segmentation_source(
    frame: pd.DataFrame,
    config: SegmentationConfig | None = None,
) -> pd.DataFrame:
    config = config or SegmentationConfig()
    _require_columns(frame, config.required_columns)
    work = frame.copy()
    months = pd.to_datetime(
        work[config.month_col].astype(str),
        format="%Y%m",
        errors="coerce",
    )
    if months.isna().any():
        examples = work.loc[months.isna(), config.month_col].head(5).tolist()
        raise ValueError(f"기준년월 파싱 실패: {examples}")
    work[config.month_col] = months.dt.to_period("M")

    duplicated = work.duplicated(
        [config.customer_id_col, config.month_col],
        keep=False,
    )
    if duplicated.any():
        raise ValueError("법인×월 중복이 있습니다.")

    amounts = work.loc[:, config.amount_cols].apply(
        pd.to_numeric,
        errors="coerce",
    )
    if amounts.isna().any().any():
        missing_counts = amounts.isna().sum()
        missing_columns = missing_counts.loc[missing_counts.gt(0)].index.tolist()
        raise ValueError(f"관계축 원천 금액에 결측이 있습니다: {missing_columns}")
    if amounts.lt(0).any().any():
        raise ValueError("관계축 원천 금액에 음수가 있습니다.")
    work.loc[:, config.amount_cols] = amounts
    return work.sort_values(
        [config.customer_id_col, config.month_col]
    ).reset_index(drop=True)


def build_monthly_relationship_axes(
    frame: pd.DataFrame,
    config: SegmentationConfig | None = None,
) -> pd.DataFrame:
    config = config or SegmentationConfig()
    work = validate_segmentation_source(frame, config)
    for output_column, source_columns in config.axis_columns.items():
        work[output_column] = work.loc[:, source_columns].sum(
            axis=1,
            min_count=len(source_columns),
        )
    return work


def summarize_relationship_window(
    monthly: pd.DataFrame,
    start: str,
    end: str,
    config: SegmentationConfig | None = None,
) -> pd.DataFrame:
    config = config or SegmentationConfig()
    _require_columns(
        monthly,
        (
            config.customer_id_col,
            config.month_col,
            *config.axis_columns.keys(),
        ),
    )
    start_period = pd.Period(start, freq="M")
    end_period = pd.Period(end, freq="M")
    expected_months = pd.period_range(start_period, end_period, freq="M")
    if len(expected_months) != 12:
        raise ValueError("관계수준 요약 구간은 정확히 12개월이어야 합니다.")

    window = monthly.loc[
        monthly[config.month_col].between(start_period, end_period)
    ].copy()
    customer_ids = pd.Index(monthly[config.customer_id_col].unique())
    month_counts = window.groupby(config.customer_id_col)[
        config.month_col
    ].nunique()
    month_counts = month_counts.reindex(customer_ids, fill_value=0)
    if not month_counts.eq(12).all():
        raise ValueError("모든 법인에 정확한 12개월 관측이 필요합니다.")

    expected_set = set(expected_months)
    actual_sets = window.groupby(config.customer_id_col)[config.month_col].agg(set)
    if not actual_sets.map(lambda values: values == expected_set).all():
        raise ValueError("모든 법인에 정확한 12개월 관측이 필요합니다.")

    for amount_column, level_column in config.amount_level_pairs:
        window[level_column] = np.log1p(window[amount_column].astype(float))
    return (
        window.groupby(config.customer_id_col, as_index=False)[
            list(config.level_columns)
        ]
        .median()
        .sort_values(config.customer_id_col)
        .reset_index(drop=True)
    )


def build_reference_relationship_levels(
    monthly: pd.DataFrame,
    config: SegmentationConfig | None = None,
) -> pd.DataFrame:
    config = config or SegmentationConfig()
    levels = summarize_relationship_window(
        monthly,
        "2023-01",
        "2023-12",
        config,
    )
    _, reference = fit_reference_scores(levels, config)
    return reference


def build_rolling_relationship_features(
    monthly: pd.DataFrame,
    reference: pd.DataFrame,
    config: SegmentationConfig | None = None,
) -> pd.DataFrame:
    config = config or SegmentationConfig()
    _require_columns(
        monthly,
        (
            config.customer_id_col,
            config.month_col,
            *config.axis_columns.keys(),
        ),
    )
    work = monthly.sort_values(
        [config.customer_id_col, config.month_col]
    ).copy()
    if work.duplicated(
        [config.customer_id_col, config.month_col]
    ).any():
        raise ValueError("법인×월 중복이 있습니다.")

    rolling = work.loc[
        :, [config.customer_id_col, config.month_col]
    ].copy()
    for amount_column, level_column in config.amount_level_pairs:
        log_amount = np.log1p(
            pd.to_numeric(work[amount_column], errors="coerce")
        )
        rolling[level_column] = log_amount.groupby(
            work[config.customer_id_col],
            sort=False,
        ).transform(
            lambda values: values.rolling(12, min_periods=12).median()
        )

    complete = rolling.dropna(subset=list(config.level_columns)).copy()
    scored = score_against_reference(complete, reference, config)
    assigned = assign_l30_h70_m15(scored, config)
    for segment, dummy_column in SEGMENT_DUMMY_MAP.items():
        assigned[dummy_column] = assigned["관계세그먼트"].eq(segment).astype(int)
    return assigned.loc[
        :,
        [
            config.customer_id_col,
            config.month_col,
            *config.level_columns,
            *config.score_columns,
            "관계세그먼트",
            *SEGMENT_DUMMY_COLUMNS,
        ],
    ].reset_index(drop=True)


def _validate_relationship_levels(
    levels: pd.DataFrame,
    config: SegmentationConfig,
) -> pd.DataFrame:
    _require_columns(
        levels,
        (config.customer_id_col, *config.level_columns),
    )
    work = levels.copy()
    numeric = work.loc[:, config.level_columns].apply(
        pd.to_numeric,
        errors="coerce",
    )
    if numeric.isna().any().any():
        raise ValueError("관계수준에 결측 또는 비수치 값이 있습니다.")
    work.loc[:, config.level_columns] = numeric
    return work


def fit_reference_scores(
    levels: pd.DataFrame,
    config: SegmentationConfig | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    config = config or SegmentationConfig()
    scored = _validate_relationship_levels(levels, config)
    if scored.empty:
        raise ValueError("기준분포를 만들 관계수준이 없습니다.")
    for level_column, score_column in config.level_score_pairs:
        scored[score_column] = scored[level_column].rank(
            method="average",
            pct=True,
        )
    reference = scored.loc[
        :, [config.customer_id_col, *config.level_columns]
    ].copy()
    return scored, reference


def _score_one_axis(
    values: np.ndarray,
    reference_values: np.ndarray,
) -> np.ndarray:
    reference_sorted = np.sort(reference_values.astype(float))
    if reference_sorted.size == 0:
        raise ValueError("고정 percentile 기준분포가 비어 있습니다.")
    values = values.astype(float)
    right = np.searchsorted(reference_sorted, values, side="right")
    count = float(reference_sorted.size)
    scores = right.astype(float) / count
    return np.clip(scores, 0.0, 1.0)


def score_against_reference(
    levels: pd.DataFrame,
    reference: pd.DataFrame,
    config: SegmentationConfig | None = None,
) -> pd.DataFrame:
    config = config or SegmentationConfig()
    scored = _validate_relationship_levels(levels, config)
    reference_work = _validate_relationship_levels(reference, config)
    if reference_work.empty:
        raise ValueError("고정 percentile 기준분포가 비어 있습니다.")
    for level_column, score_column in config.level_score_pairs:
        scored[score_column] = _score_one_axis(
            scored[level_column].to_numpy(dtype=float),
            reference_work[level_column].to_numpy(dtype=float),
        )
    return scored


def assign_l30_h70_m15(
    scored: pd.DataFrame,
    config: SegmentationConfig | None = None,
) -> pd.DataFrame:
    config = config or SegmentationConfig()
    _require_columns(
        scored,
        (config.customer_id_col, *config.score_columns),
    )
    result = scored.copy()
    scores = result.loc[:, config.score_columns].apply(
        pd.to_numeric,
        errors="coerce",
    )
    if scores.isna().any().any():
        raise ValueError("관계점수에 결측 또는 비수치 값이 있습니다.")
    if scores.lt(0).any().any() or scores.gt(1).any().any():
        raise ValueError("관계점수는 0과 1 사이여야 합니다.")

    low = scores.le(config.low_cut).all(axis=1)
    high = scores.ge(config.high_cut).sum(axis=1).ge(2)
    ordered = np.sort(scores.to_numpy(dtype=float), axis=1)
    score_margin = ordered[:, -1] - ordered[:, -2]
    dominant = score_margin >= config.dominance_margin - 1e-12

    labels = np.full(len(result), "균형·중간관계", dtype=object)
    labels[low.to_numpy()] = "저관계"
    labels[(~low & high).to_numpy()] = "복합고관계"

    remaining = ~(low | high) & dominant
    winners = scores.idxmax(axis=1).map(
        {
            "거래활동점수": "거래활동중심",
            "수신관계점수": "수신중심",
            "여신관계점수": "여신중심",
        }
    )
    labels[remaining.to_numpy()] = winners.loc[remaining].to_numpy()
    result.loc[:, config.score_columns] = scores
    result["관계세그먼트"] = labels
    return result


def build_segment_profile(assignments: pd.DataFrame) -> pd.DataFrame:
    _require_columns(assignments, ("관계세그먼트",))
    invalid = set(assignments["관계세그먼트"].dropna()) - set(SEGMENT_ORDER)
    if invalid:
        raise ValueError(f"정의되지 않은 관계세그먼트가 있습니다: {sorted(invalid)}")
    counts = assignments["관계세그먼트"].value_counts()
    profile = counts.rename_axis("관계세그먼트").reset_index(name="법인수")
    profile["비율"] = profile["법인수"].div(len(assignments))
    order = {segment: index for index, segment in enumerate(SEGMENT_ORDER)}
    profile["_order"] = profile["관계세그먼트"].map(order)
    return profile.sort_values("_order").drop(columns="_order").reset_index(drop=True)


def select_complete_segmentation_cohort(
    monthly: pd.DataFrame,
    config: SegmentationConfig | None = None,
) -> pd.DataFrame:
    config = config or SegmentationConfig()
    _require_columns(monthly, (config.customer_id_col, config.month_col))
    expected_months = set(pd.period_range("2023-01", "2025-12", freq="M"))
    month_sets = monthly.groupby(config.customer_id_col)[config.month_col].agg(set)
    complete_ids = month_sets.index[
        month_sets.map(lambda values: values == expected_months)
    ]
    if complete_ids.empty:
        raise ValueError("2023-01~2025-12 완전관측 법인이 없습니다.")
    return monthly.loc[
        monthly[config.customer_id_col].isin(complete_ids)
    ].copy().reset_index(drop=True)


def build_segment_stability(
    reference_assignments: pd.DataFrame,
    comparison_assignments: pd.DataFrame,
    config: SegmentationConfig | None = None,
) -> pd.DataFrame:
    config = config or SegmentationConfig()
    required = (config.customer_id_col, "관계세그먼트")
    _require_columns(reference_assignments, required)
    _require_columns(comparison_assignments, required)
    if reference_assignments[config.customer_id_col].duplicated().any():
        raise ValueError("기준 세그먼트에 중복 법인ID가 있습니다.")
    if comparison_assignments[config.customer_id_col].duplicated().any():
        raise ValueError("비교 세그먼트에 중복 법인ID가 있습니다.")

    merged = reference_assignments.loc[:, required].merge(
        comparison_assignments.loc[:, required],
        on=config.customer_id_col,
        how="outer",
        validate="one_to_one",
        suffixes=("_기준", "_비교"),
        indicator=True,
    )
    if not merged["_merge"].eq("both").all():
        raise ValueError("기준·비교 기간의 법인 집합이 일치하지 않습니다.")
    reference_col = "관계세그먼트_기준"
    comparison_col = "관계세그먼트_비교"
    same = merged[reference_col].eq(merged[comparison_col])
    ari = float(
        adjusted_rand_score(merged[reference_col], merged[comparison_col])
    )
    reference_share = merged[reference_col].value_counts(normalize=True)
    comparison_share = merged[comparison_col].value_counts(normalize=True)
    max_share_change = max(
        abs(
            float(comparison_share.get(segment, 0.0))
            - float(reference_share.get(segment, 0.0))
        )
        for segment in SEGMENT_ORDER
    )
    rows: list[dict[str, object]] = [
        {
            "구분": "전체",
            "기준법인수": len(merged),
            "비교법인수": len(merged),
            "동일세그먼트유지율": float(same.mean()),
            "ARI": ari,
            "기준비율": 1.0,
            "비교비율": 1.0,
            "구성비변화": max_share_change,
        }
    ]
    for segment in SEGMENT_ORDER:
        reference_mask = merged[reference_col].eq(segment)
        reference_count = int(reference_mask.sum())
        comparison_count = int(merged[comparison_col].eq(segment).sum())
        if reference_count == 0 and comparison_count == 0:
            continue
        retention = (
            float(same.loc[reference_mask].mean())
            if reference_count > 0
            else np.nan
        )
        base_share = float(reference_share.get(segment, 0.0))
        compare_share = float(comparison_share.get(segment, 0.0))
        rows.append(
            {
                "구분": segment,
                "기준법인수": reference_count,
                "비교법인수": comparison_count,
                "동일세그먼트유지율": retention,
                "ARI": np.nan,
                "기준비율": base_share,
                "비교비율": compare_share,
                "구성비변화": compare_share - base_share,
            }
        )
    return pd.DataFrame(rows)
