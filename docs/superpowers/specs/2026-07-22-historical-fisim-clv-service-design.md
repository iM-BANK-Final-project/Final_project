# 최근 6개월 실제 FISIM 기반 CLV 교체 설계

## 목표와 고정 조건

- 운영 모집단은 `score_eligible=True`인 기존 3,341개 법인으로 고정한다.
- 모델, SHAP, 2025-12 `risk_probability`는 변경하지 않는다.
- CLV와 방어순위 산식만 최신 `수익성F(y선정포함).ipynb`의 실제 수익성 방식으로 교체한다.

## 수익성 기간과 산식

기준월 `c`를 포함한 최근 실제 6개월 `c-5~c`의 월별 FISIM을 합산한다. 운영 기준월이 2025-12이므로 실제 적용 기간은 2025-07~2025-12다.

```text
P_actual = sum(actual_FISIM_m for m=c-5..c)
CLV_NoRisk = P_actual
CLV_Risk = P_actual / (1 + risk_probability)
PotentialLoss = CLV_NoRisk - CLV_Risk
defense_value = max(PotentialLoss, 0)
```

기존의 전년 동월 잔액 기반 미래 6개월 예측과 `S(h)=(1-p)^(h/6)` 생존확률 가중은 제거한다. 음수 FISIM과 음수 `PotentialLoss`는 진단을 위해 보존하되 `defense_value`는 0으로 제한한다. 양수 `defense_value`만 순위를 부여하고 동률 해소 순서는 기존처럼 `defense_value`, `risk_probability`, `CLV_NoRisk` 내림차순, 법인ID 오름차순이다.

## 데이터 계약

- 적격 3,341개 각각에 최근 실제 6개월 자료가 정확히 존재해야 하며 누락·중복 시 서비스 DB 준비를 실패시킨다.
- API 필드 `clvRisk`, `potentialLoss`, `defenseRank`와 DB 수치 컬럼은 유지한다.
- 내부 검증 컬럼 `예측월수`는 실제 의미에 맞게 `수익성월수`로 변경한다.
- 웹 요청 시 재계산하지 않고 준비 단계에서 산출한 값을 조회한다.

## 표현 계약

위험확률은 향후 6개월 지속거래약화 가능성이지만 가치의 기초는 최근 실제 6개월이다. UI와 문서에는 다음 문구를 사용한다.

> 최근 6개월 실제 FISIM을 위험확률로 조정한 경제적 기여가치 추정치이며 확정 회계손실이 아닙니다.

AI 보고서와 PDF도 `CLV_Risk`와 `PotentialLoss`를 미래 확정 수익·손실로 표현하지 않고 최근 실제 6개월 FISIM의 위험조정 값으로 설명한다.

## 검증

- 단위 테스트에서 `CLV_Risk=P_actual/(1+p)`와 생존확률 미사용을 수치로 확인한다.
- 최근 6개월 누락, 확률 범위 위반, 음수 FISIM, 순위 동률을 검증한다.
- 서비스 준비 테스트에서 모집단 및 `risk_probability` 보존을 확인한다.
- 프론트엔드 테스트에서 새 안내 문구를 확인한다.
- 실제 운영 자료로 결과 행 수 3,341개, 기준월 2025-12, 기간 2025-07~12를 확인한다.
