import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import styles from "./MetricCard.module.scss";

export type MetricAccent = "neutral" | "up" | "down" | "info";

export interface MetricCardProps {
  title: string;
  value: string;
  sub?: string;
  accent?: MetricAccent;
}

export function MetricCard({
  title,
  value,
  sub,
  accent = "neutral",
}: MetricCardProps) {
  return (
    <Card className={styles.card}>
      <span className={styles.title}>{title}</span>
      <span className={cn(styles.value, styles[accent])}>{value}</span>
      {sub !== undefined && <span className={styles.sub}>{sub}</span>}
    </Card>
  );
}
