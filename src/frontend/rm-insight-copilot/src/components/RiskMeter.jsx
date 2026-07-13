export default function RiskMeter({ value }) {
  const tone = value >= 75 ? "high" : value >= 60 ? "medium" : "watch";

  return (
    <div className="risk-meter">
      <div className="risk-meter-label">
        <span>금융관계 약화 위험</span>
        <strong>{value}%</strong>
      </div>
      <div className="meter-track">
        <span className={tone} style={{ width: `${value}%` }} />
      </div>
    </div>
  );
}
