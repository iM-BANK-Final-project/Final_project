# RM 웹 데이터 통합 설계

## 1. 목적

현재 `src/frontend/rm-insight-copilot`에 구현된 React 프로토타입의 화면 구조와 디자인을 유지하면서, `mockData.js`의 예시 값을 실제 지속거래약화 모델, 관계 세그먼트, 수익성·고객가치, SHAP 결과로 교체한다.

이번 단계는 프론트엔드 재설계가 아니라 데이터 저장·조회 계층과 화면 동작을 연결하는 로컬 시연용 MVP다.

## 2. 범위

### 포함

- SQLite 기반 로컬 서비스 데이터베이스
- 기존 분석 산출물을 검증·결합하여 SQLite에 적재하는 별도 CLI
- FastAPI 조회 API
- React의 mock 데이터 import를 API 조회로 교체
- 검색, 필터, CRM 우선순위 정렬, 추천 화면 이동
- AI 리포트 페이지의 저장 결과 조회
- 로딩, 빈 결과, API 오류 상태
- 최종 Y 계약과 실제 관계 세그먼트에 맞는 화면 용어 교정

### 제외

- 웹 화면에서 모델·세그먼트·수익성 파이프라인 재실행
- 인증과 사용자·RM 권한 관리
- PostgreSQL 또는 외부 DB 서버
- 실시간 LLM 호출
- `전략 보고서 생성` 버튼의 클릭 동작과 생성 API
- 모델 재학습, 하이퍼파라미터 변경, 새로운 성능 주장

`전략 보고서 생성` 버튼은 현재 UI에 그대로 남긴다. 이번 단계에서는 이벤트 핸들러와 API를 연결하지 않는다.

## 3. 변경 제한

다음 프론트엔드 요소를 유지한다.

- `App.jsx`의 페이지 상태 기반 전환 구조
- `TopNav`와 페이지 순서
- Overview, Risk, Priority, Recommendations, AI Report 페이지
- 기존 카드, 표, 차트, 필터, 리포트 레이아웃
- Splash 화면과 브랜드 스타일
- 기존 CSS 디자인과 컴포넌트 구성

필요한 변경은 다음으로 제한한다.

- `mockData.js` import를 API client와 데이터 hook으로 교체
- 하드코딩된 필터 선택지를 API 응답으로 교체
- 검색·필터를 제어 상태로 연결
- `추천 보기`에 선택 고객 전달 동작 추가
- 실제 데이터에 필요한 로딩·빈 결과·오류 표시 추가
- 최종 정의와 충돌하는 화면 문구 교정

대규모 레이아웃 변경, 라우팅 라이브러리 도입, 디자인 시스템 교체는 하지 않는다.

## 4. 기준 용어와 지표

- `금융관계 휴면화 예측`은 `지속거래약화 예측`로 표시한다.
- `휴면위험`은 `지속거래약화 위험`으로 표시한다.
- `기대손실`은 사용하지 않는다.
- CRM 관리 우선순위 점수는 검증된 지속거래약화 위험과 고객가치 대리지표의 결합값이다.
- 이 점수는 실제 손실액이나 예상 손실액이 아니라 RM 운영 순서용 점수다.
- 약화 유형은 `입출금`, `채널`, `카드`, `복합 거래활동`을 기본으로 한다.
- 관계 세그먼트는 `복합고관계`, `균형·중간관계`, `여신중심`, `거래활동중심`, `수신중심`, `저관계`를 사용한다.
- 화면과 API에서 사건·위험을 실제 해지나 확정 휴면으로 표현하지 않는다.

## 5. 전체 아키텍처

```text
기존 분석 산출물
  ├─ 지속거래약화 위험점수
  ├─ 관계 세그먼트·관계축 점수
  ├─ 수익성·고객가치
  ├─ 고객별 SHAP
  └─ 약화 신호
          ↓
별도 DB 적재 CLI
  ├─ 스키마 검증
  ├─ 법인ID+기준년월 키 검증
  ├─ 최신 공통 기준월 결정
  ├─ CRM 우선순위·추천 생성
  └─ 단일 트랜잭션 적재
          ↓
SQLite → FastAPI 조회 API → 현재 React UI
```

