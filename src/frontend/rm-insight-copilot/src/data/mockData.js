export const monthlyTrend = [
  { month: "2025.01", risk: 28, managed: 92 },
  { month: "2025.02", risk: 31, managed: 104 },
  { month: "2025.03", risk: 34, managed: 118 },
  { month: "2025.04", risk: 37, managed: 133 },
  { month: "2025.05", risk: 35, managed: 126 },
  { month: "2025.06", risk: 42, managed: 151 },
  { month: "2025.07", risk: 45, managed: 168 },
  { month: "2025.08", risk: 49, managed: 184 },
  { month: "2025.09", risk: 52, managed: 196 }
];

export const signalSummary = [
  { label: "상품관계폭 축소", value: 31, tone: "mint" },
  { label: "외환거래 감소", value: 24, tone: "blue" },
  { label: "예금잔액 약화", value: 19, tone: "amber" },
  { label: "카드사용 축소", value: 14, tone: "coral" },
  { label: "채널거래 감소", value: 12, tone: "gray" }
];

export const customers = [
  {
    id: "CORP-AG534",
    name: "알파코",
    industry: "교육 및 서비스",
    region: "대구",
    dedicated: "Y",
    segment: "고가치 성장형",
    risk: 82,
    health: 18,
    valueProxy: 514,
    expectedLoss: 42153,
    weakeningType: "상품관계폭 축소",
    contact: "RM 방문",
    action: "관계 회복 상담 및 교차판매 후보 점검",
    summary: "최근 3개월 상품관계폭과 채널거래가 이전 6개월 대비 약화되었습니다.",
    signals: [
      { label: "상품관계폭", change: -38, recent: 3.1, previous: 5.0 },
      { label: "채널거래금액", change: -24, recent: 68, previous: 89 },
      { label: "외환거래금액", change: -8, recent: 42, previous: 46 }
    ]
  },
  {
    id: "CORP-DK118",
    name: "대경에듀",
    industry: "교육 및 서비스",
    region: "대구",
    dedicated: "Y",
    segment: "지역 핵심거래형",
    risk: 76,
    health: 24,
    valueProxy: 438,
    expectedLoss: 33288,
    weakeningType: "외환거래 감소",
    contact: "전담 RM 전화 후 방문",
    action: "환율 우대와 수출입 금융 상담",
    summary: "외환거래금액이 과거 기준 대비 빠르게 줄고 있습니다.",
    signals: [
      { label: "외환거래금액", change: -44, recent: 28, previous: 50 },
      { label: "거래건수", change: -21, recent: 71, previous: 90 },
      { label: "예금잔액", change: -11, recent: 302, previous: 340 }
    ]
  },
  {
    id: "CORP-MT902",
    name: "민트테크",
    industry: "제조",
    region: "경기",
    dedicated: "N",
    segment: "디지털 거래형",
    risk: 68,
    health: 32,
    valueProxy: 386,
    expectedLoss: 26248,
    weakeningType: "카드/채널 약화",
    contact: "디지털 캠페인 후 RM 콜",
    action: "법인카드, CMS, 디지털채널 온보딩",
    summary: "카드사용금액과 비대면 채널거래가 동시에 감소했습니다.",
    signals: [
      { label: "카드사용금액", change: -33, recent: 41, previous: 61 },
      { label: "채널거래금액", change: -29, recent: 58, previous: 82 },
      { label: "상품관계폭", change: -12, recent: 4.4, previous: 5.0 }
    ]
  },
  {
    id: "CORP-LN443",
    name: "라임물산",
    industry: "도소매",
    region: "서울",
    dedicated: "Y",
    segment: "여신 의존형",
    risk: 63,
    health: 37,
    valueProxy: 472,
    expectedLoss: 29736,
    weakeningType: "여신 의존 + 활동 약화",
    contact: "금리 리뷰 미팅",
    action: "운전자금대출 조건 점검 및 한도 상담",
    summary: "여신잔액 규모는 크지만 거래성 활동이 둔화되고 있습니다.",
    signals: [
      { label: "거래건수", change: -27, recent: 66, previous: 91 },
      { label: "채널거래금액", change: -19, recent: 120, previous: 148 },
      { label: "여신잔액", change: 3, recent: 920, previous: 894 }
    ]
  },
  {
    id: "CORP-SV381",
    name: "세움서비스",
    industry: "교육 및 서비스",
    region: "대구",
    dedicated: "Y",
    segment: "예금 중심형",
    risk: 59,
    health: 41,
    valueProxy: 355,
    expectedLoss: 20945,
    weakeningType: "예금잔액 약화",
    contact: "자금관리 상담",
    action: "MMDA, 정기예금, 유휴자금 운용 상담",
    summary: "수신잔액합계가 이전 기준 대비 낮아져 자금 이탈 신호가 관측됩니다.",
    signals: [
      { label: "예금잔액", change: -31, recent: 244, previous: 354 },
      { label: "자동이체", change: -15, recent: 43, previous: 51 },
      { label: "상품관계폭", change: -9, recent: 4.1, previous: 4.5 }
    ]
  }
];

export const recommendations = customers.map((customer) => ({
  id: customer.id,
  name: customer.name,
  segment: customer.segment,
  weakeningType: customer.weakeningType,
  priority: customer.risk >= 75 ? "High" : customer.risk >= 65 ? "Medium" : "Watch",
  reason: customer.summary,
  contact: customer.contact,
  action: customer.action
}));

export const shapFactors = [
  { feature: "상품관계폭 변화율", impact: 0.31 },
  { feature: "외환거래금액 변화율", impact: 0.26 },
  { feature: "최근 3개월 거래 0월 수", impact: 0.21 },
  { feature: "채널거래금액 변화율", impact: 0.16 },
  { feature: "고객가치 대리지표", impact: 0.12 }
];
