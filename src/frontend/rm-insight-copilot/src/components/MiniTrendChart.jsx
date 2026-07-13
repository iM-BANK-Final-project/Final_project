export default function MiniTrendChart({ data, metric = "risk" }) {
  const max = Math.max(...data.map((item) => item[metric]));

  return (
    <div className="mini-chart" role="img" aria-label="Monthly trend chart">
      {data.map((item) => (
        <div className="chart-column" key={item.month}>
          <span style={{ height: `${(item[metric] / max) * 100}%` }} />
          <small>{item.month.slice(5)}</small>
        </div>
      ))}
    </div>
  );
}
