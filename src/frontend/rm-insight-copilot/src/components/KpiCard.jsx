import AmountUnit from "./AmountUnit.jsx";

export default function KpiCard({ label, value, detail, tone = "mint", showAmountUnit = false }) {
  return (
    <article className={`kpi-card ${tone}`}>
      <div className="kpi-main">
        <div className="kpi-heading">
          <span className="kpi-label">{label}</span>
        </div>
        <strong className="kpi-value">{value}</strong>
        {showAmountUnit && <AmountUnit />}
      </div>
      <small className="kpi-detail">{detail}</small>
    </article>
  );
}
