from __future__ import annotations

import unittest

import pandas as pd

from src.models.persistent_weakening_baseline import (
    DIRECT_SIGNAL_FEATURES,
    FUTURE_EVENT_ID_COL,
    LABEL_END_COL,
    MODEL_TARGET_COL,
)
from src.models.segment_model_ablation import (
    RELATIONSHIP_SCORE_COLUMNS,
    SEGMENT_DUMMY_COLUMNS,
    build_feature_families,
    join_relationship_features,
)


def modeling_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "법인ID": ["B", "A"],
            "기준년월": pd.PeriodIndex(["2024-03", "2024-02"], freq="M"),
            MODEL_TARGET_COL: [1, 0],
            FUTURE_EVENT_ID_COL: ["B+2024-04", pd.NA],
            LABEL_END_COL: pd.PeriodIndex(["2024-09", "2024-08"], freq="M"),
            "log1p_현재값_핵심거래활동금액": [1.0, 2.0],
            "YoY_ratio_핵심거래활동금액": [0.4, 1.1],
            "현재drop50": [1.0, 0.0],
            "현재drop50연속개월수": [2.0, 0.0],
        }
    )


def relationship_frame() -> pd.DataFrame:
    frame = pd.DataFrame(
        {
            "법인ID": ["A", "B"],
            "기준년월": pd.PeriodIndex(["2024-02", "2024-03"], freq="M"),
            "거래활동점수": [0.2, 0.8],
            "수신관계점수": [0.3, 0.7],
            "여신관계점수": [0.4, 0.6],
            "관계세그먼트": ["균형·중간관계", "거래활동중심"],
        }
    )
    for column in SEGMENT_DUMMY_COLUMNS:
        frame[column] = 0
    frame.loc[0, "segment_균형중간관계"] = 1
    frame.loc[1, "segment_거래활동중심"] = 1
    return frame


class SafeJoinTests(unittest.TestCase):
    def test_join_preserves_modeling_rows_order_and_labels(self):
        modeling = modeling_frame()

        joined = join_relationship_features(modeling, relationship_frame())

        self.assertEqual(len(joined), len(modeling))
        pd.testing.assert_frame_equal(
            joined.loc[:, modeling.columns],
            modeling,
        )
        self.assertEqual(joined["거래활동점수"].tolist(), [0.8, 0.2])

    def test_rejects_duplicate_keys_on_either_side(self):
        modeling = modeling_frame()
        duplicated_modeling = pd.concat(
            [modeling, modeling.iloc[[0]]], ignore_index=True
        )
        duplicated_relationship = pd.concat(
            [relationship_frame(), relationship_frame().iloc[[0]]],
            ignore_index=True,
        )

        with self.assertRaisesRegex(ValueError, "중복"):
            join_relationship_features(
                duplicated_modeling,
                relationship_frame(),
            )
        with self.assertRaisesRegex(ValueError, "중복"):
            join_relationship_features(modeling, duplicated_relationship)

    def test_rejects_missing_relationship_match(self):
        with self.assertRaisesRegex(ValueError, "누락"):
            join_relationship_features(
                modeling_frame(),
                relationship_frame().iloc[[0]],
            )


class FeatureFamilyTests(unittest.TestCase):
    def test_builds_exact_numeric_feature_families(self):
        joined = join_relationship_features(
            modeling_frame(), relationship_frame()
        )

        families = build_feature_families(joined)

        base = families["Base"]
        no_direct = families["NoDirect"]
        self.assertEqual(families["Segment"], [*base, *SEGMENT_DUMMY_COLUMNS])
        self.assertEqual(
            families["Axis"], [*base, *RELATIONSHIP_SCORE_COLUMNS]
        )
        self.assertEqual(
            families["Both"],
            [*base, *RELATIONSHIP_SCORE_COLUMNS, *SEGMENT_DUMMY_COLUMNS],
        )
        self.assertEqual(set(base) - set(no_direct), set(DIRECT_SIGNAL_FEATURES))
        for columns in families.values():
            self.assertTrue(
                all(pd.api.types.is_numeric_dtype(joined[col]) for col in columns)
            )


if __name__ == "__main__":
    unittest.main()
