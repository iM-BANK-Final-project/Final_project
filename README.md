# iM Bank RM Copilot

기업금융 RM이 **향후 6개월 지속거래약화 가능성**을 조기에 확인하고, FISIM 기반 경제적 기여가치를 반영해 고객 방어순위와 접촉 전략을 결정하도록 돕는 로컬 웹 서비스입니다.

> 위험 고객을 탐지하고 → 경제적 가치로 우선순위를 정하고 → 세그먼트별 접촉 전략과 AI 보고서까지 연결합니다.

## 핵심 기능

| 기능 | 제공 내용 |
| --- | --- |
| 지속거래약화 예측 | 164피처 LightGBM·Platt 보정 점수로 향후 6개월 `Y_INTERVENE_M12_v2` 발생 가능성을 표시 |
| 방어 우선순위 | 최근 6개월 실제 FISIM 기반 `PotentialLoss`로 관리 우선순위를 산정 |
| 맞춤 추천 | 세그먼트와 약화유형에 따라 RM 접촉·상품 검토 방향을 제안 |
| AI 전략 보고서 | 저장된 위험·CLV·SHAP·추천 근거만 Gemini에 전달해 6개 고정 섹션의 보고서와 A4 PDF 생성 |

## 서비스 흐름

```text
36개월 완전관측 3,372개 법인
→ Y_INTERVENE_M12_v2 164피처 LightGBM·Platt 점수
→ score_eligible=True 3,341개만 서비스 노출
→ FISIM 기반 CLV_Risk·PotentialLoss
→ 방어순위
→ 세그먼트 기반 맞춤 추천
→ 저장 SHAP 기반 Gemini AI 전략 보고서·PDF
```

## 빠른 실행

### 1. 사전 요구사항

- Python 3.10 이상 및 Conda 환경 `final`
- Node.js 18 이상
- 프로젝트 루트의 원천·금리 파일과 `src/models/`의 최종 점수·추세 CSV

처음 한 번만 Node 의존성을 설치합니다.

```bash
npm install
npm --prefix src/frontend/rm-insight-copilot install
```

### 2. 서비스 SQLite DB 준비

최종 점수와 원천·금리 파일을 검증한 뒤, CLV를 계산하고 SQLite DB를 원자적으로 재생성합니다.

```bash
cd /Users/gggyyu/Final_project
conda run -n final python -m src.backend.prepare_service_database
```

정상 완료 시 주요 생성물은 다음과 같습니다.

```text
outputs/rm_service_inputs/clv_202512.csv
outputs/rm_service/rm_service.sqlite
```

### 3. 백엔드와 프론트엔드 실행

아래처럼 터미널 두 개에서 실행하는 방식을 권장합니다.

```bash
# Terminal 1 — FastAPI
cd /Users/gggyyu/Final_project
conda run -n final uvicorn src.backend.app:app --host 127.0.0.1 --port 8000 --reload
```

```bash
# Terminal 2 — React/Vite
cd /Users/gggyyu/Final_project
npm --prefix src/frontend/rm-insight-copilot run dev
```

- 프론트엔드: `http://127.0.0.1:5173`
- 백엔드: `http://127.0.0.1:8000`
- 상태 점검: `http://127.0.0.1:8000/api/health`

`conda activate final`로 환경을 활성화한 상태라면, 루트에서 `npm run dev`로 두 서버를 함께 실행할 수도 있습니다.

## 운영 기준

### 서비스 대상과 예측모델

| 항목 | 최종 운영 기준 |
| --- | --- |
| 운영 target | `Y_INTERVENE_M12_v2` |
| 모델 | `FS_FINAL_164_TUNED` LightGBM |
| 보정 | validation에서 고정한 Platt calibration |
| 기준월 | 2025-12 |
| 운영 임계값 | `0.26479401324821045` |
| 서비스 대상 | `score_eligible=True`인 3,341개 법인 |
| 미노출 대상 | 부적격 31개 법인 — DB·API·KPI·화면에서 모두 제외 |
| 위험구간 | 상위 1%, 상위 1~3%, 상위 3~5%, 상위 5~10%, 나머지 90% |

`risk_probability`는 향후 6개월 지속거래약화 target 발생 가능성이며, 실제 해지·부도·폐업·확정 휴면 확률이 아닙니다.

운영 target은 다음 조건으로 정의합니다.

```text
D = 요구불입금금액 + 요구불출금금액
A = 자동이체금액
C = 창구 + 인터넷뱅킹 + 스마트뱅킹 + 폰뱅킹 + ATM 거래금액
K = 신용카드사용금액 + 체크카드사용금액

ONSET_g   = c+1~c+3 각 월의 전년동월비 < 0.60
PERSIST_g = mean(c+4:c+6) / mean(c-11:c) < 0.70
W_g       = ONSET_g AND PERSIST_g

Y_INTERVENE_M12_v2 = W_D AND (W_A OR W_C OR W_K)
```

### FISIM 기반 CLV와 방어순위

FISIM은 월말 잔액과 월별 금리로 계산합니다.