웹 요청은 모델을 다시 실행하지 않는다. 분석 재실행과 DB 재적재는 웹 외부의 명시적 CLI 작업으로 분리한다.

## 6. 기준월과 결합 계약

서비스의 기본 `as_of_month`는 위험, 세그먼트, 수익성 결과가 모두 존재하는 가장 최신 공통 기준월이다.

적재 CLI는 다음 조건을 검사한다.

- 각 입력의 `법인ID+기준년월` 중복이 없어야 한다.
- 필수 입력의 기준월 표현을 `YYYY-MM`으로 정규화할 수 있어야 한다.
- 위험·세그먼트·수익성 결과에 공통 기준월이 있어야 한다.
- 고객별 필수 위험점수와 고객가치가 결측이 아니어야 한다.
- 위험점수는 0과 1 사이여야 한다.
- CRM 우선순위 계산에 미래 3개월 평균이나 `future3_to_baseline`을 사용하지 않아야 한다.
- 결합 과정에서 기준 테이블의 고객 행 수가 예기치 않게 증가하지 않아야 한다.

검증 실패 시 기존 SQLite 파일을 부분 갱신하지 않는다. 새 임시 DB를 완성·검증한 뒤 정상 DB로 교체한다.

## 7. SQLite 데이터 모델

### `customers`

고객의 정적·표시 속성을 저장한다.

```text
corporate_id PK
corporate_name nullable
industry
region
customer_grade
dedicated_yn
```

원천에 기업명이 없으면 법인ID를 표시명으로 사용한다. 임의의 기업명을 생성하지 않는다.

### `risk_scores`

```text
corporate_id
as_of_month
model_name
risk_probability
risk_level
PRIMARY KEY (corporate_id, as_of_month, model_name)
```

서비스 기본 모델은 현재 검증된 전체 feature LightGBM 결과로 고정한다. 다른 모델 결과가 함께 존재해도 화면에서 묵시적으로 혼합하지 않는다.

### `segments`

```text
corporate_id
as_of_month
segment_name
activity_score
deposit_score
loan_score
PRIMARY KEY (corporate_id, as_of_month)
```

### `profitability`

```text
corporate_id
as_of_month
profitability_value nullable
defense_value nullable
customer_value_proxy
value_components_json
PRIMARY KEY (corporate_id, as_of_month)
```

`profitability_value`에는 `V_FTP_12M`, `defense_value`에는 `V_FTP_12M_방어가치`를 저장한다. 두 수익성 필드와 `customer_value_proxy`는 구분한다. 실제 수익성 정의가 완성된 경우에만 수익성 값을 표시하며, 고객가치 대리지표를 수익으로 이름 붙이지 않는다.

### `weakening_signals`

```text
corporate_id
as_of_month
signal_type
current_value
comparison_value
change_rate
signal_rank
PRIMARY KEY (corporate_id, as_of_month, signal_type)
```

### `shap_factors`

```text
corporate_id
as_of_month
model_name
feature_name
feature_value
shap_value
abs_shap_rank
PRIMARY KEY (corporate_id, as_of_month, model_name, abs_shap_rank)
```

### `recommendations`

```text
corporate_id
as_of_month
weakening_type
priority_level
reason
contact_strategy
recommended_action
strategy_summary
PRIMARY KEY (corporate_id, as_of_month)
```

추천은 초기 단계에서 rule-based + segment-based 방식으로 생성한다. LLM 생성 결과로 표현하지 않는다.

### `customer_snapshots`

React의 목록 화면이 여러 테이블을 반복 조인하지 않도록 최신 공통 기준월의 표시 필드를 통합한다.

```text
corporate_id
as_of_month
risk_probability
risk_level
customer_value_proxy
profitability_value nullable
defense_value nullable
crm_priority_score
crm_priority_rank
segment_name
weakening_type
industry
region
dedicated_yn
PRIMARY KEY (corporate_id, as_of_month)
```

### `monthly_summaries`

Overview KPI와 월별 추이용 집계를 저장한다.

```text
as_of_month PK
managed_customer_count
average_risk
high_risk_share
priority_value_total
signal_distribution_json
```

### `import_runs`

```text
run_id PK
started_at
completed_at
status
as_of_month
source_manifest_json
row_counts_json
error_message nullable
```

