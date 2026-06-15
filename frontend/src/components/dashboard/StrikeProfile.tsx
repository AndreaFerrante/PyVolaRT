import { useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { Card } from "@/components/ui/card";
import { ScopeToggle, type Scope } from "./ScopeToggle";
import { CHART, NEAR_STRIKE_COUNT } from "@/lib/constants";
import type { StrikeGex } from "@/types/api";
import { fmtAxisMillions, fmtOi, fmtUsdCompact } from "@/utils/format";
import styles from "./StrikeProfile.module.scss";

interface StrikeProfileProps {
  profile: StrikeGex[];
  spot: number;
  callWall: number | null;
  putWall: number | null;
}

export function StrikeProfile({
  profile,
  spot,
  callWall,
  putWall,
}: StrikeProfileProps) {
  const [scope, setScope] = useState<Scope>("near");

  const data = useMemo<StrikeGex[]>(() => {
    if (scope === "all") {
      return [...profile].sort((a, b) => a.strike - b.strike);
    }
    return [...profile]
      .sort((a, b) => Math.abs(a.strike - spot) - Math.abs(b.strike - spot))
      .slice(0, NEAR_STRIKE_COUNT)
      .sort((a, b) => a.strike - b.strike);
  }, [profile, scope, spot]);

  return (
    <Card className={styles.panel}>
      <div className={styles.header}>
        <h2 className={styles.title}>Strike Profile</h2>
        <ScopeToggle value={scope} onChange={setScope} />
      </div>

      <div className={styles.chart}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart
            data={data}
            stackOffset="sign"
            margin={{ top: 16, right: 12, bottom: 8, left: 4 }}
          >
            <CartesianGrid stroke={CHART.grid} vertical={false} />
            <XAxis
              dataKey="strike"
              type="number"
              domain={["dataMin", "dataMax"]}
              tick={{ fill: CHART.axis, fontSize: 11 }}
              tickFormatter={(v: number) => String(Math.round(v))}
              minTickGap={36}
              tickLine={false}
              axisLine={{ stroke: CHART.grid }}
            />
            <YAxis
              width={64}
              tick={{ fill: CHART.axis, fontSize: 11 }}
              tickFormatter={fmtAxisMillions}
              tickLine={false}
              axisLine={false}
            />
            <Tooltip
              cursor={{ fill: "rgba(255,255,255,0.04)" }}
              content={({ active, payload }) => {
                if (!active || !payload || payload.length === 0) return null;
                const row = payload[0]?.payload as StrikeGex | undefined;
                if (!row) return null;
                return (
                  <div className={styles.tooltip}>
                    <div className={styles.tipStrike}>Strike {row.strike}</div>
                    <div className={styles.tipRow}>
                      <span>Net</span>
                      <span>{fmtUsdCompact(row.net_gex, 2)}</span>
                    </div>
                    <div className={styles.tipRow}>
                      <span style={{ color: CHART.call }}>Call γ</span>
                      <span>{fmtUsdCompact(row.call_gex, 2)}</span>
                    </div>
                    <div className={styles.tipRow}>
                      <span style={{ color: CHART.put }}>Put γ</span>
                      <span>{fmtUsdCompact(row.put_gex, 2)}</span>
                    </div>
                    <div className={styles.tipRow}>
                      <span>OI C/P</span>
                      <span>
                        {fmtOi(row.call_oi)} / {fmtOi(row.put_oi)}
                      </span>
                    </div>
                  </div>
                );
              }}
            />

            <ReferenceLine y={0} stroke={CHART.grid} />
            <ReferenceLine
              x={spot}
              stroke={CHART.spot}
              strokeDasharray="4 4"
              label={{
                value: "Spot",
                position: "top",
                fill: CHART.spot,
                fontSize: 11,
              }}
            />

            <Bar dataKey="call_gex" stackId="gex" fill={CHART.call} maxBarSize={9}>
              {data.map((d) => (
                <Cell
                  key={`c-${d.strike}`}
                  stroke={d.strike === callWall ? CHART.wallStroke : undefined}
                  strokeWidth={d.strike === callWall ? 1.5 : 0}
                />
              ))}
            </Bar>
            <Bar dataKey="put_gex" stackId="gex" fill={CHART.put} maxBarSize={9}>
              {data.map((d) => (
                <Cell
                  key={`p-${d.strike}`}
                  stroke={d.strike === putWall ? CHART.wallStroke : undefined}
                  strokeWidth={d.strike === putWall ? 1.5 : 0}
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div className={styles.legend}>
        <span className={styles.legendItem}>
          <span className={styles.swatch} style={{ background: CHART.call }} />
          Call Gamma
        </span>
        <span className={styles.legendItem}>
          <span className={styles.swatch} style={{ background: CHART.put }} />
          Put Gamma
        </span>
      </div>
    </Card>
  );
}
