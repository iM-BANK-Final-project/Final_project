from __future__ import annotations

import pandas as pd

from src.models.persistent_weakening_baseline import (
    ablation_feature_columns,
    model_feature_columns,
)
from src.segmentation.relationship_segments import (
    SEGMENT_DUMMY_COLUMNS as RELATIONSHIP_SEGMENT_DUMMY_COLUMNS,
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
