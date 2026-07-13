from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from src.segmentation.relationship_segments import (
    SegmentationConfig,
    assign_l30_h70_m15,
    build_monthly_relationship_axes,
    build_segment_profile,
    build_segment_stability,
    fit_reference_scores,
    score_against_reference,
    select_complete_segmentation_cohort,
    summarize_relationship_window,
)


OUTPUT_FILENAMES = {
    "reference_2023": "relationship_segment_reference_2023.csv",
    "assignments_2023": "relationship_segment_assignments_2023.csv",
    "profile_2023": "relationship_segment_profile_2023.csv",
    "assignments_2024": "relationship_segment_assignments_2024.csv",
    "profile_2024": "relationship_segment_profile_2024.csv",
    "stability_2023_2024": "relationship_segment_stability_2023_2024.csv",
}


def run_relationship_segmentation(
    input_path: Path,
    output_dir: Path,
) -> dict[str, Path]:
    config = SegmentationConfig()
    source = pd.read_csv(input_path, usecols=list(config.required_columns))
    monthly = select_complete_segmentation_cohort(
        build_monthly_relationship_axes(source, config),
        config,
    )

    levels_2023 = summarize_relationship_window(
        monthly,
        "2023-01",
        "2023-12",
        config,
    )
    scored_2023, reference = fit_reference_scores(levels_2023, config)
    assignments_2023 = assign_l30_h70_m15(scored_2023, config)

    levels_2024 = summarize_relationship_window(
        monthly,
        "2024-01",
        "2024-12",
        config,
    )
    scored_2024 = score_against_reference(levels_2024, reference, config)
    assignments_2024 = assign_l30_h70_m15(scored_2024, config)

    tables = {
        "reference_2023": reference,
        "assignments_2023": assignments_2023,
        "profile_2023": build_segment_profile(assignments_2023),
        "assignments_2024": assignments_2024,
        "profile_2024": build_segment_profile(assignments_2024),
        "stability_2023_2024": build_segment_stability(
            assignments_2023,
            assignments_2024,
            config,
        ),
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}
    for name, table in tables.items():
        path = output_dir / OUTPUT_FILENAMES[name]
        table.to_csv(path, index=False, encoding="utf-8-sig")
        paths[name] = path
    return paths


def main() -> None:
    parser = argparse.ArgumentParser(
        description="2023 고정 기준 L30_H70_M15 관계 세그먼트 생성",
    )
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("outputs/relationship_segments"),
    )
    args = parser.parse_args()
    paths = run_relationship_segmentation(args.input, args.output_dir)
    for name, path in paths.items():
        print(f"saved {name}: {path}")


if __name__ == "__main__":
    main()
