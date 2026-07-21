"""Deterministic FS2 SHAP evidence rules for strategy-report generation."""

import math
from numbers import Real

R1_FEATURES = (
    "핵심거래_수준",
    "수신자산_수준",
    "여신관계_수준",
    "수신상품_활성폭",
    "여신세부상품_활성폭",
    "채널_활성폭",
    "관계영역_활성폭",
    "수신_요구불대기타_로그균형",
    "여신_운전대시설_로그균형",
    "핵심거래_입출금대채널_평균비중",
    "채널_비대면대창구_로그균형",
    "수신좌수_강도",
    "여신부모좌수_강도",
    "신용카드개수_강도",
    "자동이체건수_강도",
    "카드_활성률",
)
AXES = ("요구불", "자동이체", "채널", "카드")
DYNAMIC_SUFFIXES = (
    "최근3대직전3_로그차이",
    "최근3대이전9_로그차이",
    "H2대H1_로그차이",
    "로그변동성",
    "TheilSen_추세",
    "최근3대이전9_활성률차이",
    "월간50퍼감소횟수",
    "월간감소율",
    "최대연속비활성개월",
    "현재월대직전6_로그차이",
)
FS2_FEATURES = R1_FEATURES + tuple(
    f"{axis}_{suffix}" for axis in AXES for suffix in DYNAMIC_SUFFIXES
)

FEATURE_GROUPS = {
    "핵심거래_수준": "관계 폭·구성",
    "수신자산_수준": "수신 관계",
    "여신관계_수준": "여신 관계",
    "수신상품_활성폭": "수신 관계",
    "여신세부상품_활성폭": "여신 관계",
    "채널_활성폭": "채널 이용",
    "관계영역_활성폭": "관계 폭·구성",
    "수신_요구불대기타_로그균형": "수신 관계",
    "여신_운전대시설_로그균형": "여신 관계",
    "핵심거래_입출금대채널_평균비중": "관계 폭·구성",
    "채널_비대면대창구_로그균형": "채널 이용",
    "수신좌수_강도": "수신 관계",
    "여신부모좌수_강도": "여신 관계",
    "신용카드개수_강도": "카드 관계",
    "자동이체건수_강도": "자동이체",
    "카드_활성률": "카드 관계",
}
BASE_FEATURE_MEANINGS = {
    "핵심거래_수준": "최근 12개월 핵심거래 활동 수준",
    "수신자산_수준": "최근 12개월 수신자산 수준",
    "여신관계_수준": "최근 12개월 여신관계 수준",
    "수신상품_활성폭": "최근 12개월 수신상품 활성 폭",
    "여신세부상품_활성폭": "최근 12개월 여신세부상품 활성 폭",
    "채널_활성폭": "최근 12개월 채널 활성 폭",
    "관계영역_활성폭": "최근 12개월 거래관계 영역 폭",
    "수신_요구불대기타_로그균형": "요구불과 기타 수신의 구성 균형",
    "여신_운전대시설_로그균형": "운전자금과 시설자금 여신의 구성 균형",
    "핵심거래_입출금대채널_평균비중": "핵심거래에서 입출금과 채널의 평균 비중",
    "채널_비대면대창구_로그균형": "비대면과 창구 채널의 구성 균형",
    "수신좌수_강도": "수신 좌수 강도",
    "여신부모좌수_강도": "여신 부모좌수 강도",
    "신용카드개수_강도": "신용카드 개수 강도",
    "자동이체건수_강도": "자동이체 건수 강도",
    "카드_활성률": "카드 활동월 비율",
}
DYNAMIC_AXIS_GROUPS = {
    "요구불": "입출금 활동",
    "자동이체": "자동이체",
    "채널": "채널 이용",
    "카드": "카드 관계",
}
SUFFIX_MEANINGS = {
    "최근3대직전3_로그차이": "최근 3개월과 직전 3개월 비교",
    "최근3대이전9_로그차이": "최근 3개월과 이전 9개월 비교",
    "H2대H1_로그차이": "최근 반기와 앞선 반기 비교",
    "로그변동성": "최근 12개월 활동 변동성",
    "TheilSen_추세": "최근 12개월 강건 추세",
    "최근3대이전9_활성률차이": "활동월 빈도 변화",
    "월간50퍼감소횟수": "최근 12개월 월간 50% 이상 감소 횟수",
    "월간감소율": "전월보다 감소한 월의 비율",
    "최대연속비활성개월": "최장 연속 비활성 기간",
    "현재월대직전6_로그차이": "현재월과 직전 6개월 평균 비교",
}


