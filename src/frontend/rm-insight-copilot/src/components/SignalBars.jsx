import { formatPercent } from "../utils/formatters.js";
import AmountUnit from "./AmountUnit.jsx";

export default function SignalBars({ signals }) {
  return (
    <div className="signal-bars">
      <div className="amount-unit-row">
        <AmountUnit />
      </div>
      {signals.map((signal) => (
        <div className="signal-row" key={signal.label}>
          <div>
            <strong>{signal.label}</strong>
            <small>최근 {signal.recent} / 이전 {signal.previous}</small>
          </div>
          <span className={signal.change < -25 ? "drop strong" : "drop"}>
            {signal.change > 0 ? "+" : ""}
            {formatPercent(signal.change)}%
          </span>
        </div>
      ))}
    </div>
  );
}
