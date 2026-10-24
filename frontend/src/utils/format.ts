/** Compact USD: -$14.7B, $10.1B, $34.9M. Sign precedes the dollar sign. */
export function fmtUsdCompact(n: number, digits = 1): string {
  const sign = n < 0 ? "-" : "";
  const abs = Math.abs(n);
  if (abs >= 1e9) return `${sign}$${(abs / 1e9).toFixed(digits)}B`;
  if (abs >= 1e6) return `${sign}$${(abs / 1e6).toFixed(digits)}M`;
  if (abs >= 1e3) return `${sign}$${(abs / 1e3).toFixed(digits)}K`;
  return `${sign}$${abs.toFixed(0)}`;
}

/** Spot / price: $7376.81 */
export function fmtPrice(n: number): string {
  return `$${n.toFixed(2)}`;
}

/** Strike level: $7460 (no decimals, no thousands separator — matches mockup). */
export function fmtStrike(n: number | null): string {
  return n === null ? "N/A" : `$${Math.round(n)}`;
}

/** Open interest: 182,091 */
export function fmtOi(n: number): string {
  return n.toLocaleString("en-US");
}

/** Signed percentage: +1.13%, -0.77%, — when unknown. */
export function fmtSignedPct(n: number | null, digits = 2): string {
  if (n === null) return "—";
  const sign = n >= 0 ? "+" : "";
  return `${sign}${n.toFixed(digits)}%`;
}

/** Signed points: +35.25, N/A when unknown. */
export function fmtSignedPts(n: number | null): string {
  if (n === null) return "N/A";
  return `${n >= 0 ? "+" : ""}${n.toFixed(2)}`;
}

/** SPX level shifted to ES, rounded to the 0.25 ES tick: 6110.25, N/A when unknown. */
export function fmtEsLevel(level: number | null, basis: number | null): string {
  if (level === null || basis === null) return "N/A";
  return (Math.round((level + basis) * 4) / 4).toFixed(2);
}

/** Ratio: 0.41, — when unknown. */
export function fmtRatio(n: number | null, digits = 2): string {
  return n === null ? "—" : n.toFixed(digits);
}

/** Y-axis tick: 1500.0M, 0.0M, -1500.0M */
export function fmtAxisMillions(n: number): string {
  return `${(n / 1e6).toFixed(1)}M`;
}
