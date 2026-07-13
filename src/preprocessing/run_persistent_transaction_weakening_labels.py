from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from src.preprocessing.persistent_transaction_weakening_labels import (
    build_persistent_weakening_labels,
)


def run_label_pipeline(
    input_path: Path,
    output_dir: Path,
) -> tuple[Path, Path]:
    source = pd.read_csv(input_path)
    panel, events = build_persistent_weakening_labels(source)
    output_dir.mkdir(parents=True, exist_ok=True)
    panel_path = output_dir / "persistent_transaction_weakening_panel.csv"
    events_path = output_dir / "persistent_transaction_weakening_events.csv"
    panel.to_csv(panel_path, index=False, encoding="utf-8-sig")
    events.to_csv(events_path, index=False, encoding="utf-8-sig")
    return panel_path, events_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="지속거래약화 3M70 이벤트 라벨 생성"
    )
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument(
        "--output-dir",
        default=Path("outputs/persistent_transaction_weakening_labels"),
        type=Path,
    )
    args = parser.parse_args()
    panel_path, events_path = run_label_pipeline(args.input, args.output_dir)
    print(f"saved: {panel_path}")
    print(f"saved: {events_path}")


if __name__ == "__main__":
    main()
