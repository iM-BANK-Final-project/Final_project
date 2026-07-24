"""
M12 지속거래약화 웹 서비스용 단일 추론 코드

새 노트북 사용법
----------------
1. 이 파일과 web_service_assets 폴더를 같은 상위 폴더에 둡니다.
2. 노트북에서 아래 한 줄을 실행합니다.

   %run web_service_m12_final_scoring.py

또는 이 파일 전체를 노트북 셀에 붙여넣어 실행합니다.

필수 패키지
-----------
numpy, pandas, joblib, scikit-learn, lightgbm

주의
----
- 모델: FS_FINAL_164_TUNED, Optuna LightGBM
- 보정: Validation에서 잠근 Platt
- 참고용 이진 임계값: 0.264794
- 위험등급: 해당 기준월 적격 법인의 확률 순위 상위 1%, 1~3%,
  3~5%, 5~10%, 나머지 90%
- 개별 설명: 법인별 절대 SHAP 기여도가 큰 피처 상위 10개
- 현재 확률은 Validation Platt 잠금 확률입니다.
  2025.06까지 전체 라벨 OOF를 이용한 서비스 확률 재추정은 별도 단계입니다.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd


BUNDLE_FILENAME = "web_m12_final_platt_bundle.joblib"
FEATURE_FILENAME = "web_m12_final_features_202512_all_3372.csv"
OUTPUT_FILENAME = "web_m12_final_scores_202512_all_3372.csv"
METADATA_FILENAME = "web_m12_final_scoring_metadata.json"

EXPECTED_TARGET = "Y_INTERVENE_M12_v2"
EXPECTED_FEATURE_SET = "FS_FINAL_164_TUNED"
EXPECTED_FEATURE_COUNT = 164
EXPECTED_ALL_FIRMS = 3372
EXPECTED_ELIGIBLE_FIRMS = 3341
EXPECTED_CUTOFF_MONTH = 202512


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def find_file(filename: str) -> Path:
    """Find a companion file from a notebook or script working directory."""
    roots = [Path.cwd()]
    if "__file__" in globals():
        roots.insert(0, Path(__file__).resolve().parent)

    candidates: list[Path] = []
    for root in roots:
        candidates.extend(
            [
                root / filename,
                root / "web_service_assets" / filename,
                root / "models" / filename,
                root / "output" / filename,
            ]
        )
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()

    matches: list[Path] = []
    for root in roots:
        matches.extend(root.rglob(filename))
    unique_matches = sorted({path.resolve() for path in matches})
    if len(unique_matches) == 1:
        return unique_matches[0]
    if len(unique_matches) > 1:
        raise RuntimeError(
            f"{filename} 파일이 여러 개 발견되었습니다: "
            + ", ".join(map(str, unique_matches))
        )
    raise FileNotFoundError(
        f"{filename}을 찾지 못했습니다. 이 코드와 web_service_assets 폴더를 "
        "같은 상위 폴더에 두세요."
    )


def probability_logit(probability: np.ndarray) -> np.ndarray:
    clipped = np.clip(np.asarray(probability, dtype=float), 1e-6, 1 - 1e-6)
    return np.log(clipped / (1 - clipped))


def apply_platt(calibrator: Any, raw_probability: np.ndarray) -> np.ndarray:
    values = probability_logit(raw_probability).reshape(-1, 1)
    return calibrator.predict_proba(values)[:, 1]


def to_boolean(series: pd.Series) -> pd.Series:
    if pd.api.types.is_bool_dtype(series):
        return series.astype(bool)
    normalized = series.astype(str).str.strip().str.lower()
    mapping = {
        "true": True,
        "1": True,
        "y": True,
        "yes": True,
        "false": False,
        "0": False,
        "n": False,
        "no": False,
    }
    converted = normalized.map(mapping)
    if converted.isna().any():
        bad = sorted(normalized[converted.isna()].unique().tolist())
        raise ValueError(f"불리언으로 변환할 수 없는 값: {bad}")
    return converted.astype(bool)


def stable_rank(
    score: np.ndarray,
    firm_ids: np.ndarray,
    mask: np.ndarray | None = None,
) -> np.ndarray:
    """Rank high scores first and use firm ID as a deterministic tie-breaker."""
    score = np.asarray(score, dtype=float)
    firm_ids = np.asarray(firm_ids, dtype=str)
    if mask is None:
        mask = np.ones(len(score), dtype=bool)
    index = np.flatnonzero(mask)
    ordered = index[np.lexsort((firm_ids[index], -score[index]))]
    rank = np.full(len(score), np.nan, dtype=float)
    rank[ordered] = np.arange(1, len(ordered) + 1, dtype=float)
    return rank


def assign_risk_bands(
    probability: np.ndarray,
    firm_ids: np.ndarray,
    eligible: np.ndarray,
) -> pd.DataFrame:
    """Assign EDA-locked percentile bands among model-eligible firms."""
    rank = stable_rank(probability, firm_ids, eligible)
    eligible_n = int(eligible.sum())
    cutoffs = {
        boundary: min(eligible_n, math.ceil(eligible_n * boundary / 100))
        for boundary in [1, 3, 5, 10]
    }

    order = np.full(len(probability), np.nan)
    names = np.full(len(probability), "적격 제외", dtype=object)
    codes = np.full(len(probability), "OUT_OF_SCOPE", dtype=object)

    eligible_index = np.flatnonzero(eligible)
    eligible_rank = rank[eligible_index]
    band_order = np.full(eligible_n, 5, dtype=int)
    band_order[eligible_rank <= cutoffs[10]] = 4
    band_order[eligible_rank <= cutoffs[5]] = 3
    band_order[eligible_rank <= cutoffs[3]] = 2
    band_order[eligible_rank <= cutoffs[1]] = 1

    labels = {
        1: ("G1_TOP_1", "상위 1%"),
        2: ("G2_1_TO_3", "상위 1~3%"),
        3: ("G3_3_TO_5", "상위 3~5%"),
        4: ("G4_5_TO_10", "상위 5~10%"),
        5: ("G5_REST", "나머지 90%"),
    }
    order[eligible_index] = band_order
    codes[eligible_index] = [labels[value][0] for value in band_order]
    names[eligible_index] = [labels[value][1] for value in band_order]

    return pd.DataFrame(
        {
            "risk_rank_eligible": pd.array(rank, dtype="Int64"),
            "risk_percentile_top_pct": np.where(
                eligible,
                100.0 * rank / eligible_n,
                np.nan,
            ),
            "risk_band_order": pd.array(order, dtype="Int64"),
            "risk_band": codes,
            "risk_band_name": names,
        }
    )


def eligibility_reason(frame: pd.DataFrame) -> pd.Series:
    required = [
        "score_eligible",
        "score_eligible_D",
        "score_eligible_A",
        "score_eligible_C",
        "score_eligible_K",
    ]
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise KeyError(f"적격 판단 칼럼 누락: {missing}")

    flags = {column: to_boolean(frame[column]) for column in required}
    reason = pd.Series("정식 모델 대상", index=frame.index, dtype=object)
    out_of_scope = ~flags["score_eligible"]
    reason.loc[out_of_scope] = "Y 산식 적격 조건 미충족"
    reason.loc[out_of_scope & ~flags["score_eligible_D"]] = "요구불(D) 기준 부족"
    no_confirmation = ~(
        flags["score_eligible_A"]
        | flags["score_eligible_C"]
        | flags["score_eligible_K"]
    )
    reason.loc[out_of_scope & no_confirmation] = "A/C/K 확인축 모두 기준 부족"
    reason.loc[out_of_scope & ~flags["score_eligible_D"] & no_confirmation] = (
        "요구불(D) 및 A/C/K 확인축 기준 부족"
    )
    return reason


def relative_change_pct(log_difference: pd.Series) -> np.ndarray:
    values = pd.to_numeric(log_difference, errors="coerce").to_numpy(float)
    return 100.0 * np.expm1(np.clip(values, -20.0, 20.0))


def add_local_shap_top10(
    feature_frame: pd.DataFrame,
    output: pd.DataFrame,
    bundle: dict[str, Any],
) -> pd.DataFrame:
    """Add the ten largest absolute local SHAP contributions per firm."""
    pipeline = bundle["model"]
    features = bundle["features"]
    transformed = pipeline.named_steps["preprocessor"].transform(
        feature_frame[features]
    )
    contributions = pipeline.named_steps["model"].booster_.predict(
        transformed,
        pred_contrib=True,
    )
    contributions = np.asarray(contributions, dtype=float)[:, : len(features)]
    top_index = np.argsort(-np.abs(contributions), axis=1)[:, :10]
    row_index = np.arange(len(feature_frame))

    for position in range(10):
        feature_index = top_index[:, position]
        values = contributions[row_index, feature_index]
        output[f"shap_top{position + 1}_feature"] = [
            features[index] for index in feature_index
        ]
        output[f"shap_top{position + 1}_value"] = values
        output[f"shap_top{position + 1}_direction"] = np.where(
            values >= 0,
            "위험확률 상승",
            "위험확률 하락",
        )
    return output


def validate_assets(
    feature_frame: pd.DataFrame,
    bundle: dict[str, Any],
) -> None:
    required_keys = {
        "model",
        "calibrator",
        "calibration_method",
        "threshold",
        "features",
        "target",
        "feature_set",
    }
    missing_keys = sorted(required_keys - set(bundle))
    if missing_keys:
        raise KeyError(f"모델 번들 키 누락: {missing_keys}")
    if bundle["target"] != EXPECTED_TARGET:
        raise RuntimeError(f"예상하지 않은 Y: {bundle['target']}")
    if bundle["feature_set"] != EXPECTED_FEATURE_SET:
        raise RuntimeError(f"예상하지 않은 피처셋: {bundle['feature_set']}")
    if bundle["calibration_method"] != "PLATT":
        raise RuntimeError("최신 잠금 보정법 PLATT가 아닙니다.")
    if len(bundle["features"]) != EXPECTED_FEATURE_COUNT:
        raise RuntimeError(
            f"피처 수 불일치: {len(bundle['features'])} "
            f"!= {EXPECTED_FEATURE_COUNT}"
        )
    missing_features = sorted(set(bundle["features"]) - set(feature_frame.columns))
    if missing_features:
        raise KeyError(f"최종 모델 피처 누락: {missing_features}")
    if len(feature_frame) != EXPECTED_ALL_FIRMS:
        raise RuntimeError(
            f"법인 행 수 불일치: {len(feature_frame):,} "
            f"!= {EXPECTED_ALL_FIRMS:,}"
        )
    if feature_frame["법인ID"].astype(str).nunique() != EXPECTED_ALL_FIRMS:
        raise RuntimeError("법인ID가 3,372개로 유일하지 않습니다.")
    cutoff_values = set(
        pd.to_numeric(feature_frame["cutoff_month"], errors="raise").astype(int)
    )
    if cutoff_values != {EXPECTED_CUTOFF_MONTH}:
        raise RuntimeError(f"예상하지 않은 기준월: {sorted(cutoff_values)}")
    eligible_n = int(to_boolean(feature_frame["score_eligible"]).sum())
    if eligible_n != EXPECTED_ELIGIBLE_FIRMS:
        raise RuntimeError(
            f"적격 법인 수 불일치: {eligible_n:,} "
            f"!= {EXPECTED_ELIGIBLE_FIRMS:,}"
        )


def score_firms(
    feature_frame: pd.DataFrame,
    bundle: dict[str, Any],
) -> pd.DataFrame:
    validate_assets(feature_frame, bundle)

    features = bundle["features"]
    pipeline = bundle["model"]
    raw_probability = pipeline.predict_proba(feature_frame[features])[:, 1]
    risk_probability = apply_platt(bundle["calibrator"], raw_probability)
    threshold = float(bundle["threshold"])

    firm_ids = feature_frame["법인ID"].astype(str).to_numpy()
    eligible = to_boolean(feature_frame["score_eligible"]).to_numpy()
    all_rank = stable_rank(risk_probability, firm_ids)
    bands = assign_risk_bands(risk_probability, firm_ids, eligible)

    optional_columns = [
        "SEG__baseline_segment_2023",
        "SEG__current_segment",
        "SEG__transition",
        "CTX__업종_대분류__현재",
        "CTX__업종_중분류__현재",
        "CTX__사업장_시도__현재",
        "CTX__사업장_시군구__현재",
        "CTX__법인_고객등급__현재",
        "CTX__전담고객여부__현재",
        "score_eligible_D",
        "score_eligible_A",
        "score_eligible_C",
        "score_eligible_K",
        "score_eligible",
    ]
    keep_columns = ["법인ID", "cutoff_month"] + [
        column for column in optional_columns if column in feature_frame.columns
    ]
    output = feature_frame[keep_columns].copy().reset_index(drop=True)
    output["model_scope_status"] = np.where(
        eligible,
        "MODEL_ELIGIBLE",
        "RULE_REVIEW_OUT_OF_SCOPE",
    )
    output["model_scope_reason"] = eligibility_reason(feature_frame).to_numpy()
    output["raw_model_probability"] = raw_probability
    output["risk_probability"] = risk_probability
    output["risk_probability_pct"] = 100.0 * risk_probability
    output["reference_rank_all_3372"] = all_rank.astype(int)
    output = pd.concat([output, bands], axis=1)

    predicted = np.where(risk_probability >= threshold, 1, 0)
    output["predicted_positive_reference"] = predicted
    output["predicted_positive_model_scope"] = pd.array(
        np.where(eligible, predicted, np.nan),
        dtype="Int64",
    )
    output["threshold"] = threshold

    output["selected_top1"] = (
        output["risk_band"].eq("G1_TOP_1") & eligible
    ).astype(int)
    output["selected_top3"] = (
        output["risk_band_order"].fillna(99).astype(int) <= 2
    ).astype(int)
    output["selected_top5"] = (
        output["risk_band_order"].fillna(99).astype(int) <= 3
    ).astype(int)
    output["selected_top10"] = (
        output["risk_band_order"].fillna(99).astype(int) <= 4
    ).astype(int)

    action_by_band = {
        "G1_TOP_1": "최우선 확인",
        "G2_1_TO_3": "고위험 확인",
        "G3_3_TO_5": "집중 모니터링",
        "G4_5_TO_10": "일반 모니터링",
        "G5_REST": "정기 관찰",
        "OUT_OF_SCOPE": "룰 기반 별도 확인",
    }
    output["operating_action"] = output["risk_band"].map(action_by_band)

    axis_names = {
        "D": "요구불_최근3대이전9_변화율_pct",
        "A": "자동이체_최근3대이전9_변화율_pct",
        "C": "채널_최근3대이전9_변화율_pct",
        "K": "카드_최근3대이전9_변화율_pct",
    }
    for axis, output_name in axis_names.items():
        source_column = f"DACK__{axis}__최근3_이전9_로그차이"
        if source_column in feature_frame.columns:
            output[output_name] = relative_change_pct(feature_frame[source_column])

    output = add_local_shap_top10(feature_frame, output, bundle)
    output["target_name"] = bundle["target"]
    output["feature_set"] = bundle["feature_set"]
    output["feature_count"] = len(features)
    output["calibration_method"] = bundle["calibration_method"]
    output["probability_status"] = bundle.get(
        "probability_status",
        "VALIDATION_PLATT_LOCKED",
    )

    status_order = pd.Categorical(
        output["model_scope_status"],
        categories=["MODEL_ELIGIBLE", "RULE_REVIEW_OUT_OF_SCOPE"],
        ordered=True,
    )
    output = (
        output.assign(_status_order=status_order)
        .sort_values(
            ["_status_order", "risk_rank_eligible", "reference_rank_all_3372"],
            na_position="last",
            kind="mergesort",
        )
        .drop(columns="_status_order")
        .reset_index(drop=True)
    )
    return output


def build_summary(scores: pd.DataFrame, bundle: dict[str, Any]) -> dict[str, Any]:
    eligible = scores["model_scope_status"].eq("MODEL_ELIGIBLE")
    band_counts = (
        scores.loc[eligible, "risk_band_name"]
        .value_counts()
        .reindex(
            ["상위 1%", "상위 1~3%", "상위 3~5%", "상위 5~10%", "나머지 90%"],
            fill_value=0,
        )
        .astype(int)
        .to_dict()
    )
    return {
        "cutoff_month": EXPECTED_CUTOFF_MONTH,
        "all_firms": int(len(scores)),
        "eligible_firms": int(eligible.sum()),
        "out_of_scope_firms": int((~eligible).sum()),
        "predicted_positive_eligible": int(
            scores.loc[eligible, "predicted_positive_model_scope"].sum()
        ),
        "threshold": float(bundle["threshold"]),
        "calibration_method": bundle["calibration_method"],
        "feature_set": bundle["feature_set"],
        "feature_count": int(len(bundle["features"])),
        "risk_band_counts": band_counts,
        "top10_firms": int(scores["selected_top10"].sum()),
        "probability_status": bundle.get(
            "probability_status",
            "VALIDATION_PLATT_LOCKED",
        ),
    }


def run_scoring(output_dir: str | Path | None = None):
    bundle_path = find_file(BUNDLE_FILENAME)
    feature_path = find_file(FEATURE_FILENAME)
    bundle = joblib.load(bundle_path)
    feature_frame = pd.read_csv(
        feature_path,
        dtype={"법인ID": "string"},
        low_memory=False,
    )
    feature_frame["법인ID"] = feature_frame["법인ID"].astype(str)

    scores = score_firms(feature_frame, bundle)
    summary = build_summary(scores, bundle)

    if output_dir is None:
        output_path_root = feature_path.parent
    else:
        output_path_root = Path(output_dir).expanduser().resolve()
    output_path_root.mkdir(parents=True, exist_ok=True)

    score_path = output_path_root / OUTPUT_FILENAME
    metadata_path = output_path_root / METADATA_FILENAME
    scores.to_csv(score_path, index=False, encoding="utf-8-sig")

    metadata = {
        **summary,
        "bundle_path": str(bundle_path),
        "bundle_sha256": sha256_file(bundle_path),
        "feature_path": str(feature_path),
        "feature_sha256": sha256_file(feature_path),
        "score_path": str(score_path),
        "score_sha256": sha256_file(score_path),
    }
    metadata_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("M12 웹 추론 완료")
    print(json.dumps(metadata, ensure_ascii=False, indent=2))
    print("\n상위 위험 법인 미리보기")
    display_columns = [
        "법인ID",
        "risk_probability_pct",
        "risk_band_name",
        "predicted_positive_model_scope",
        "operating_action",
        "shap_top1_feature",
    ]
    print(scores.loc[scores["selected_top10"].eq(1), display_columns].head(10))
    return scores, metadata


# 노트북에서 이 파일을 실행하면 scores 데이터프레임이 바로 생성됩니다.
scores, scoring_metadata = run_scoring()
