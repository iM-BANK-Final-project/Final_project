import unittest

import pandas as pd

from src.models.persistent_weakening_baseline import (
    MODEL_TARGET_COL,
    build_modeling_targets,
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


if __name__ == "__main__":
    unittest.main()
