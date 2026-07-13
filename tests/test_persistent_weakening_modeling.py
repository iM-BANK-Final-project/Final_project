import unittest
import tempfile
from pathlib import Path

import pandas as pd

from src.models.persistent_weakening_baseline import (
    FUTURE_EVENT_ID_COL,
    LEAD_MONTHS_COL,
    MODEL_TARGET_COL,
    build_lift_table,
    build_modeling_features,
    build_modeling_targets,
    evaluate_scored_rows,
    fit_and_score_baselines,
    model_feature_columns,
    split_train_validation,
)
from src.models.run_persistent_weakening_baseline import (
    OUTPUT_FILENAMES,
    run_baseline,
    write_baseline_outputs,
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


def raw_activity_panel(customer_id, event_month=None):
    months = pd.period_range("2023-01", "2025-12", freq="M")
    core_values = [100.0] * len(months)
    if event_month is not None:
        event_index = months.get_loc(pd.Period(event_month))
        core_values[event_index - 2 : event_index + 1] = [49.0, 49.0, 49.0]
        core_values[event_index + 1 : event_index + 4] = [40.0, 40.0, 40.0]
    amount_columns = [
        "요구불입금금액",
        "요구불출금금액",
        "창구거래금액",
        "인터넷뱅킹거래금액",
        "스마트뱅킹거래금액",
        "폰뱅킹거래금액",
        "ATM거래금액",
        "신용카드사용금액",
        "체크카드사용금액",
    ]
    rows = []
    for month, core_value in zip(months, core_values):
        row = {
            "법인ID": customer_id,
            "기준년월": int(month.strftime("%Y%m")),
        }
        row.update(
            {
                column: core_value / len(amount_columns)
                for column in amount_columns
            }
        )
        rows.append(row)
    return pd.DataFrame(rows)


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

    def test_excludes_positive_event_month_and_all_later_anchors(self):
        result = build_modeling_targets(labeled_panel("2024-05"))

        self.assertEqual(str(result["기준년월"].max()), "2024-04")
        self.assertFalse(
            result["기준년월"].ge(pd.Period("2024-05")).any()
        )

    def test_latest_anchor_is_june_2025(self):
        result = build_modeling_targets(labeled_panel("2024-05", event_y=0))

        self.assertEqual(str(result["기준년월"].max()), "2025-06")

    def test_split_has_six_month_label_window_purge(self):
        result = build_modeling_targets(labeled_panel("2024-05", event_y=0))

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


class BaselineEvaluationTest(unittest.TestCase):
    def test_constant_scores_do_not_report_arbitrary_ranking_metrics(self):
        scored = pd.DataFrame(
            {
                "법인ID": ["A", "B", "C", "D"],
                "기준년월": [pd.Period("2025-04")] * 4,
                MODEL_TARGET_COL: [1, 0, 1, 0],
                FUTURE_EVENT_ID_COL: [
                    "A+2025-05",
                    pd.NA,
                    "C+2025-06",
                    pd.NA,
                ],
                LEAD_MONTHS_COL: [1, pd.NA, 2, pd.NA],
                "현재drop50연속개월수": [0, 0, 1, 0],
                "모델": "Prevalence",
                "예측확률": 0.5,
            }
        )

        metrics = evaluate_scored_rows(scored, top_fractions=(0.5,))

        self.assertTrue(pd.isna(metrics.iloc[0]["Recall_at_K"]))
        self.assertTrue(pd.isna(metrics.iloc[0]["Lift_at_K"]))
        self.assertTrue(pd.isna(metrics.iloc[0]["사건Recall_at_K"]))
        lift = build_lift_table(scored, n_bins=2)
        self.assertEqual(len(lift), 1)
        self.assertEqual(lift.iloc[0]["Lift"], 1.0)

    def test_top_half_metrics_and_event_recall(self):
        scored = pd.DataFrame(
            {
                "법인ID": ["A", "B", "C", "D"],
                "기준년월": [pd.Period("2025-04")] * 4,
                MODEL_TARGET_COL: [1, 0, 1, 0],
                FUTURE_EVENT_ID_COL: [
                    "A+2025-05",
                    pd.NA,
                    "C+2025-06",
                    pd.NA,
                ],
                LEAD_MONTHS_COL: [1, pd.NA, 2, pd.NA],
                "현재drop50연속개월수": [0, 0, 1, 0],
                "모델": "rule",
                "예측확률": [0.9, 0.8, 0.7, 0.1],
            }
        )

        metrics = evaluate_scored_rows(scored, top_fractions=(0.5,))

        row = metrics.iloc[0]
        self.assertEqual(row["Recall_at_K"], 0.5)
        self.assertEqual(row["Precision_at_K"], 0.5)
        self.assertEqual(row["Lift_at_K"], 1.0)
        self.assertEqual(row["사건Recall_at_K"], 0.5)
        self.assertEqual(row["Lead1_Recall_at_K"], 1.0)
        self.assertEqual(row["Lead2_Recall_at_K"], 0.0)
        self.assertEqual(row["현재무감소_Recall_at_K"], 1.0)

    def test_three_baselines_return_same_validation_rows(self):
        panels = pd.concat(
            [
                labeled_panel("2024-05", customer_id="C1"),
                labeled_panel("2025-05", customer_id="C2"),
            ],
            ignore_index=True,
        )
        frame = build_modeling_features(panels)
        train, validation = split_train_validation(frame)

        scores, metrics = fit_and_score_baselines(train, validation)

        expected_models = {
            "Prevalence",
            "CurrentSignalRule",
            "LogisticRegression",
        }
        self.assertEqual(set(scores["모델"]), expected_models)
        self.assertEqual(scores.groupby("모델").size().nunique(), 1)
        self.assertEqual(set(metrics["모델"]), expected_models)
        self.assertTrue(scores["예측확률"].notna().all())

    def test_lift_table_uses_highest_scores_as_first_bucket(self):
        scores = pd.DataFrame(
            {
                "모델": "rule",
                MODEL_TARGET_COL: [1, 1, 0, 0],
                "예측확률": [0.9, 0.8, 0.2, 0.1],
            }
        )

        lift = build_lift_table(scores, n_bins=2)

        first = lift.loc[lift["점수구간"].eq(1)].iloc[0]
        self.assertEqual(first["행수"], 2)
        self.assertEqual(first["양성률"], 1.0)
        self.assertEqual(first["Lift"], 2.0)


class BaselineRunnerTest(unittest.TestCase):
    def test_writes_all_output_contract_files(self):
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory)
            frames = {
                name: pd.DataFrame({"value": [1]})
                for name in OUTPUT_FILENAMES
            }

            paths = write_baseline_outputs(frames, output_dir)

            self.assertEqual(set(paths), set(OUTPUT_FILENAMES))
            self.assertTrue(all(path.exists() for path in paths.values()))

    def test_runs_from_raw_csv_through_validation_outputs(self):
        source = pd.concat(
            [
                raw_activity_panel("C1", "2024-05"),
                raw_activity_panel("C2"),
                raw_activity_panel("C3", "2025-05"),
                raw_activity_panel("C4"),
                raw_activity_panel("C5").iloc[:-1],
            ],
            ignore_index=True,
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path = root / "corporate.csv"
            source.to_csv(input_path, index=False)

            paths = run_baseline(input_path, root / "outputs")

            metrics = pd.read_csv(paths["validation_metrics"])
            modeling = pd.read_csv(paths["modeling_panel"])
            self.assertEqual(
                set(metrics["모델"]),
                {
                    "Prevalence",
                    "CurrentSignalRule",
                    "LogisticRegression",
                },
            )
            self.assertTrue(paths["validation_lift"].exists())
            self.assertTrue(paths["segment_diagnostics"].exists())
            self.assertNotIn("C5", modeling["법인ID"].astype(str).tolist())


if __name__ == "__main__":
    unittest.main()
