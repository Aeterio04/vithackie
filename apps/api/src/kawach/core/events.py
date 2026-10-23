"""In-memory event bus supporting pub/sub for real-time SSE streaming and pipeline events."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any, Callable, Dict, List, Optional
import weakref


class EventBus:
    """Lightweight in-memory publish/subscribe event bus."""

    def __init__(self):
        self._subscribers: Dict[str, List[Callable[[Dict[str, Any]], None]]] = defaultdict(list)
        self._async_queues: Dict[str, List[asyncio.Queue]] = defaultdict(list)

    def subscribe(self, topic: str, callback: Callable[[Dict[str, Any]], None]) -> Callable[[], None]:
        """Subscribe a synchronous callback to topic; returns unsubscribe function."""
        self._subscribers[topic].append(callback)

        def unsubscribe():
            if callback in self._subscribers[topic]:
                self._subscribers[topic].remove(callback)

        return unsubscribe

    def subscribe_async(self, topic: str) -> Tuple_Queue_Unsub:
        """Register an asyncio queue for an active SSE stream."""
        q: asyncio.Queue = asyncio.Queue()
        self._async_queues[topic].append(q)

        def unsubscribe():
            if q in self._async_queues[topic]:
                self._async_queues[topic].remove(q)

        return q, unsubscribe

    def publish(self, topic: str, event_data: Dict[str, Any]) -> None:
        """Broadcast an event payload to all topic subscribers."""
        # Sync subscribers
        for cb in list(self._subscribers.get(topic, [])):
            try:
                cb(event_data)
            except Exception:
                pass

        # Async queues
        for q in list(self._async_queues.get(topic, [])):
            try:
                q.put_nowait(event_data)
            except Exception:
                pass


Tuple_Queue_Unsub = tuple[asyncio.Queue, Callable[[], None]]
event_bus = EventBus()
