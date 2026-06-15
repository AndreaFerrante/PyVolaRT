import { cn } from "@/lib/utils";
import type { DataQuality, FeedStatus } from "@/types/api";
import type { WsStatus } from "@/hooks/useGexStream";

interface StatusMeta {
  label: string;
  dot: string;
  text: string;
}

const FEED_META: Record<FeedStatus, StatusMeta> = {
  live: { label: "LIVE", dot: "bg-emerald-400", text: "text-emerald-400" },
  degraded: { label: "DEGRADED", dot: "bg-amber-400", text: "text-amber-400" },
  stale: { label: "STALE", dot: "bg-amber-400", text: "text-amber-400" },
  offline_hours: { label: "OFFLINE", dot: "bg-slate-400", text: "text-slate-400" },
  disconnected: { label: "DISCONNECTED", dot: "bg-rose-500", text: "text-rose-500" },
};

interface StatusBadgeProps {
  quality: DataQuality;
  wsStatus: WsStatus;
}

export function StatusBadge({ quality, wsStatus }: StatusBadgeProps) {
  const meta = FEED_META[quality.status];
  const age =
    quality.spot_age_s !== null ? `${quality.spot_age_s.toFixed(1)}s` : "—";
  const socketLabel =
    wsStatus === "open"
      ? "stream live"
      : wsStatus === "connecting"
        ? "stream connecting"
        : "stream down";

  return (
    <div className="flex items-center gap-3 text-xs">
      <span className="inline-flex items-center gap-1.5 rounded-full border bg-card px-2.5 py-1">
        <span className={cn("h-2 w-2 rounded-full", meta.dot)} />
        <span className={cn("font-semibold tracking-wide", meta.text)}>
          {meta.label}
        </span>
      </span>
      <span className="text-muted-foreground">spot age {age}</span>
      <span className="text-muted-foreground">·</span>
      <span className="text-muted-foreground">
        {quality.lines_in_use}/{quality.line_cap} lines
      </span>
      <span className="text-muted-foreground">·</span>
      <span className="text-muted-foreground">{socketLabel}</span>
    </div>
  );
}
