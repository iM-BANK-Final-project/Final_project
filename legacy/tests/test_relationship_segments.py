from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

import numpy as np
import pandas as pd

from src.segmentation.relationship_segments import (
    SEGMENT_DUMMY_COLUMNS,
    SegmentationConfig,
    assign_l30_h70_m15,
    build_monthly_relationship_axes,
    build_reference_relationship_levels,
    build_rolling_relationship_features,
    build_segment_profile,
    build_segment_stability,
    fit_reference_scores,
    score_against_reference,
    select_complete_segmentation_cohort,
    summarize_relationship_window,
)
from src.segmentation.run_relationship_segments import (
    run_relationship_segmentation,
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


def level_frame(
    activity: list[float],
    deposit: list[float],
    loan: list[float],
) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "법인ID": [f"C{index}" for index in range(len(activity))],
            "거래활동관계수준": activity,
            "수신관계수준": deposit,
            "여신관계수준": loan,
        }
    )


def score_frame(values: list[tuple[float, float, float]]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "법인ID": [f"C{index}" for index in range(len(values))],
            "거래활동점수": [value[0] for value in values],
            "수신관계점수": [value[1] for value in values],
            "여신관계점수": [value[2] for value in values],
        }
    )


def assignment_frame(segments: list[str]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "법인ID": [f"C{index}" for index in range(len(segments))],
            "관계세그먼트": segments,
        }
    )


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


class RollingRelationshipFeatureTests(unittest.TestCase):
    def setUp(self):
        self.source = make_monthly_source(
            customer_ids=("A", "B"),
            years=(2023, 2024),
        )
        for position, customer_id in enumerate(("A", "B"), start=1):
            mask = self.source["법인ID"].eq(customer_id)
            sequence = np.arange(1, 25) * position
            self.source.loc[mask, "요구불입금금액"] = sequence
            self.source.loc[mask, "요구불예금잔액"] = 2 * sequence
            self.source.loc[mask, "여신_운전자금대출잔액"] = 3 * sequence
        self.monthly = build_monthly_relationship_axes(self.source)
        self.reference = build_reference_relationship_levels(self.monthly)

    def test_uses_exact_customer_local_trailing_twelve_months(self):
        rolling = build_rolling_relationship_features(
            self.monthly,
            self.reference,
        )
        anchor = rolling.loc[
            rolling["법인ID"].eq("A")
            & rolling["기준년월"].eq(pd.Period("2024-02", freq="M"))
        ].iloc[0]

        expected_activity = np.median(np.log1p(np.arange(3, 15)))
        expected_deposit = np.median(np.log1p(2 * np.arange(3, 15)))
        expected_loan = np.median(np.log1p(3 * np.arange(3, 15)))
        self.assertAlmostEqual(
            anchor["거래활동관계수준"], expected_activity
        )
        self.assertAlmostEqual(anchor["수신관계수준"], expected_deposit)
        self.assertAlmostEqual(anchor["여신관계수준"], expected_loan)

        customer_b = rolling.loc[
            rolling["법인ID"].eq("B")
            & rolling["기준년월"].eq(pd.Period("2024-02", freq="M"))
        ].iloc[0]
        self.assertAlmostEqual(
            customer_b["거래활동관계수준"],
            float(np.median(np.log1p(2 * np.arange(3, 15)))),
        )

    def test_future_source_changes_do_not_change_anchor_features(self):
        baseline = build_rolling_relationship_features(
            self.monthly,
            self.reference,
        )
        changed_source = self.source.copy()
        future = changed_source["기준년월"].gt(202402)
        changed_source.loc[
            future, SegmentationConfig().amount_cols
        ] = 1_000_000_000.0
        changed_monthly = build_monthly_relationship_axes(changed_source)
        changed = build_rolling_relationship_features(
            changed_monthly,
            self.reference,
        )

        columns = [
            *SegmentationConfig().level_columns,
            *SegmentationConfig().score_columns,
            "관계세그먼트",
            *SEGMENT_DUMMY_COLUMNS,
        ]
        key = (
            baseline["법인ID"].eq("A")
            & baseline["기준년월"].eq(pd.Period("2024-02", freq="M"))
        )
        changed_key = (
            changed["법인ID"].eq("A")
            & changed["기준년월"].eq(pd.Period("2024-02", freq="M"))
        )
        pd.testing.assert_series_equal(
            baseline.loc[key, columns].iloc[0],
            changed.loc[changed_key, columns].iloc[0],
        )

    def test_uses_frozen_reference_and_materializes_one_hot_segments(self):
        rolling = build_rolling_relationship_features(
            self.monthly,
            self.reference,
        )
        last_month = rolling.loc[
            rolling["기준년월"].eq(pd.Period("2024-12", freq="M"))
        ].sort_values("법인ID")

        self.assertEqual(
            last_month["거래활동점수"].tolist(),
            [1.0, 1.0],
        )
        self.assertEqual(
            last_month.loc[:, SEGMENT_DUMMY_COLUMNS].sum(axis=1).tolist(),
            [1, 1],
        )
        for _, row in last_month.iterrows():
            normalized = row["관계세그먼트"].replace("·", "")
            self.assertEqual(row[f"segment_{normalized}"], 1)


