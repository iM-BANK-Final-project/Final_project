# Persistent Transaction Weakening Modeling Definition

## 1. Current Gate

최종 이벤트 라벨은 `Y_지속거래약화_3M70`으로 확정됐다. 기존 5축 동시감소 모델은 실행을 중단한다. 새 Y는 사후 확인 라벨이므로 rolling 조기예측 target이 별도로 승인되기 전에는 모델을 재학습하거나 성능을 주장하지 않는다.

## 2. Event Label Contract

```text
핵심거래활동금액 = 입출금활동금액 + 채널활동금액 + 카드활동금액

drop50(t) = 핵심거래활동금액(t) / 핵심거래활동금액(t-12) < 0.50

Y_지속거래약화_3M70 = 1
if
drop50이 3개월 연속 발생
AND
이벤트 이후 3개월 평균 / 이벤트 이전 12개월 평균 < 0.70
```

3개월 연속 조건이 처음 완성된 달이 이벤트월이다. 사건 ID는 `법인ID+이벤트월`이다. 미래 관찰창 부족이나 분모 판정 불가능은 Y 결측이다.

## 3. Cohort

```text
기간 = 2023-01~2025-12
대상 = 정확한 연속 36개월 완전관측 법인
현재 EDA 기준 = 3,372개
이벤트 라벨 단위 = 법인 × 이벤트월
```

누락 고객-월과 결측 금액을 0으로 보충하지 않는다.

## 4. Feature Boundary

향후 예측 모델은 기준월 `t` 이하 정보만 feature로 사용한다. 다음 사후 확인 열은 feature에서 반드시 제외한다.

```text
이벤트이후3개월평균
future3_to_baseline
Y_지속거래약화_3M70
```

수신, 여신, 외환, 자동이체, 상품관계폭과 고객 프로필은 Y 판정축이 아니지만 과거 시점 정보에 한해 예측 feature 또는 원인 설명축으로 검토할 수 있다.

## 5. Rolling Prediction Target Pending

다음 항목은 아직 확정되지 않았다.

- 기준월 `t`에서 예측할 미래 사건창
- 이미 약화 중인 법인의 제외 또는 cooldown 규칙
- 학습 가능 기준월과 시간 embargo 길이
- 운영 Top-K와 RM 업무량

이 계약이 승인된 후 Logistic Regression, LightGBM 및 해석 가능한 규칙 baseline을 새로 학습한다.

## 6. Evaluation

- PR-AUC
- Top-K 사건 recall
- 점수 구간별 lift
- 업종·지역·등급·전담여부별 안정성
- 기간별 안정성과 이상치 민감도
- 미래 정보 누수 자동 검사

과거 Y로 계산한 성능은 새 Y의 성능으로 재사용하지 않는다.

## 7. Output Contract Pending Retraining

향후 검증된 모델은 다음 운영 필드를 제공한다.

```text
법인ID
기준년월
지속거래약화확률
금융관계약화위험
조기관리대상여부
주요약화원인
```

고객가치 결합과 CRM 순위는 모델 검증 이후 별도 단계에서 계산한다.
