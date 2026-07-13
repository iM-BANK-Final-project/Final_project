import unittest

import numpy as np
import pandas as pd

from src.preprocessing.persistent_transaction_weakening_labels import (
    LabelConfig,
    build_core_activity,
    validate_complete_cohort,
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


if __name__ == "__main__":
    unittest.main()
