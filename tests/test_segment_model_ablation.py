from __future__ import annotations

import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from src.models.persistent_weakening_baseline import (
    DIRECT_SIGNAL_FEATURES,
    FUTURE_EVENT_ID_COL,
    LABEL_END_COL,
    LEAD_MONTHS_COL,
    MODEL_TARGET_COL,
)
from src.models.segment_model_ablation import (
    RELATIONSHIP_SCORE_COLUMNS,
    SEGMENT_DUMMY_COLUMNS,
    build_feature_families,
    build_segment_diagnostics,
    fit_and_score_segment_ablation,
    join_relationship_features,
    select_best_feature_addition,
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


def experiment_frame() -> pd.DataFrame:
    rows = pd.concat([modeling_frame()] * 5, ignore_index=True)
    rows["법인ID"] = [f"C{index}" for index in range(10)]
    rows["기준년월"] = pd.PeriodIndex(
        ["2024-02"] * 10,
        freq="M",
    )
    rows[MODEL_TARGET_COL] = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0]
    rows[FUTURE_EVENT_ID_COL] = [
        "C0+2024-03",
        pd.NA,
        pd.NA,
        pd.NA,
        pd.NA,
        "C5+2024-04",
        pd.NA,
        pd.NA,
        pd.NA,
        pd.NA,
    ]
    rows[LEAD_MONTHS_COL] = [1, pd.NA, pd.NA, pd.NA, pd.NA, 2, pd.NA, pd.NA, pd.NA, pd.NA]
    rows["현재drop50연속개월수"] = [0.0] * 10
    rows["관계세그먼트"] = [
        "저관계",
        "균형·중간관계",
        "거래활동중심",
        "수신중심",
        "여신중심",
        "복합고관계",
        "저관계",
        "균형·중간관계",
        "거래활동중심",
        "수신중심",
    ]
    for position, column in enumerate(RELATIONSHIP_SCORE_COLUMNS, start=1):
        rows[column] = np.linspace(0.1 * position, 0.9, 10)
    for column in SEGMENT_DUMMY_COLUMNS:
        rows[column] = 0
    for index, segment in enumerate(rows["관계세그먼트"]):
        rows.loc[index, f"segment_{segment.replace('·', '')}"] = 1
    return rows


class FakeModel:
    fitted_columns: list[tuple[str, ...]] = []

    def fit(self, features, target):
        self.columns = tuple(features.columns)
        self.__class__.fitted_columns.append(self.columns)
        return self

    def predict_proba(self, features):
        probability = np.linspace(0.9, 0.1, len(features))
        return np.column_stack([1 - probability, probability])


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


class FixedAblationExperimentTests(unittest.TestCase):
    def setUp(self):
        FakeModel.fitted_columns = []

    def test_selector_uses_documented_tie_break_order(self):
        metrics = pd.DataFrame(
            {
                "모델": [
                    "LightGBM_Base",
                    "LightGBM_Segment",
                    "LightGBM_Axis",
                    "LightGBM_Both",
                ],
                "K": [0.10] * 4,
                "PR_AUC": [0.20, 0.21, 0.21, 0.21],
                "사건Recall_at_K": [0.6, 0.7, 0.8, 0.8],
                "Recall_at_K": [0.6, 0.7, 0.7, 0.7],
            }
        )
        families = {
            "Base": ["b"],
            "Segment": ["b", "s1", "s2"],
            "Axis": ["b", "a"],
            "Both": ["b", "a", "s1", "s2"],
        }

        selected = select_best_feature_addition(metrics, families)

        self.assertEqual(selected, "Axis")

    @patch(
        "src.models.segment_model_ablation.select_best_feature_addition",
        return_value="Axis",
    )
    @patch(
        "src.models.segment_model_ablation.build_fixed_lightgbm",
        side_effect=FakeModel,
    )
    def test_all_models_use_fixed_builder_same_rows_and_add_best_to_no_direct(
        self,
        mocked_builder,
        _mocked_selector,
    ):
        frame = experiment_frame()
        train = frame.copy()
        validation = frame.iloc[::-1].reset_index(drop=True)

        scores, metrics, selection = fit_and_score_segment_ablation(
            train,
            validation,
        )

        expected_models = {
            "LightGBM_Base",
            "LightGBM_Segment",
            "LightGBM_Axis",
            "LightGBM_Both",
            "LightGBM_NoDirect",
            "LightGBM_NoDirect_Best",
        }
        self.assertEqual(set(scores["모델"]), expected_models)
        self.assertEqual(set(metrics["모델"]), expected_models)
        self.assertEqual(mocked_builder.call_count, 6)
        for _, group in scores.groupby("모델"):
            self.assertEqual(
                group[["법인ID", "기준년월"]].reset_index(drop=True).to_dict("records"),
                validation[["법인ID", "기준년월"]].to_dict("records"),
            )
        no_direct_best = selection.loc[
            selection["모델"].eq("LightGBM_NoDirect_Best")
        ].iloc[0]
        self.assertEqual(no_direct_best["추가feature군"], "Axis")
        self.assertEqual(no_direct_best["추가feature수"], 3)

    @patch(
        "src.models.segment_model_ablation.select_best_feature_addition",
        return_value="Base",
    )
    @patch(
        "src.models.segment_model_ablation.build_fixed_lightgbm",
        side_effect=FakeModel,
    )
    def test_base_winner_does_not_create_duplicate_no_direct_best(
        self,
        mocked_builder,
        _mocked_selector,
    ):
        frame = experiment_frame()

        scores, _, _ = fit_and_score_segment_ablation(frame, frame)

        self.assertNotIn("LightGBM_NoDirect_Best", set(scores["모델"]))
        self.assertEqual(mocked_builder.call_count, 5)

    def test_segment_diagnostics_include_all_fixed_segments(self):
        frame = experiment_frame()
        scores = frame.loc[
            :, [
                "법인ID",
                "기준년월",
                MODEL_TARGET_COL,
                FUTURE_EVENT_ID_COL,
                LEAD_MONTHS_COL,
                "현재drop50연속개월수",
                "관계세그먼트",
            ]
        ].copy()
        scores["모델"] = "LightGBM_Base"
        scores["예측확률"] = np.linspace(1.0, 0.1, len(scores))
        scores = scores.loc[
            ~scores["관계세그먼트"].eq("여신중심")
        ].reset_index(drop=True)

        diagnostics = build_segment_diagnostics(scores)

        self.assertEqual(len(diagnostics), 6)
        absent = diagnostics.loc[
            diagnostics["관계세그먼트"].eq("여신중심")
        ].iloc[0]
        self.assertEqual(absent["행수"], 0)
        self.assertEqual(absent["상위10%알림수"], 0)
        self.assertTrue(
            {
                "상위10%알림구성비",
                "상위10%Recall",
                "상위10%Precision",
                "상위10%Lift",
            }.issubset(diagnostics.columns)
        )


if __name__ == "__main__":
    unittest.main()