def prepare_shap_report_evidence(shap_factors: list[dict]) -> dict:
    """Validate stored Local SHAP Top 10 rows and add deterministic context."""
    if not isinstance(shap_factors, list) or not 1 <= len(shap_factors) <= 10:
        raise ValueError("SHAP Top 10 must contain between 1 and 10 items.")

    validated_factors = []
    for factor in shap_factors:
        if not isinstance(factor, dict):
            raise ValueError("Each SHAP factor must be a dictionary.")
        feature = factor.get("feature")
        if feature not in FS2_FEATURES:
            raise ValueError("SHAP feature must belong to FS2_R1_DACK_DYNAMIC.")

        rank = factor.get("rank")
        if not isinstance(rank, int) or isinstance(rank, bool):
            raise ValueError("SHAP rank must be an integer.")

        impact = factor.get("impact")
        if (
            not isinstance(impact, Real)
            or isinstance(impact, bool)
            or not math.isfinite(impact)
        ):
            raise ValueError("SHAP impact must be a finite number.")
        validated_factors.append(factor)

    ordered_factors = sorted(validated_factors, key=lambda factor: factor["rank"])
    expected_ranks = list(range(1, len(ordered_factors) + 1))
    if [factor["rank"] for factor in ordered_factors] != expected_ranks:
        raise ValueError("SHAP ranks must be continuous from 1 without duplicates.")

    total_absolute_shap = sum(abs(float(factor["impact"])) for factor in ordered_factors)
    local_shap_top10 = []
    grouped_items: dict[str, list[dict]] = {}
    for factor in ordered_factors:
        feature = factor["feature"]
        group, meaning = _feature_context(feature)
        impact = float(factor["impact"])
        item = {
            **factor,
            "group": group,
            "direction": _impact_direction(impact),
            "meaning": meaning,
            "top10AbsShare": _absolute_share(impact, total_absolute_shap),
        }
        local_shap_top10.append(item)
        grouped_items.setdefault(group, []).append(item)

    return {
        "featureSet": "FS2_R1_DACK_DYNAMIC",
        "localShapTop10": local_shap_top10,
        "groupedSignals": [
            _group_summary(group, items, total_absolute_shap)
            for group, items in grouped_items.items()
        ],
    }


def _feature_context(feature: str) -> tuple[str, str]:
    if feature in FEATURE_GROUPS:
        return FEATURE_GROUPS[feature], BASE_FEATURE_MEANINGS[feature]
    axis, suffix = feature.split("_", maxsplit=1)
    return DYNAMIC_AXIS_GROUPS[axis], SUFFIX_MEANINGS[suffix]


def _impact_direction(impact: float) -> str:
    if impact > 0:
        return "risk_up"
    if impact < 0:
        return "risk_down"
    return "neutral"


def _absolute_share(impact: float, total_absolute_shap: float) -> float:
    if total_absolute_shap == 0:
        return 0.0
    return abs(impact) / total_absolute_shap


def _group_summary(group: str, items: list[dict], total_absolute_shap: float) -> dict:
    impacts = [float(item["impact"]) for item in items]
    signed_shap = sum(impacts)
    absolute_shap = sum(abs(impact) for impact in impacts)
    directions = {_impact_direction(impact) for impact in impacts}
    direction = (
        "mixed"
        if {"risk_up", "risk_down"} <= directions
        else _impact_direction(signed_shap)
    )
    representatives = sorted(
        items,
        key=lambda item: (-abs(float(item["impact"])), item["rank"]),
    )[:2]
    return {
        "group": group,
        "signedShap": signed_shap,
        "absoluteShap": absolute_shap,
        "top10AbsShare": _absolute_share(absolute_shap, total_absolute_shap),
        "direction": direction,
        "includedRanks": [item["rank"] for item in items],
        "representativeFeatures": [item["feature"] for item in representatives],
    }
