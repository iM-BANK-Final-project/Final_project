# 지속거래약화 Baseline 모델링 설계

> 상태: 사용자 승인 반영
> 기준일: 2026-07-13
> 이벤트 Y: `Y_지속거래약화_3M70`

## 1. 목표

확정된 지속거래약화 이벤트 Y를 이용해, 법인별 기준월 `t`에서 향후 3개월 안에 최종 양성 사건이 발생할지를 예측하는 누수 방지 baseline 모델을 만든다.

이번 범위는 rolling 모델링 패널, 시간 분할, 고정 baseline, Logistic Regression, 평가와 누수 감사를 포함한다. LightGBM 튜닝, CRM 고객가치 결합, SHAP, 운영 임계값 최적화는 후속 단계다.

## 2. 이벤트 Y와 모델링 Y의 분리

이벤트 Y는 사후 확정 정답이다.

```text
Y_지속거래약화_3M70(e)=1
if
이벤트월 e에 핵심거래 YoY ratio < 0.50이 3개월 연속 완성
AND
e+1~e+3 평균 / e-12~e-1 평균 < 0.70
```

모델링 Y는 기준월 rolling 정답이다.

```text
Y_향후3개월_지속거래약화(t)=1
if
t+1~t+3에 Y_지속거래약화_3M70=1인 이벤트월이 하나 이상 존재

Y_향후3개월_지속거래약화(t)=0
if
t+1~t+3에 최종 양성 이벤트가 없고 전체 미래창을 판정 가능
```

같은 사건이 최대 3개 기준월의 양성 라벨을 만들 수 있다. 행 단위 평가와 함께 `법인ID+이벤트월` 기준 사건 단위 recall을 계산해 중복 anchor의 영향을 분리한다.

법인별 최초 최종 양성 사건월과 그 이후 기준월은 신규 조기경고 대상이 아니므로 모델링 패널에서 제외한다. 현재 1~2개월 연속 drop50은 기준월까지 관측된 합법적인 조기신호이므로 feature로 유지한다.

## 3. 라벨 관찰 범위와 학습 가능 기준월

기준월 `t`의 예측 사건창은 `t+1~t+3`이다. 가장 늦은 `t+3` 사건의 지속성을 확인하려면 `t+6`까지 필요하다.

```text
t             = feature cutoff
t+1~t+3       = 예측 사건창
t+4~t+6       = 가장 늦은 사건의 지속성 확인 가능 구간
label_end(t)  = t+6
```

원천 데이터가 2023-01~2025-12이므로 완전한 모델 라벨을 만들 수 있는 마지막 기준월은 2025-06이다.

YoY는 12개월 전 값이 필요하고 3개월 연속 이벤트는 최초 2024-03에 완성될 수 있다. 모든 기준월이 완전한 3개월 사건 기회를 갖도록 최초 모델 기준월은 2024-02로 둔다.

## 4. 시간 분할

train/validation 두 구간만 사용한다. validation은 반복 튜닝용이 아니라 최종 시간 외 검증셋으로 취급한다.

```text
Train anchors:       2024-02~2024-09
Label-window purge:  2024-10~2025-03
Validation anchors:  2025-04~2025-06
```

마지막 train 기준월 2024-09의 정답은 2025-03까지 사용해 확정된다. validation은 그다음 달인 2025-04부터 시작한다. 마지막 validation 기준월 2025-06의 정답은 데이터 마지막 달인 2025-12에 확정된다.

purge 월은 기준월 학습·평가 행으로 사용하지 않지만 validation feature의 과거 이력을 만들 때는 사용할 수 있다. 분할은 모든 법인에 동일한 달력 기준을 적용하며 법인 행을 무작위로 섞지 않는다.

## 5. Feature cutoff와 누수 금지

모든 feature는 기준월 `t` 행과 그 이전 월만 사용한다. rolling 연산은 반드시 법인별 정렬 후 계산하며 미래 방향 shift를 금지한다.

직접 금지 컬럼:

```text
Y_지속거래약화_3M70
Y_향후3개월_지속거래약화
이벤트이후3개월평균
future3_to_baseline
미래지속거래약화사건월
미래지속거래약화사건ID
```

`core_3m_event(t)`, `drop50(t)`, `drop50_연속개월수(t)`는 현재까지 관측된 값이지만 `core_3m_event=1` 행은 모집단에서 제외한다.

업종, 지역, 고객등급, 전담여부 등 프로필은 기준월 당시 값을 사용한다. 최신월 프로필을 과거 전체 행에 소급하지 않는다. 정적이라고 가정하려면 기간 중 불변 여부를 먼저 검증한다.

결측 대체값, 스케일러, 범주형 인코더는 train에서만 `fit`하고 validation에는 `transform`만 수행한다.

## 6. Baseline feature set

핵심거래와 입출금·채널·카드 각 축에 다음 과거 feature를 만든다.