## 8. 우선순위와 추천 규칙

```text
수신점수 = 기준월 수신잔액합계의 cohort 내 percentile rank
여신점수 = 기준월 여신잔액합계의 cohort 내 percentile rank
거래성금액점수 = 기준월 핵심거래활동금액의 cohort 내 percentile rank
상품관계폭점수 = 기준월 상품관계폭의 cohort 내 percentile rank
고객등급점수 = 일반 0.0, 우수 0.5, 최우수 1.0
전담점수 = N 0.0, Y 1.0

customer_value_proxy
= mean(
    수신점수,
    여신점수,
    거래성금액점수,
    상품관계폭점수,
    고객등급점수,
    전담점수
  )

crm_priority_score
= risk_probability × customer_value_proxy
```

금액·상품관계폭 percentile은 pandas `rank(method="average", pct=True)`와 동일하게 계산한다. 여섯 구성요소 중 하나라도 결측이거나 고객등급·전담여부가 허용 범주 밖이면 고객가치와 CRM 우선순위를 계산하지 않고 적재를 실패시킨다. 점수는 최신 공통 기준월 안에서 내림차순 순위를 계산한다. 화면에서 금액 단위를 붙이거나 손실액으로 표시하지 않는다.

FTP 기반 수익성 `V_FTP_12M`과 방어가치 `V_FTP_12M_방어가치`는 `profitability_value`로 별도 저장·표시한다. 이를 고객가치 대리지표의 구성요소로 섞거나 수익성 값을 고객가치로 이름 붙이지 않는다.

약화 원인은 기준월까지의 입출금·채널·카드 신호에서 결정한다.

| 약화 원인 | 추천 방향 |
| --- | --- |
| 입출금 | 자금관리 상담, CMS, 결제성 거래 점검 |
| 채널 | 디지털채널 온보딩, 이용 장애·불편 확인 |
| 카드 | 법인카드 이용조건 점검, 한도·혜택 상담 |
| 복합 거래활동 | RM 직접 접촉, 관계 회복 상담 |

세그먼트는 접촉 문구와 상담 우선 포인트를 보정하지만 위험확률을 임의로 덮어쓰지 않는다.

## 9. FastAPI 경계

FastAPI는 DB 조회와 응답 직렬화만 담당한다. pandas 모델 계산을 API 요청 안에서 실행하지 않는다.

```text
GET /api/health
GET /api/overview?as_of_month=
GET /api/filter-options?as_of_month=
GET /api/customers?search=&segment=&risk_level=&industry=&region=&dedicated=&as_of_month=
GET /api/customers/{corporate_id}?as_of_month=
GET /api/priorities?industry=&region=&dedicated=&weakening_type=&segment=&as_of_month=
GET /api/recommendations?segment=&weakening_type=&as_of_month=
GET /api/reports/{corporate_id}?as_of_month=
```

`GET /api/reports/{corporate_id}`는 저장된 위험, 세그먼트, SHAP, 약화 신호, 추천, 전략 요약을 반환한다. 보고서를 새로 생성하지 않는다.

목록 API는 기본 페이지 크기와 최대 페이지 크기를 둔다. 정렬 가능한 필드는 서버에서 허용 목록으로 제한한다.

## 10. React 연결

### 공통

- 작은 `apiClient` 모듈에서 base URL, JSON 파싱, 오류 변환을 담당한다.
- 페이지별 hook이 로딩·데이터·오류 상태를 관리한다.
- `App.jsx`는 기존 `activePage` 외에 `selectedCustomerId`를 보관한다.
- 별도 라우팅 라이브러리를 도입하지 않는다.

### Overview

- `GET /api/overview`로 KPI, 월별 추이, 주요 약화 신호를 받는다.
- `관리 우선순위`, `약화 신호 보기` 버튼의 기존 페이지 이동을 유지한다.

### 지속거래약화 예측

- `GET /api/customers`를 사용한다.
- 검색, 세그먼트, 위험등급 필터를 실제 쿼리 파라미터로 연결한다.
- 현재 카드와 RiskMeter, SignalBars 레이아웃을 유지한다.

### CRM 우선순위

