"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  type Run,
  type SSEEvent,
  SSEEventSchema,
  type CatalogTest,
  type ReviewDecision,
  type Bug,
  type ExecutionTest,
  type ExecutionState,
  type Worker,
} from "@/types";
import { API_ENDPOINTS } from "@/lib/api/config";
import { apiClient } from "@/lib/api/client";

export type ConnectionState = "live" | "reconnecting" | "polling" | "disconnected";

export interface StreamLogEntry {
  id: string;
  timestamp: string;
  level: "info" | "warn" | "error" | "debug";
  source?: string;
  message: string;
}

export function useRunStream(runId: string | null | undefined, isFinished = false) {
  const queryClient = useQueryClient();
  const [connectionState, setConnectionState] = useState<ConnectionState>("disconnected");
  const [logs, setLogs] = useState<StreamLogEntry[]>([]);

  const eventSourceRef = useRef<EventSource | null>(null);
  const failureCountRef = useRef(0);
  const lastEventIdRef = useRef<string | null>(null);
  const pollingIntervalRef = useRef<NodeJS.Timeout | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  // Helper to handle received SSE events and update React Query cache directly
  const handleSSEMessage = useCallback(
    (rawEventData: string, eventId?: string) => {
      if (eventId) {
        lastEventIdRef.current = eventId;
      }

      let parsedJson: unknown;
      try {
        parsedJson = JSON.parse(rawEventData);
      } catch {
        // Not JSON, ignore safely
        return;
      }

      const parseResult = SSEEventSchema.safeParse(parsedJson);
      if (!parseResult.success) {
        // Unknown or invalid event type, ignore safely
        return;
      }

      const event: SSEEvent = parseResult.data;

      if (!runId) return;

      switch (event.type) {
        case "run.status": {
          queryClient.setQueryData<Run>(["runs", runId], (old) => {
            if (!old) return old;
            return {
              ...old,
              status: event.status,
              progress: event.progress,
            };
          });
          break;
        }

        case "log": {
          const newEntry: StreamLogEntry = {
            id: `${Date.now()}-${Math.random().toString(36).substring(2, 7)}`,
            timestamp: event.timestamp || new Date().toISOString(),
            level: event.level,
            source: event.source,
            message: event.message,
          };
          setLogs((prev) => [...prev.slice(-499), newEntry]); // keep last 500 lines
          break;
        }

        case "catalog.ready": {
          queryClient.setQueryData<CatalogTest[]>(
            ["runs", runId, "catalog"],
            event.tests
          );
          break;
        }

        case "review.decision": {
          const decision = event.decision;
          queryClient.setQueryData<CatalogTest[]>(
            ["runs", runId, "catalog"],
            (old: CatalogTest[] | undefined) => {
              if (!old) return old;
              return old.map((test) =>
                test.id === decision.test_id
                  ? {
                      ...test,
                      review_status: decision.decision,
                      last_decision: decision,
                    }
                  : test
              );
            }
          );
          queryClient.setQueryData<ReviewDecision[]>(
            ["runs", runId, "reviewLog"],
            (old: ReviewDecision[] | undefined) => (old ? [decision, ...old] : [decision])
          );
          break;
        }

        case "worker.update": {
          const worker = event.worker;
          queryClient.setQueryData<ExecutionState>(
            ["runs", runId, "execution"],
            (old: ExecutionState | undefined) => {
              if (!old) return { workers: [worker], tests: [] };
              const exists = old.workers.some((w: Worker) => w.id === worker.id);
              return {
                ...old,
                workers: exists
                  ? old.workers.map((w: Worker) => (w.id === worker.id ? worker : w))
                  : [...old.workers, worker],
              };
            }
          );
          break;
        }

        case "test.update": {
          const test = event.test;
          queryClient.setQueryData<ExecutionState>(
            ["runs", runId, "execution"],
            (old: ExecutionState | undefined) => {
              if (!old) return { workers: [], tests: [test] };
              const exists = old.tests.some((t: ExecutionTest) => t.id === test.id);
              return {
                ...old,
                tests: exists
                  ? old.tests.map((t: ExecutionTest) => (t.id === test.id ? test : t))
                  : [...old.tests, test],
              };
            }
          );
          queryClient.setQueryData<ExecutionTest[]>(
            ["runs", runId, "tests"],
            (old: ExecutionTest[] | undefined) => {
              if (!old) return [test];
              const exists = old.some((t: ExecutionTest) => t.id === test.id);
              return exists
                ? old.map((t: ExecutionTest) => (t.id === test.id ? test : t))
                : [...old, test];
            }
          );
          break;
        }

        case "bug.suspected": {
          const bug = event.bug;
          queryClient.setQueryData<Bug[]>(["runs", runId, "bugs"], (old) => {
            if (!old) return [bug];
            const exists = old.some((b) => b.id === bug.id);
            return exists ? old.map((b) => (b.id === bug.id ? bug : b)) : [bug, ...old];
          });
          break;
        }

        case "bug.verification": {
          const { bug_id, replay_index, result, duration_ms, video_url } = event;
          queryClient.setQueryData<Bug[]>(["runs", runId, "bugs"], (old) => {
            if (!old) return old;
            return old.map((b) => {
              if (b.id !== bug_id) return b;
              const replays = [...(b.replays || [])];
              const idx = replays.findIndex((r) => r.index === replay_index);
              const updatedReplay = {
                index: replay_index,
                result,
                duration_ms: duration_ms ?? undefined,
                video_url: video_url ?? undefined,
                timestamp: new Date().toISOString(),
              };
              if (idx >= 0) {
                replays[idx] = updatedReplay;
              } else {
                replays.push(updatedReplay);
              }
              return { ...b, replays, status: "verifying" };
            });
          });
          break;
        }

        case "bug.final": {
          const bug = event.bug;
          queryClient.setQueryData<Bug[]>(["runs", runId, "bugs"], (old) => {
            if (!old) return [bug];
            const exists = old.some((b) => b.id === bug.id);
            return exists ? old.map((b) => (b.id === bug.id ? bug : b)) : [bug, ...old];
          });
          queryClient.setQueryData<Bug>(["bugs", bug.id], bug);
          break;
        }

        case "budget.update": {
          queryClient.setQueryData<Run>(["runs", runId], (old: Run | undefined) => {
            if (!old) return old;
            return { ...old, budget_usage: event.usage };
          });
          queryClient.setQueryData<ExecutionState>(
            ["runs", runId, "execution"],
            (old: ExecutionState | undefined) => (old ? { ...old, budget_usage: event.usage } : old)
          );
          break;
        }

        case "run.done": {
          queryClient.setQueryData<Run>(["runs", runId], event.run);
          queryClient.invalidateQueries({ queryKey: ["runs", runId] });
          queryClient.invalidateQueries({ queryKey: ["runs", runId, "report"] });
          setConnectionState("disconnected");
          break;
        }
      }
    },
    [queryClient, runId]
  );

  // Polling fallback when SSE fails repeatedly
  const startPollingFallback = useCallback(() => {
    if (pollingIntervalRef.current || !runId) return;
    setConnectionState("polling");

    const poll = async () => {
      try {
        const events = await apiClient<Array<{ id: string; data: string }>>(
          API_ENDPOINTS.RUN_EVENTS_POLL(runId, lastEventIdRef.current || undefined)
        );
        if (Array.isArray(events)) {
          for (const ev of events) {
            handleSSEMessage(ev.data, ev.id);
          }
        }
      } catch {
        // Quietly wait for next poll
      }
    };

    poll();
    pollingIntervalRef.current = setInterval(poll, 4000);
  }, [runId, handleSSEMessage]);

  const connectSSERef = useRef<() => void>(() => {});

  // Connect SSE
  const connectSSE = useCallback(() => {
    if (!runId || isFinished) return;

    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }

    const streamUrl = API_ENDPOINTS.RUN_STREAM(runId);
    const es = new EventSource(streamUrl, { withCredentials: true });
    eventSourceRef.current = es;

    es.onopen = () => {
      failureCountRef.current = 0;
      setConnectionState("live");
      // On successful reconnect, refetch run to ensure clean sync
      queryClient.invalidateQueries({ queryKey: ["runs", runId] });
    };

    es.onmessage = (e) => {
      handleSSEMessage(e.data, e.lastEventId);
    };

    es.onerror = () => {
      es.close();
      eventSourceRef.current = null;
      failureCountRef.current += 1;

      if (failureCountRef.current >= 3) {
        // Fall back to polling after 3 failures
        startPollingFallback();
      } else {
        setConnectionState("reconnecting");
        // Exponential backoff reconnect: 1s, 2s, 4s...
        const delay = Math.min(1000 * Math.pow(2, failureCountRef.current - 1), 8000);
        reconnectTimeoutRef.current = setTimeout(() => {
          connectSSERef.current();
        }, delay);
      }
    };
  }, [runId, isFinished, handleSSEMessage, queryClient, startPollingFallback]);

  useEffect(() => {
    connectSSERef.current = connectSSE;
  }, [connectSSE]);

  useEffect(() => {
    if (!runId || isFinished) {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
        eventSourceRef.current = null;
      }
      if (pollingIntervalRef.current) {
        clearInterval(pollingIntervalRef.current);
        pollingIntervalRef.current = null;
      }
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
        reconnectTimeoutRef.current = null;
      }
      return;
    }

    connectSSERef.current();

    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
        eventSourceRef.current = null;
      }
      if (pollingIntervalRef.current) {
        clearInterval(pollingIntervalRef.current);
        pollingIntervalRef.current = null;
      }
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
        reconnectTimeoutRef.current = null;
      }
    };
  }, [runId, isFinished]);

  const clearLogs = useCallback(() => setLogs([]), []);

  return {
    connectionState,
    logs,
    clearLogs,
    isLive: connectionState === "live",
    isPolling: connectionState === "polling",
    isReconnecting: connectionState === "reconnecting",
  };
}