```text
현재값
1개월 변화율
YoY ratio
최근 3개월 평균
최근 6개월 평균
이전 6개월 평균
최근 3개월 / 이전 6개월 비율
최근 3·6개월 표준편차
최근 3·6개월 활성월 비율
최근 3·6·12개월 선형 기울기
현재 drop50
현재 drop50 연속개월수
```

금액은 치우침이 크므로 Logistic Regression 입력의 금액 수준·평균·표준편차에는 `log1p` 변환을 적용한다. 비율은 분모가 0이면 결측으로 유지하고 train 중앙값으로 대체한다. 무한대는 허용하지 않는다.

수신, 여신, 외환, 자동이체, 상품관계폭은 이벤트 Y 판정축은 아니지만 원천 데이터 계약을 확인한 뒤 확장 feature로 추가한다. 첫 baseline은 핵심거래·입출금·채널·카드에 한정해 Y 구현과 직접 연결되는 최소 범위를 사용한다.

## 7. 비교 Baseline

### 7.1 Prevalence baseline

모든 validation 행에 train 양성률을 동일 점수로 부여한다. 모델이 무정보 수준보다 나은지 확인하는 하한선이다.

### 7.2 Current-signal rule

학습 없는 해석 가능한 규칙 점수를 사용한다.

```text
rule_score
= 2 × min(drop50_연속개월수, 2)
 + 1 × I(핵심거래_YoY_ratio < 0.70)
 + max(0, 1 - 핵심거래_YoY_ratio)
```

현재 사건 행은 이미 모집단에서 제외되므로 연속개월수는 0~2다. 이 점수는 미래 정보나 validation 분포로 임계값을 조정하지 않는다.

### 7.3 Logistic Regression

```text
penalty = l2
C = 1.0
class_weight = balanced
max_iter = 1000
random_state = 42
```

수치형 결측은 train 중앙값, 이후 StandardScaler를 적용한다. 범주형 feature를 추가하는 경우 train 최빈값과 `OneHotEncoder(handle_unknown="ignore")`를 사용한다. validation을 보고 파라미터를 변경하지 않는다.

## 8. 평가

불균형 분류이므로 accuracy를 주요 지표로 사용하지 않는다.

주요 지표:

```text
행 단위 PR-AUC
Recall@상위 5%, 10%, 20%
Precision@상위 5%, 10%, 20%
Lift@상위 5%, 10%, 20%
법인ID+이벤트월 기준 사건 Recall@상위 5%, 10%, 20%
점수 십분위별 양성률과 lift
```

보조 진단:

- validation 월별 양성률·PR-AUC·Top-K recall
- 업종·지역·등급·전담여부별 표본 수, 양성률, Top-K 포착률
- train과 validation feature 결측률·분포 변화
- 같은 사건을 가리키는 중복 양성 anchor 수
- 법인별 알림 횟수와 반복 알림 비율

validation에 양성 사건이 없거나 월별 표본이 부족하면 해당 지표를 억지로 계산하지 않고 `NaN`과 사유를 기록한다.

## 9. 누수 자동 검사

다음 테스트를 필수로 둔다.

1. 한 법인의 `t+1` 이후 원천 값을 변경해도 `t` feature가 변하지 않는다.
2. `t+1~t+3` 이벤트만 `Y_향후3개월_지속거래약화(t)`에 포함된다.
3. `t+4` 이벤트는 해당 기준월 Y에 포함되지 않는다.
4. 미래 6개월이 부족한 기준월은 Y 결측이다.
5. 최초 최종 양성 사건월과 그 이후 기준월은 학습 패널에서 제외된다.
6. train의 최대 `label_end`가 validation 최소 기준월보다 이르다.
7. 전처리기는 train에만 fit된다.
8. 금지 컬럼이 모델 feature 목록에 포함되지 않는다.
9. 법인별 rolling 연산이 다른 법인의 값과 섞이지 않는다.

## 10. 산출물

```text
src/models/persistent_weakening_baseline.py
src/models/run_persistent_weakening_baseline.py
tests/test_persistent_weakening_modeling.py

outputs/persistent_weakening_baseline/
  modeling_panel.csv
  validation_scores.csv
  validation_metrics.csv
  validation_lift.csv
  segment_diagnostics.csv
```

실제 원천 데이터로 재실행할 때는 완전관측 법인 수, 최초 양성 사건 수, 사건월 이후 패널 잔존 여부를 성과표와 함께 검증한다.

## 11. 완료 기준

- rolling 모델링 Y가 정의대로 생성된다.
- feature cutoff와 6개월 label-window purge 테스트가 통과한다.
- 세 baseline이 동일 validation 행에서 평가된다.
- validation은 모델·전처리 fit에 사용되지 않는다.
- PR-AUC, Top-K, lift, 사건 recall 산출 계약이 테스트된다.
- 실제 데이터 실행 결과는 위험집단 구성과 함께 기록한다.
