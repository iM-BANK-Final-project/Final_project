from __future__ import annotations

import pandas as pd

from src.preprocessing.persistent_transaction_weakening_labels import (
    EVENT_ID_COL,
    TARGET_COL,
)


MODEL_TARGET_COL = "Y_향후3개월_지속거래약화"
FUTURE_EVENT_MONTH_COL = "미래지속거래약화사건월"
FUTURE_EVENT_ID_COL = "미래지속거래약화사건ID"
LEAD_MONTHS_COL = "사건까지개월수"
LABEL_END_COL = "label_end"

FIRST_ANCHOR = pd.Period("2024-02", freq="M")
LAST_ANCHOR = pd.Period("2025-06", freq="M")
TRAIN_START = pd.Period("2024-02", freq="M")
TRAIN_END = pd.Period("2024-09", freq="M")
VALIDATION_START = pd.Period("2025-04", freq="M")
VALIDATION_END = pd.Period("2025-06", freq="M")


def _require_columns(frame: pd.DataFrame, columns: tuple[str, ...]) -> None:
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise ValueError(f"모델링 패널 필수 컬럼이 없습니다: {missing}")


def build_modeling_targets(label_panel: pd.DataFrame) -> pd.DataFrame:
    _require_columns(
        label_panel,
        (
            "법인ID",
            "기준년월",
            "core_3m_event",
            TARGET_COL,
            EVENT_ID_COL,
        ),
    )
    panel = label_panel.sort_values(["법인ID", "기준년월"]).copy()
    if not isinstance(panel["기준년월"].dtype, pd.PeriodDtype):
        panel["기준년월"] = pd.PeriodIndex(
            panel["기준년월"].astype(str),
            freq="M",
        )

    rows: list[dict[str, object]] = []
    for _, group in panel.groupby("법인ID", sort=False):
        positive_events = group.loc[
            group[TARGET_COL].eq(1),
            ["기준년월", EVENT_ID_COL],
        ].sort_values("기준년월")
        for _, anchor in group.iterrows():
            month = anchor["기준년월"]
            current_event = pd.notna(anchor["core_3m_event"]) and bool(
                anchor["core_3m_event"]
            )
            if (
                month < FIRST_ANCHOR
                or month > LAST_ANCHOR
                or current_event
            ):
                continue

            future = positive_events.loc[
                positive_events["기준년월"].between(month + 1, month + 3)
            ]
            row = anchor.to_dict()
            row[MODEL_TARGET_COL] = int(not future.empty)
            row[LABEL_END_COL] = month + 6
            if future.empty:
                row[FUTURE_EVENT_MONTH_COL] = pd.NaT
                row[FUTURE_EVENT_ID_COL] = pd.NA
                row[LEAD_MONTHS_COL] = pd.NA
            else:
                event_month = future.iloc[0]["기준년월"]
                row[FUTURE_EVENT_MONTH_COL] = event_month
                row[FUTURE_EVENT_ID_COL] = future.iloc[0][EVENT_ID_COL]
                row[LEAD_MONTHS_COL] = event_month.ordinal - month.ordinal
            rows.append(row)
    return pd.DataFrame(rows).reset_index(drop=True)


def split_train_validation(
    frame: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    _require_columns(frame, ("기준년월", LABEL_END_COL))
    train = frame.loc[
        frame["기준년월"].between(TRAIN_START, TRAIN_END)
    ].copy()
    validation = frame.loc[
        frame["기준년월"].between(VALIDATION_START, VALIDATION_END)
    ].copy()
    if train.empty or validation.empty:
        raise ValueError("train 또는 validation 구간이 비어 있습니다.")
    if train[LABEL_END_COL].max() >= validation["기준년월"].min():
        raise ValueError("train label 관찰창과 validation 기준월이 겹칩니다.")
    return train, validation
