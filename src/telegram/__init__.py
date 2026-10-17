"""AgriVoice-AI: Telegram Integration Package.

Provides Telegram bot application, asynchronous queuing, rate limiting,
audio downloading, and AI processing workers.
"""

from __future__ import annotations

from src.telegram.bot import AgriVoiceTelegramBot
from src.telegram.config import TelegramBotConfig, get_telegram_config
from src.telegram.handlers import TelegramUpdateHandler
from src.telegram.queue import (
    InboundMessageItem,
    MessageBroker,
    OutboundResponseItem,
    SlidingWindowRateLimiter,
)
from src.telegram.worker import AIProcessingWorker, ResponseDispatcherWorker

__all__ = [
    "AgriVoiceTelegramBot",
    "TelegramBotConfig",
    "get_telegram_config",
    "MessageBroker",
    "InboundMessageItem",
    "OutboundResponseItem",
    "SlidingWindowRateLimiter",
    "AIProcessingWorker",
    "ResponseDispatcherWorker",
    "TelegramUpdateHandler",
]
