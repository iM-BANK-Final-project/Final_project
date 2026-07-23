# Corporate RM M12 Intervention Service

기업금융 RM이 향후 6개월의 지속거래약화 위험을 확인하고, FISIM 기반 잠재 손실에 따라 방어 대상을 정하도록 지원하는 프로젝트입니다.

현재 운영 계약의 최종 근거는 다음 두 노트북입니다.

- `src/models/web_202512_m12_final_model.ipynb`: 최종 모델과 2025-12 운영 점수
- `src/수익성F(y선정포함).ipynb`: 최종 Y, FISIM, CLV 및 방어순위

구현 상세는 `financial_dormancy.md`와 `docs/superpowers/specs/2026-07-21-m12-model-clv-service-integration-design.md`에 기록합니다.

## Final Operating Target

운영 모델의 Y는 `Y_INTERVENE_M12_v2`입니다. 기준월 `c`에서 활동축은 다음과 같습니다.

```text
D = 요구불입금금액 + 요구불출금금액
A = 자동이체금액
C = 창구 + 인터넷뱅킹 + 스마트뱅킹 + 폰뱅킹 + ATM 거래금액
K = 신용카드사용금액 + 체크카드사용금액

ONSET_g   = c+1~c+3의 각 전년동월비가 모두 0.60 미만
PERSIST_g = mean(c+4:c+6) / mean(c-11:c) < 0.70
W_g       = ONSET_g AND PERSIST_g

Y_INTERVENE_M12_v2 = W_D AND (W_A OR W_C OR W_K)
```

D가 판정 가능하고 A/C/K 중 하나 이상이 판정 가능할 때만 `score_eligible=True`입니다. 운영 기준월 `2025-12`의 3,372개 법인 중 적격 3,341개만 DB·API·화면·KPI에 노출하며, 부적격 31개를 음성으로 대체하지 않습니다.

`Y_지속거래약화_3M70`은 최종 Y 탐색 과정의 과거 사후 이벤트 라벨입니다. 현재 배포 모델의 target이나 성능으로 사용하지 않습니다.

## Final Model

- Feature set: `FS2_R1_DACK_DYNAMIC`, 56개
- Model: LightGBM
- Calibration: grouped out-of-fold 예측으로 적합한 Isotonic regression
- Final test cutoff: `2025-06` (3,346행, 양성 119행)
- Operating cutoff: `2025-12`
- 점수 의미: 향후 6개월 `Y_INTERVENE_M12_v2` 발생 확률

점수는 실제 해지·부도·확정 휴면 확률이 아닙니다. 서비스 입력은 재학습 승인 모델로 생성한 `src/models/web_m12_intervene_v2_scores_202512_eligible_3341.csv`이며, 적격 3,341개만 포함합니다. 고객별 설명은 절대 기여도 기준 `SHAP Top 10`을 저장합니다.

## FISIM CLV Priority

월말 잔액과 월별 금리를 사용해 다음 FISIM 기여를 계산합니다.

```text
V_FTP = 대출잔액 × (기업대출금리 - FTP)
      + 저축성수신잔액 × (FTP - 저축성수신금리)
      + 요구불잔액 × (FTP - 0.0001)
```

은행 금리는 `% / 100`, FTP는 이미 decimal이므로 재변환하지 않습니다. 월평잔과 일수 연환산은 사용하지 않습니다. CLV의 가치 기초는 2025-12 기준 최근 실제 6개월(2025-07~12) 월별 FISIM 합계입니다.

```text
CLV_NoRisk = Σ(actual_FISIM_m), m=2025-07..2025-12
CLV_Risk = CLV_NoRisk / (1+p)
PotentialLoss = CLV_NoRisk - CLV_Risk
defense_value = max(PotentialLoss, 0)
```

화면에는 `CLV_Risk`, `PotentialLoss`, `방어순위`만 표시합니다. `CLV_NoRisk`는 감사·재현을 위해 DB에만 저장합니다. `PotentialLoss`는 최근 6개월 실제 FISIM 기반 위험조정 경제적 기여가치 차이이며 확정 회계손실이 아닙니다.

