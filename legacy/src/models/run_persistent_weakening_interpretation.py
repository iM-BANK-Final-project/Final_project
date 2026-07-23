from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from src.models.persistent_weakening_baseline import split_train_validation
from src.models.persistent_weakening_interpretation import (
    build_feature_importance,
    build_local_shap_top_rows,
    build_shap_global_importance,
    compute_shap_explanations,
    fit_interpretation_models,
    plot_ranked_importance,
    plot_shap_beeswarm,
)


OUTPUT_FILENAMES = {
    "feature_importance": "feature_importance.csv",
    "shap_global_importance": "shap_global_importance.csv",
    "shap_local_top_rows": "shap_local_top_rows.csv",
    "feature_importance_chart": "feature_importance_gain.png",
    "shap_global_chart": "shap_global_importance.png",
    "shap_beeswarm_lightgbm": "shap_beeswarm_lightgbm.png",
    "shap_beeswarm_lightgbm_no_direct": (
        "shap_beeswarm_lightgbm_no_direct.png"
    ),
}


def load_modeling_panel(path: Path) -> pd.DataFrame:
    panel = pd.read_csv(path)
    for column in ("기준년월", "label_end"):
        panel[column] = pd.PeriodIndex(
            panel[column].astype(str),
            freq="M",
        )
    return panel


def run_interpretation(
    modeling_panel_path: Path,
    output_dir: Path,
) -> dict[str, Path]:
    panel = load_modeling_panel(modeling_panel_path)
    train, validation = split_train_validation(panel)
    models, feature_sets = fit_interpretation_models(train)
    feature_importance = build_feature_importance(models, feature_sets)
    explanations = compute_shap_explanations(
        models,
        validation,
        feature_sets,
    )
    shap_global = build_shap_global_importance(explanations)
    probabilities = {
        model_name: model.predict_proba(
            validation[feature_sets[model_name]].astype(float)
        )[:, 1]
        for model_name, model in models.items()
    }
    shap_local = build_local_shap_top_rows(
        explanations,
        validation,
        probabilities,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        key: output_dir / filename
        for key, filename in OUTPUT_FILENAMES.items()
    }
    feature_importance.to_csv(paths["feature_importance"], index=False)
    shap_global.to_csv(paths["shap_global_importance"], index=False)
    shap_local.to_csv(paths["shap_local_top_rows"], index=False)

    plot_ranked_importance(
        feature_importance,
        value_col="gain_share",
        title="LightGBM Feature Importance (Gain)",
        subtitle="Train 적합 모델 기준, 모델별 gain 합계=100%, 상위 15개",
        output_path=paths["feature_importance_chart"],
    )
    plot_ranked_importance(
        shap_global,
        value_col="shap_share",
        title="LightGBM Global SHAP Importance",
        subtitle="Validation 8,839행 mean(|SHAP|), 모델별 합계=100%, 상위 15개",
        output_path=paths["shap_global_chart"],
    )
    plot_shap_beeswarm(
        explanations["LightGBM"],
        "LightGBM",
        paths["shap_beeswarm_lightgbm"],
    )
    plot_shap_beeswarm(
        explanations["LightGBM_NoDirect"],
        "LightGBM_NoDirect",
        paths["shap_beeswarm_lightgbm_no_direct"],
    )
    return paths


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="고정 LightGBM feature importance와 SHAP을 산출합니다."
    )
    parser.add_argument("--modeling-panel", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    paths = run_interpretation(args.modeling_panel, args.output_dir)
    for name, path in paths.items():
        print(f"{name}: {path}")


if __name__ == "__main__":
    main()
