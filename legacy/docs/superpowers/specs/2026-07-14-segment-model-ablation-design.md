# Segment-Enriched Weakening Model Ablation Design

## 1. Goal

기존 `Y_향후3개월_지속거래약화` LightGBM에 `L30_H70_M15` 관계 세그먼트와 세 관계축 점수를 순차적으로 추가해 예측 성능과 조기탐지 효과를 비교한다.

이번 단계는 고정 Feature ablation이다. 하이퍼파라미터 튜닝, 세그먼트별 별도 모델, SHAP 재계산은 결과를 확인한 뒤 별도 단계에서 진행한다.

## 2. Leakage Contract

관계 세그먼트는 모델 기준월마다 rolling 방식으로 다시 만든다.

```text
기준월 t의 관계수준 입력 = t-11 ~ t의 월별 거래정보
percentile 기준분포 = 2023-01 ~ 2023-12로 고정
예측 target = t+1 ~ t+3 최초 지속거래약화 사건
```

모델 기준월은 2024-02부터 시작하므로 2023년 기준분포는 모든 모델 행보다 과거다. 기준월 이후 거래정보, 2024년 연간 세그먼트, Y, 이벤트 이후 지속성 정보는 rolling 세그먼트 Feature에 사용하지 않는다.

자동 검증 조건은 다음과 같다.

- rolling 관계수준은 법인별 12개월 관측이 모두 있을 때만 계산한다.
- 기준월 `t` 이후 값을 바꿔도 `t`의 관계축 점수와 세그먼트는 변하지 않아야 한다.
- 모델링 패널 결합은 `법인ID+기준년월` one-to-one이어야 한다.
- 결합 전후 Train/Validation 행 수와 target 값이 같아야 한다.
- 2023 기준분포는 이후 기간 scoring 과정에서 다시 fit하지 않는다.

## 3. Rolling Relationship Features

기존 세그먼트와 같은 세 축을 사용한다.

```text
거래활동관계수준 = 직전 12개월 log1p(입출금+채널+카드)의 중앙값
수신관계수준 = 직전 12개월 log1p(6개 수신잔액 합)의 중앙값
여신관계수준 = 직전 12개월 log1p(운전+시설자금대출잔액)의 중앙값
```

2023 기준분포의 right-continuous 경험적 CDF로 다음 점수를 만든다.

```text
거래활동점수
수신관계점수
여신관계점수
```

`L30_H70_M15` 우선순위로 `관계세그먼트`를 부여한다. 모델에는 세 점수를 0~1 연속형으로 넣고, 관계세그먼트는 고정된 6개 one-hot 컬럼으로 넣는다.

```text
segment_저관계
segment_균형중간관계
segment_거래활동중심
segment_수신중심
segment_여신중심
segment_복합고관계
```

## 4. Data Flow

runner는 원천 CSV에서 라벨용 거래활동 컬럼과 세그먼트용 수신·여신 컬럼의 합집합을 한 번 읽는다.

```text
원천 CSV
→ 36개월 완전관측 법인 선택
→ 지속거래약화 사건 라벨
→ 기존 법인×기준월 모델링 Feature

동일 원천 CSV
→ 월별 세 관계축
→ 2023 고정 기준분포
→ 법인×기준월 rolling 관계 Feature

두 패널을 법인ID+기준년월 one-to-one 결합
→ 기존 Train/Purge/Validation 분할 재사용
```

Train은 2024-02~2024-09, Validation은 2025-04~2025-06이며 기존 6개월 label-window purge를 변경하지 않는다.

## 5. Fixed Model Comparison

모든 모델은 기존 고정 LightGBM 파라미터, 같은 Train/Validation 행, 같은 seed를 사용한다.

### Phase 1

| 모델 | Feature |
|---|---|
| `LightGBM_Base` | 기존 전체 Feature |
| `LightGBM_Segment` | Base + 세그먼트 one-hot |
| `LightGBM_Axis` | Base + 세 관계축 점수 |
| `LightGBM_Both` | Base + 세그먼트 one-hot + 세 관계축 점수 |

### Phase 2

| 모델 | Feature |
|---|---|
| `LightGBM_NoDirect` | 기존 직접신호 3개 제거 Feature |
| `LightGBM_NoDirect_Best` | NoDirect + Phase 1에서 선택된 관계 Feature |

