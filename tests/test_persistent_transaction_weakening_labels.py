import unittest
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

from src.preprocessing.persistent_transaction_weakening_labels import (
    LabelConfig,
    build_core_activity,
    build_persistent_weakening_labels,
    validate_complete_cohort,
)
from src.preprocessing.run_persistent_transaction_weakening_labels import (
    run_label_pipeline,
)


RAW_COLUMNS = {
    "요구불입금금액": 1.0,
    "요구불출금금액": 2.0,
    "창구거래금액": 3.0,
    "인터넷뱅킹거래금액": 4.0,
    "스마트뱅킹거래금액": 5.0,
    "폰뱅킹거래금액": 6.0,
    "ATM거래금액": 7.0,
    "신용카드사용금액": 8.0,
    "체크카드사용금액": 9.0,
}


def complete_frame(customer="C1"):
    months = pd.period_range("2023-01", "2025-12", freq="M")
    return pd.DataFrame(
        [
            {
                "법인ID": customer,
                "기준년월": int(month.strftime("%Y%m")),
                **RAW_COLUMNS,
            }
            for month in months
        ]
    )


def activity_frame(core_values):
    frame = complete_frame()
    for index, core_value in enumerate(core_values):
        for column in RAW_COLUMNS:
            frame.loc[index, column] = core_value / len(RAW_COLUMNS)
    return frame


class CoreActivityContractTest(unittest.TestCase):
    def test_aggregates_flow_channel_card_and_core(self):
        result = build_core_activity(complete_frame(), LabelConfig())
        row = result.iloc[0]
        self.assertEqual(row["입출금활동금액"], 3.0)
        self.assertEqual(row["채널활동금액"], 25.0)
        self.assertEqual(row["카드활동금액"], 17.0)
        self.assertEqual(row["핵심거래활동금액"], 45.0)

    def test_missing_component_keeps_core_activity_missing(self):
        frame = complete_frame()
        frame.loc[0, "ATM거래금액"] = np.nan
        result = build_core_activity(frame, LabelConfig())
        self.assertTrue(pd.isna(result.loc[0, "핵심거래활동금액"]))

    def test_rejects_duplicate_customer_month(self):
        frame = pd.concat([complete_frame(), complete_frame().iloc[[0]]])
        with self.assertRaisesRegex(ValueError, "중복"):
            validate_complete_cohort(frame, LabelConfig())

    def test_rejects_incomplete_month_sequence(self):
        with self.assertRaisesRegex(ValueError, "36개월"):
            validate_complete_cohort(complete_frame().iloc[:-1], LabelConfig())


class PersistentWeakeningLabelTest(unittest.TestCase):
    def test_marks_only_first_completion_month_and_confirms_below_point_seven(self):
        values = [100.0] * 36
        values[12:18] = [49.0, 49.0, 49.0, 40.0, 40.0, 40.0]

        panel, events = build_persistent_weakening_labels(activity_frame(values))

        event = events.iloc[0]
        expected_baseline = (10 * 100.0 + 2 * 49.0) / 12
        self.assertEqual(str(event["기준년월"]), "2024-03")
        self.assertAlmostEqual(event["이벤트이전12개월평균"], expected_baseline)
        self.assertAlmostEqual(event["future3_to_baseline"], 40.0 / expected_baseline)
        self.assertEqual(event["Y_지속거래약화_3M70"], 1)
        self.assertEqual(panel["core_3m_event"].sum(), 1)

    def test_ratio_equal_half_is_not_drop50(self):
        values = [100.0] * 36
        values[12:15] = [49.0, 50.0, 49.0]

        panel, events = build_persistent_weakening_labels(activity_frame(values))

        february = panel["기준년월"].eq(pd.Period("2024-02"))
        self.assertFalse(panel.loc[february, "drop50"].iloc[0])
        self.assertTrue(events.empty)

    def test_ratio_equal_point_seven_is_negative(self):
        values = [100.0] * 36
        values[12:15] = [49.0, 49.0, 49.0]
        baseline = (10 * 100.0 + 2 * 49.0) / 12
        values[15:18] = [baseline * 0.70] * 3

        _, events = build_persistent_weakening_labels(activity_frame(values))

        self.assertAlmostEqual(events.iloc[0]["future3_to_baseline"], 0.70)
        self.assertEqual(events.iloc[0]["Y_지속거래약화_3M70"], 0)

    def test_insufficient_future_window_keeps_y_missing(self):
        values = [100.0] * 36
        values[33:36] = [49.0, 49.0, 49.0]

        _, events = build_persistent_weakening_labels(activity_frame(values))

        self.assertTrue(pd.isna(events.iloc[0]["Y_지속거래약화_3M70"]))

    def test_zero_prior_year_value_makes_drop50_undecidable(self):
        values = [0.0] * 36
        values[12:15] = [10.0, 10.0, 10.0]
        values[24:36] = [100.0] * 12

        panel, events = build_persistent_weakening_labels(activity_frame(values))

        target_months = panel["기준년월"].between(
            pd.Period("2024-01"),
            pd.Period("2024-03"),
        )
        self.assertTrue(panel.loc[target_months, "drop50"].isna().all())
        self.assertTrue(events.empty)

    def test_recovery_allows_a_new_three_month_event(self):
        values = [100.0] * 36
        values[12:18] = [49.0, 49.0, 49.0, 100.0, 49.0, 49.0]
        values[18:22] = [49.0, 40.0, 40.0, 40.0]

        _, events = build_persistent_weakening_labels(activity_frame(values))

        self.assertEqual(events["기준년월"].astype(str).tolist(), ["2024-03", "2024-07"])
        self.assertEqual(events["지속거래약화사건ID"].nunique(), 2)


class LabelRunnerTest(unittest.TestCase):
    def test_writes_panel_and_event_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path = root / "input.csv"
            complete_frame().to_csv(input_path, index=False)

            panel_path, events_path = run_label_pipeline(
                input_path,
                root / "outputs",
            )

            self.assertTrue(panel_path.exists())
            self.assertTrue(events_path.exists())
            self.assertEqual(
                panel_path.name,
                "persistent_transaction_weakening_panel.csv",
            )
            self.assertEqual(
                events_path.name,
                "persistent_transaction_weakening_events.csv",
            )


if __name__ == "__main__":
    unittest.main()