- `GET /api/priorities`를 사용한다.
- 업종, 지역, 전담여부, 약화유형, 세그먼트 필터를 제공한다.
- `기대손실` 열을 `CRM 우선순위 점수`로 교정한다.
- `추천 보기`는 선택 법인ID를 App에 저장하고 추천 페이지로 이동한다.

### 맞춤 추천

- `GET /api/recommendations`를 사용한다.
- 선택 법인ID가 있으면 해당 카드가 우선 보이도록 한다.
- 기존 추천 카드 레이아웃을 유지한다.

### AI 리포트

- 고객 선택 목록은 실제 고객 데이터로 채운다.
- 고객 선택 시 `GET /api/reports/{corporate_id}`를 호출한다.
- 기존 SHAP 시각화, 전략 요약, waterfall 영역에 저장 결과를 표시한다.
- `전략 보고서 생성` 버튼은 그대로 표시하지만 이번 단계에서 핸들러와 API를 연결하지 않는다.

## 11. 오류와 빈 상태

- API 연결 실패: 페이지 패널 안에 재시도 가능한 오류 메시지를 표시한다.
- DB 미생성: FastAPI health 응답과 화면에서 적재 CLI 실행 필요를 안내한다.
- 필터 결과 0건: 레이아웃을 유지한 채 빈 결과 문구를 표시한다.
- 고객 상세 없음: 404를 반환하고 다른 고객 선택을 안내한다.
- SHAP 없음: 위험 결과는 표시하되 설명값 미생성 상태를 명시한다.
- 수익성 없음: 고객가치와 수익성을 혼동하지 않고 수익성 미산출로 표시한다.
- 일부 입력 적재 실패: 기존 정상 DB를 유지한다.

API 오류 때문에 mock 데이터로 자동 대체하지 않는다. 실제 데이터와 예시 데이터를 섞지 않기 위해서다.

## 12. 보안과 로컬 실행 경계

- 법인ID와 원천 금융 데이터는 외부 서비스로 전송하지 않는다.
- SQLite 파일과 적재 산출물은 Git에 커밋하지 않는다.
- 로컬 FastAPI는 기본적으로 `127.0.0.1`에 바인딩한다.
- React는 환경변수로 API base URL을 받는다.
- CORS는 로컬 Vite origin만 허용한다.

## 13. 테스트 전략

### DB 적재 테스트

- 중복 키 거부
- 기준월 정규화와 최신 공통 기준월 선택
- 기준월 불일치 거부
- 필수 결측 거부
- 위험확률 범위 검증
- CRM 우선순위 계산과 순위 재현
- 실패 시 기존 DB 보존

### API 테스트

- health, overview, 목록, 상세, 우선순위, 추천, 리포트 응답 스키마
- 각 필터 조합과 검색
- 존재하지 않는 고객 404
- 빈 DB와 SHAP·수익성 누락 처리
- 정렬 허용 목록과 페이지 크기 제한

### React 테스트와 검증

- 각 페이지의 loading, success, empty, error 상태
- 검색·필터 쿼리 반영
- 추천 보기 페이지 이동과 고객 선택 전달
- AI 리포트 고객 변경 시 결과 갱신
- `전략 보고서 생성` 버튼이 유지되며 생성 요청을 보내지 않음
- 기존 카피 검증 테스트를 최종 용어로 수정
- 프로덕션 빌드 성공
- 주요 화면 시각 확인으로 기존 레이아웃 보존 검증

## 14. 완료 기준

- SQLite 적재 CLI가 실제 산출물을 검증하고 최신 공통 기준월 스냅샷을 만든다.
- FastAPI가 모든 조회 API를 제공한다.
- React 페이지에서 `mockData.js` 고객·KPI·추천 값을 사용하지 않는다.
- 현재 프론트엔드 구조와 스타일이 유지된다.
- 검색·필터·추천 보기·고객 선택이 실제 데이터로 동작한다.
- AI 리포트 결과 영역은 저장된 실제 결과를 표시한다.
- `전략 보고서 생성` 버튼은 유지되지만 이번 단계에서 생성 기능은 구현하지 않는다.
- 화면 문구가 최종 Y와 CRM 우선순위 계약을 위반하지 않는다.
- API·적재 테스트와 React 프로덕션 빌드가 통과한다.