class SegmentRuleTests(unittest.TestCase):
    def test_reference_scores_use_average_percentile_for_ties(self):
        levels = level_frame(
            activity=[0, 0, 10, 20],
            deposit=[0, 1, 2, 3],
            loan=[0, 1, 2, 3],
        )

        scored, reference = fit_reference_scores(levels)
        rescored = score_against_reference(levels, reference)

        self.assertEqual(
            scored["거래활동점수"].tolist(),
            [0.375, 0.375, 0.75, 1.0],
        )
        self.assertEqual(
            rescored["거래활동점수"].tolist(),
            [0.5, 0.5, 0.75, 1.0],
        )

    def test_future_scores_use_frozen_reference_distribution(self):
        reference_levels = level_frame(
            activity=[1, 2, 3, 4],
            deposit=[1, 2, 3, 4],
            loan=[1, 2, 3, 4],
        )
        _, reference = fit_reference_scores(reference_levels)
        future = level_frame(
            activity=[0, 2.5, 5],
            deposit=[0, 2.5, 5],
            loan=[0, 2.5, 5],
        )

        scored = score_against_reference(future, reference)

        self.assertEqual(
            scored["거래활동점수"].tolist(),
            [0.0, 0.5, 1.0],
        )

    def test_assigns_all_six_segments_with_priority_and_inclusive_edges(self):
        scored = score_frame(
            [
                (0.30, 0.30, 0.30),
                (0.85, 0.70, 0.10),
                (0.65, 0.40, 0.20),
                (0.20, 0.55, 0.40),
                (0.20, 0.35, 0.50),
                (0.50, 0.40, 0.35),
            ]
        )

        result = assign_l30_h70_m15(scored)

        self.assertEqual(
            result["관계세그먼트"].tolist(),
            [
                "저관계",
                "복합고관계",
                "거래활동중심",
                "수신중심",
                "여신중심",
                "균형·중간관계",
            ],
        )

    def test_profile_counts_and_shares_are_auditable(self):
        assigned = assign_l30_h70_m15(
            score_frame([(0.1, 0.1, 0.1), (0.9, 0.8, 0.1)])
        )

        profile = build_segment_profile(assigned)

        self.assertEqual(profile["법인수"].sum(), 2)
        self.assertAlmostEqual(profile["비율"].sum(), 1.0)
        self.assertEqual(set(profile["관계세그먼트"]), {"저관계", "복합고관계"})


class RunnerTests(unittest.TestCase):
    def test_selects_only_complete_2023_to_2025_customers(self):
        complete = make_monthly_source(
            customer_ids=("A", "B"),
            years=(2023, 2024, 2025),
        )
        incomplete = complete.loc[
            ~(
                complete["법인ID"].eq("B")
                & complete["기준년월"].eq(202512)
            )
        ]
        monthly = build_monthly_relationship_axes(incomplete)

        selected = select_complete_segmentation_cohort(monthly)

        self.assertEqual(selected["법인ID"].unique().tolist(), ["A"])
        self.assertEqual(len(selected), 36)

    def test_stability_contains_overall_and_segment_metrics(self):
        reference = assignment_frame(
            ["저관계", "저관계", "수신중심", "수신중심"]
        )
        comparison = assignment_frame(
            ["저관계", "수신중심", "수신중심", "수신중심"]
        )

        stability = build_segment_stability(reference, comparison)

        overall = stability.loc[stability["구분"].eq("전체")].iloc[0]
        low = stability.loc[stability["구분"].eq("저관계")].iloc[0]
        self.assertEqual(overall["동일세그먼트유지율"], 0.75)
        self.assertAlmostEqual(overall["ARI"], 0.0)
        self.assertEqual(low["기준법인수"], 2)
        self.assertEqual(low["동일세그먼트유지율"], 0.5)
        self.assertIn("구성비변화", stability.columns)

    def test_runner_writes_six_auditable_csv_files(self):
        source = make_monthly_source(
            customer_ids=("A", "B", "C"),
            years=(2023, 2024, 2025),
        )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path = root / "source.csv"
            source.to_csv(input_path, index=False)

            paths = run_relationship_segmentation(
                input_path,
                root / "outputs",
            )

            self.assertEqual(
                set(paths),
                {
                    "reference_2023",
                    "assignments_2023",
                    "profile_2023",
                    "assignments_2024",
                    "profile_2024",
                    "stability_2023_2024",
                },
            )
            self.assertTrue(all(path.exists() for path in paths.values()))
            assignments = pd.read_csv(paths["assignments_2023"])
            self.assertEqual(len(assignments), 3)
            self.assertTrue(
                {
                    "거래활동관계수준",
                    "수신관계수준",
                    "여신관계수준",
                    "거래활동점수",
                    "수신관계점수",
                    "여신관계점수",
                    "관계세그먼트",
                }.issubset(assignments.columns)
            )


if __name__ == "__main__":
    unittest.main()