```text
V_FTP = 대출잔액 × (기업대출금리 - FTP)
      + 저축성수신잔액 × (FTP - 저축성수신금리)
      + 요구불잔액 × (FTP - 0.0001)

CLV_NoRisk   = Σ actual_FISIM_m, m=c-5..c
CLV_Risk     = CLV_NoRisk / (1 + risk_probability)
PotentialLoss = CLV_NoRisk - CLV_Risk
defense_value = max(PotentialLoss, 0)
```

- 2025-12 운영 기준 최근 실제 6개월은 2025-07~12입니다.
- 화면에는 `CLV_Risk`, `PotentialLoss`, `defenseRank`를 표시합니다.
- `PotentialLoss`는 최근 실제 FISIM 기반 위험조정 경제적 기여가치 차이이며, 확정 회계손실이 아닙니다.
- 양수 `defense_value`만 방어순위를 부여합니다.

## 화면과 API

| 화면 | 주요 API | RM 활용 목적 |
| --- | --- | --- |
| Overview | `GET /api/overview` | 관리 고객 규모, 평균 위험, 모델 임계값 이상 비중, 잠재손실 합계 확인 |
| 거래약화 위험 | `GET /api/customers` | 고객 검색·필터 및 위험구간·약화신호 조회 |
| CRM 우선순위 | `GET /api/priorities` | FISIM 기반 방어순위로 관리 순서 결정 |
| 맞춤 추천 | `GET /api/recommendations` | 세그먼트·약화유형별 추천 접촉 전략 확인 |
| AI 리포트 | `GET /api/reports/{corporate_id}` | 저장된 위험·CLV·SHAP·추천 근거 확인 |

필터는 업종, 지역, 전담여부, 약화유형, 세그먼트를 지원합니다. 고객 응답은 위험구간, 위험순위, 임계값 충족 여부, `CLV_Risk`, `PotentialLoss`, 방어순위를 포함합니다.

## Gemini AI 전략 보고서와 PDF

AI 보고서는 정량 결과를 새로 계산하거나 생성하지 않습니다. 저장된 고객 근거만 사용해 RM이 읽기 쉬운 전략 문장으로 변환합니다.

```text
저장 위험·CLV_Risk·PotentialLoss·D/A/C/K 신호·SHAP Top 10·추천
→ POST /api/reports/{corporate_id}/generate
→ Gemini 6개 고정 섹션 생성
→ POST /api/reports/{corporate_id}/pdf
→ DB 근거 재대조 후 A4 한국어 PDF를 메모리에서 생성
```

생성되는 섹션은 다음과 같습니다.

1. 종합 위험 요약
2. 고객가치 및 잠재손실 해석
3. 주요 약화 원인
4. RM 접촉 전략
5. 실행 권고사항
6. 분석 유의사항

Gemini 기능을 사용하려면 백엔드 실행 환경에 키를 설정합니다. `RM_REPORT_FONT_PATH`는 선택 사항이며, 설정하지 않으면 지원 OS의 한국어 폰트를 탐색합니다.

```bash
export GEMINI_API_KEY="your-key"
export RM_REPORT_FONT_PATH="/path/to/korean-font.ttf"  # 선택 사항
conda run -n final uvicorn src.backend.app:app --host 127.0.0.1 --port 8000
```

API Key는 프론트엔드에 노출하지 않으며, 생성된 AI 보고서와 PDF는 DB에 저장하지 않습니다. SHAP은 모델 예측의 로컬 기여도이지 인과관계나 확률 변화량이 아닙니다.

## 검증과 테스트

```bash
# 백엔드·서비스 계약 테스트
conda run -n final pytest

# 프론트엔드 테스트
npm --prefix src/frontend/rm-insight-copilot test

# 프론트엔드 프로덕션 빌드
npm --prefix src/frontend/rm-insight-copilot run build
```

## 프로젝트 구조

```text
src/backend/                         FastAPI, SQLite, FISIM/CLV, AI 보고서·PDF
src/frontend/rm-insight-copilot/     React/Vite 사용자 화면
src/models/                          최종 점수 생성 코드, 운영 점수·추세 산출물
tests/                               서비스·모델 계약 테스트
outputs/                             서비스 DB와 CLV 파생 산출물
docs/superpowers/specs/              서비스 통합 설계 문서
```

## 기준 문서와 산출물

현재 운영 정의는 아래 순서로 판단합니다.

1. `src/models/web_service_m12_final_scoring.py`
2. `src/models/web_m12_final_scores_202512_all_3372.csv`
3. `src/models/web_m12_final_risk_trend_202507_202512.csv`
4. `src/수익성F(y선정포함).ipynb`
5. `docs/superpowers/specs/2026-07-23-final-164-model-service-integration-design.md`
6. `financial_dormancy.md`
7. `src/models/model.md`

`y_setting_pipeline.md`와 2026-07-13 이전 설계·코드는 과거 Y 탐색 이력이며, 현재 배포 운영 정의로 사용하지 않습니다.
