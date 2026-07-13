from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import shap
from matplotlib import font_manager

from src.models.persistent_weakening_baseline import (
    MODEL_TARGET_COL,
    ablation_feature_columns,
    build_fixed_lightgbm,
    model_feature_columns,
)


def fit_interpretation_models(
    train: pd.DataFrame,
) -> tuple[dict[str, object], dict[str, list[str]]]:
    feature_sets = {
        "LightGBM": model_feature_columns(train),
        "LightGBM_NoDirect": ablation_feature_columns(train),
    }
    models: dict[str, object] = {}
    target = train[MODEL_TARGET_COL].astype(int)
    for model_name, columns in feature_sets.items():
        model = build_fixed_lightgbm()
        model.fit(train[columns].astype(float), target)
        models[model_name] = model
    return models, feature_sets


def _share(values: np.ndarray) -> np.ndarray:
    total = float(values.sum())
    if total <= 0:
        return np.zeros_like(values, dtype=float)
    return values.astype(float) / total


def build_feature_importance(
    models: dict[str, object],
    feature_sets: dict[str, list[str]],
) -> pd.DataFrame:
    rows: list[pd.DataFrame] = []
    for model_name, model in models.items():
        features = feature_sets[model_name]
        gain = model.booster_.feature_importance(importance_type="gain")
        split = model.booster_.feature_importance(importance_type="split")
        table = pd.DataFrame(
            {
                "모델": model_name,
                "feature": features,
                "gain": gain,
                "gain_share": _share(gain),
                "split": split,
                "split_share": _share(split),
            }
        ).sort_values(["gain", "split"], ascending=False)
        table["gain_rank"] = np.arange(1, len(table) + 1)
        rows.append(table)
    return pd.concat(rows, ignore_index=True)


def compute_shap_explanations(
    models: dict[str, object],
    validation: pd.DataFrame,
    feature_sets: dict[str, list[str]],
) -> dict[str, shap.Explanation]:
    explanations: dict[str, shap.Explanation] = {}
    for model_name, model in models.items():
        columns = feature_sets[model_name]
        values = validation[columns].astype(float)
        explainer = shap.TreeExplainer(model)
        explanations[model_name] = explainer(
            values,
            check_additivity=False,
        )
    return explanations


def _explanation_values(explanation: shap.Explanation) -> np.ndarray:
    values = np.asarray(explanation.values)
    if values.ndim == 3 and values.shape[-1] == 2:
        return values[:, :, 1]
    if values.ndim != 2:
        raise ValueError(f"예상하지 못한 SHAP shape: {values.shape}")
    return values


def build_shap_global_importance(
    explanations: dict[str, shap.Explanation],
) -> pd.DataFrame:
    rows: list[pd.DataFrame] = []
    for model_name, explanation in explanations.items():
        values = _explanation_values(explanation)
        mean_abs = np.abs(values).mean(axis=0)
        table = pd.DataFrame(
            {
                "모델": model_name,
                "feature": list(explanation.feature_names),
                "mean_abs_shap": mean_abs,
                "shap_share": _share(mean_abs),
                "mean_shap": values.mean(axis=0),
            }
        ).sort_values("mean_abs_shap", ascending=False)
        table["shap_rank"] = np.arange(1, len(table) + 1)
        rows.append(table)
    return pd.concat(rows, ignore_index=True)


def _base_value_at(explanation: shap.Explanation, position: int) -> float:
    base_values = np.asarray(explanation.base_values)
    if base_values.ndim == 0:
        return float(base_values)
    if base_values.ndim == 2 and base_values.shape[1] == 2:
        return float(base_values[position, 1])
    return float(base_values[position])


