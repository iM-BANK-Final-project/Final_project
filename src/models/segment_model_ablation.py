from __future__ import annotations

import numpy as np
import pandas as pd

from src.models.persistent_weakening_baseline import (
    FUTURE_EVENT_ID_COL,
    LEAD_MONTHS_COL,
    MODEL_TARGET_COL,
    ablation_feature_columns,
    build_fixed_lightgbm,
    evaluate_scored_rows,
    model_feature_columns,
)
from src.segmentation.relationship_segments import (
    SEGMENT_DUMMY_COLUMNS as RELATIONSHIP_SEGMENT_DUMMY_COLUMNS,
    SEGMENT_ORDER,
    SegmentationConfig,
)


RELATIONSHIP_SCORE_COLUMNS = SegmentationConfig().score_columns
SEGMENT_DUMMY_COLUMNS = RELATIONSHIP_SEGMENT_DUMMY_COLUMNS
JOIN_KEYS = ("법인ID", "기준년월")


def _require_columns(frame: pd.DataFrame, columns: tuple[str, ...]) -> None:
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise ValueError(f"필수 컬럼이 없습니다: {missing}")


def join_relationship_features(
    modeling: pd.DataFrame,
    relationship_features: pd.DataFrame,
) -> pd.DataFrame:
    relationship_columns = (
        *RELATIONSHIP_SCORE_COLUMNS,
        "관계세그먼트",
        *SEGMENT_DUMMY_COLUMNS,
    )
    _require_columns(modeling, JOIN_KEYS)
    _require_columns(
        relationship_features,
        (*JOIN_KEYS, *relationship_columns),
    )
    if modeling.duplicated(list(JOIN_KEYS)).any():
        raise ValueError("모델링 패널에 법인×기준월 중복이 있습니다.")
    if relationship_features.duplicated(list(JOIN_KEYS)).any():
        raise ValueError("관계 feature에 법인×기준월 중복이 있습니다.")
    overlapping = set(relationship_columns).intersection(modeling.columns)
    if overlapping:
        raise ValueError(f"모델링 패널에 관계 feature가 이미 있습니다: {overlapping}")

    left = modeling.copy()
    left["_원본행순서"] = range(len(left))
    joined = left.merge(
        relationship_features.loc[:, [*JOIN_KEYS, *relationship_columns]],
        on=list(JOIN_KEYS),
        how="left",
        validate="one_to_one",
        indicator=True,
        sort=False,
    )
    if not joined["_merge"].eq("both").all():
        missing = joined.loc[
            joined["_merge"].ne("both"), list(JOIN_KEYS)
        ].head(5)
        raise ValueError(
            "모델링 패널에 대응하는 관계 feature가 누락되었습니다: "
            f"{missing.to_dict(orient='records')}"
        )
    joined = (
        joined.sort_values("_원본행순서")
        .drop(columns=["_원본행순서", "_merge"])
        .reset_index(drop=True)
    )
    expected = modeling.reset_index(drop=True)
    if not joined.loc[:, modeling.columns].equals(expected):
        raise ValueError("관계 feature 결합 중 모델링 원본 값이 변경되었습니다.")
    return joined


def build_feature_families(frame: pd.DataFrame) -> dict[str, list[str]]:
    _require_columns(
        frame,
        (*RELATIONSHIP_SCORE_COLUMNS, *SEGMENT_DUMMY_COLUMNS),
    )
    base = model_feature_columns(frame)
    no_direct = ablation_feature_columns(frame)
    families = {
        "Base": base,
        "Segment": [*base, *SEGMENT_DUMMY_COLUMNS],
        "Axis": [*base, *RELATIONSHIP_SCORE_COLUMNS],
        "Both": [
            *base,
            *RELATIONSHIP_SCORE_COLUMNS,
            *SEGMENT_DUMMY_COLUMNS,
        ],
        "NoDirect": no_direct,
    }
    non_numeric = {
        column
        for columns in families.values()
        for column in columns
        if not pd.api.types.is_numeric_dtype(frame[column])
    }
    if non_numeric:
        raise ValueError(
            f"수치형 feature가 아닌 컬럼이 있습니다: {sorted(non_numeric)}"
        )
    return families