Phase 1 선택은 Validation의 `K=10%` 행에서 다음 순서로 고정한다.

1. PR-AUC가 높은 모델
2. 동률이면 사건 Recall@10%가 높은 모델
3. 다시 동률이면 행 Recall@10%가 높은 모델
4. 다시 동률이면 추가 Feature 수가 적은 모델

Base가 가장 높으면 선택 관계 Feature는 `None`으로 기록하고 `LightGBM_NoDirect_Best`는 만들지 않는다. 효과가 없는 Feature를 억지로 최종 모델에 넣지 않는다.

Validation이 Phase 1 선택에 사용되므로 Phase 2 결과는 탐색적 개발 비교다. 선택 모델을 최종 일반화 성능으로 발표하려면 추가 시간 구간 검증이 필요하다.

## 6. Metrics And Diagnostics

기존 평가함수를 재사용해 다음을 동일하게 계산한다.

- PR-AUC
- Recall@5/10/20%
- Precision@5/10/20%
- Lift@5/10/20%
- 사건 Recall@5/10/20%
- Lead 1/2/3 Recall
- 현재 무감소 Recall
- decile lift

Validation 세그먼트별로 다음 진단도 만든다.

- 행 수와 양성 수
- 실제 양성률
- 모델별 평균 예측확률
- 모델별 PR-AUC(양성과 음성이 모두 있을 때만)
- 모델별 상위 10% 포함률과 양성 포착 수

세그먼트별 표본과 양성 수가 작으면 수치를 기술통계로만 해석하고 모델 선택 기준으로 사용하지 않는다.

## 7. Components

### 7.1 Rolling Feature Layer

`src/segmentation/relationship_segments.py`에 다음을 추가한다.

- `build_reference_relationship_levels(monthly, config)`
- `build_rolling_relationship_features(monthly, reference, config)`
- 고정 6개 one-hot 컬럼 계약

### 7.2 Model Ablation Layer

`src/models/segment_model_ablation.py`가 다음 책임을 가진다.

- 모델링 패널과 rolling Feature의 안전한 결합
- Phase 1 Feature family 구성
- 고정 LightGBM 학습과 평가
- Phase 1 선택 규칙
- NoDirect 비교
- 세그먼트별 Validation 진단

### 7.3 Runner

`src/models/run_segment_model_ablation.py`가 원천 CSV부터 다음 파일을 만든다.

```text
segment_modeling_panel.csv
segment_validation_scores.csv
segment_validation_metrics.csv
segment_validation_lift.csv
segment_validation_diagnostics.csv
segment_feature_selection.csv
```

## 8. Test Contract

합성 데이터 테스트에서 다음을 RED-GREEN으로 검증한다.

- rolling Feature가 정확히 `t-11~t`만 사용한다.
- 미래 월 변경이 기준월 Feature를 바꾸지 않는다.
- 다른 법인의 월이 rolling 계산에 섞이지 않는다.
- 2023 기준분포가 고정되고 이후 월 분포로 재순위화되지 않는다.
- 6개 one-hot이 정확히 하나만 1이다.
- one-to-one 결합 실패와 누락 Feature를 오류로 중단한다.
- 생성된 모든 비교 모델이 동일한 Validation 행을 사용한다.
- Feature family 외에는 LightGBM 설정이 동일하다.
- 선택 tie-break가 명세 순서를 따른다.
- runner가 정확한 6개 CSV를 저장한다.

실데이터에서는 기존 `LightGBM_Base`가 기존 LightGBM 결과와 허용 오차 내에서 동일해야 한다. 행 수, 양성 수, 법인 수, 기준월 범위가 기존 모델링 결과와 같아야 한다.

## 9. Acceptance And Interpretation

관계 Feature는 다음 조건으로 판단한다.

- PR-AUC와 Recall@10%를 함께 본다.
- 사건 Recall@10%와 Lead3 Recall을 조기경보 guardrail로 본다.
- 작은 단일 지표 상승만으로 최종 개선을 주장하지 않는다.
- 성능 개선이 없으면 관계축 점수와 세그먼트는 모델 입력에서 제외할 수 있다.
- 모델 입력에서 제외해도 CRM 설명과 전략 구분용 세그먼트는 유지한다.
