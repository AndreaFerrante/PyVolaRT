import { useQuery, type UseQueryResult } from "@tanstack/react-query";

import {
  fetchCurrent,
  fetchFlipCurve,
  fetchHistory,
  type HistoryParams,
} from "@/api/endpoints";
import type { FlipCurve, GexSnapshot } from "@/types/api";

/** Centralized query keys so the WebSocket hook can write into the same cache. */
export const gexKeys = {
  current: ["gex", "current"] as const,
  flip: ["gex", "flip"] as const,
  history: (params: HistoryParams) => ["gex", "history", params] as const,
};

/**
 * Latest snapshot. The WebSocket pushes updates straight into this cache
 * (see useGexStream), so the polling interval here is only a safety net for
 * when the socket is down.
 */
export function useCurrentGex(): UseQueryResult<GexSnapshot> {
  return useQuery({
    queryKey: gexKeys.current,
    queryFn: fetchCurrent,
    staleTime: 5_000,
    refetchInterval: 10_000,
  });
}

export function useFlipCurve(): UseQueryResult<FlipCurve> {
  return useQuery({
    queryKey: gexKeys.flip,
    queryFn: fetchFlipCurve,
    staleTime: 10_000,
    refetchInterval: 30_000,
  });
}

/** Historical snapshots from the backend's `/gex/history` endpoint. */
export function useGexHistory(
  params: HistoryParams,
): UseQueryResult<GexSnapshot[]> {
  return useQuery({
    queryKey: gexKeys.history(params),
    queryFn: () => fetchHistory(params),
    staleTime: 10_000,
    refetchInterval: 15_000,
  });
}
