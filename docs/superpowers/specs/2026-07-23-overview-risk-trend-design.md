# Overview 최근 6개월 위험 추세 설계

## 목표

Overview의 단일 막대 `월별 지속거래약화 위험` 영역을 2025-07~2025-12의 실제 월말 점수 추세로 교체한다. 서비스의 현재 기준월은 계속 2025-12이며, 기존 3,341개 운영 고객·2025-12 위험확률·CLV·SHAP은 변경하지 않는다.

## 월별 점수 계약

- 2025-07~2025-12 각 월말에 `FS2_R1_DACK_DYNAMIC` 56개 피처를 기준월까지의 데이터로 만든다.
- 최종 2025-12 운영 점수에 사용한 LightGBM 모델과 grouped OOF Isotonic 보정기를 모든 월에 고정 적용한다. 월별 재학습·재보정은 하지 않는다.
- 각 월은 해당 월의 D/A/C/K 판정 가능 조건으로 `score_eligible`을 독립 판정한다. 부적격 고객을 0점으로 포함하지 않는다.
- 모델 피처는 해당 기준월까지만 사용하며 미래 target 관찰창을 피처 또는 집계에 사용하지 않는다.
- `risk_probability`는 각 월말에서 본 향후 6개월 지속거래약화 가능성이다. 실제 해지·부도·휴면 확률로 해석하지 않는다.
- 2025-12 월별 집계는 기존 운영 점수 CSV의 3,341개 및 위험확률과 허용오차 `1e-12` 이내로 일치해야 한다.

월별 사전 산출 CSV는 다음 필드를 가진다.

```text
as_of_month          YYYY-MM
eligible_count       해당 월 score_eligible=True 법인 수
average_risk         적격 법인의 risk_probability 평균, decimal
high_risk_count      risk_probability >= 0.75 법인 수
high_risk_share      high_risk_count / eligible_count, decimal
model_name           FS2_R1_DACK_DYNAMIC_LIGHTGBM_ISOTONIC
```

파일은 `src/models/web_m12_overview_risk_trend_202507_202512.csv`로 저장한다. 정확히 6행, 월 중복 없음, 확률·비중 0~1, 건수 비음수, `high_risk_count <= eligible_count`를 만족해야 한다.

## 서비스 데이터 구조

기존 `monthly_summaries`는 2025-12 상세 화면의 CLV 합계와 신호 분포를 보존한다. 과거 월의 존재하지 않는 CLV·신호 값을 채우지 않는다.

추세 전용 테이블을 추가한다.

```text
risk_trends
- as_of_month TEXT PRIMARY KEY
- eligible_count INTEGER NOT NULL
- average_risk REAL NOT NULL CHECK 0<=value<=1
- high_risk_count INTEGER NOT NULL
- high_risk_share REAL NOT NULL CHECK 0<=value<=1
- model_name TEXT NOT NULL
```

서비스 준비 단계가 월별 CSV를 검증하고 임시 SQLite에 적재한다. 6개 월 중 하나라도 누락되거나 2025-12 운영 점수와 불일치하면 기존 SQLite를 교체하지 않는다. 웹 요청에서는 점수를 재계산하지 않는다.

`GET /api/overview`의 현재 KPI와 `signalSummary`는 기존 2025-12 값을 유지한다. `monthlyTrend`는 `risk_trends`에서 기준월 이하 최근 6개 월을 오름차순으로 반환한다.

```json
{
  "month": "2025-12",
  "risk": 12.3,
  "highRiskShare": 8.4,
  "highRiskCount": 281,
  "eligibleCount": 3341,
  "isCurrent": true
}
```

API의 퍼센트 값은 기존 프론트 계약에 맞춰 0~100으로 반환한다. `isCurrent`는 요청 기준월과 같은 행에만 `true`다.

## UI 설계

패널 제목은 `최근 6개월 지속거래약화 위험 추세`, 설명은 `동일 모델 기준 월말 평균 위험과 고위험 고객 비중입니다.`로 변경한다.

- X축: 7월~12월
- 평균 위험: 민트색 선과 원형 점
- 고위험 고객 비중: 선 뒤의 연한 라임 세로 막대
- 12월: 진한 외곽선, `현재 기준` 라벨
- 각 월: 평균 위험은 선의 점 위에 소수점 한 자리로 직접 표시하고, 평균 위험·고위험 비중·고위험 고객 수·적격 고객 수 전체는 hover/focus 툴팁으로 제공
- 범례: `평균 위험`, `고위험 비중`
- 6개 월이 없으면 빈 값을 보간하거나 복제하지 않고 `최근 6개월 추세 데이터가 준비되지 않았습니다.` 상태를 표시한다.

그래프는 별도 `OverviewRiskTrendChart` 컴포넌트로 분리한다. SVG를 사용해 선·점과 키보드 포커스 가능한 데이터 포인트를 만들고, CSS 막대로 보조 계열을 표현한다. 작은 화면에서는 월별 수치 라벨을 줄이고 툴팁을 유지한다.

## 검증

- 모델/노트북 계약: 6개월, 동일 모델·보정기, 월별 적격 필터, 2025-12 점수 일치를 검증한다.
- 서비스 준비: 정상 6행 적재, 월 누락·중복·범위 위반·12월 불일치 시 원자적 실패를 검증한다.
- 저장소/API: 최근 6개월 정렬, 0~100 변환, `isCurrent` 한 건, 요청 기준월 처리를 검증한다.
- 프론트: 6개 막대·선·범례·12월 강조·소수점 한 자리·키보드 접근성을 검증한다.
- 회귀: Overview의 기존 KPI, 관리 포커스, 주요 약화 신호 및 다른 4개 페이지 계약은 변경하지 않는다.
