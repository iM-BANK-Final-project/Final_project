"""Modeling gate after migration to the persistent-weakening event label.

The previous five-axis target implementation is retired. A predictive model
must not be trained until the rolling prediction horizon is approved.
"""

TARGET_COL = "Y_지속거래약화_3M70"


def require_approved_rolling_target() -> None:
    raise RuntimeError(
        "Y_지속거래약화_3M70 이벤트 라벨은 구현됐지만 rolling 예측 target은 "
        "아직 승인되지 않았습니다. 미래 사건창과 embargo를 먼저 확정하세요."
    )
