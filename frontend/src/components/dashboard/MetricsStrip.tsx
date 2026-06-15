import { MetricCard, type MetricAccent } from "./MetricCard";
import type { GexSnapshot } from "@/types/api";
import {
  fmtOi,
  fmtPrice,
  fmtRatio,
  fmtSignedPct,
  fmtStrike,
  fmtUsdCompact,
} from "@/utils/format";
import styles from "./MetricsStrip.module.scss";

interface MetricsStripProps {
  snapshot: GexSnapshot;
}

export function MetricsStrip({ snapshot }: MetricsStripProps) {
  const { levels } = snapshot;
  const netAccent: MetricAccent = snapshot.net_gex >= 0 ? "up" : "down";

  return (
    <section className={styles.grid} aria-label="GEX metrics">
      <MetricCard
        title="Spot Price"
        value={fmtPrice(snapshot.spot)}
        sub={snapshot.underlying}
        accent="neutral"
      />
      <MetricCard
        title="Net GEX"
        value={fmtUsdCompact(snapshot.net_gex)}
        sub={`Ratio: ${fmtRatio(snapshot.gex_ratio)}`}
        accent={netAccent}
      />
      <MetricCard
        title="Call GEX"
        value={fmtUsdCompact(snapshot.call_gex_total)}
        sub={`${fmtOi(snapshot.call_oi_total)} OI`}
        accent="up"
      />
      <MetricCard
        title="Put GEX"
        value={fmtUsdCompact(snapshot.put_gex_total)}
        sub={`${fmtOi(snapshot.put_oi_total)} OI`}
        accent="down"
      />
      <MetricCard
        title="Total GEX"
        value={fmtUsdCompact(snapshot.gross_gex)}
        sub={`${fmtOi(snapshot.total_oi)} OI`}
        accent="info"
      />
      <MetricCard
        title="Call Wall"
        value={fmtStrike(levels.call_wall)}
        sub={fmtSignedPct(levels.call_wall_dist_pct)}
        accent="up"
      />
      <MetricCard
        title="Put Wall"
        value={fmtStrike(levels.put_wall)}
        sub={fmtSignedPct(levels.put_wall_dist_pct)}
        accent="down"
      />
      <MetricCard
        title="Zero Gamma"
        value={fmtStrike(levels.zero_gamma)}
        accent="neutral"
      />
    </section>
  );
}
