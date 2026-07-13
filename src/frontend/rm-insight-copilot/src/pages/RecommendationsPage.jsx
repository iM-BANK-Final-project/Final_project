import SectionHeader from "../components/SectionHeader.jsx";
import StatusBadge from "../components/StatusBadge.jsx";
import { recommendations } from "../data/mockData.js";

export default function RecommendationsPage() {
  return (
    <main className="page">
      <SectionHeader
        eyebrow="Next Best Action"
        title="고객 세분화 기반 맞춤형 마케팅"
        description="자동 판매가 아니라 RM이 다음 접촉과 상담 포인트를 빠르게 고르도록 돕습니다."
      />
      <div className="filter-bar">
        <select defaultValue="전체 세그먼트">
          <option>전체 세그먼트</option>
          <option>고가치 성장형</option>
          <option>여신 의존형</option>
        </select>
        <select defaultValue="전체 약화 유형">
          <option>전체 약화 유형</option>
          <option>예금잔액 약화</option>
          <option>외환거래 감소</option>
          <option>복수 지표 약화</option>
        </select>
      </div>
      <div className="recommendation-grid">
        {recommendations.map((item) => (
          <article className="recommendation-card" key={item.id}>
            <div className="card-topline">
              <div>
                <strong>{item.name}</strong>
                <small>{item.segment}</small>
              </div>
              <StatusBadge tone={item.priority === "High" ? "coral" : "lime"}>
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
