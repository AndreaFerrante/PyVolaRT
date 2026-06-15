/**
 * API contract types — a hand-authored mirror of the backend Pydantic models
 * (app/core/models/*). In production these are generated from the backend's
 * OpenAPI export (e.g. `openapi-typescript`) so drift fails the build; here we
 * keep them in sync by hand and match field-for-field.
 *
 * `string` is used for `datetime`/`date` (ISO-8601 over the wire). `null`
 * means "unknown" — never silently zero (matches the backend's None semantics).
 */

export type OptionRight = "C" | "P";
export type GreeksBasis = "model" | "bid" | "ask" | "last";
export type DataSource = "stream" | "snapshot" | "bs_fallback";

export type Regime = "long_gamma" | "short_gamma" | "unknown";

export type FeedStatus =
  | "live"
  | "degraded"
  | "stale"
  | "offline_hours"
  | "disconnected";

export interface GexLevels {
  zero_gamma: number | null;
  call_wall: number | null;
  put_wall: number | null;
  call_wall_dist_pct: number | null;
  put_wall_dist_pct: number | null;
}

export interface StrikeGex {
  strike: number;
  call_gex: number; // >= 0
  put_gex: number; // <= 0
  net_gex: number;
  call_oi: number;
  put_oi: number;
  quality: number; // 0..1
}

export interface DataQuality {
  status: FeedStatus;
  t1_coverage: number;
  spot_age_s: number | null;
  oi_session_date: string | null;
  lines_in_use: number;
  line_cap: number;
}

export interface GexSnapshot {
  ts: string;
  underlying: string;
  spot: number;

  net_gex: number;
  gross_gex: number;
  call_gex_total: number; // >= 0
  put_gex_total: number; // <= 0
  gex_ratio: number | null;

  call_oi_total: number;
  put_oi_total: number;
  total_oi: number;

  regime: Regime;
  levels: GexLevels;
  profile: StrikeGex[];
  expiries_included: string[];
  quality: DataQuality;
}

export interface FlipCurvePoint {
  spot: number;
  net_gex: number;
}

export interface FlipCurve {
  ts: string;
  points: FlipCurvePoint[];
  zero_crossing: number | null;
}

export interface LevelsResponse {
  ts: string;
  underlying: string;
  spot: number;
  regime: Regime;
  levels: GexLevels;
  quality: DataQuality;
}

export interface MetaRun {
  run_id: string;
  started_at: string;
  provider: string;
  underlying: string;
  line_cap: number;
  config_hash: string;
}

/* --- WebSocket envelope (app/core/models/envelope.py) --- */

export interface GexSnapshotMsg {
  kind: "gex_snapshot";
  data: GexSnapshot;
}
export interface FlipCurveMsg {
  kind: "flip_curve";
  data: FlipCurve;
}
export interface QualityMsg {
  kind: "quality";
  data: DataQuality;
}
export interface HeartbeatMsg {
  kind: "heartbeat";
  data: string;
}

export type WsMessage =
  | GexSnapshotMsg
  | FlipCurveMsg
  | QualityMsg
  | HeartbeatMsg;

export interface WsEnvelope {
  v: 1;
  seq: number;
  sent_at: string;
  msg: WsMessage;
}
