export default function SignalBars({ signals }) {
  return (
    <div className="signal-bars">
      {signals.map((signal) => (
        <div className="signal-row" key={signal.label}>
          <div>
            <strong>{signal.label}</strong>
            <small>최근 {signal.recent} / 이전 {signal.previous}</small>
          </div>
          <span className={signal.change < -25 ? "drop strong" : "drop"}>
            {signal.change > 0 ? "+" : ""}
            {signal.change}%
          </span>
        </div>
      ))}
    </div>
  );
}
