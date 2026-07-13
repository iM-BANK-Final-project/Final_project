from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from src.preprocessing.persistent_transaction_weakening_labels import (
    EVENT_ID_COL,
    TARGET_COL,
)


MODEL_TARGET_COL = "Y_향후3개월_지속거래약화"
FUTURE_EVENT_MONTH_COL = "미래지속거래약화사건월"
FUTURE_EVENT_ID_COL = "미래지속거래약화사건ID"
LEAD_MONTHS_COL = "사건까지개월수"
LABEL_END_COL = "label_end"

FIRST_ANCHOR = pd.Period("2024-02", freq="M")
LAST_ANCHOR = pd.Period("2025-06", freq="M")
TRAIN_START = pd.Period("2024-02", freq="M")
TRAIN_END = pd.Period("2024-09", freq="M")
VALIDATION_START = pd.Period("2025-04", freq="M")
VALIDATION_END = pd.Period("2025-06", freq="M")

FEATURE_AXES = (
    "핵심거래활동금액",
    "입출금활동금액",
    "채널활동금액",
    "카드활동금액",
)
FEATURE_PREFIXES = (
    "log1p_현재값_",
    "1개월변화율_",
    "YoY_ratio_",
    "log1p_최근",
    "최근3개월_이전6개월비율_",
    "최근3개월기울기_",
    "최근6개월기울기_",
    "최근12개월기울기_",
    "최근3개월활성률_",
    "최근6개월활성률_",
)


def _require_columns(frame: pd.DataFrame, columns: tuple[str, ...]) -> None:
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise ValueError(f"모델링 패널 필수 컬럼이 없습니다: {missing}")


def build_modeling_targets(label_panel: pd.DataFrame) -> pd.DataFrame:
    _require_columns(
        label_panel,
        (
            "법인ID",
            "기준년월",
            "core_3m_event",
            TARGET_COL,
            EVENT_ID_COL,
        ),
    )
    panel = label_panel.sort_values(["법인ID", "기준년월"]).copy()
    if not isinstance(panel["기준년월"].dtype, pd.PeriodDtype):
        panel["기준년월"] = pd.PeriodIndex(
            panel["기준년월"].astype(str),
            freq="M",
        )

    rows: list[dict[str, object]] = []
    for _, group in panel.groupby("법인ID", sort=False):
        positive_events = group.loc[
            group[TARGET_COL].eq(1),
            ["기준년월", EVENT_ID_COL],
        ].sort_values("기준년월")
        for _, anchor in group.iterrows():
            month = anchor["기준년월"]
            current_event = pd.notna(anchor["core_3m_event"]) and bool(
                anchor["core_3m_event"]
            )
            if (
                month < FIRST_ANCHOR
                or month > LAST_ANCHOR
                or current_event
            ):
                continue

            future = positive_events.loc[
                positive_events["기준년월"].between(month + 1, month + 3)
            ]
            row = anchor.to_dict()
            row[MODEL_TARGET_COL] = int(not future.empty)
            row[LABEL_END_COL] = month + 6
            if future.empty:
                row[FUTURE_EVENT_MONTH_COL] = pd.NaT
                row[FUTURE_EVENT_ID_COL] = pd.NA
                row[LEAD_MONTHS_COL] = pd.NA
            else:
                event_month = future.iloc[0]["기준년월"]
                row[FUTURE_EVENT_MONTH_COL] = event_month
                row[FUTURE_EVENT_ID_COL] = future.iloc[0][EVENT_ID_COL]
                row[LEAD_MONTHS_COL] = event_month.ordinal - month.ordinal
            rows.append(row)
    return pd.DataFrame(rows).reset_index(drop=True)


