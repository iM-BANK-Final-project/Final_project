const percentFormatter = new Intl.NumberFormat("ko-KR", {
  maximumFractionDigits: 1
});

export function formatPercent(value) {
  const numericValue = Number(value);
  return percentFormatter.format(Number.isFinite(numericValue) ? numericValue : 0);
}
