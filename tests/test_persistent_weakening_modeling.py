import unittest

import pandas as pd

from src.models.persistent_weakening_baseline import (
    FUTURE_EVENT_ID_COL,
    MODEL_TARGET_COL,
    build_modeling_features,
    build_modeling_targets,
    model_feature_columns,
    split_train_validation,
)


def labeled_panel(event_month="2024-05", event_y=1, customer_id="C1"):
    months = pd.period_range("2023-01", "2025-12", freq="M")
    panel = pd.DataFrame(
        {
            "법인ID": customer_id,
            "기준년월": months,
            "핵심거래활동금액": 100.0,
            "입출금활동금액": 40.0,
            "채널활동금액": 40.0,
            "카드활동금액": 20.0,
            "핵심거래_YoY_ratio": 1.0,
            "drop50": False,
            "drop50_연속개월수": 0,
            "core_3m_event": False,
            "Y_지속거래약화_3M70": pd.Series(
                pd.NA,
                index=range(36),
                dtype="Int8",
            ),
            "지속거래약화사건ID": pd.NA,
        }
    )
    event = panel["기준년월"].eq(pd.Period(event_month))
    panel.loc[event, "core_3m_event"] = True
    panel.loc[event, "Y_지속거래약화_3M70"] = event_y
    panel.loc[event, "지속거래약화사건ID"] = f"{customer_id}+{event_month}"
    return panel


class RollingTargetTest(unittest.TestCase):
    def test_positive_event_labels_only_previous_three_anchors(self):
        result = build_modeling_targets(labeled_panel("2024-05"))

        positives = result.loc[result[MODEL_TARGET_COL].eq(1), "기준년월"]

        self.assertEqual(
            positives.astype(str).tolist(),
            ["2024-02", "2024-03", "2024-04"],
        )

    def test_event_at_t_plus_four_is_not_in_target(self):
        result = build_modeling_targets(labeled_panel("2024-06"))

        february = result["기준년월"].eq(pd.Period("2024-02"))

        self.assertEqual(result.loc[february, MODEL_TARGET_COL].iloc[0], 0)

    def test_current_event_anchor_is_excluded(self):
        result = build_modeling_targets(labeled_panel("2024-05"))

        self.assertNotIn("2024-05", result["기준년월"].astype(str).tolist())

    def test_latest_anchor_is_june_2025(self):
        result = build_modeling_targets(labeled_panel("2024-05"))

        self.assertEqual(str(result["기준년월"].max()), "2025-06")

    def test_split_has_six_month_label_window_purge(self):
        result = build_modeling_targets(labeled_panel("2024-05"))

        train, validation = split_train_validation(result)

        self.assertEqual(str(train["기준년월"].min()), "2024-02")
        self.assertEqual(str(train["기준년월"].max()), "2024-09")
        self.assertEqual(str(validation["기준년월"].min()), "2025-04")
        self.assertEqual(str(validation["기준년월"].max()), "2025-06")
        self.assertLess(
            train["label_end"].max(),
            validation["기준년월"].min(),
        )


class PastOnlyFeatureTest(unittest.TestCase):
    def test_changing_future_values_does_not_change_anchor_features(self):
        original = labeled_panel("2024-05")
        changed = original.copy()
        changed.loc[
            changed["기준년월"].gt(pd.Period("2024-02")),
            [
                "핵심거래활동금액",
                "입출금활동금액",
                "채널활동금액",
                "카드활동금액",
            ],
        ] = 999999.0

        before_frame = build_modeling_features(original)
        after_frame = build_modeling_features(changed)
        feature_columns = model_feature_columns(before_frame)
        before = before_frame.set_index(["법인ID", "기준년월"]).loc[
            ("C1", pd.Period("2024-02")), feature_columns
        ]
        after = after_frame.set_index(["법인ID", "기준년월"]).loc[
            ("C1", pd.Period("2024-02")), feature_columns
        ]

        pd.testing.assert_series_equal(before, after)

    def test_forbidden_columns_are_not_model_features(self):
        features = build_modeling_features(labeled_panel("2024-05"))

        selected = model_feature_columns(features)

        forbidden = {
            "Y_지속거래약화_3M70",
            MODEL_TARGET_COL,
            "이벤트이후3개월평균",
            "future3_to_baseline",
            FUTURE_EVENT_ID_COL,
        }
        self.assertTrue(forbidden.isdisjoint(selected))

    def test_customer_rolling_features_do_not_mix_customers(self):
        first = labeled_panel("2024-05", customer_id="C1")
        second = labeled_panel("2025-05", customer_id="C2")
        second["핵심거래활동금액"] = 10000.0

        combined = build_modeling_features(
            pd.concat([first, second], ignore_index=True)
        )
        single = build_modeling_features(first)
        feature_columns = model_feature_columns(single)
        combined_first = combined.loc[
            combined["법인ID"].eq("C1"),
            ["기준년월", *feature_columns],
        ].reset_index(drop=True)
        single_first = single[["기준년월", *feature_columns]].reset_index(
            drop=True
        )

        pd.testing.assert_frame_equal(combined_first, single_first)


if __name__ == "__main__":
    unittest.main()
