"""AgriVoice-AI: Asynchronous Message & Response Queues.

Implements two asyncio queues (message_queue and response_queue),
inbound/outbound data structures, and sliding-window rate limiting.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from src.telegram.config import TelegramBotConfig, get_telegram_config


@dataclass
class InboundMessageItem:
    """Represents a message received from Telegram queued for AI processing."""

    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    chat_id: int = 0
    message_id: int = 0
    user_id: int = 0
    username: Optional[str] = None
    full_name: str = ""
    chat_type: str = "private"  # private, group, supergroup
    msg_type: str = "TEXT"      # TEXT, VOICE, AUDIO
    content: Optional[str] = None
    audio_file_id: Optional[str] = None
    audio_duration_seconds: Optional[int] = None
    audio_local_path: Optional[Path] = None
    received_at: float = field(default_factory=time.time)


@dataclass
class OutboundResponseItem:
    """Represents an AI synthesized response ready to be dispatched back to Telegram."""

    inbound_id: str
    chat_id: int
    reply_to_message_id: Optional[int] = None
    text: str = ""
    parse_mode: Optional[str] = "HTML"
    reply_markup: Optional[Any] = None
    is_rate_limit_alert: bool = False
    dispatched_at: Optional[float] = None


class SlidingWindowRateLimiter:
    """Thread-safe and async-friendly sliding window rate limiter per user/chat."""

    def __init__(self, window_seconds: float = 60.0, max_requests: int = 5):
        self.window_seconds = window_seconds
        self.max_requests = max_requests
        self._history: Dict[str, List[float]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def is_allowed(self, client_key: Union[str, int]) -> Tuple[bool, float]:
        """Checks if client is allowed to send a request within the current window.

        Returns (is_allowed, retry_after_seconds).
        """
        key = str(client_key)
        now = time.time()
        cutoff = now - self.window_seconds

        async with self._lock:
            # Clean expired timestamps
            timestamps = [t for t in self._history[key] if t > cutoff]
            self._history[key] = timestamps

            if len(timestamps) >= self.max_requests:
                earliest = timestamps[0]
                retry_after = round(earliest + self.window_seconds - now, 1)
                return False, max(1.0, retry_after)

            timestamps.append(now)
            return True, 0.0

    async def reset(self, client_key: Optional[Union[str, int]] = None):
        """Resets the rate limiter for a specific key or all keys."""
        async with self._lock:
            if client_key is not None:
                self._history.pop(str(client_key), None)
            else:
                self._history.clear()


class MessageBroker:
    """Central broker managing the dual message_queue and response_queue pipeline."""

    def __init__(self, config: Optional[TelegramBotConfig] = None):
        self.config = config or get_telegram_config()
        self.message_queue: asyncio.Queue[InboundMessageItem] = asyncio.Queue(
            maxsize=self.config.message_queue_maxsize
        )
        self.response_queue: asyncio.Queue[OutboundResponseItem] = asyncio.Queue(
            maxsize=self.config.response_queue_maxsize
        )
        self.rate_limiter = SlidingWindowRateLimiter(
            window_seconds=self.config.rate_limit_window_seconds,
            max_requests=self.config.rate_limit_max_requests,
        )

    async def push_inbound(self, item: InboundMessageItem) -> Tuple[bool, Optional[str]]:
        """Validates rate limits and enqueues inbound item into message_queue.

        Returns:
            (True, None) if enqueued successfully.
            (False, "USER_RATE_LIMIT:<seconds>") if user exceeded rate limit.
            (False, "QUEUE_FULL") if the message queue is at maximum capacity.
        """
        # 1. User rate limit check (admins bypass rate limit)
        if not self.config.is_admin(item.user_id):
            client_key = f"{item.chat_id}:{item.user_id}"
            allowed, retry_after = await self.rate_limiter.is_allowed(client_key)
            if not allowed:
                return False, f"USER_RATE_LIMIT:{retry_after}"

        # 2. Queue fullness check
        if self.message_queue.full():
            return False, "QUEUE_FULL"

        try:
            self.message_queue.put_nowait(item)
            return True, None
        except asyncio.QueueFull:
            return False, "QUEUE_FULL"

    async def push_outbound(self, response: OutboundResponseItem) -> bool:
        """Pushes a synthesized response into response_queue without dropping."""
        await self.response_queue.put(response)
        return True

    def get_queue_status(self) -> Dict[str, Any]:
        """Returns instantaneous snapshot of both queues."""
        return {
            "message_queue_size": self.message_queue.qsize(),
            "message_queue_maxsize": self.message_queue.maxsize,
            "response_queue_size": self.response_queue.qsize(),
            "response_queue_maxsize": self.response_queue.maxsize,
            "is_busy": self.message_queue.qsize() > 0,
        }