def split_train_validation(
    frame: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    _require_columns(frame, ("기준년월", LABEL_END_COL))
    train = frame.loc[
        frame["기준년월"].between(TRAIN_START, TRAIN_END)
    ].copy()
    validation = frame.loc[
        frame["기준년월"].between(VALIDATION_START, VALIDATION_END)
    ].copy()
    if train.empty or validation.empty:
        raise ValueError("train 또는 validation 구간이 비어 있습니다.")
    if train[LABEL_END_COL].max() >= validation["기준년월"].min():
        raise ValueError("train label 관찰창과 validation 기준월이 겹칩니다.")
    return train, validation


def _slope(values: pd.Series) -> float:
    clean = values.dropna().to_numpy(dtype=float)
    if len(clean) < 2:
        return np.nan
    return float(np.polyfit(np.arange(len(clean)), clean, 1)[0])


def build_modeling_features(label_panel: pd.DataFrame) -> pd.DataFrame:
    _require_columns(
        label_panel,
        ("법인ID", "기준년월", *FEATURE_AXES, "drop50", "drop50_연속개월수"),
    )
    monthly = label_panel.sort_values(["법인ID", "기준년월"]).copy()
    engineered = monthly[["법인ID", "기준년월"]].copy()

    for axis in FEATURE_AXES:
        values = pd.to_numeric(monthly[axis], errors="coerce")
        grouped = values.groupby(monthly["법인ID"], sort=False)
        prior_year = grouped.shift(12)
        engineered[f"log1p_현재값_{axis}"] = np.log1p(values)
        engineered[f"1개월변화율_{axis}"] = grouped.pct_change(
            fill_method=None
        ).replace([np.inf, -np.inf], np.nan)
        engineered[f"YoY_ratio_{axis}"] = values.div(
            prior_year.where(prior_year.gt(0))
        )

        for window in (3, 6):
            mean = grouped.transform(
                lambda series, size=window: series.rolling(
                    size,
                    min_periods=size,
                ).mean()
            )
            std = grouped.transform(
                lambda series, size=window: series.rolling(
                    size,
                    min_periods=size,
                ).std()
            )
            active = grouped.transform(
                lambda series, size=window: series.gt(0).rolling(
                    size,
                    min_periods=size,
                ).mean()
            )
            engineered[f"log1p_최근{window}개월평균_{axis}"] = np.log1p(mean)
            engineered[f"log1p_최근{window}개월표준편차_{axis}"] = np.log1p(std)
            engineered[f"최근{window}개월활성률_{axis}"] = active

        recent3 = grouped.transform(
            lambda series: series.rolling(3, min_periods=3).mean()
        )
        previous6 = grouped.transform(
            lambda series: series.shift(3).rolling(6, min_periods=6).mean()
        )
        engineered[f"최근3개월_이전6개월비율_{axis}"] = recent3.div(
            previous6.where(previous6.gt(0))
        )
        for window in (3, 6, 12):
            engineered[f"최근{window}개월기울기_{axis}"] = grouped.transform(
                lambda series, size=window: series.rolling(
                    size,
                    min_periods=size,
                ).apply(_slope, raw=False)
            )

    engineered["현재drop50"] = monthly["drop50"].astype("Float64")
    engineered["현재drop50연속개월수"] = pd.to_numeric(
        monthly["drop50_연속개월수"],
        errors="coerce",
    )
    targets = build_modeling_targets(label_panel)
    return targets.merge(
        engineered,
        on=["법인ID", "기준년월"],
        how="left",
        validate="one_to_one",
    )


def model_feature_columns(frame: pd.DataFrame) -> list[str]:
    selected = [
        column
        for column in frame.columns
        if column.startswith(FEATURE_PREFIXES)
        or column in {"현재drop50", "현재drop50연속개월수"}
    ]
    non_numeric = [
        column
        for column in selected
        if not pd.api.types.is_numeric_dtype(frame[column])
    ]
    if non_numeric:
        raise ValueError(f"수치형 feature가 아닌 컬럼이 있습니다: {non_numeric}")
    return selected


def _recall_for_mask(
    top: pd.DataFrame,
    full: pd.DataFrame,
    mask: pd.Series,
) -> float:
    denominator = int(mask.sum())
    if denominator == 0:
        return np.nan
    eligible_keys = set(full.index[mask])
    return len(eligible_keys.intersection(top.index)) / denominator


def evaluate_scored_rows(
    scored: pd.DataFrame,
    top_fractions: tuple[float, ...] = (0.05, 0.10, 0.20),
) -> pd.DataFrame:
    _require_columns(
        scored,
        (
            MODEL_TARGET_COL,
            FUTURE_EVENT_ID_COL,
            LEAD_MONTHS_COL,
            "현재drop50연속개월수",
            "모델",
            "예측확률",
        ),
    )
    rows: list[dict[str, object]] = []
    for model_name, group in scored.groupby("모델", sort=False):
        group = group.copy()
        has_ranking = group["예측확률"].nunique(dropna=False) > 1
        positives = int(group[MODEL_TARGET_COL].sum())
        base_rate = float(group[MODEL_TARGET_COL].mean())
        total_events = group[FUTURE_EVENT_ID_COL].dropna().nunique()
        pr_auc = (
            average_precision_score(
                group[MODEL_TARGET_COL],
                group["예측확률"],
            )
            if positives
            else np.nan
        )
        for fraction in top_fractions:
            if not 0 < fraction <= 1:
                raise ValueError("top fraction은 0보다 크고 1 이하여야 합니다.")
            count = max(1, int(np.ceil(len(group) * fraction)))
            top = group.nlargest(count, "예측확률")
            captured = int(top[MODEL_TARGET_COL].sum())
            captured_events = top[FUTURE_EVENT_ID_COL].dropna().nunique()
            precision = captured / count
            positive_mask = group[MODEL_TARGET_COL].eq(1)
            no_current_drop_mask = positive_mask & group[
                "현재drop50연속개월수"
            ].eq(0)
            row: dict[str, object] = {
                "모델": model_name,
                "K": fraction,
                "알림수": count,
                "PR_AUC": pr_auc,
                "Recall_at_K": (
                    captured / positives if positives and has_ranking else np.nan
                ),
                "Precision_at_K": precision if has_ranking else np.nan,
                "Lift_at_K": (
                    precision / base_rate
                    if base_rate and has_ranking
                    else np.nan
                ),
                "사건Recall_at_K": (
                    captured_events / total_events
                    if total_events and has_ranking
                    else np.nan
                ),
                "현재무감소_Recall_at_K": (
                    _recall_for_mask(top, group, no_current_drop_mask)
                    if has_ranking
                    else np.nan
                ),
            }
            for lead in (1, 2, 3):
                lead_mask = positive_mask & group[LEAD_MONTHS_COL].eq(lead)
                row[f"Lead{lead}_Recall_at_K"] = (
                    _recall_for_mask(top, group, lead_mask)
                    if has_ranking
                    else np.nan
                )
            rows.append(row)
    return pd.DataFrame(rows)


def fit_and_score_baselines(
    train: pd.DataFrame,
    validation: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    _require_columns(
        train,
        (MODEL_TARGET_COL,),
    )
    _require_columns(
        validation,
        (
            "법인ID",
            "기준년월",
            MODEL_TARGET_COL,
            FUTURE_EVENT_ID_COL,
            LEAD_MONTHS_COL,
            "현재drop50연속개월수",
            "핵심거래_YoY_ratio",
            "drop50_연속개월수",
        ),
    )
    if train[MODEL_TARGET_COL].nunique() < 2:
        raise ValueError("train에 양성과 음성이 모두 필요합니다.")

    feature_columns = model_feature_columns(train)
    base_columns = [
        "법인ID",
        "기준년월",
        MODEL_TARGET_COL,
        FUTURE_EVENT_ID_COL,
        LEAD_MONTHS_COL,
        "현재drop50연속개월수",
    ]
    base = validation[base_columns].copy()
    outputs: list[pd.DataFrame] = []

    prevalence = base.copy()
    prevalence["모델"] = "Prevalence"
    prevalence["예측확률"] = float(train[MODEL_TARGET_COL].mean())
    outputs.append(prevalence)

    rule = base.copy()
    yoy = pd.to_numeric(
        validation["핵심거래_YoY_ratio"],
        errors="coerce",
    ).fillna(1.0)
    current_streak = pd.to_numeric(
        validation["drop50_연속개월수"],
        errors="coerce",
    ).fillna(0)
    rule["모델"] = "CurrentSignalRule"
    rule["예측확률"] = (
        2 * current_streak.clip(upper=2)
        + yoy.lt(0.70).astype(int)
        + (1 - yoy).clip(lower=0)
    )
    outputs.append(rule)

    pipeline = Pipeline(
        [
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
            (
                "model",
                LogisticRegression(
                    C=1.0,
                    class_weight="balanced",
                    max_iter=1000,
                    random_state=42,
                ),
            ),
        ]
    )
    pipeline.fit(
        train[feature_columns],
        train[MODEL_TARGET_COL].astype(int),
    )
    logistic = base.copy()
    logistic["모델"] = "LogisticRegression"
    logistic["예측확률"] = pipeline.predict_proba(
        validation[feature_columns]
    )[:, 1]
    outputs.append(logistic)

    scores = pd.concat(outputs, ignore_index=True)
    return scores, evaluate_scored_rows(scores)


def build_lift_table(
    scores: pd.DataFrame,
    n_bins: int = 10,
) -> pd.DataFrame:
    _require_columns(scores, ("모델", MODEL_TARGET_COL, "예측확률"))
    if n_bins < 1:
        raise ValueError("n_bins는 1 이상이어야 합니다.")
    rows: list[pd.DataFrame] = []
    for model_name, group in scores.groupby("모델", sort=False):
        work = group.copy()
        base_rate = float(work[MODEL_TARGET_COL].mean())
        if work["예측확률"].nunique(dropna=False) == 1:
            rows.append(
                pd.DataFrame(
                    {
                        "모델": [model_name],
                        "점수구간": [1],
                        "행수": [len(work)],
                        "양성수": [int(work[MODEL_TARGET_COL].sum())],
                        "양성률": [base_rate],
                        "최소점수": [work["예측확률"].iloc[0]],
                        "최대점수": [work["예측확률"].iloc[0]],
                        "전체양성률": [base_rate],
                        "Lift": [1.0 if base_rate else np.nan],
                    }
                )
            )
            continue
        rank = work["예측확률"].rank(method="first", ascending=False)
        work["점수구간"] = np.ceil(rank / len(work) * n_bins).astype(int)
        summary = (
            work.groupby("점수구간", as_index=False)
            .agg(
                행수=(MODEL_TARGET_COL, "size"),
                양성수=(MODEL_TARGET_COL, "sum"),
                양성률=(MODEL_TARGET_COL, "mean"),
                최소점수=("예측확률", "min"),
                최대점수=("예측확률", "max"),
            )
            .sort_values("점수구간")
        )
        summary.insert(0, "모델", model_name)
        summary["전체양성률"] = base_rate
        summary["Lift"] = (
            summary["양성률"] / base_rate if base_rate else np.nan
        )
        rows.append(summary)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()
