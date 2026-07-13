import { useMemo, useState } from "react";
import SectionHeader from "../components/SectionHeader.jsx";
import StatusBadge from "../components/StatusBadge.jsx";
import { customers, shapFactors } from "../data/mockData.js";

export default function AiReportPage() {
  const [selectedId, setSelectedId] = useState(customers[0].id);
  const selected = useMemo(
    () => customers.find((customer) => customer.id === selectedId) ?? customers[0],
    [selectedId]
  );

  return (
    <main className="page">
      <SectionHeader
        eyebrow="AI Report"
        title="AI 기반 마케팅 전략 보고서"
        description="SHAP 요인과 고객별 약화 신호를 RM 언어의 실행 전략으로 바꿔 보여줍니다."
      />
      <div className="report-layout">
        <section className="panel">
          <div className="report-controls">
            <select value={selectedId} onChange={(event) => setSelectedId(event.target.value)}>
              {customers.map((customer) => (
                <option value={customer.id} key={customer.id}>
                  {customer.name} · {customer.id}
                </option>
              ))}
            </select>
            <button className="primary-button">전략 보고서 생성</button>
          </div>
          <div className="beeswarm">
            {shapFactors.map((factor, index) => (
              <div className="bee-row" key={factor.feature}>
                <span>{factor.feature}</span>
                <div>
                  <i style={{ left: `${factor.impact * 210 + 24}px` }} />
                  <i style={{ left: `${factor.impact * 180 + 58}px` }} />
                  <i style={{ left: `${factor.impact * 150 + 90}px` }} />
                </div>
                <strong>{factor.impact.toFixed(2)}</strong>
              </div>
            ))}
          </div>
        </section>
        <section className="panel report-card">
          <StatusBadge tone="mint">선택 고객 리포트</StatusBadge>
          <h3>{selected.name}</h3>
          <p>
            {selected.name}는 최근 3개월 기준 <strong>{selected.weakeningType}</strong> 신호가
            관측되며, 동일 세그먼트 대비 고객 관계 약화 가능성이 높게 나타납니다. RM은
            {` ${selected.contact}`}을 우선 검토하고, {selected.action}을 상담 포인트로 사용할 수
            있습니다.
          </p>
          <div className="waterfall">
            {selected.signals.map((signal) => (
              <div key={signal.label}>
                <span>{signal.label}</span>
                <b style={{ width: `${Math.min(Math.abs(signal.change) * 2.3, 92)}%` }}>
                  {signal.change}%
                </b>
              </div>
            ))}
          </div>
          <small className="report-note">
            이 보고서는 모델 결과를 재계산하지 않고, 검증된 스코어와 설명값을 RM 상담 문장으로
            요약하는 프로토타입입니다.
          </small>
        </section>
      </div>
    </main>
  );
}
