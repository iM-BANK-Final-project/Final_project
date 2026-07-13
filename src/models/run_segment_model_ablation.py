from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from src.models.persistent_weakening_baseline import (
    build_lift_table,
    build_modeling_features,
    split_train_validation,
)
from src.models.segment_model_ablation import (
    build_segment_diagnostics,
    fit_and_score_segment_ablation,
    join_relationship_features,
)
from src.preprocessing.persistent_transaction_weakening_labels import (
    LabelConfig,
    build_persistent_weakening_labels,
    select_complete_cohort,
)
from src.segmentation.relationship_segments import (
    SegmentationConfig,
    build_monthly_relationship_axes,
    build_reference_relationship_levels,
    build_rolling_relationship_features,
)


OUTPUT_FILENAMES = {
    "modeling_panel": "segment_modeling_panel.csv",
    "validation_scores": "segment_validation_scores.csv",
    "validation_metrics": "segment_validation_metrics.csv",
    "validation_lift": "segment_validation_lift.csv",
    "segment_diagnostics": "segment_validation_diagnostics.csv",
    "feature_selection": "segment_feature_selection.csv",
}


def build_source_columns() -> tuple[str, ...]:
    label_config = LabelConfig()
    segment_config = SegmentationConfig()
    return tuple(
        dict.fromkeys(
            (
                label_config.customer_id_col,
                label_config.month_col,
                *label_config.amount_cols,
                *segment_config.amount_cols,
            )
        )
    )


def write_segment_ablation_outputs(
    frames: dict[str, pd.DataFrame],
    output_dir: Path,
) -> dict[str, Path]:
    missing = sorted(set(OUTPUT_FILENAMES).difference(frames))
    if missing:
        raise ValueError(f"저장할 세그먼트 모델 산출물이 없습니다: {missing}")
    output_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}
    for name, filename in OUTPUT_FILENAMES.items():
        path = output_dir / filename
        frames[name].to_csv(path, index=False, encoding="utf-8-sig")
        paths[name] = path
    return paths


def run_segment_model_ablation(
    input_path: Path,
    output_dir: Path,
) -> dict[str, Path]:
    label_config = LabelConfig()
    segment_config = SegmentationConfig()
    source = pd.read_csv(input_path, usecols=list(build_source_columns()))
    cohort = select_complete_cohort(source, label_config)
    if cohort.empty:
        raise ValueError("2023-01~2025-12 완전관측 법인이 없습니다.")

    labels, _ = build_persistent_weakening_labels(cohort, label_config)
    modeling = build_modeling_features(labels)

    monthly_relationships = build_monthly_relationship_axes(
        cohort,
        segment_config,
    )
    reference = build_reference_relationship_levels(
        monthly_relationships,
        segment_config,
    )
    relationship_features = build_rolling_relationship_features(
        monthly_relationships,
        reference,
        segment_config,
    )
    augmented = join_relationship_features(modeling, relationship_features)
    train, validation = split_train_validation(augmented)
    scores, metrics, feature_selection = fit_and_score_segment_ablation(
        train,
        validation,
    )
    frames = {
        "modeling_panel": augmented,
        "validation_scores": scores,
        "validation_metrics": metrics,
        "validation_lift": build_lift_table(scores),
        "segment_diagnostics": build_segment_diagnostics(scores),
        "feature_selection": feature_selection,
    }
    return write_segment_ablation_outputs(frames, output_dir)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="rolling 관계 세그먼트 feature 고정 LightGBM 비교",
    )
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument(
        "--output-dir",
        default=Path("outputs/segment_model_ablation"),
        type=Path,
    )
    args = parser.parse_args()
    for name, path in run_segment_model_ablation(
        args.input,
        args.output_dir,
    ).items():
        print(f"{name}: {path}")


if __name__ == "__main__":
    main()