def select_best_feature_addition(
    metrics: pd.DataFrame,
    feature_families: dict[str, list[str]],
) -> str:
    model_to_family = {
        "LightGBM_Base": "Base",
        "LightGBM_Segment": "Segment",
        "LightGBM_Axis": "Axis",
        "LightGBM_Both": "Both",
    }
    required = (
        "모델",
        "K",
        "PR_AUC",
        "사건Recall_at_K",
        "Recall_at_K",
    )
    _require_columns(metrics, required)
    missing_families = set(model_to_family.values()).difference(feature_families)
    if missing_families:
        raise ValueError(f"선택할 feature family가 없습니다: {missing_families}")

    candidates = metrics.loc[
        metrics["모델"].isin(model_to_family)
        & np.isclose(metrics["K"].astype(float), 0.10)
    ].copy()
    if set(candidates["모델"]) != set(model_to_family):
        raise ValueError("K=10% 1단계 모델 지표가 모두 필요합니다.")
    if candidates["모델"].duplicated().any():
        raise ValueError("K=10% 모델 지표가 중복되었습니다.")
    candidates["feature군"] = candidates["모델"].map(model_to_family)
    base_count = len(feature_families["Base"])
    candidates["추가feature수"] = candidates["feature군"].map(
        lambda family: len(feature_families[family]) - base_count
    )
    for column in ("PR_AUC", "사건Recall_at_K", "Recall_at_K"):
        candidates[column] = pd.to_numeric(
            candidates[column], errors="coerce"
        ).fillna(-np.inf)
    candidates["_순서"] = candidates["feature군"].map(
        {"Base": 0, "Segment": 1, "Axis": 2, "Both": 3}
    )
    selected = candidates.sort_values(
        [
            "PR_AUC",
            "사건Recall_at_K",
            "Recall_at_K",
            "추가feature수",
            "_순서",
        ],
        ascending=[False, False, False, True, True],
        kind="mergesort",
    ).iloc[0]
    return str(selected["feature군"])


def _score_lightgbm(
    train: pd.DataFrame,
    validation: pd.DataFrame,
    columns: list[str],
    model_name: str,
) -> pd.DataFrame:
    model = build_fixed_lightgbm()
    model.fit(
        train.loc[:, columns].astype(float),
        train[MODEL_TARGET_COL].astype(int),
    )
    output_columns = [
        "법인ID",
        "기준년월",
        MODEL_TARGET_COL,
        FUTURE_EVENT_ID_COL,
        LEAD_MONTHS_COL,
        "현재drop50연속개월수",
        "관계세그먼트",
    ]
    scored = validation.loc[:, output_columns].copy()
    scored["모델"] = model_name
    scored["예측확률"] = model.predict_proba(
        validation.loc[:, columns].astype(float)
    )[:, 1]
    return scored


