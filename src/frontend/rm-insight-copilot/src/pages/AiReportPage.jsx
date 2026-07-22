import { useEffect, useRef, useState } from "react";

import ExpandableText from "../components/ExpandableText.jsx";
import AmountUnit from "../components/AmountUnit.jsx";
import { EmptyState, ErrorState, LoadingState } from "../components/PageState.jsx";
import SectionHeader from "../components/SectionHeader.jsx";
import StatusBadge from "../components/StatusBadge.jsx";
import { apiPost, apiPostBlob } from "../api/client.js";
import { useApi } from "../hooks/useApi.js";
import { formatPercent } from "../utils/formatters.js";

const impactFormatter = new Intl.NumberFormat("ko-KR", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2
});
const scoreFormatter = new Intl.NumberFormat("ko-KR", { maximumFractionDigits: 2 });

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
  const [generatedReport, setGeneratedReport] = useState(null);
  const [generating, setGenerating] = useState(false);
  const [generationError, setGenerationError] = useState(null);
  const [downloading, setDownloading] = useState(false);
  const [downloadError, setDownloadError] = useState(null);
  const generationRequest = useRef(0);

  useEffect(() => {
    generationRequest.current += 1;
    setGeneratedReport(null);
    setGenerating(false);
    setGenerationError(null);
    setDownloading(false);
    setDownloadError(null);
  }, [selectedId, asOfMonth]);

  async function generateReport() {
    const requestId = generationRequest.current + 1;
    generationRequest.current = requestId;
    setGenerating(true);
    setGenerationError(null);
    setDownloadError(null);
    try {
      const result = await apiPost(
        `/api/reports/${encodeURIComponent(selectedId)}/generate`,
        {},
        { as_of_month: asOfMonth }
      );
      if (generationRequest.current === requestId) setGeneratedReport(result);
    } catch (requestError) {
      if (generationRequest.current === requestId) {
        setGenerationError(
          requestError?.message || "AI 보고서 생성에 실패했습니다."
        );
      }
    } finally {
      if (generationRequest.current === requestId) setGenerating(false);
    }
  }

  async function downloadPdf() {
    if (!generatedReport) return;
    setDownloading(true);
    setDownloadError(null);
    try {
      const { blob, filename } = await apiPostBlob(
        `/api/reports/${encodeURIComponent(selectedId)}/pdf`,
        generatedReport
      );
      const objectUrl = URL.createObjectURL(blob);
      try {
        const link = document.createElement("a");
        link.href = objectUrl;
        link.download = filename;
        document.body.appendChild(link);
        link.click();
        link.remove();
      } finally {
        URL.revokeObjectURL(objectUrl);
      }
    } catch (requestError) {
      setDownloadError(
        requestError?.message || "PDF 보고서 생성에 실패했습니다."
      );
    } finally {
      setDownloading(false);
    }
  }

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
          <button
            type="button"
            className="primary-button"
            disabled={generating}
            onClick={generateReport}
          >
            {generating ? "보고서 생성 중..." : "전략 보고서 생성"}
          </button>
        </div>
        {generationError && (
          <div className="ai-report-error" role="alert">
            <span>{generationError}</span>
            <button type="button" className="mini-button" onClick={generateReport}>
              보고서 생성 재시도
            </button>
          </div>
        )}
        {reportState.loading && <LoadingState message="저장된 보고서를 불러오는 중입니다." />}
        {reportState.error && <ErrorState error={reportState.error} onRetry={reportState.retry} />}
        {!reportState.loading && !reportState.error && shapFactors.length === 0 && (
          <EmptyState message="설명값 미산출" />
        )}
        {!reportState.loading && !reportState.error && shapFactors.length > 0 && (
          <section className="shap-section" aria-labelledby="shap-section-title">
            <small id="shap-section-title" className="shap-section-title">
              주요 SHAP Value (상위 10개)
            </small>
            <div className="beeswarm">
              {shapFactors.map((factor) => {
                const markerPosition = Math.min(Math.max(50 + factor.impact * 100, 8), 92);

                return (
                  <div
                    className="bee-row"
                    data-testid="shap-factor"
                    key={`${factor.rank}-${factor.feature}`}
                  >
                    <span>{factor.feature}</span>
                    <div>
                      <i style={{ left: `${markerPosition}%` }} />
                    </div>
                    <strong>{impactFormatter.format(factor.impact)}</strong>
                  </div>
                );
              })}
            </div>
          </section>
        )}
      </section>
      <section className="panel report-card">
        <StatusBadge kind="stage" value="stored">선택 고객 저장 리포트</StatusBadge>
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
            <div className="amount-unit-row">
              <AmountUnit />
            </div>
            <div className="waterfall">
              {signals.map((signal) => {
                const hasChange = signal.change != null;
                const width = hasChange ? Math.min(Math.abs(signal.change) * 2.3, 92) : 0;

                return (
                  <div key={signal.label}>
                    <span>{signal.label}</span>
                    <b style={{ width: `${width}%` }}>
                      {hasChange ? `${formatPercent(signal.change)}%` : "변화율 미산출"}
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
          검증 완료된 위험, CLV, SHAP과 추천 결과는 재계산하지 않습니다.
          AI 보고서는 생성 요청 시 이 근거만 Gemini에 전달해 작성합니다.
        </small>
      </section>
      {generatedReport && (
          <section
            className="panel report-card generated-ai-report"
            aria-labelledby="generated-report-title"
          >
            <div className="generated-report-heading">
              <div>
                <StatusBadge kind="stage" value="generated">AI Report</StatusBadge>
                <h3 id="generated-report-title">AI 전략 보고서</h3>
              </div>
              <button
                type="button"
                className="secondary-button"
                disabled={downloading}
                onClick={downloadPdf}
              >
                {downloading ? "PDF 생성 중..." : "PDF 다운로드"}
              </button>
            </div>
            {downloadError && (
              <p className="ai-report-error-text" role="alert">{downloadError}</p>
            )}
            <div className="amount-unit-row">
              <AmountUnit />
            </div>
            <div className="generated-report-metrics">
              <div>
                <span>지속거래약화 위험</span>
                <strong>{formatPercent(generatedReport.metrics.risk)}%</strong>
              </div>
              <div>
                <span>CLV_Risk</span>
                <strong>{scoreFormatter.format(generatedReport.metrics.clvRisk)}</strong>
              </div>
              <div>
                <span>PotentialLoss</span>
                <strong>{scoreFormatter.format(generatedReport.metrics.potentialLoss)}</strong>
              </div>
            </div>
            <div className="generated-report-grid">
              <article>
                <h4>AI 종합 위험 요약</h4>
                <p>{generatedReport.riskSummary}</p>
              </article>
              <article>
                <h4>고객가치 및 잠재손실 해석</h4>
                <p>{generatedReport.valueAssessment}</p>
              </article>
              <article>
                <h4>주요 약화 원인</h4>
                <p>{generatedReport.weakeningDrivers}</p>
              </article>
              <article>
                <h4>RM 접촉 전략</h4>
                <p>{generatedReport.contactStrategy}</p>
              </article>
              <article>
                <h4>실행 권고사항</h4>
                <ol>
                  {generatedReport.recommendedActions.map((action) => (
                    <li key={action}>{action}</li>
                  ))}
                </ol>
              </article>
              <article className="generated-report-caveats">
                <h4>분석 유의사항</h4>
                <ul>
                  {generatedReport.caveats.map((caveat) => (
                    <li key={caveat}>{caveat}</li>
                  ))}
                </ul>
              </article>
            </div>
          </section>
      )}
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
