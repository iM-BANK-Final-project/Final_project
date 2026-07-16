export default function RiskMeter({ value }) {
  const numericValue = Number.isFinite(value) ? value : 0;
  const tone = numericValue >= 75 ? "high" : numericValue >= 60 ? "medium" : "watch";
  const displayValue = new Intl.NumberFormat("ko-KR", {
    maximumFractionDigits: 1
  }).format(numericValue);
  const meterWidth = Math.min(100, Math.max(0, numericValue));

  return (
    <div className="risk-meter">
      <div className="risk-meter-label">
        <span>지속거래약화 위험</span>
        <strong>{displayValue}%</strong>
      </div>
      <div className="meter-track">
        <span className={tone} style={{ width: `${meterWidth}%` }} />
      </div>
    </div>
  );
}
