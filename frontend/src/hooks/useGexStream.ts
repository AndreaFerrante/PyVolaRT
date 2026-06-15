import { useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { wsUrl } from "@/api/client";
import { gexKeys } from "@/hooks/useGexQueries";
import type { GexSnapshot, WsEnvelope } from "@/types/api";

export type WsStatus = "connecting" | "open" | "closed";

export interface GexStreamState {
  status: WsStatus;
  lastSeq: number | null;
}

function isEnvelope(value: unknown): value is WsEnvelope {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  return typeof v.seq === "number" && typeof v.msg === "object" && v.msg !== null;
}

/**
 * Subscribe to the backend WebSocket and push every snapshot/flip/quality
 * message into the TanStack Query cache, so components read live data through
 * the same `useQuery` hooks they use for the REST bootstrap. Auto-reconnects
 * with a fixed backoff. The canonical feed is push; REST is the fallback.
 */
export function useGexStream(): GexStreamState {
  const queryClient = useQueryClient();
  const [status, setStatus] = useState<WsStatus>("connecting");
  const [lastSeq, setLastSeq] = useState<number | null>(null);
  const socketRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    let stopped = false;
    let retryTimer: ReturnType<typeof setTimeout> | undefined;

    const connect = (): void => {
      setStatus("connecting");
      const socket = new WebSocket(wsUrl("/api/v1/ws/stream"));
      socketRef.current = socket;

      socket.onopen = () => {
        if (!stopped) setStatus("open");
      };

      socket.onmessage = (event: MessageEvent<string>) => {
        let parsed: unknown;
        try {
          parsed = JSON.parse(event.data);
        } catch {
          return;
        }
        if (!isEnvelope(parsed)) return;

        const envelope = parsed;
        setLastSeq(envelope.seq);

        switch (envelope.msg.kind) {
          case "gex_snapshot":
            queryClient.setQueryData<GexSnapshot>(
              gexKeys.current,
              envelope.msg.data,
            );
            break;
          case "flip_curve":
            queryClient.setQueryData(gexKeys.flip, envelope.msg.data);
            break;
          case "quality": {
            const quality = envelope.msg.data;
            queryClient.setQueryData<GexSnapshot | undefined>(
              gexKeys.current,
              (prev) => (prev ? { ...prev, quality } : prev),
            );
            break;
          }
          case "heartbeat":
            break;
        }
      };

      socket.onclose = () => {
        if (stopped) return;
        setStatus("closed");
        retryTimer = setTimeout(connect, 2_000);
      };

      socket.onerror = () => {
        socket.close();
      };
    };

    connect();

    return () => {
      stopped = true;
      if (retryTimer) clearTimeout(retryTimer);
      socketRef.current?.close();
    };
  }, [queryClient]);

  return { status, lastSeq };
}
