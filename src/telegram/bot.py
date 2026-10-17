"""AgriVoice-AI: Telegram Bot Application Runner.

Assembles Telegram Application, MessageBroker, AIProcessingWorker,
ResponseDispatcherWorker, and command/message/callback handlers into a complete, production-ready bot.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from src.admin.service import AdminService
from src.ai.harness import GenAIHarness, get_ai_harness
from src.telegram.config import TelegramBotConfig, get_telegram_config
from src.telegram.handlers import TelegramUpdateHandler
from src.telegram.queue import MessageBroker
from src.telegram.worker import AIProcessingWorker, ResponseDispatcherWorker

logger = logging.getLogger("agrivoice.telegram.bot")


class AgriVoiceTelegramBot:
    """Main AgriVoice Telegram Bot orchestrator."""

    def __init__(
        self,
        config: Optional[TelegramBotConfig] = None,
        harness: Optional[GenAIHarness] = None,
        admin_service: Optional[AdminService] = None,
    ):
        self.config = config or get_telegram_config()
        if not self.config.token:
            raise ValueError("TELEGRAM_TOKEN is missing. Please set it in .env or environment.")

        self.harness = harness or get_ai_harness()
        self.admin_service = admin_service or AdminService()

        # Build broker and workers
        self.broker = MessageBroker(config=self.config)

        # Build python-telegram-bot Application
        self.app = Application.builder().token(self.config.token).build()

        # Workers
        self.ai_worker = AIProcessingWorker(
            broker=self.broker,
            bot=self.app.bot,
            harness=self.harness,
            config=self.config,
        )
        self.dispatcher_worker = ResponseDispatcherWorker(
            broker=self.broker,
            bot=self.app.bot,
        )

        # Handlers
        self.handler = TelegramUpdateHandler(
            broker=self.broker,
            admin_service=self.admin_service,
            config=self.config,
        )

        self._setup_handlers()

    def _setup_handlers(self) -> None:
        """Registers command, message, and callback handlers with the application."""
        # /start command
        self.app.add_handler(CommandHandler("start", self.handler.handle_start))

        # Inline button callbacks for approve/reject
        self.app.add_handler(CallbackQueryHandler(self.handler.handle_callback_query))

        # Audio, Voice and Text message filter
        msg_filter = filters.VOICE | filters.AUDIO | filters.TEXT
        self.app.add_handler(MessageHandler(msg_filter, self.handler.handle_message))

    async def start(self) -> None:
        """Starts background workers and initializes the Telegram Application."""
        await self.ai_worker.start()
        await self.dispatcher_worker.start()
        await self.app.initialize()
        await self.app.start()
        await self.app.updater.start_polling()
        logger.info(f"AgriVoice Telegram Bot ({self.config.username}) is running.")

    async def stop(self) -> None:
        """Stops the bot and background workers gracefully."""
        if self.app.updater and self.app.updater.running:
            await self.app.updater.stop()
        if self.app.running:
            await self.app.stop()
        await self.app.shutdown()
        await self.ai_worker.stop()
        await self.dispatcher_worker.stop()
        logger.info("AgriVoice Telegram Bot stopped.")

    def run_polling(self) -> None:
        """Runs the bot in blocking polling mode (convenience wrapper for scripts)."""
        async def _main():
            await self.start()
            # Keep running until interrupted
            stop_event = asyncio.Event()
            try:
                await stop_event.wait()
            except (KeyboardInterrupt, asyncio.CancelledError):
                pass
            finally:
                await self.stop()

        try:
            asyncio.run(_main())
        except KeyboardInterrupt:
            logger.info("Bot execution terminated by user.")