def fit_and_score_segment_ablation(
    train: pd.DataFrame,
    validation: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    validation_required = (
        "법인ID",
        "기준년월",
        MODEL_TARGET_COL,
        FUTURE_EVENT_ID_COL,
        LEAD_MONTHS_COL,
        "현재drop50연속개월수",
        "관계세그먼트",
    )
    _require_columns(train, (MODEL_TARGET_COL,))
    _require_columns(validation, validation_required)
    if train[MODEL_TARGET_COL].nunique() < 2:
        raise ValueError("train에 양성과 음성이 모두 필요합니다.")

    train_families = build_feature_families(train)
    validation_families = build_feature_families(validation)
    for family, columns in train_families.items():
        if validation_families[family] != columns:
            raise ValueError(f"train·validation {family} feature가 다릅니다.")

    phase_one = (
        ("LightGBM_Base", "Base"),
        ("LightGBM_Segment", "Segment"),
        ("LightGBM_Axis", "Axis"),
        ("LightGBM_Both", "Both"),
    )
    outputs: list[pd.DataFrame] = []
    selection_rows: list[dict[str, object]] = []
    base_count = len(train_families["Base"])
    for model_name, family in phase_one:
        columns = train_families[family]
        outputs.append(
            _score_lightgbm(train, validation, columns, model_name)
        )
        selection_rows.append(
            {
                "모델": model_name,
                "feature군": family,
                "feature수": len(columns),
                "추가feature군": family if family != "Base" else "없음",
                "추가feature수": len(columns) - base_count,
            }
        )

    phase_one_scores = pd.concat(outputs, ignore_index=True)
    phase_one_metrics = evaluate_scored_rows(phase_one_scores)
    best_family = select_best_feature_addition(
        phase_one_metrics,
        train_families,
    )

    no_direct_columns = train_families["NoDirect"]
    outputs.append(
        _score_lightgbm(
            train,
            validation,
            no_direct_columns,
            "LightGBM_NoDirect",
        )
    )
    selection_rows.append(
        {
            "모델": "LightGBM_NoDirect",
            "feature군": "NoDirect",
            "feature수": len(no_direct_columns),
            "추가feature군": "없음",
            "추가feature수": 0,
        }
    )

    if best_family != "Base":
        additions = [
            column
            for column in train_families[best_family]
            if column not in train_families["Base"]
        ]
        no_direct_best_columns = [*no_direct_columns, *additions]
        outputs.append(
            _score_lightgbm(
                train,
                validation,
                no_direct_best_columns,
                "LightGBM_NoDirect_Best",
            )
        )
        selection_rows.append(
            {
                "모델": "LightGBM_NoDirect_Best",
                "feature군": "NoDirect+Best",
                "feature수": len(no_direct_best_columns),
                "추가feature군": best_family,
                "추가feature수": len(additions),
            }
        )

    scores = pd.concat(outputs, ignore_index=True)
    metrics = evaluate_scored_rows(scores)
    selection = pd.DataFrame(selection_rows)
    selection["1단계선택"] = selection["feature군"].eq(best_family)
    selection["선택기준K"] = 0.10
    return scores, metrics, selection


def build_segment_diagnostics(scores: pd.DataFrame) -> pd.DataFrame:
    _require_columns(
        scores,
        (
            "모델",
            "관계세그먼트",
            MODEL_TARGET_COL,
            "예측확률",
        ),
    )
    invalid = set(scores["관계세그먼트"].dropna()) - set(SEGMENT_ORDER)
    if invalid:
        raise ValueError(f"정의되지 않은 관계세그먼트가 있습니다: {invalid}")

    rows: list[dict[str, object]] = []
    for model_name, group in scores.groupby("모델", sort=False):
        group = group.copy()
        alert_count = max(1, int(np.ceil(len(group) * 0.10)))
        top = group.nlargest(alert_count, "예측확률")
        global_base_rate = float(group[MODEL_TARGET_COL].mean())
        for segment in SEGMENT_ORDER:
            segment_rows = group.loc[group["관계세그먼트"].eq(segment)]
            segment_alerts = top.loc[top["관계세그먼트"].eq(segment)]
            count = len(segment_rows)
            positives = int(segment_rows[MODEL_TARGET_COL].sum())
            alerts = len(segment_alerts)
            captured = int(segment_alerts[MODEL_TARGET_COL].sum())
            precision = captured / alerts if alerts else 0.0
            rows.append(
                {
                    "모델": model_name,
                    "관계세그먼트": segment,
                    "행수": count,
                    "양성수": positives,
                    "양성률": positives / count if count else 0.0,
                    "평균예측확률": (
                        float(segment_rows["예측확률"].mean())
                        if count
                        else 0.0
                    ),
                    "상위10%알림수": alerts,
                    "상위10%알림구성비": alerts / alert_count,
                    "상위10%포착양성수": captured,
                    "상위10%Recall": captured / positives if positives else 0.0,
                    "상위10%Precision": precision,
                    "상위10%Lift": (
                        precision / global_base_rate
                        if global_base_rate
                        else 0.0
                    ),
                }
            )
    return pd.DataFrame(rows)
