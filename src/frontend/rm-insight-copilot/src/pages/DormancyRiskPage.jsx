import RiskMeter from "../components/RiskMeter.jsx";
import SectionHeader from "../components/SectionHeader.jsx";
import SignalBars from "../components/SignalBars.jsx";
import StatusBadge from "../components/StatusBadge.jsx";
import { customers } from "../data/mockData.js";

export default function DormancyRiskPage() {
  return (
    <main className="page">
      <SectionHeader
        eyebrow="Dormancy Risk"
        title="금융관계 휴면화 예측"
        description="기준월까지의 다축 금융관계 추세로 향후 휴면화 가능성을 설명합니다. 현재 화면 수치는 예시 데이터입니다."
      />
      <div className="filter-bar">
        <input placeholder="기업명 또는 법인ID 검색" />
        <select defaultValue="전체 세그먼트">
          <option>전체 세그먼트</option>
          <option>고가치 성장형</option>
          <option>여신 의존형</option>
        </select>
        <select defaultValue="위험도 전체">
          <option>위험도 전체</option>
          <option>High</option>
          <option>Medium</option>
        </select>
      </div>
      <div className="customer-grid">
        {customers.map((customer) => (
          <article className="customer-card" key={customer.id}>
            <div className="card-topline">
              <div>
                <strong>{customer.name}</strong>
                <small>{customer.id} · {customer.segment}</small>
              </div>
              <StatusBadge tone={customer.risk >= 75 ? "coral" : "amber"}>
                {customer.weakeningType}
              </StatusBadge>
            </div>
            <RiskMeter value={customer.risk} />
            <p>{customer.summary}</p>
            <SignalBars signals={customer.signals} />
          </article>
        ))}
      </div>
    </main>
  );
}
