const percentFormatter = new Intl.NumberFormat("ko-KR", {
  minimumFractionDigits: 1,
  maximumFractionDigits: 1
});

export default function OverviewRiskTrendChart({ data }) {
  if (!data?.length) return null;

  const width = 600;
  const height = 210;
  const plotTop = 24;
  const plotBottom = 180;
  const step = width / data.length;
  const xAt = (index) => step * index + step / 2;
  const maxShare = Math.max(...data.map((item) => item.thresholdShare), 0.1);
  const risks = data.map((item) => item.risk);
  const riskMin = Math.min(...risks);
  const riskMax = Math.max(...risks);
  const riskPadding = Math.max((riskMax - riskMin) * 0.25, 0.25);
  const domainMin = Math.max(0, riskMin - riskPadding);
  const domainMax = riskMax + riskPadding;
  const yAt = (risk) =>
    plotBottom - ((risk - domainMin) / (domainMax - domainMin || 1)) * (plotBottom - plotTop);
  const linePoints = data.map((item, index) => `${xAt(index)},${yAt(item.risk)}`).join(" ");

  return (
    <div className="overview-risk-trend" role="group" aria-label="월별 지속거래약화 위험 추세">
      <div className="risk-trend-legend" aria-label="차트 범례">
        <span><i className="legend-line" aria-hidden="true" />평균 위험</span>
        <span><i className="legend-bar" aria-hidden="true" />모델 임계값 이상 비중</span>
      </div>

      <svg className="risk-trend-plot" viewBox={`0 0 ${width} ${height}`} aria-hidden="true">
        {[0, 1, 2].map((line) => {
          const y = plotTop + ((plotBottom - plotTop) / 2) * line;
          return <line className="risk-trend-gridline" key={line} x1="0" x2={width} y1={y} y2={y} />;
        })}
        {data.map((item, index) => {
          const barHeight = Math.max((item.thresholdShare / maxShare) * 112, 8);
          return (
            <rect
              className={`risk-trend-bar${item.isCurrent ? " is-current" : ""}`}
              key={item.month}
              x={xAt(index) - 22}
              y={plotBottom - barHeight}
              width="44"
              height={barHeight}
              rx="9"
            />
          );
        })}
        <polyline className="risk-trend-line" points={linePoints} />
        {data.map((item, index) => (
          <circle
            className={`risk-trend-point${item.isCurrent ? " is-current" : ""}`}
            key={item.month}
            cx={xAt(index)}
            cy={yAt(item.risk)}
            r={item.isCurrent ? 6 : 4.5}
          />
        ))}
      </svg>

      <div className="risk-trend-labels">
        {data.map((item) => (
          <div className={`risk-trend-label${item.isCurrent ? " is-current" : ""}`} key={item.month}>
            <span className="risk-trend-month">{item.month.slice(5)}월</span>
            {item.isCurrent && <small className="current-label">현재 기준</small>}
            <strong>{percentFormatter.format(item.risk)}%</strong>
            <small>임계값 이상 {percentFormatter.format(item.thresholdShare)}% · {item.thresholdCount.toLocaleString("ko-KR")}명</small>
          </div>
        ))}
      </div>
      <p className="risk-trend-note">동일 모델의 운영 임계값 26.5% 이상 판정 비중입니다.</p>
    </div>
  );
}
