import { useState } from "react";

import ExpandableText from "../components/ExpandableText.jsx";
import { EmptyState, ErrorState, LoadingState } from "../components/PageState.jsx";
import SectionHeader from "../components/SectionHeader.jsx";
import StatusBadge from "../components/StatusBadge.jsx";
import { useApi } from "../hooks/useApi.js";

export default function RecommendationsPage({ selectedCustomerId }) {
  const [segment, setSegment] = useState("");
  const [weakeningType, setWeakeningType] = useState("");
  const optionsState = useApi("/api/filter-options");
  const recommendationsState = useApi("/api/recommendations", {
    segment,
    weakening_type: weakeningType
  });

  const recommendations = recommendationsState.data?.items ?? [];
  const selectedRecommendation = recommendations.find((item) => item.id === selectedCustomerId);
  const orderedRecommendations = selectedRecommendation
    ? [selectedRecommendation, ...recommendations.filter((item) => item.id !== selectedCustomerId)]
    : recommendations;
  const loading = optionsState.loading || recommendationsState.loading;
  const error = optionsState.error || recommendationsState.error;

  return (
    <main className="page">
      <SectionHeader
        eyebrow="Next Best Action"
        title="고객 세분화 기반 맞춤형 마케팅"
        description="자동 판매가 아니라 RM이 다음 접촉과 상담 포인트를 빠르게 고르도록 돕습니다."
      />
      <div className="filter-bar">
        <select aria-label="세그먼트" value={segment} onChange={(event) => setSegment(event.target.value)}>
          <option value="">전체 세그먼트</option>
          {(optionsState.data?.segments ?? []).map((option) => (
            <option key={option} value={option}>{option}</option>
          ))}
        </select>
        <select aria-label="약화유형" value={weakeningType} onChange={(event) => setWeakeningType(event.target.value)}>
          <option value="">전체 약화 유형</option>
          {(optionsState.data?.weakeningTypes ?? []).map((option) => (
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
            recommendationsState.retry();
          }}
        />
      )}
      {!loading && !error && recommendations.length === 0 && (
        <EmptyState message="조건에 맞는 추천 전략이 없습니다." />
      )}
      <div className="recommendation-grid">
        {orderedRecommendations.map((item) => (
          <article className="recommendation-card" key={item.id}>
            <div className="card-topline">
              <div>
                <strong>
                  <ExpandableText text={item.name} label="기업명" />
                </strong>
                <StatusBadge kind="segment" value={item.segment}>{item.segment}</StatusBadge>
              </div>
              <StatusBadge kind="priority" value={item.priority}>
                {item.priority}
              </StatusBadge>
            </div>
            <h3>{item.weakeningType}</h3>
            <p>{item.reason}</p>
            <div className="action-box">
              <span>우선 접촉</span>
              <strong>{item.contact}</strong>
            </div>
            <div className="action-box pale">
              <span>제안 전략</span>
              <strong>{item.action}</strong>
            </div>
          </article>
        ))}
      </div>
    </main>
  );
}
