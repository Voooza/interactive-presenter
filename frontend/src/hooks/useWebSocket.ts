/**
 * Custom React hook for managing a WebSocket connection to the presentation server.
 *
 * Handles connection lifecycle, reconnection with exponential backoff + jitter,
 * application-level heartbeat (ping/pong), and message parsing.
 */

import { useCallback, useEffect, useRef, useState } from 'react';

import type { ClientMessage, ServerMessage } from '../types';

const WS_BASE_URL = 'ws://localhost:8000';
const HEARTBEAT_INTERVAL_MS = 30_000;
const HEARTBEAT_TIMEOUT_MS = 10_000;
const MAX_RECONNECT_ATTEMPTS = 10;
const RECONNECT_CAP_MS = 15_000;

export interface UseWebSocketOptions {
  presentationId: string;
  role: 'presenter' | 'audience';
  onMessage?: (message: ServerMessage) => void;
}

export interface UseWebSocketReturn {
  isConnected: boolean;
  isReconnecting: boolean;
  audienceCount: number;
  currentSlide: number;
  send: (message: ClientMessage) => void;
  reconnect: () => void;
}

/** Compute reconnection delay with exponential backoff and +-20% jitter. */
function reconnectDelay(attempt: number): number {
  const base = Math.min(1000 * 2 ** (attempt - 1), RECONNECT_CAP_MS);
  const jitter = base * 0.2 * (Math.random() * 2 - 1);
  return base + jitter;
}

export function useWebSocket(options: UseWebSocketOptions): UseWebSocketReturn {
  const { presentationId, role, onMessage } = options;

  const [isConnected, setIsConnected] = useState(false);
  const [isReconnecting, setIsReconnecting] = useState(false);
  const [audienceCount, setAudienceCount] = useState(0);
  const [currentSlide, setCurrentSlide] = useState(0);

  const wsRef = useRef<WebSocket | null>(null);
  const heartbeatIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const pongTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const reconnectAttemptRef = useRef(0);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const manualDisconnectRef = useRef(false);
  const gaveUpRef = useRef(false);

  // Keep onMessage ref stable to avoid re-connecting on callback changes.
  const onMessageRef = useRef(onMessage);
  onMessageRef.current = onMessage;

  const clearHeartbeat = useCallback(() => {
    if (heartbeatIntervalRef.current !== null) {
      clearInterval(heartbeatIntervalRef.current);
      heartbeatIntervalRef.current = null;
    }
    if (pongTimeoutRef.current !== null) {
      clearTimeout(pongTimeoutRef.current);
      pongTimeoutRef.current = null;
    }
  }, []);

  const startHeartbeat = useCallback(
    (ws: WebSocket) => {
      clearHeartbeat();
      heartbeatIntervalRef.current = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ type: 'ping', timestamp: new Date().toISOString() }));
          pongTimeoutRef.current = setTimeout(() => {
            // No pong received — consider connection dead.
            ws.close();
          }, HEARTBEAT_TIMEOUT_MS);
        }
      }, HEARTBEAT_INTERVAL_MS);
    },
    [clearHeartbeat],
  );

  const connect = useCallback(() => {
    // Clean up any existing connection.
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }

    const url = `${WS_BASE_URL}/ws/${encodeURIComponent(presentationId)}?role=${role}`;
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      setIsConnected(true);
      setIsReconnecting(false);
      reconnectAttemptRef.current = 0;
      gaveUpRef.current = false;
      startHeartbeat(ws);
    };

    ws.onmessage = (event: MessageEvent) => {
      let msg: ServerMessage;
      try {
        msg = JSON.parse(event.data as string) as ServerMessage;
      } catch {
        return;
      }

      // Handle pong — clear timeout.
      if (msg.type === 'pong') {
        if (pongTimeoutRef.current !== null) {
          clearTimeout(pongTimeoutRef.current);
          pongTimeoutRef.current = null;
        }
      }

      // Track state from server messages.
      if (msg.type === 'connected') {
        setAudienceCount(msg.audience_count);
        setCurrentSlide(msg.current_slide);
      } else if (msg.type === 'peer_count') {
        setAudienceCount(msg.audience_count);
      } else if (msg.type === 'slide_changed') {
        setCurrentSlide(msg.slide_index);
      }

      onMessageRef.current?.(msg);
    };

    ws.onclose = () => {
      setIsConnected(false);
      clearHeartbeat();

      if (!manualDisconnectRef.current && !gaveUpRef.current) {
        const attempt = reconnectAttemptRef.current + 1;
        reconnectAttemptRef.current = attempt;

        if (attempt <= MAX_RECONNECT_ATTEMPTS) {
          setIsReconnecting(true);
          const delay = reconnectDelay(attempt);
          reconnectTimeoutRef.current = setTimeout(() => {
            connect();
          }, delay);
        } else {
          setIsReconnecting(false);
          gaveUpRef.current = true;
        }
      }
    };

    ws.onerror = () => {
      // The close handler will fire after this and handle reconnection.
    };
  }, [presentationId, role, clearHeartbeat, startHeartbeat]);

  const send = useCallback((message: ClientMessage) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(message));
    }
  }, []);

  const reconnect = useCallback(() => {
    manualDisconnectRef.current = false;
    reconnectAttemptRef.current = 0;
    gaveUpRef.current = false;
    connect();
  }, [connect]);

  useEffect(() => {
    manualDisconnectRef.current = false;
    connect();

    return () => {
      manualDisconnectRef.current = true;
      clearHeartbeat();
      if (reconnectTimeoutRef.current !== null) {
        clearTimeout(reconnectTimeoutRef.current);
        reconnectTimeoutRef.current = null;
      }
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [connect, clearHeartbeat]);

  return {
    isConnected,
    isReconnecting,
    audienceCount,
    currentSlide,
    send,
    reconnect,
  };
}
