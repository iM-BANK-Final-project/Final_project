from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from src.models.persistent_weakening_baseline import (
    MODEL_TARGET_COL,
    build_lift_table,
    build_modeling_features,
    fit_and_score_baselines,
    split_train_validation,
)
from src.preprocessing.persistent_transaction_weakening_labels import (
    build_persistent_weakening_labels,
)


OUTPUT_FILENAMES = {
    "modeling_panel": "modeling_panel.csv",
    "validation_scores": "validation_scores.csv",
    "validation_metrics": "validation_metrics.csv",
    "validation_lift": "validation_lift.csv",
    "segment_diagnostics": "segment_diagnostics.csv",
}


def write_baseline_outputs(
    frames: dict[str, pd.DataFrame],
    output_dir: Path,
) -> dict[str, Path]:
    missing = sorted(set(OUTPUT_FILENAMES).difference(frames))
    if missing:
        raise ValueError(f"저장할 baseline 산출물이 없습니다: {missing}")
    output_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}
    for name, filename in OUTPUT_FILENAMES.items():
        path = output_dir / filename
        frames[name].to_csv(path, index=False, encoding="utf-8-sig")
        paths[name] = path
    return paths


def build_monthly_diagnostics(scores: pd.DataFrame) -> pd.DataFrame:
    return (
        scores.groupby(["모델", "기준년월"], as_index=False)
        .agg(
            행수=(MODEL_TARGET_COL, "size"),
            양성수=(MODEL_TARGET_COL, "sum"),
            양성률=(MODEL_TARGET_COL, "mean"),
            평균점수=("예측확률", "mean"),
        )
        .sort_values(["모델", "기준년월"])
        .reset_index(drop=True)
    )


def run_baseline(
    input_path: Path,
    output_dir: Path,
) -> dict[str, Path]:
    source = pd.read_csv(input_path)
    labels, _ = build_persistent_weakening_labels(source)
    modeling = build_modeling_features(labels)
    train, validation = split_train_validation(modeling)
    scores, metrics = fit_and_score_baselines(train, validation)
    frames = {
        "modeling_panel": modeling,
        "validation_scores": scores,
        "validation_metrics": metrics,
        "validation_lift": build_lift_table(scores),
        "segment_diagnostics": build_monthly_diagnostics(scores),
    }
    return write_baseline_outputs(frames, output_dir)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="지속거래약화 baseline 모델 실행"
    )
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument(
        "--output-dir",
        default=Path("outputs/persistent_weakening_baseline"),
        type=Path,
    )
    args = parser.parse_args()
    for name, path in run_baseline(args.input, args.output_dir).items():
        print(f"{name}: {path}")


if __name__ == "__main__":
    main()
