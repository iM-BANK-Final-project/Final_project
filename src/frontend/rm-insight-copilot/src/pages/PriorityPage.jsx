import { useState } from "react";

import ExpandableText from "../components/ExpandableText.jsx";
import { EmptyState, ErrorState, LoadingState } from "../components/PageState.jsx";
import SectionHeader from "../components/SectionHeader.jsx";
import StatusBadge from "../components/StatusBadge.jsx";
import { useApi } from "../hooks/useApi.js";

const percentFormatter = new Intl.NumberFormat("ko-KR", { maximumFractionDigits: 1 });
const scoreFormatter = new Intl.NumberFormat("ko-KR", { maximumFractionDigits: 2 });

export default function PriorityPage({ onRecommendationOpen }) {
  const [industry, setIndustry] = useState("");
  const [region, setRegion] = useState("");
  const [dedicated, setDedicated] = useState("");
  const [weakeningType, setWeakeningType] = useState("");
  const [segment, setSegment] = useState("");
  const optionsState = useApi("/api/filter-options");
  const prioritiesState = useApi("/api/priorities", {
    industry,
    region,
    dedicated,
    weakening_type: weakeningType,
    segment
  });

  const options = optionsState.data;
  const customers = prioritiesState.data?.items ?? [];
  const loading = optionsState.loading || prioritiesState.loading;
  const error = optionsState.error || prioritiesState.error;

  return (
    <main className="page">
      <SectionHeader
        eyebrow="CRM Priority"
        title="고객가치 기반 CRM 관리 우선순위"
        description="지속거래약화 위험과 고객가치 대리지표를 결합한 RM 운영 순서용 점수로 먼저 볼 고객을 정렬합니다."
      />
      <div className="filter-bar">
        <select aria-label="업종" value={industry} onChange={(event) => setIndustry(event.target.value)}>
          <option value="">전체 업종</option>
          {(options?.industries ?? []).map((option) => (
            <option key={option} value={option}>{option}</option>
          ))}
        </select>
        <select aria-label="지역" value={region} onChange={(event) => setRegion(event.target.value)}>
          <option value="">전체 지역</option>
          {(options?.regions ?? []).map((option) => (
            <option key={option} value={option}>{option}</option>
          ))}
        </select>
        <select aria-label="전담여부" value={dedicated} onChange={(event) => setDedicated(event.target.value)}>
          <option value="">전담여부 전체</option>
          {(options?.dedicatedOptions ?? []).map((option) => (
            <option key={option} value={option}>{option}</option>
          ))}
        </select>
        <select aria-label="약화유형" value={weakeningType} onChange={(event) => setWeakeningType(event.target.value)}>
          <option value="">약화유형 전체</option>
          {(options?.weakeningTypes ?? []).map((option) => (
            <option key={option} value={option}>{option}</option>
          ))}
        </select>
        <select aria-label="세그먼트" value={segment} onChange={(event) => setSegment(event.target.value)}>
          <option value="">전체 세그먼트</option>
          {(options?.segments ?? []).map((option) => (
            <option key={option} value={option}>{option}</option>
          ))}
        </select>
      </div>
      {loading && <LoadingState />}
      {error && (
        <ErrorState
          error={error}
          onRetry={() => {
            optionsState.retry();
            prioritiesState.retry();
          }}
        />
      )}
      {!loading && !error && customers.length === 0 && (
        <EmptyState message="조건에 맞는 관리 대상이 없습니다." />
      )}
      <div className="table-panel">
        <table>
          <thead>
            <tr>
              <th>순위</th>
              <th>법인ID</th>
              <th>기업명</th>
              <th>업종</th>
              <th>지역</th>
              <th>전담</th>
              <th>지속거래약화 위험</th>
              <th>고객가치 대리지표</th>
              <th>수익성</th>
              <th>CRM 우선순위 점수</th>
              <th>주요 약화 유형</th>
              <th>액션</th>
            </tr>
          </thead>
          <tbody>
            {customers.map((customer, index) => (
              <tr key={customer.id}>
                <td>{customer.priorityRank ?? index + 1}</td>
                <td><ExpandableText text={customer.id} label="법인ID" /></td>
                <td><strong><ExpandableText text={customer.name} label="기업명" /></strong></td>
                <td>{customer.industry}</td>
                <td>{customer.region}</td>
                <td>{customer.dedicated}</td>
                <td>{percentFormatter.format(customer.risk)}%</td>
                <td>{scoreFormatter.format(customer.valueProxy)}</td>
                <td>{customer.profitability == null ? "-" : scoreFormatter.format(customer.profitability)}</td>
                <td>{scoreFormatter.format(customer.priorityScore)}</td>
                <td><StatusBadge tone="mint">{customer.weakeningType}</StatusBadge></td>
                <td>
                  <button className="mini-button" onClick={() => onRecommendationOpen(customer.id)}>
                    추천 보기
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </main>
  );
}
