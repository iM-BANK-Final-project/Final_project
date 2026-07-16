export default function MiniTrendChart({ data, metric = "risk" }) {
  if (!data?.length) {
    return null;
  }

  const max = Math.max(...data.map((item) => item[metric]));
  const denominator = max === 0 ? 1 : max;

  return (
    <div className="mini-chart" role="img" aria-label="Monthly trend chart">
      {data.map((item) => (
        <div className="chart-column" key={item.month}>
          <span style={{ height: `${(item[metric] / denominator) * 100}%` }} />
          <small>{item.month.slice(5)}</small>
        </div>
      ))}
    </div>
  );
}
