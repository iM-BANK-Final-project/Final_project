import { useEffect, useState } from "react";

import ExpandableText from "../components/ExpandableText.jsx";
import { EmptyState, ErrorState, LoadingState } from "../components/PageState.jsx";
import SectionHeader from "../components/SectionHeader.jsx";
import StatusBadge from "../components/StatusBadge.jsx";
import { useApi } from "../hooks/useApi.js";

const impactFormatter = new Intl.NumberFormat("ko-KR", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2
});

function StoredReport({ asOfMonth, customers, selectedId, onSelectedIdChange }) {
  const reportState = useApi(`/api/reports/${encodeURIComponent(selectedId)}`, {
    as_of_month: asOfMonth
  });
  const report = reportState.data;
  const customer = report?.customer;
  const recommendation = report?.recommendation;
  const shapFactors = report?.shapFactors ?? [];
  const signals = customer?.signals ?? [];
  const selectedCustomerIsListed = customers.some((item) => item.id === selectedId);

  return (
    <div className="report-layout">
      <section className="panel">
        <div className="report-controls">
          <select
            aria-label="보고서 고객"
            value={selectedId}
            onChange={(event) => onSelectedIdChange(event.target.value)}
          >
            {!selectedCustomerIsListed && (
              <option value={selectedId}>
                {customer ? `${customer.name} · ${customer.id}` : selectedId}
              </option>
            )}
            {customers.map((item) => (
              <option value={item.id} key={item.id}>
                {item.name} · {item.id}
              </option>
            ))}
          </select>
          <button type="button" className="primary-button">전략 보고서 생성</button>
        </div>
        {reportState.loading && <LoadingState message="저장된 보고서를 불러오는 중입니다." />}
        {reportState.error && <ErrorState error={reportState.error} onRetry={reportState.retry} />}
        {!reportState.loading && !reportState.error && shapFactors.length === 0 && (
          <EmptyState message="설명값 미산출" />
        )}
        {!reportState.loading && !reportState.error && shapFactors.length > 0 && (
          <div className="beeswarm">
            {shapFactors.map((factor) => {
              const markerPosition = Math.min(Math.max(50 + factor.impact * 100, 8), 92);

              return (
                <div className="bee-row" key={`${factor.rank}-${factor.feature}`}>
                  <span>{factor.feature}</span>
                  <div>
                    <i style={{ left: `${markerPosition}%` }} />
                  </div>
                  <strong>{impactFormatter.format(factor.impact)}</strong>
                </div>
              );
            })}
          </div>
        )}
      </section>
      <section className="panel report-card">
        <StatusBadge tone="mint">선택 고객 저장 리포트</StatusBadge>
        {reportState.loading && <LoadingState message="고객 전략을 불러오는 중입니다." />}
        {reportState.error && (
          <EmptyState message="다른 고객을 선택하거나 보고서 조회를 다시 시도해 주세요." />
        )}
        {!reportState.loading && !reportState.error && report && (
          <>
            <h3>
              <ExpandableText text={customer?.name ?? selectedId} label="기업명" lines={2} />
            </h3>
            <p>{report.strategySummary || "저장된 전략 요약이 없습니다."}</p>
            <div className="waterfall">
              {signals.map((signal) => {
                const hasChange = signal.change != null;
                const width = hasChange ? Math.min(Math.abs(signal.change) * 2.3, 92) : 0;

                return (
                  <div key={signal.label}>
                    <span>{signal.label}</span>
                    <b style={{ width: `${width}%` }}>
                      {hasChange ? `${signal.change}%` : "변화율 미산출"}
                    </b>
                  </div>
                );
              })}
            </div>
            {signals.length === 0 && (
              <EmptyState message="저장된 약화 신호가 없습니다." />
            )}
            {recommendation ? (
              <div className="report-actions">
                <div className="action-box">
                  <span>우선 접촉</span>
                  <strong>{recommendation.contact || "접촉 전략 미지정"}</strong>
                </div>
                <div className="action-box pale">
                  <span>추천 접촉 전략</span>
                  <strong>{recommendation.action || "추천 액션 미지정"}</strong>
                </div>
              </div>
            ) : (
              <EmptyState message="저장된 추천 접촉 전략이 없습니다." />
            )}
          </>
        )}
        <small className="report-note">
          이 화면은 사전에 저장된 검증 완료 지속거래약화 위험, 설명값, 추천 결과를 조회합니다.
          웹에서 모델 또는 LLM을 실행하거나 결과를 재계산하지 않습니다.
        </small>
      </section>
    </div>
  );
}

function ReportData({ asOfMonth, selectedCustomerId }) {
  const customersState = useApi("/api/customers", {
    as_of_month: asOfMonth,
    page: 1,
    page_size: 200,
    sort_by: "defense_rank",
    sort_order: "asc"
  });
  const customers = customersState.data?.items ?? [];
  const [selectedId, setSelectedId] = useState(selectedCustomerId ?? "");

  useEffect(() => {
    if (selectedCustomerId) {
      setSelectedId(selectedCustomerId);
    }
  }, [selectedCustomerId]);

  useEffect(() => {
    if (!selectedId && customers.length > 0) {
      setSelectedId(customers[0].id);
    }
  }, [customers, selectedId]);

  if (customersState.loading) {
    return <LoadingState message="보고서 대상 고객을 불러오는 중입니다." />;
  }

  if (customersState.error) {
    return <ErrorState error={customersState.error} onRetry={customersState.retry} />;
  }

  if (!selectedId) {
    return <EmptyState message="보고서를 조회할 고객이 없습니다." />;
  }

  return (
    <StoredReport
      asOfMonth={asOfMonth}
      customers={customers}
      selectedId={selectedId}
      onSelectedIdChange={setSelectedId}
    />
  );
}

export default function AiReportPage({ selectedCustomerId }) {
  const optionsState = useApi("/api/filter-options");

  return (
    <main className="page">
      <SectionHeader
        eyebrow="Saved AI Report"
        title="저장된 지속거래약화 전략 보고서"
        description="검증 후 저장된 고객별 약화 신호, 설명값, 추천 접촉 전략을 RM 업무 언어로 보여줍니다."
      />
      {optionsState.loading && <LoadingState message="보고서 기준월을 불러오는 중입니다." />}
      {optionsState.error && <ErrorState error={optionsState.error} onRetry={optionsState.retry} />}
      {!optionsState.loading && !optionsState.error && optionsState.data && (
        <ReportData
          asOfMonth={optionsState.data.asOfMonth}
          selectedCustomerId={selectedCustomerId}
        />
      )}
    </main>
  );
}
