"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { Snapshot, SocketStatus } from "@/lib/types";

const PORT = 43124;

export function useSim() {
  const [status, setStatus] = useState<SocketStatus>("connecting");
  const [snap, setSnap] = useState<Snapshot | null>(null);
  const [attempt, setAttempt] = useState(0);
  const socket = useRef<WebSocket | null>(null);

  useEffect(() => {
    let cancelled = false;
    const host = window.location.hostname || "127.0.0.1";
    const ws = new WebSocket(`ws://${host}:${PORT}/ws`);
    socket.current = ws;
    setStatus("connecting");
    ws.onopen = () => {
      if (!cancelled) setStatus("open");
    };
    ws.onmessage = (event) => {
      if (cancelled) return;
      try {
        setSnap(JSON.parse(event.data) as Snapshot);
        setStatus("open");
      } catch {
        setStatus("error");
      }
    };
    ws.onerror = () => {
      if (!cancelled) setStatus("error");
    };
    ws.onclose = () => {
      if (!cancelled) setStatus("error");
    };
    return () => {
      cancelled = true;
      ws.onclose = null;
      ws.close();
    };
  }, [attempt]);

  const send = useCallback((message: Record<string, unknown>) => {
    const ws = socket.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(message));
    }
  }, []);

  const retry = useCallback(() => setAttempt((value) => value + 1), []);

  return { status, snap, send, retry };
}
