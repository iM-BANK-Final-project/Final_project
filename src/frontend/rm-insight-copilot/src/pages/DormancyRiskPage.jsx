import { useEffect, useState } from "react";

import ExpandableText from "../components/ExpandableText.jsx";
import { EmptyState, ErrorState, LoadingState } from "../components/PageState.jsx";
import RiskMeter from "../components/RiskMeter.jsx";
import SectionHeader from "../components/SectionHeader.jsx";
import SignalBars from "../components/SignalBars.jsx";
import StatusBadge from "../components/StatusBadge.jsx";
import { useApi } from "../hooks/useApi.js";

export default function DormancyRiskPage() {
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [segment, setSegment] = useState("");
  const [riskLevel, setRiskLevel] = useState("");
  const optionsState = useApi("/api/filter-options");
  const customersState = useApi("/api/customers", {
    search,
    segment,
    risk_level: riskLevel
  });

  useEffect(() => {
    const timer = window.setTimeout(() => setSearch(searchInput), 250);
    return () => window.clearTimeout(timer);
  }, [searchInput]);

  const options = optionsState.data;
  const customers = customersState.data?.items ?? [];

  return (
    <main className="page">
      <SectionHeader
        eyebrow="Persistent Weakening"
        title="지속거래약화 예측"
        description="기준월까지의 거래활동 신호로 지속거래약화 위험과 조기관리 필요성을 확인합니다."
      />
      <div className="filter-bar">
        <input
          placeholder="기업명 또는 법인ID 검색"
          value={searchInput}
          onChange={(event) => setSearchInput(event.target.value)}
        />
        <select
          aria-label="세그먼트"
          value={segment}
          onChange={(event) => setSegment(event.target.value)}
        >
          <option value="">전체 세그먼트</option>
          {(options?.segments ?? []).map((option) => (
            <option key={option} value={option}>{option}</option>
          ))}
        </select>
        <select
          aria-label="위험도"
          value={riskLevel}
          onChange={(event) => setRiskLevel(event.target.value)}
        >
          <option value="">위험도 전체</option>
          {(options?.riskLevels ?? []).map((option) => (
            <option key={option} value={option}>{option}</option>
          ))}
        </select>
      </div>
      <div className="customer-grid">
        {(optionsState.loading || customersState.loading) && <LoadingState />}
        {(optionsState.error || customersState.error) && (
          <ErrorState
            error={optionsState.error || customersState.error}
            onRetry={() => {
              optionsState.retry();
              customersState.retry();
            }}
          />
        )}
        {!optionsState.loading && !customersState.loading &&
          !optionsState.error && !customersState.error && customers.length === 0 && (
            <EmptyState message="조건에 맞는 고객이 없습니다." />
          )}
        {!optionsState.loading && !customersState.loading &&
          !optionsState.error && !customersState.error && customers.map((customer) => (
          <article className="customer-card" key={customer.id}>
            <div className="card-topline">
              <div>
                <strong>
                  <ExpandableText text={customer.name} label="기업명" />
                </strong>
                <small className="customer-meta">
                  <ExpandableText text={customer.id} label="법인ID" lines={2} />
                  <StatusBadge kind="segment" value={customer.segment}>
                    {customer.segment}
                  </StatusBadge>
                </small>
              </div>
              <StatusBadge kind="weakening" value={customer.weakeningType}>
                {customer.weakeningType}
              </StatusBadge>
            </div>
            <RiskMeter value={customer.risk} />
            <p>{customer.weakeningType} 신호가 관찰되어 조기관리 검토가 필요합니다.</p>
            <SignalBars signals={customer.signals} />
          </article>
        ))}
      </div>
    </main>
  );
}
