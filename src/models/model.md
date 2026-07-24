# Final M12 Modeling Contract

## Source of Truth

현재 배포 모델의 기준은 `web_service_m12_final_scoring.py`, `web_m12_final_scores_202512_all_3372.csv`, `web_m12_final_risk_trend_202507_202512.csv`와 `../수익성F(y선정포함).ipynb`다. 과거 `Y_지속거래약화_3M70` 및 관련 baseline은 탐색 이력이며 현재 운영 모델 계약이 아니다.

## Target

```text
ONSET_g   = cutoff+1~3 각 월의 전년동월비 < 0.60
PERSIST_g = mean(cutoff+4:cutoff+6) / mean(cutoff-11:cutoff) < 0.70
W_g       = ONSET_g AND PERSIST_g

Y_INTERVENE_M12_v2 = W_D AND (W_A OR W_C OR W_K)
```

D는 입출금, A는 자동이체, C는 채널, K는 카드 활동축이다. D가 판정 가능하고 A/C/K 중 하나 이상이 판정 가능할 때만 target 적격이다. 판정 불가능 행은 음성으로 대체하지 않는다.

롤링 target lock:

- 전체 64,068행
- 적격 63,572행
- 양성 1,966행
- 적격 법인 3,354개
- 양성 법인 639개

## Model

- Feature set: `FS_FINAL_164_TUNED`
- Feature count: 164
- Estimator: LightGBM
- Calibration: validation에서 잠근 Platt
- Operating threshold: `0.26479401324821045`
- Probability status: `VALIDATION_PLATT_LOCKED_SERVICE_REESTIMATION_DEFERRED`
- Operating cutoff: 2025-12

업종·세그먼트 필드는 설명과 안정성 감사용이며 모델 입력에서 제외한다. `risk_probability`는 향후 6개월 `Y_INTERVENE_M12_v2` 발생 확률이다.

## Operating Artifact

`web_m12_final_scores_202512_all_3372.csv`는 2025-12 전체 3,372개를 포함하며 서비스 준비 단계에서 `score_eligible=True`인 정확히 3,341개만 선별한다. 부적격 31개는 DB, API, KPI, 필터, 화면에서 제외한다. 적격 모집단의 위험 밴드는 확률순위 기준 상위 1%, 1~3%, 3~5%, 5~10%, 나머지 90%다.

고객별 로컬 설명은 164개 feature의 LightGBM contribution 중 절대값이 큰 `SHAP Top 10`을 저장한다. 서비스 DB의 `shap_factors`는 33,410행이며 API와 UI는 순위 1~10을 모두 반환·표시한다. AI 서술은 관계 기본 피처와 `DACK__`, `EXP_DIFF__`, `EXP_PATH__`, `EXP_CROSS__`, `EXP_KM__`만 모델 근거로 허용하며 `CTX__`, `SEG__`는 제외한다.

점수 artifact의 현재 세그먼트, 세그먼트 전이, D/A/C/K 변화율, 상위 10개 SHAP 설명을 서비스에 저장한다. 웹에서는 모델이나 SHAP를 재계산하지 않는다.

## Value and Priority Contract

최종 우선순위는 고객가치 대리지표가 아니라 기준월 포함 최근 실제 6개월 FISIM 기반 위험조정 CLV 차이를 사용한다. 2025-12 운영에서는 2025-07~12 실제 월별 FISIM을 사용하며 미래 잔액과 생존확률은 예측하지 않는다.

```text
CLV_NoRisk = Σ actual_FISIM_m, m=2025-07..2025-12
CLV_Risk = CLV_NoRisk / (1+p)
PotentialLoss = CLV_NoRisk - CLV_Risk
defense_value = max(PotentialLoss, 0)
```

양수 `defense_value`만 `defense_rank`를 갖고, 값·위험·`CLV_NoRisk` 내림차순 후 법인ID 오름차순으로 동률을 해소한다. UI에는 `CLV_Risk`와 `PotentialLoss`만 표시한다. `PotentialLoss`는 확정 회계손실이 아니다.

## Reproduction

```bash
conda run -n final python -m src.backend.prepare_service_database
```

이 명령은 최종 점수, 원천 월별 패널, FTP, 은행 금리로 `outputs/rm_service_inputs/clv_202512.csv`와 3,341개 대상 SQLite를 생성한다.

## Gemini AI Report and PDF

`POST /api/reports/{corporate_id}/generate`는 SQLite에 저장된 위험·`CLV_Risk`·`PotentialLoss`·D/A/C/K·`SHAP Top 10`·추천 근거로 Gemini 6개 서술 섹션을 생성한다. 백엔드는 `GEMINI_API_KEY` 또는 Vertex AI 설정을 사용하며 정량 수치와 SHAP을 LLM 응답에서 받지 않는다.

`POST /api/reports/{corporate_id}/pdf`는 생성 보고서의 고객·기준월·수치·SHAP을 DB와 재검증한 후 `RM_REPORT_FONT_PATH` 또는 OS fallback 한국어 폰트로 A4 PDF를 메모리에서 생성한다. AI 보고서와 PDF는 DB에 저장하지 않는다.
