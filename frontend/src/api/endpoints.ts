import { getJson } from "@/api/client";
import type {
  DataQuality,
  FlipCurve,
  GexSnapshot,
  LevelsResponse,
  MetaRun,
} from "@/types/api";

export function fetchCurrent(): Promise<GexSnapshot> {
  return getJson<GexSnapshot>("/api/v1/gex/current");
}

export function fetchLevels(): Promise<LevelsResponse> {
  return getJson<LevelsResponse>("/api/v1/gex/levels");
}

export function fetchFlipCurve(): Promise<FlipCurve> {
  return getJson<FlipCurve>("/api/v1/gex/flip-curve");
}

export function fetchQuality(): Promise<DataQuality> {
  return getJson<DataQuality>("/api/v1/quality");
}

export function fetchMeta(): Promise<MetaRun> {
  return getJson<MetaRun>("/api/v1/meta/run");
}

export interface HistoryParams {
  start?: string;
  end?: string;
  underlying?: string;
  limit?: number;
  step?: number;
}

export function fetchHistory(params: HistoryParams): Promise<GexSnapshot[]> {
  return getJson<GexSnapshot[]>("/api/v1/gex/history", { ...params });
}
