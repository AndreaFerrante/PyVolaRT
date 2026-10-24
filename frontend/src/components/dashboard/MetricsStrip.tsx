import { MetricCard, type MetricAccent } from "./MetricCard";
import type { GexSnapshot } from "@/types/api";
import {
  fmtEsLevel,
  fmtOi,
  fmtPrice,
  fmtRatio,
  fmtSignedPct,
  fmtSignedPts,
  fmtStrike,
  fmtUsdCompact,
} from "@/utils/format";
import styles from "./MetricsStrip.module.scss";

interface MetricsStripProps {
  snapshot: GexSnapshot;
}

export function MetricsStrip({ snapshot }: MetricsStripProps) {
  const { levels, es_basis } = snapshot;
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
        title="Net DEX"
        value={fmtUsdCompact(snapshot.net_dex)}
        sub="Delta of OI"
        accent={snapshot.net_dex >= 0 ? "up" : "down"}
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
      <MetricCard
        title="ES Basis"
        value={fmtSignedPts(es_basis)}
        sub={`ES  CW ${fmtEsLevel(levels.call_wall, es_basis)} · PW ${fmtEsLevel(levels.put_wall, es_basis)} · ZG ${fmtEsLevel(levels.zero_gamma, es_basis)}`}
        accent="info"
      />
    </section>
  );
}