## Run the Service

저장된 최종 점수와 원천·금리 CSV로 CLV를 계산하고 SQLite를 원자적으로 재생성합니다. 노트북이나 모델을 웹 요청 중 실행하지 않습니다.

먼저 백엔드 의존성이 설치된 Python 환경을 활성화합니다. 프로젝트를 처음 받은 경우 루트와 프론트엔드의 Node 의존성을 각각 한 번 설치합니다.

```bash
npm install
npm --prefix src/frontend/rm-insight-copilot install
```

최초 실행 또는 입력 데이터 변경 시 서비스 DB를 준비합니다.

```bash
python -m src.backend.prepare_service_database
```

이후 프로젝트 루트에서 백엔드와 프론트엔드를 함께 실행합니다.

```bash
npm run dev
```

백엔드는 `http://127.0.0.1:8000`, 프론트엔드는 `http://127.0.0.1:5173`에서 실행됩니다. `Ctrl+C`를 누르거나 한 프로세스가 종료되면 나머지 프로세스도 함께 종료됩니다.

기본 생성물:

```text
outputs/rm_service_inputs/clv_202512.csv
outputs/rm_service/rm_service.sqlite
```

## Service Flow

```text
36개월 원천 패널
→ Y_INTERVENE_M12_v2 최종 LightGBM·Isotonic 점수
→ score_eligible 적격 3,341개 필터
→ FISIM 기반 CLV_Risk·PotentialLoss
→ 방어순위 및 세그먼트 추천
→ 저장 SHAP 기반 AI 전략 보고서
```

## Gemini AI Report and PDF

AI 리포트의 `전략 보고서 생성`은 `POST /api/reports/{corporate_id}/generate`를 호출한다. 백엔드는 저장된 위험, `CLV_Risk`, `PotentialLoss`, D/A/C/K 변화율, `SHAP Top 10`, 추천 결과만 Gemini에 전달하고 6개 고정 섹션을 구조화해 반환한다. 정량 수치와 SHAP은 Gemini가 재생성하지 않는다.

```bash
GEMINI_API_KEY=<your-key> \
RM_REPORT_FONT_PATH=/path/to/korean-font.ttf \
RM_SERVICE_DB_PATH=outputs/rm_service/rm_service.sqlite \
  conda run -n final uvicorn src.backend.app:app --host 127.0.0.1 --port 8000
```

`PDF 다운로드`는 화면의 구조화 보고서를 `POST /api/reports/{corporate_id}/pdf`로 보내고, 백엔드가 DB 근거와 다시 대조한 뒤 한국어 A4 PDF를 메모리에서 생성한다. AI 보고서와 PDF는 DB에 저장하지 않는다. `RM_REPORT_FONT_PATH`가 없으면 macOS AppleGothic/NotoSansGothic 또는 Linux Noto/Nanum 폰트를 순서대로 탐색한다. 자동화 테스트는 Gemini를 대체해 외부 비용을 발생시키지 않는다.

## Main Artifacts

- 운영 설계: `financial_dormancy.md`
- 최종 Y 탐색 이력: `y_setting_pipeline.md`
- 모델 정의: `src/models/model.md`
- 서비스 통합 설계: `docs/superpowers/specs/2026-07-21-m12-model-clv-service-integration-design.md`
- 서비스 준비: `src/backend/prepare_service_database.py`
- FISIM/CLV 구현: `src/backend/m12_clv.py`

## Project Layout

```text
src/backend/                         현재 FastAPI·SQLite·CLV·AI 보고서 코드
src/frontend/rm-insight-copilot/     현재 React 서비스
src/models/                          최종 웹 모델 노트북·운영 산출물 계약
tests/                               현재 서비스와 최종 모델 계약 테스트
outputs/                             현재 서비스 입력·DB·최종 모델 재현 산출물
```

기본 `pytest`는 활성 `tests/`만 수집하며, 현재 구현은 `AGENTS.md`의 source-of-truth 순서를 따른다.
