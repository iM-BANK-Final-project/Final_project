# Persistent Transaction Weakening Modeling Definition

## 1. Event Label

최종 이벤트 라벨은 `Y_지속거래약화_3M70`이다.

```text
핵심거래활동금액 = 입출금활동금액 + 채널활동금액 + 카드활동금액

drop50(t) = 핵심거래활동금액(t) / 핵심거래활동금액(t-12) < 0.50

Y_지속거래약화_3M70 = 1
if
drop50이 3개월 연속 발생
AND
이벤트 이후 3개월 평균 / 이벤트 이전 12개월 평균 < 0.70
```

이 라벨은 실제 해지나 확정 휴면이 아니라 사후 확인되는 지속거래약화 proxy다.

## 2. Baseline Modeling Status

```text
모델링 Y = Y_향후3개월_지속거래약화
Train anchors = 2024-02~2024-09
Label-window purge = 2024-10~2025-03
Validation anchors = 2025-04~2025-06
실제 데이터 재실행 = 2026-07-13
```

모델링 Y는 기준월 `t`의 다음 3개월인 `t+1~t+3`에 최종 양성 이벤트가 하나 이상 존재하는지 나타낸다. 법인별 최초 `Y_지속거래약화_3M70=1` 사건월과 그 이후 기준월은 이미 사건이 발생한 고객이므로 신규 조기경고 위험집단에서 제외한다.

마지막 train 기준월의 라벨은 최대 `t+6`까지 사용해 확정되므로 train과 validation 사이에 6개월 label-window purge를 둔다. purge 월의 원천 거래는 validation의 과거 feature를 만들 때 사용할 수 있지만 별도 기준월 행으로 학습하거나 평가하지 않는다.

## 3. Baselines And Ablation

비교 모델은 다음과 같다.

```text
Prevalence = train 양성률을 모든 행에 동일하게 부여
CurrentSignalRule = 현재 YoY와 drop50 연속기간의 고정 규칙 점수
LogisticRegression = train-only 전처리와 고정 하이퍼파라미터
LogisticRegression_NoDirect = 직접 약화 신호 3개를 제거한 Logistic Regression
LightGBM = 전체 feature의 고정 LightGBM
LightGBM_NoDirect = 직접 약화 신호 3개를 제거한 고정 LightGBM
```

Logistic Regression은 `C=1.0`, `class_weight=balanced`, `max_iter=1000`, `random_state=42`를 사용한다. validation을 보고 파라미터를 변경하지 않는다.

직접 신호 제거 feature는 전체 feature에서 `현재drop50`, `현재drop50연속개월수`, `YoY_ratio_핵심거래활동금액`만 제외한다.

고정 LightGBM은 `n_estimators=300`, `learning_rate=0.03`, `num_leaves=15`, `max_depth=5`, `min_child_samples=100`, `subsample=0.8`, `colsample_bytree=0.8`, `reg_alpha=0.1`, `reg_lambda=1.0`, `class_weight=balanced`, `random_state=42`를 사용한다. FLAML과 validation 기반 튜닝은 사용하지 않았다.

## 4. Feature Boundary

핵심거래·입출금·채널·카드에 대해 현재값, 1개월 변화율, YoY, 최근 3·6개월 평균·표준편차·활성률, 최근 3개월/이전 6개월 비율, 3·6·12개월 기울기를 만든다. 모든 rolling 계산은 법인별로 분리하고 기준월 `t`까지만 사용한다.

다음 열은 모델 feature에서 제외한다.

```text
Y_지속거래약화_3M70
Y_향후3개월_지속거래약화
이벤트이후3개월평균
future3_to_baseline
미래지속거래약화사건월
미래지속거래약화사건ID
지속거래약화사건ID
label_end
```

결측 대체와 StandardScaler는 train에만 fit하고 validation에는 transform만 적용한다.

## 5. Evaluation

- PR-AUC
- Recall·Precision·Lift@상위 5%, 10%, 20%
- `법인ID+이벤트월` 기준 사건 recall
- 사건까지 1·2·3개월 리드타임별 recall
- 현재 drop50 연속기간이 0인 고객의 recall
- 점수 구간별 양성률과 lift
- validation 월별 양성률과 평균 점수

validation은 최종 시간 외 holdout으로 취급한다.

2026-07-13 위험집단 보정 후 실데이터 baseline 결과는 다음과 같다.

| 모델 | PR-AUC | Top 10% Recall | Top 10% Lift | Top 10% 사건 Recall | Lead 3 / 현재 무감소 Recall |
| --- | ---: | ---: | ---: | ---: | ---: |
| Prevalence | 0.0249 | - | - | - | - |
| CurrentSignalRule | 0.1521 | 53.64% | 5.36 | 70.94% | 0.00% |
| LogisticRegression | 0.1360 | 55.45% | 5.54 | 70.94% | 4.00% |
| LogisticRegression_NoDirect | 0.0778 | 35.00% | 3.50 | 46.15% | 16.00% |
| LightGBM | **0.1970** | **61.82%** | **6.18** | **79.49%** | 18.67% |
| LightGBM_NoDirect | 0.1824 | 55.45% | 5.54 | 70.09% | **22.67%** |

Validation은 8,839행, 양성 220행, 고유 양성 사건 117개다. 전체 LightGBM이 종합 성능이 가장 높고, 직접 신호를 제거한 LightGBM은 종합 성능을 일부 유지하면서 Lead 3과 현재 무감소 Recall이 높아졌다. 현재 성능은 baseline 비교용이며 세그먼트 안정성과 추가 시간구간은 아직 검증하지 않았다.

## 6. Run

```bash
python -m src.models.run_persistent_weakening_baseline \
  --input /path/to/corporate_monthly.csv \
  --output-dir outputs/persistent_weakening_baseline
```

출력:

```text
modeling_panel.csv
validation_scores.csv
validation_metrics.csv
validation_lift.csv
segment_diagnostics.csv
```

구현 파일:

```text
src/models/persistent_weakening_baseline.py
src/models/run_persistent_weakening_baseline.py
tests/test_persistent_weakening_modeling.py
```
