import KpiCard from "../components/KpiCard.jsx";
import MiniTrendChart from "../components/MiniTrendChart.jsx";
import SectionHeader from "../components/SectionHeader.jsx";
import StatusBadge from "../components/StatusBadge.jsx";
import { customers, monthlyTrend, signalSummary } from "../data/mockData.js";

export default function OverviewPage({ onPageChange }) {
  const topCustomer = customers[0];

  return (
    <main className="page">
      <section className="hero-panel">
        <div className="hero-copy">
          <span className="service-pill">RM Insight Copilot</span>
          <h1>RM 인사이트 코파일럿</h1>
          <p>법인고객의 금융활동 약화 신호를 읽고, 우선 관리 대상과 다음 액션을 제안합니다.</p>
          <div className="hero-actions">
            <button className="primary-button" onClick={() => onPageChange("priority")}>
              우선순위 보기
            </button>
            <button className="ghost-button" onClick={() => onPageChange("report")}>
              AI 보고서 보기
            </button>
          </div>
        </div>
        <div className="hero-card service-summary-card">
          <span className="summary-label">오늘의 우선 관리</span>
          <strong>{topCustomer.name}</strong>
          <div className="summary-metric">
            <span>금융관계 약화 위험</span>
            <b>{topCustomer.risk}%</b>
          </div>
          <StatusBadge tone="lime">{topCustomer.weakeningType}</StatusBadge>
        </div>
      </section>

      <section className="kpi-grid">
        <KpiCard label="조기관리 대상 고객" value="196개" detail="전월 대비 +12개" />
        <KpiCard label="평균 금융관계 약화 위험" value="52%" detail="예시 데이터 · 상위 위험군" tone="lime" />
        <KpiCard label="고위험 고객 비중" value="18.4%" detail="risk 75% 이상" tone="amber" />
        <KpiCard label="조기관리 우선 금액" value="128.4억" detail="예시 데이터 · 고객가치 대리지표" tone="blue" />
      </section>

      <section className="two-column">
        <article className="panel">
          <SectionHeader
            eyebrow="Trend"
            title="월별 금융활동 약화 추이"
            description="최신월 하나가 아니라 기준월별 rolling scoring 흐름으로 해석합니다."
          />
          <MiniTrendChart data={monthlyTrend} />
        </article>
        <article className="panel">
          <SectionHeader eyebrow="Signals" title="약화 원인 Top 5" />
          <div className="rank-list">
            {signalSummary.map((signal, index) => (
              <div className="rank-item" key={signal.label}>
                <span>{index + 1}</span>
                <strong>{signal.label}</strong>
                <StatusBadge tone={signal.tone}>{signal.value}%</StatusBadge>
              </div>
            ))}
          </div>
        </article>
      </section>
    </main>
  );
}
