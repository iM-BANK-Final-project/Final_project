import importlib
import importlib.util
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd


MODULE_NAME = "src.models.persistent_weakening_interpretation"
RUNNER_MODULE_NAME = "src.models.run_persistent_weakening_interpretation"


class InterpretationContractTest(unittest.TestCase):
    def test_module_exposes_interpretation_contract(self):
        spec = importlib.util.find_spec(MODULE_NAME)
        self.assertIsNotNone(spec)
        module = importlib.import_module(MODULE_NAME)

        for name in (
            "fit_interpretation_models",
            "build_feature_importance",
            "compute_shap_explanations",
            "build_shap_global_importance",
            "build_local_shap_top_rows",
            "plot_ranked_importance",
            "plot_shap_beeswarm",
        ):
            self.assertTrue(callable(getattr(module, name, None)), name)

    def test_runner_declares_complete_output_contract(self):
        spec = importlib.util.find_spec(RUNNER_MODULE_NAME)
        self.assertIsNotNone(spec)
        runner = importlib.import_module(RUNNER_MODULE_NAME)
        self.assertEqual(
            set(runner.OUTPUT_FILENAMES),
            {
                "feature_importance",
                "shap_global_importance",
                "shap_local_top_rows",
                "feature_importance_chart",
                "shap_global_chart",
                "shap_beeswarm_lightgbm",
                "shap_beeswarm_lightgbm_no_direct",
            },
        )

    def test_runner_restores_all_period_columns_from_csv(self):
        runner = importlib.import_module(RUNNER_MODULE_NAME)
        function = getattr(runner, "load_modeling_panel", None)
        self.assertTrue(callable(function))
        source = pd.DataFrame(
            {
                "기준년월": ["2024-02"],
                "label_end": ["2024-08"],
            }
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "panel.csv"
            source.to_csv(path, index=False)

            loaded = function(path)

        self.assertIsInstance(loaded.loc[0, "기준년월"], pd.Period)
        self.assertIsInstance(loaded.loc[0, "label_end"], pd.Period)


class InterpretationTableTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = importlib.import_module(MODULE_NAME)
        rng = np.random.default_rng(42)
        size = 600
        signal = rng.normal(size=size)
        trend = rng.normal(size=size)
        yoy = np.clip(0.8 - 0.25 * signal + rng.normal(0, 0.1, size), 0.05, 2)
        target = (signal + 0.7 * trend + rng.normal(0, 0.5, size) > 0.8).astype(int)
        cls.train = pd.DataFrame(
            {
                "법인ID": [f"T{index:04d}" for index in range(size)],
                "기준년월": pd.Period("2024-09", freq="M"),
                "log1p_현재값_핵심거래활동금액": signal,
                "최근3개월기울기_핵심거래활동금액": trend,
                "YoY_ratio_핵심거래활동금액": yoy,
                "현재drop50": (yoy < 0.5).astype(float),
                "현재drop50연속개월수": np.where(yoy < 0.5, 1.0, 0.0),
                "Y_향후3개월_지속거래약화": target,
            }
        )
        cls.validation = cls.train.iloc[:80].copy()

    def test_models_use_full_and_no_direct_feature_sets(self):
        models, feature_sets = self.module.fit_interpretation_models(self.train)

        self.assertEqual(set(models), {"LightGBM", "LightGBM_NoDirect"})
        self.assertEqual(set(feature_sets), set(models))
        self.assertIn("현재drop50", feature_sets["LightGBM"])
        self.assertNotIn("현재drop50", feature_sets["LightGBM_NoDirect"])
        self.assertNotIn(
            "YoY_ratio_핵심거래활동금액",
            feature_sets["LightGBM_NoDirect"],
        )

    def test_feature_importance_has_normalized_gain_and_split(self):
        models, feature_sets = self.module.fit_interpretation_models(self.train)

        importance = self.module.build_feature_importance(
            models,
            feature_sets,
        )

        self.assertEqual(set(importance["모델"]), set(models))
        for _, group in importance.groupby("모델"):
            self.assertAlmostEqual(group["gain_share"].sum(), 1.0)
            self.assertAlmostEqual(group["split_share"].sum(), 1.0)
            self.assertEqual(group["gain_rank"].min(), 1)

    def test_shap_global_and_local_tables_are_complete(self):
        models, feature_sets = self.module.fit_interpretation_models(self.train)
        explanations = self.module.compute_shap_explanations(
            models,
            self.validation,
            feature_sets,
        )
        global_table = self.module.build_shap_global_importance(explanations)
        probabilities = {
            name: model.predict_proba(
                self.validation[feature_sets[name]].astype(float)
            )[:, 1]
            for name, model in models.items()
        }
        local = self.module.build_local_shap_top_rows(
            explanations,
            self.validation,
            probabilities,
            top_rows=2,
            top_features=2,
        )

        self.assertEqual(set(explanations), set(models))
        self.assertEqual(set(global_table["모델"]), set(models))
        for _, group in global_table.groupby("모델"):
            self.assertAlmostEqual(group["shap_share"].sum(), 1.0)
        self.assertEqual(len(local), 2 * 2 * 2)
        self.assertTrue(local["shap_value"].notna().all())
        self.assertTrue(local["예측확률"].between(0, 1).all())

    def test_local_shap_defaults_to_all_validation_rows(self):
        models, feature_sets = self.module.fit_interpretation_models(self.train)
        explanations = self.module.compute_shap_explanations(
            models,
            self.validation,
            feature_sets,
        )
        probabilities = {
            name: model.predict_proba(
                self.validation[feature_sets[name]].astype(float)
            )[:, 1]
            for name, model in models.items()
        }

        local = self.module.build_local_shap_top_rows(
            explanations,
            self.validation,
            probabilities,
            top_features=2,
        )

        self.assertEqual(
            len(local),
            len(models) * len(self.validation) * 2,
        )


if __name__ == "__main__":
    unittest.main()