def build_local_shap_top_rows(
    explanations: dict[str, shap.Explanation],
    validation: pd.DataFrame,
    predicted_probabilities: dict[str, np.ndarray],
    top_rows: int = 20,
    top_features: int = 10,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for model_name, explanation in explanations.items():
        probabilities = np.asarray(predicted_probabilities[model_name])
        selected = np.argsort(-probabilities, kind="stable")[:top_rows]
        shap_values = _explanation_values(explanation)
        feature_values = np.asarray(explanation.data)
        feature_names = list(explanation.feature_names)
        for risk_rank, position in enumerate(selected, start=1):
            feature_order = np.argsort(-np.abs(shap_values[position]))[
                :top_features
            ]
            source_row = validation.iloc[position]
            for shap_rank, feature_position in enumerate(
                feature_order,
                start=1,
            ):
                rows.append(
                    {
                        "모델": model_name,
                        "위험순위": risk_rank,
                        "법인ID": source_row.get("법인ID", pd.NA),
                        "기준년월": str(source_row.get("기준년월", "")),
                        "예측확률": float(probabilities[position]),
                        "base_value": _base_value_at(explanation, position),
                        "feature": feature_names[feature_position],
                        "feature_value": feature_values[
                            position,
                            feature_position,
                        ],
                        "shap_value": float(
                            shap_values[position, feature_position]
                        ),
                        "abs_shap_rank": shap_rank,
                    }
                )
    return pd.DataFrame(rows)


def _configure_korean_font() -> None:
    font_path = Path("/System/Library/Fonts/AppleSDGothicNeo.ttc")
    if font_path.exists():
        font_manager.fontManager.addfont(str(font_path))
        font_name = font_manager.FontProperties(fname=font_path).get_name()
        plt.rcParams["font.family"] = font_name
    plt.rcParams["axes.unicode_minus"] = False


def _display_feature_name(name: str) -> str:
    replacements = (
        ("log1p_최근", "최근"),
        ("log1p_현재값_", "현재값(log)_"),
        ("개월평균_", "개월평균(log)_"),
        ("개월표준편차_", "개월표준편차(log)_"),
    )
    result = name
    for source, target in replacements:
        result = result.replace(source, target)
    return result


def plot_ranked_importance(
    table: pd.DataFrame,
    value_col: str,
    title: str,
    subtitle: str,
    output_path: Path,
    top_n: int = 15,
) -> None:
    _configure_korean_font()
    models = ["LightGBM", "LightGBM_NoDirect"]
    colors = {"LightGBM": "#2457A7", "LightGBM_NoDirect": "#D97706"}
    fig, axes = plt.subplots(1, 2, figsize=(18, 9), constrained_layout=True)
    for axis, model_name in zip(axes, models):
        work = (
            table.loc[table["모델"].eq(model_name)]
            .nlargest(top_n, value_col)
            .sort_values(value_col)
            .copy()
        )
        labels = [_display_feature_name(value) for value in work["feature"]]
        values = work[value_col].to_numpy(dtype=float)
        axis.barh(labels, values, color=colors[model_name], alpha=0.9)
        axis.set_title(model_name, fontsize=13, fontweight="bold")
        axis.set_xlabel("모델 내 중요도 비중")
        axis.xaxis.set_major_formatter(lambda value, _: f"{value:.0%}")
        axis.grid(axis="x", color="#D8DEE8", linewidth=0.8, alpha=0.7)
        axis.set_axisbelow(True)
        axis.spines[["top", "right", "left"]].set_visible(False)
        for index, value in enumerate(values):
            axis.text(
                value,
                index,
                f" {value:.1%}",
                va="center",
                fontsize=9,
                color="#263238",
            )
    fig.suptitle(title, fontsize=17, fontweight="bold", color="#1F2937")
    fig.text(0.5, 0.955, subtitle, ha="center", fontsize=10, color="#5B6472")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=180, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def plot_shap_beeswarm(
    explanation: shap.Explanation,
    model_name: str,
    output_path: Path,
    max_display: int = 15,
) -> None:
    _configure_korean_font()
    display = shap.Explanation(
        values=_explanation_values(explanation),
        base_values=explanation.base_values,
        data=explanation.data,
        feature_names=[
            _display_feature_name(value) for value in explanation.feature_names
        ],
    )
    shap.plots.beeswarm(
        display,
        max_display=max_display,
        show=False,
        plot_size=(13, 8),
    )
    figure = plt.gcf()
    axis = plt.gca()
    axis.set_title(
        f"{model_name} Validation SHAP",
        fontsize=16,
        fontweight="bold",
        pad=18,
        color="#1F2937",
    )
    axis.set_xlabel("SHAP value (양수: 약화 위험 증가)")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(
        output_path,
        dpi=180,
        bbox_inches="tight",
        facecolor="white",
    )
    plt.close(figure)
