# Corporate RM Persistent Transaction Weakening Service

기업금융 RM이 법인고객의 지속적인 거래관계 약화를 발견하고, 고객가치에 따라 관리 순서와 접촉 전략을 정하도록 지원하는 프로젝트입니다.

프로젝트의 기준 설계 문서는 [financial_dormancy.md](/Users/gggyyu/Final_project/financial_dormancy.md), 최종 Y의 분석 근거는 [y_setting_pipeline.md](/Users/gggyyu/Final_project/y_setting_pipeline.md)입니다.

## Final Target

최종 Y는 `Y_지속거래약화_3M70`입니다.

```text
핵심거래활동금액 = 입출금활동금액 + 채널활동금액 + 카드활동금액

Y_지속거래약화_3M70 = 1
if
핵심거래 YoY ratio < 0.50이 3개월 연속 발생
AND
이벤트 이후 3개월 평균 / 이벤트 이전 12개월 평균 < 0.70
```

3개월 연속 조건이 처음 완성된 세 번째 달을 이벤트월로 사용합니다. 이벤트월은 전후 평균에서 제외하며, `0.50`과 `0.70`은 양성 경계에 포함하지 않습니다.

이 Y는 실제 해지나 확정 휴면이 아니라 2023-01~2025-12의 36개월 완전관측 법인 3,372개에서 정의한 지속거래약화 proxy입니다. 분석상 516개 법인(15.30%)이 최종 조건을 충족했습니다.

## Current Status

- 최종 이벤트 Y 확정
- pandas 기반 법인×월 라벨 및 사건 테이블 구현
- 기존 5축 동시감소 Y와 해당 모델 성능 사용 중단
- rolling 조기예측 target과 새 모델 성능은 재설계·재학습 대기

## Run Labels

```bash
python -m src.preprocessing.run_persistent_transaction_weakening_labels \
  --input /path/to/corporate_monthly.csv \
  --output-dir outputs/persistent_transaction_weakening_labels
```

출력:

```text
persistent_transaction_weakening_panel.csv
persistent_transaction_weakening_events.csv
```

## Service Flow

```text
36개월 완전관측 코호트
→ Y_지속거래약화_3M70 이벤트 라벨
→ rolling 예측 target 승인
→ 지속거래약화 예측
→ 고객가치 기반 CRM 우선순위
→ 세그먼트 추천
→ SHAP/차트 기반 AI 전략 보고서
```

## Rules

- 결측 고객-월과 결측 금액을 0으로 처리하지 않습니다.
- 전년 동월이 0이면 YoY 감소를 판정하지 않습니다.
- 사후 확인용 이후 3개월 정보를 모델 feature로 사용하지 않습니다.
- 새 Y로 재학습하기 전에는 과거 모델 성능을 현재 성과로 제시하지 않습니다.
- 결과를 실제 해지나 전체 법인 모집단의 성과로 일반화하지 않습니다.

## Main Artifacts

- Design: [financial_dormancy.md](/Users/gggyyu/Final_project/financial_dormancy.md)
- Y evidence: [y_setting_pipeline.md](/Users/gggyyu/Final_project/y_setting_pipeline.md)
- Implementation spec: [2026-07-13-persistent-transaction-weakening-y-design.md](/Users/gggyyu/Final_project/docs/superpowers/specs/2026-07-13-persistent-transaction-weakening-y-design.md)
- Implementation plan: [2026-07-13-persistent-transaction-weakening-y.md](/Users/gggyyu/Final_project/docs/superpowers/plans/2026-07-13-persistent-transaction-weakening-y.md)
- Modeling gate: [src/models/model.md](/Users/gggyyu/Final_project/src/models/model.md)
