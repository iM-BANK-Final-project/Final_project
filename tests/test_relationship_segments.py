from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from src.segmentation.relationship_segments import (
    SegmentationConfig,
    build_monthly_relationship_axes,
    summarize_relationship_window,
)


def make_monthly_source(
    customer_ids: tuple[str, ...] = ("A",),
    years: tuple[int, ...] = (2023,),
) -> pd.DataFrame:
    config = SegmentationConfig()
    rows: list[dict[str, object]] = []
    for customer_position, customer_id in enumerate(customer_ids, start=1):
        for year in years:
            for month in range(1, 13):
                row: dict[str, object] = {
                    config.customer_id_col: customer_id,
                    config.month_col: year * 100 + month,
                }
                row.update({column: 0.0 for column in config.amount_cols})
                row["요구불입금금액"] = float(month * customer_position)
                row["요구불예금잔액"] = float(2 * month * customer_position)
                row["여신_운전자금대출잔액"] = float(
                    3 * month * customer_position
                )
                rows.append(row)
    return pd.DataFrame(rows)


class RelationshipLevelTests(unittest.TestCase):
    def test_sums_report_axes_and_uses_median_log_level(self):
        source = make_monthly_source()

        monthly = build_monthly_relationship_axes(source)
        levels = summarize_relationship_window(
            monthly,
            "2023-01",
            "2023-12",
        )

        self.assertEqual(monthly["거래활동금액"].tolist(), list(range(1, 13)))
        self.assertEqual(
            monthly["수신관계금액"].tolist(),
            list(range(2, 25, 2)),
        )
        self.assertEqual(
            monthly["여신관계금액"].tolist(),
            list(range(3, 37, 3)),
        )
        self.assertAlmostEqual(
            levels.loc[0, "거래활동관계수준"],
            float(np.median(np.log1p(np.arange(1, 13)))),
        )
        self.assertAlmostEqual(
            levels.loc[0, "수신관계수준"],
            float(np.median(np.log1p(np.arange(2, 25, 2)))),
        )
        self.assertAlmostEqual(
            levels.loc[0, "여신관계수준"],
            float(np.median(np.log1p(np.arange(3, 37, 3)))),
        )

    def test_rejects_missing_amount_instead_of_filling_zero(self):
        source = make_monthly_source()
        source.loc[0, "요구불입금금액"] = np.nan

        with self.assertRaisesRegex(ValueError, "결측"):
            build_monthly_relationship_axes(source)

    def test_rejects_negative_amount(self):
        source = make_monthly_source()
        source.loc[0, "요구불입금금액"] = -1

        with self.assertRaisesRegex(ValueError, "음수"):
            build_monthly_relationship_axes(source)

    def test_rejects_duplicate_customer_month(self):
        source = make_monthly_source()
        duplicate = pd.concat([source, source.iloc[[0]]], ignore_index=True)

        with self.assertRaisesRegex(ValueError, "중복"):
            build_monthly_relationship_axes(duplicate)

    def test_rejects_incomplete_twelve_month_window(self):
        source = make_monthly_source()
        monthly = build_monthly_relationship_axes(source.iloc[:-1])

        with self.assertRaisesRegex(ValueError, "12개월"):
            summarize_relationship_window(
                monthly,
                "2023-01",
                "2023-12",
            )


if __name__ == "__main__":
    unittest.main()
