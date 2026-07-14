import KpiCard from "../components/KpiCard.jsx";
import MiniTrendChart from "../components/MiniTrendChart.jsx";
import { EmptyState, ErrorState, LoadingState } from "../components/PageState.jsx";
import SectionHeader from "../components/SectionHeader.jsx";
import StatusBadge from "../components/StatusBadge.jsx";
import { useApi } from "../hooks/useApi.js";

const percentFormatter = new Intl.NumberFormat("ko-KR", { maximumFractionDigits: 1 });
const scoreFormatter = new Intl.NumberFormat("ko-KR", { maximumFractionDigits: 2 });
const signalTones = ["mint", "blue", "amber", "coral", "gray"];

export default function OverviewPage({ onPageChange }) {
  const overviewState = useApi("/api/overview");
  const customerState = useApi("/api/customers", { page: 1, page_size: 1 });

  if (overviewState.loading || customerState.loading) {
    return <LoadingState />;
  }

  if (overviewState.error || customerState.error) {
    return (
      <ErrorState
        error={overviewState.error || customerState.error}
        onRetry={() => {
          overviewState.retry();
          customerState.retry();
        }}
      />
    );
  }

  const overview = overviewState.data;
  const topCustomer = customerState.data?.items?.[0];

  if (!overview || !topCustomer) {
    return <EmptyState message="표시할 관리 대상이 없습니다." />;
  }

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
            <p>{topCustomer.weakeningType} 신호가 관찰되어 조기관리 검토가 필요합니다.</p>
          </div>
          <div className="focus-meta">
            <div>
              <span>지속거래약화 위험</span>
              <strong>{percentFormatter.format(topCustomer.risk)}%</strong>
            </div>
            <StatusBadge tone="lime">{topCustomer.weakeningType}</StatusBadge>
          </div>
        </article>

        <section className="kpi-grid compact">
          <KpiCard
            label="조기관리 대상"
            value={overview.managedCustomerCount.toLocaleString("ko-KR")}
            detail={`${overview.asOfMonth} 기준`}
          />
          <KpiCard
            label="평균 위험"
            value={`${percentFormatter.format(overview.averageRisk)}%`}
            detail="지속거래약화 위험 평균"
            tone="lime"
          />
          <KpiCard
            label="고위험 비중"
            value={`${percentFormatter.format(overview.highRiskShare)}%`}
            detail="고위험 고객 비중"
            tone="amber"
          />
          <KpiCard
            label="CRM 관리 우선순위 점수"
            value={scoreFormatter.format(overview.priorityValueTotal)}
            detail="RM 운영 순서용 합산 점수"
            tone="blue"
          />
        </section>
      </section>

      <section className="two-column overview-content">
        <article className="panel">
          <SectionHeader
            eyebrow="Trend"
            title="월별 지속거래약화 위험"
            description="기준월별 rolling scoring 흐름으로 관리 대상 변화를 확인합니다."
          />
          <MiniTrendChart data={overview.monthlyTrend} />
        </article>
        <article className="panel">
          <SectionHeader eyebrow="Signals" title="주요 약화 신호" />
          <div className="rank-list">
            {overview.signalSummary.map((signal, index) => (
              <div className="rank-item" key={signal.label}>
                <span>{index + 1}</span>
                <strong>{signal.label}</strong>
                <StatusBadge tone={signalTones[index % signalTones.length]}>
                  {signal.value}건
                </StatusBadge>
              </div>
            ))}
          </div>
        </article>
      </section>
    </main>
  );
}
