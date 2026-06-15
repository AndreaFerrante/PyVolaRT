import { useMemo } from "react";
import { Area, AreaChart, ResponsiveContainer, YAxis } from "recharts";

import { Card } from "@/components/ui/card";
import { useGexHistory } from "@/hooks/useGexQueries";
import { CHART, HISTORY_LIMIT } from "@/lib/constants";
import { fmtUsdCompact } from "@/utils/format";
import styles from "./NetGexSparkline.module.scss";

interface Point {
  t: number;
  net: number;
}

export function NetGexSparkline() {
  const { data, isLoading, isError } = useGexHistory({ limit: HISTORY_LIMIT });

  const series = useMemo<Point[]>(
    () =>
      (data ?? []).map((s) => ({
        t: new Date(s.ts).getTime(),
        net: s.net_gex,
      })),
    [data],
  );

  const latest = series.length > 0 ? series[series.length - 1]!.net : null;
  const color = latest === null ? CHART.info : latest >= 0 ? CHART.call : CHART.put;

  return (
    <Card className={styles.card}>
      <div className={styles.head}>
        <span className={styles.label}>Net GEX · recent</span>
        <span className={styles.value} style={{ color }}>
          {latest === null ? "—" : fmtUsdCompact(latest)}
        </span>
      </div>

      <div className={styles.spark}>
        {series.length < 2 ? (
          <div className={styles.empty}>
            {isError
              ? "history unavailable"
              : isLoading
                ? "loading history…"
                : "collecting history…"}
          </div>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart
              data={series}
              margin={{ top: 4, right: 0, bottom: 0, left: 0 }}
            >
              <defs>
                <linearGradient id="netFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={color} stopOpacity={0.35} />
                  <stop offset="100%" stopColor={color} stopOpacity={0} />
                </linearGradient>
              </defs>
              <YAxis hide domain={["dataMin", "dataMax"]} />
              <Area
                type="monotone"
                dataKey="net"
                stroke={color}
                strokeWidth={1.5}
                fill="url(#netFill)"
                isAnimationActive={false}
                dot={false}
              />
            </AreaChart>
          </ResponsiveContainer>
        )}
      </div>
    </Card>
  );
}
