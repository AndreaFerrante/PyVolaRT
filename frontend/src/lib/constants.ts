/** Chart colors as literals (mirrors the --c-* tokens in styles/tailwind.css)
 *  so Recharts SVG fills resolve without CSS variable lookups. */
export const CHART = {
  call: "#22c55e",
  put: "#f43f5e",
  info: "#3b82f6",
  spot: "#3b82f6",
  grid: "hsl(222 18% 18%)",
  axis: "hsl(220 12% 64%)",
  wallStroke: "#ffffff",
} as const;

/** Snapshots shown in the Net GEX sparkline (~10 min at the 2 s recompute cadence). */
export const HISTORY_LIMIT = 300;

/** "Near" scope: the N strikes closest to spot (backend sends ±30 = 61). */
export const NEAR_STRIKE_COUNT = 30;
