# Modeling Reproduction Guide Design

## 1. 목적

`docs/modeling_end_to_end_reproduction_guide.md` 하나만 읽어도 다른 팀원이 현재까지의 지속거래약화 모델링을 이해하고, 원천 CSV에서 동일한 산출물과 성과지표를 재현할 수 있게 한다.

## 2. 독자와 문서 성격

- 주 독자: 데이터 분석가, 모델 개발자, 프로젝트 신규 합류자
- 문서 성격: 기술 설명서 + 재현 절차 + 결과 해석 가이드
- 범위: 최종 이벤트 Y, 탐색 rolling target, 시간 분할, feature, baseline, 관계 세그먼트 ablation, 평가, 검증, 실행 방법
- 제외: 고객가치 점수, CRM 화면, 추천 로직, 배포 인프라의 상세 구현

## 3. 상태 구분 원칙

문서 첫 부분에서 다음을 명확히 분리한다.

1. `Y_지속거래약화_3M70` 이벤트 정의는 최종 확정 계약이다.
2. 현재 코드의 `Y_향후3개월_지속거래약화`와 모델 성과는 탐색 구현이다.
3. 현재 프로젝트 지침에 따라 rolling 예측 target, 사건창, cooldown, 학습 기준월, embargo를 다시 승인하기 전에는 해당 성과를 최종 운영 성능으로 사용하지 않는다.
4. 하이퍼파라미터 튜닝은 실시하지 않았으며 모든 LightGBM 비교는 고정 파라미터다.

## 4. 문서 구조

1. 기술 요약과 현재 결론
2. 승인 상태와 용어
3. 데이터·코호트 계약
4. 최종 이벤트 Y 정의와 경계조건
5. 탐색 rolling 예측 target과 위험집단
6. 누수 방지 및 시간 분할
7. 기존 feature engineering
8. baseline과 직접신호 ablation
9. 관계 세그먼트·관계축 feature
10. Base·Segment·Axis·Both 비교
11. 평가 지표와 실데이터 결과
12. feature importance·SHAP 결과
13. 코드 구조와 end-to-end 실행 명령
14. 출력 파일과 검증 체크리스트
15. 제한사항, 금지 해석, 다음 작업

## 5. 근거 자료

- `financial_dormancy.md`
- `y_setting_pipeline.md`
- `docs/superpowers/specs/2026-07-13-persistent-transaction-weakening-y-design.md`
- `src/models/model.md`
- `segmentation_final_report.md`
- `src/preprocessing/persistent_transaction_weakening_labels.py`
- `src/models/persistent_weakening_baseline.py`
- `src/models/segment_model_ablation.py`
- 실제 실행 산출물 `outputs/segment_model_ablation/*.csv`
- 관련 pytest 계약

서로 충돌하는 설명은 현재 프로젝트 지침의 상태를 우선하고, 탐색 당시 가정은 별도 경고문과 함께 기록한다.

## 6. 재현 계약

문서에는 다음을 정확히 포함한다.

- 요구되는 원천 컬럼
- 코호트 선택 조건과 3,372개 검증
- 이벤트 516개·15.30% 검증
- 기준월별 X와 Y의 시간 경계
- Train 2024-02~2024-09, purge 2024-10~2025-03, Validation 2025-04~2025-06
- 직접신호 3개와 NoDirect 정의
- 고정 Logistic Regression·LightGBM 파라미터
- 관계축 3개와 세그먼트 6개 정의
- 모델별 feature 구성
- 실행 명령, 산출물, 예상 행 수와 성과지표
- 미래값 불변성, one-to-one join, 모델별 동일 평가행 검사

## 7. 결과 표현 원칙

- 성과는 실제 해지 예측이 아니라 지속거래약화 proxy의 탐색 성능으로 표현한다.
- 세그먼트 추가 효과는 `Both`의 PR-AUC 소폭 상승만 강조하지 않고 Top 10% Recall과 사건 Recall 하락을 함께 쓴다.
- Validation을 feature 선택에 사용했으므로 추가 시간 holdout 없이는 일반화 개선을 주장하지 않는다.
- 관계 세그먼트는 예측 성능 향상이 작더라도 CRM 설명·전략 분리용으로 유지할 수 있음을 구분한다.

## 8. 완료 조건

- 첫 독자가 코드 내부를 읽지 않아도 데이터 흐름과 누수 경계를 설명할 수 있다.
- 명령과 파일 경로만으로 label, baseline, 세그먼트 ablation을 순서대로 실행할 수 있다.
- 표에 적힌 표본 수와 성과가 저장된 CSV와 일치한다.
- 승인된 정의와 탐색 구현이 혼동되지 않는다.
- 문서 내 경로와 명령이 현재 브랜치의 실제 파일과 일치한다.
