# Project Working Notes

## Project Topic

기업금융 RM을 위한 **지속거래약화 예측, 고객가치 기반 CRM 우선순위, 세그먼트 기반 맞춤형 마케팅, AI 전략 보고서 생성 서비스**.

## Primary Design Documents

- 중심 설계: `financial_dormancy.md`
- 최종 Y 근거: `y_setting_pipeline.md`
- 구현 명세: `docs/superpowers/specs/2026-07-13-persistent-transaction-weakening-y-design.md`

활성 문서나 코드가 최종 Y 정의와 충돌하면 위 문서의 현재 정의를 우선한다.

## Product Questions

서비스는 기업금융 RM의 네 가지 질문에 답해야 한다.

1. 어떤 법인고객을 먼저 관리해야 하는가?
2. 거래관계가 지속적으로 약해지고 있는가?
3. 고객가치까지 고려하면 관리 순서는 어떻게 달라지는가?
4. 어떤 상품 또는 접촉 전략을 시도해야 하는가?

```text
36개월 완전관측 법인 코호트
→ Y_지속거래약화_3M70 이벤트 라벨
→ rolling 조기예측 target 승인
→ 지속거래약화 예측
→ 고객가치 대리지표 결합
→ CRM 관리 우선순위
→ 세그먼트 기반 맞춤형 마케팅
→ SHAP/차트 기반 AI 전략 보고서
```

## Final Y Contract

최종 Y는 `Y_지속거래약화_3M70`이다. 실제 해지나 확정 휴면이 아니라 거래활동 시계열의 지속거래약화 proxy다.

```text
입출금활동금액 = 요구불입금금액 + 요구불출금금액

채널활동금액 = 창구거래금액
                + 인터넷뱅킹거래금액
                + 스마트뱅킹거래금액
                + 폰뱅킹거래금액
                + ATM거래금액

카드활동금액 = 신용카드사용금액 + 체크카드사용금액

핵심거래활동금액 = 입출금활동금액
                    + 채널활동금액
                    + 카드활동금액

drop50(t) = 핵심거래활동금액(t) / 핵심거래활동금액(t-12) < 0.50

Y_지속거래약화_3M70 = 1
if
drop50이 3개월 연속 발생
AND
이벤트 이후 3개월 평균 / 이벤트 이전 12개월 평균 < 0.70
```

### Event Rules

- 3개월 연속 조건이 처음 완성된 세 번째 달이 이벤트월이다.
- 같은 연속 구간의 네 번째 이후 달은 새 사건이 아니다.
- 회복 후 새 3개월 연속 구간은 별도 사건이다.
- 이벤트 이전 평균은 `t-12~t-1`, 이후 평균은 `t+1~t+3`이며 이벤트월은 제외한다.
- YoY 분모가 0이거나 원천 금액이 결측이면 drop50을 판정하지 않는다.
- `ratio=0.50`은 drop50이 아니고 `future3_to_baseline=0.70`은 Y=0이다.
- 미래 3개월 부족 또는 지속성 분모 판정 불가능은 Y=0이 아니라 결측이다.
- 사건 단위 키는 `법인ID+이벤트월`이다.

분석 결과 최종 조건은 516개 법인, 전체 3,372개의 15.30%를 식별했다. 실제 원천 데이터 실행에서 이 수치를 재현 검증해야 한다.

## Retired Target

과거의 5개 핵심축 중 3축 이상 동시감소 방식은 최종 Y가 아니다. 해당 라벨과 그 모델 성능을 현재 결과로 표현하지 않는다.

수신, 여신, 외환, 자동이체, 상품관계폭은 최종 Y 조건에서 제외한다. 기준월까지의 값은 향후 모델 feature와 설명축으로 검토할 수 있다.

## Data Rules

- 분석 기간은 2023-01~2025-12다.
- 법인별 고객-월이 중복 없이 정확히 36개이며 연속인지 검증한다.
- 결측 고객-월과 결측 원천 금액을 자동으로 0 처리하지 않는다.
- 음수 거래금액은 원천 데이터 오류로 처리한다.
- feature는 기준월 `t`까지의 정보만 사용한다.
- 이벤트 이후 3개월 평균과 `future3_to_baseline`은 feature로 사용하지 않는다.
- 업종·지역 등 정적 속성이 기간 중 변했는지 점검한다.
- 초기 6개월 평균 대비 지수는 EDA 비교용이며 종합 금융활동 점수로 부르지 않는다.

## Modeling Gate

현재 확정된 것은 사후 이벤트 라벨이다. rolling 조기예측 target은 별도 승인 전까지 미정이다.

- 기존 모델 실행을 중단한다.
- 기존 성능을 새 Y의 성능으로 재사용하지 않는다.
- 미래 사건창, cooldown, 학습 가능 기준월, embargo를 승인한 뒤 재학습한다.
- 시간 기반 검증을 우선한다.
- PR-AUC, Top-K 사건 recall, lift와 세그먼트 안정성을 확인한다.
- 미래 정보 누수 검사를 자동화한다.

## CRM Priority

```text
고객가치 대리지표
= 정규화된 수신 + 여신 + 거래성금액 + 상품관계폭 + 고객등급 + 전담여부

CRM 관리 우선순위 점수
= 검증된 지속거래약화 위험 × 고객가치 대리지표
```

필수 필터는 업종, 지역, 전담여부, 약화유형, 세그먼트다. 관리 우선순위 점수는 실제 손실액이 아니라 RM 운영 순서를 정하기 위한 점수다.

## Recommendations

초기 추천은 rule-based + segment-based baseline으로 둔다.

| 약화 원인 | 추천 방향 |
| --- | --- |
| 입출금 | 자금관리 상담, CMS, 결제성 거래 점검 |
| 채널 | 디지털채널 온보딩, 이용 장애·불편 확인 |
| 카드 | 법인카드 이용조건 점검, 한도·혜택 상담 |
| 복합 거래활동 | RM 직접 접촉, 관계 회복 상담 |

## AI Report

LLM은 검증된 모델 출력과 SHAP·차트를 RM 언어로 설명한다. 상위 위험군, 선택 고객, 보고서 요청 건으로 호출을 제한한다. “지속거래약화 가능성”, “금융관계 약화 위험”, “조기관리 필요”, “추천 접촉 전략”을 사용한다.

## Current Priority

1. 실제 원천 데이터에서 새 이벤트 라벨 재현
2. 월별·업종별·지역별 안정성과 이상치 민감도 검증
3. rolling 조기예측 target 승인
4. 새 모델 시간 검증
5. 고객가치 기반 CRM 우선순위
6. 추천·SHAP·AI 보고서 연결

## Current Artifacts

- Main design: `financial_dormancy.md`
- Y evidence: `y_setting_pipeline.md`
- Label implementation: `src/preprocessing/persistent_transaction_weakening_labels.py`
- Label runner: `src/preprocessing/run_persistent_transaction_weakening_labels.py`
- Modeling gate: `src/models/model.md`
- Main EDA: `EDA/36개월 특성.ipynb`
- Historical implementations: `legacy/`
