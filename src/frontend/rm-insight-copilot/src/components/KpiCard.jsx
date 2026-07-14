export default function KpiCard({ label, value, detail, tone = "mint" }) {
  return (
    <article className={`kpi-card ${tone}`}>
      <div className="kpi-main">
        <span className="kpi-label">{label}</span>
        <strong className="kpi-value">{value}</strong>
      </div>
      <small className="kpi-detail">{detail}</small>
    </article>
  );
}
