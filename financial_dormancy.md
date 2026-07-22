# M12 지속거래약화 예측 및 CRM 운영 설계

> 상태: 최종 Y·모델·FISIM CLV 서비스 계약 확정  
> 기준일: 2026-07-21  
> 최종 근거: `src/models/web_202512_m12_final_model.ipynb`, `src/수익성F(y선정포함).ipynb`

## 1. 목적과 모집단

기업금융 RM이 향후 6개월의 지속거래약화 가능성을 조기에 확인하고, 방어 가능한 경제적 기여가치가 큰 법인을 우선 관리하도록 지원한다.

- 원천 기간: 2023-01~2025-12
- 완전관측 법인: 3,372개, 법인별 36개월
- 운영 기준월: 2025-12
- 서비스 노출: `score_eligible=True`인 3,341개
- 부적격 31개: DB·API·KPI·필터·UI에서 제외하며 Y=0으로 대체하지 않음

## 2. 최종 Y

최종 배포 target은 `Y_INTERVENE_M12_v2`다.

```text
D = 요구불입금금액 + 요구불출금금액
A = 자동이체금액
C = 창구거래금액 + 인터넷뱅킹거래금액 + 스마트뱅킹거래금액
    + 폰뱅킹거래금액 + ATM거래금액
K = 신용카드사용금액 + 체크카드사용금액

ONSET_g   = c+1, c+2, c+3 각 월의 전년동월비 < 0.60
PERSIST_g = mean(c+4:c+6) / mean(c-11:c) < 0.70
W_g       = ONSET_g AND PERSIST_g

Y_INTERVENE_M12_v2 = W_D AND (W_A OR W_C OR W_K)
```

ONSET 전년동월 분모 또는 PERSIST 과거 12개월 평균이 0이면 그 축은 판정 불가능하다. 전체 target은 D가 판정 가능하고 A/C/K 중 하나 이상이 판정 가능할 때만 적격이다.

롤링 target lock은 전체 64,068행, 적격 63,572행, 양성 1,966행, 적격 법인 3,354개, 양성 법인 639개다.

과거 `Y_지속거래약화_3M70`은 Y 탐색 근거로 보존하는 사후 first-event 라벨이다. 현재 운영 target이 아니며 그 기반의 과거 모델 성능도 현재 모델 성능으로 제시하지 않는다.

## 3. 최종 모델

- Feature set: `FS2_R1_DACK_DYNAMIC`, 56개
- Model: LightGBM
- Calibration: grouped out-of-fold Isotonic regression
- 학습행: 43,499개
- 최종 test: 2025-06, 3,346행, 양성 119행
- 운영 점수: 원본 웹 model artifact 부재로 사용자 승인 후 최종 수익성 노트북에서 재학습
- 서비스 점수: `src/models/web_m12_intervene_v2_scores_202512_eligible_3341.csv`, 적격 3,341개
- 로컬 설명: 고객별 절대 기여도 기준 `SHAP Top 10`, DB 총 33,410행

업종과 세그먼트 식별자는 모델 입력이 아니라 설명 및 안정성 점검용이다. `risk_probability`는 향후 6개월 `Y_INTERVENE_M12_v2` 발생 확률이며 해지·부도·확정 휴면 확률이 아니다.

## 4. FISIM

```text
L  = 여신_운전자금대출잔액 + 여신_시설자금대출잔액
DS = 거치식예금잔액 + 적립식예금잔액
DR = 요구불예금잔액

V_FTP(i,m) = L  × (기업대출금리_m - FTP_m)
           + DS × (FTP_m - 저축성수신금리_m)
           + DR × (FTP_m - 0.0001)
```

- 은행 월별 금리는 백분율이므로 100으로 한 번 나눈다.
- FTP는 이미 월별 decimal이므로 다시 변환하지 않는다.
- 월말 잔액을 직접 사용하고 월평잔·일수 연환산을 사용하지 않는다.
- 역마진 진단을 위해 음수 FISIM을 보존한다.
- D/A/C/K 활동, 업종, 세그먼트는 직접 FISIM 입력이 아니다.

## 5. CLV와 방어순위

2025-12 기준 가치 기초는 최근 실제 6개월인 2025-07~2025-12 월별 FISIM 합계다. 미래 잔액·2026년 수익성과 생존확률은 예측하지 않는다.

```text
CLV_NoRisk = Σ actual_FISIM_m, m=2025-07..2025-12
CLV_Risk = CLV_NoRisk / (1+p)
PotentialLoss = CLV_NoRisk - CLV_Risk
defense_value = max(PotentialLoss, 0)
```

`defense_value > 0`인 고객만 방어순위를 갖는다. 정렬은 `defense_value desc`, `risk_probability desc`, `CLV_NoRisk desc`, `corporate_id asc` 순서다.

DB에는 `CLV_NoRisk`, `CLV_Risk`, `PotentialLoss`, `defense_value`, nullable `defense_rank`를 저장한다. UI 고객가치 영역에는 `CLV_Risk`와 `PotentialLoss`만 표시하며 `CLV_NoRisk`는 표시하지 않는다. `PotentialLoss`는 확정 회계손실이 아니다.

과거 고객가치 대리점수와 `risk_probability × customer_value_proxy` 우선순위는 폐기했다.

## 6. 서비스 계약

```text
최종 점수 CSV
→ score_eligible=True 3,341개 검증
→ 월별 FISIM 및 최근 실제 6개월 위험조정 CLV 계산
→ 고객·위험·CLV·신호·세그먼트·SHAP·추천 테이블 생성
→ 임시 SQLite 검증 후 원자적 교체
→ FastAPI 조회
→ React 화면
```

API 고객 응답은 `clvRisk`, `potentialLoss`, `defenseRank`를 제공한다. 우선순위 기본 정렬은 `defenseRank`이며 null 순위는 양수 방어대상 뒤에 둔다. Overview는 양수 잠재손실 합계인 `potentialLossTotal`을 반환한다.

필터는 업종, 지역, 전담여부, 약화유형, 세그먼트를 유지한다. UI에는 다음 해석 문구를 표시한다.

> 최근 6개월 실제 FISIM을 위험확률로 조정한 경제적 기여가치 추정치이며 확정 회계손실이 아닙니다.

### Gemini AI 보고서·PDF

`POST /api/reports/{corporate_id}/generate`는 적격 3,341개 고객의 사전 계산 위험, `CLV_Risk`, `PotentialLoss`, D/A/C/K, `SHAP Top 10`, 추천 근거를 `GEMINI_API_KEY` 또는 Vertex AI로 전달해 6개 서술 섹션을 생성한다. 수치와 SHAP은 백엔드가 그대로 결합하며 Gemini가 재생성하지 않는다.

`POST /api/reports/{corporate_id}/pdf`는 현재 화면의 보고서를 DB 근거와 대조한 후 `RM_REPORT_FONT_PATH` 또는 OS 한국어 폰트를 포함한 A4 PDF로 반환한다. AI 보고서와 PDF는 DB에 저장하지 않는다.

## 7. 데이터·누수·표현 원칙

- 법인-월 중복, 36개월 연속성, 필수 잔액의 결측·음수를 실패 처리한다.
- target 미래창은 feature에 사용하지 않는다.
- 웹 요청 중 모델·CLV·SHAP은 재실행하지 않고 사전 계산 결과만 조회한다. LLM은 명시적 보고서 생성 요청에서만 실행한다.
- “향후 6개월 지속거래약화 가능성”, “조기관리 필요”, “추천 접촉 전략”을 사용한다.
- “실제 해지”, “확정 휴면”, “부도 위험”, “확정 회계손실”로 표현하지 않는다.
