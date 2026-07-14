import KpiCard from "../components/KpiCard.jsx";
import MiniTrendChart from "../components/MiniTrendChart.jsx";
import SectionHeader from "../components/SectionHeader.jsx";
import StatusBadge from "../components/StatusBadge.jsx";
import { customers, monthlyTrend, signalSummary } from "../data/mockData.js";

export default function OverviewPage({ onPageChange }) {
  const topCustomer = customers[0];

  return (
    <main className="page">
      <section className="overview-hero">
        <div className="overview-intro">
          <h1>RM 인사이트 코파일럿</h1>
          <p>지속거래약화 가능성이 높은 법인고객을 추려 오늘의 관리 순서와 접촉 전략을 정리합니다.</p>
        </div>
        <div className="overview-actions">
          <button className="primary-button" onClick={() => onPageChange("priority")}>
            관리 우선순위
          </button>
          <button className="ghost-button" onClick={() => onPageChange("risk")}>
            약화 신호 보기
          </button>
        </div>
      </section>

      <section className="overview-layout">
        <article className="focus-panel">
          <div>
            <span className="summary-label">오늘의 관리 포커스</span>
            <h2>{topCustomer.name}</h2>
            <p>{topCustomer.summary}</p>
          </div>
          <div className="focus-meta">
            <div>
              <span>금융관계 약화 위험</span>
              <strong>{topCustomer.risk}%</strong>
            </div>
            <StatusBadge tone="lime">{topCustomer.weakeningType}</StatusBadge>
          </div>
        </article>

        <section className="kpi-grid compact">
          <KpiCard label="조기관리 대상" value="196" detail="전월 대비 +12" />
          <KpiCard label="평균 위험" value="52%" detail="상위 위험군 기준" tone="lime" />
          <KpiCard label="고위험 비중" value="18.4%" detail="risk 75% 이상" tone="amber" />
          <KpiCard label="우선관리 금액" value="128.4억" detail="고객가치 대리지표" tone="blue" />
        </section>
      </section>

      <section className="two-column overview-content">
        <article className="panel">
          <SectionHeader
            eyebrow="Trend"
            title="월별 지속거래약화 위험"
            description="기준월별 rolling scoring 흐름으로 관리 대상 변화를 확인합니다."
          />
          <MiniTrendChart data={monthlyTrend} />
        </article>
        <article className="panel">
          <SectionHeader eyebrow="Signals" title="주요 약화 신호" />
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
