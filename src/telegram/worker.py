"""AgriVoice-AI: Asynchronous Background Workers.

Contains:
1. AIProcessingWorker: Dequeues messages, downloads audio, calls AI Harness (2 agents + DraftMemory),
   enforces rate pacing, and generates interactive approval cards.
2. ResponseDispatcherWorker: Dequeues responses and delivers them to Telegram chats.
"""

from __future__ import annotations

import asyncio
import html
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ExtBot

from src.ai.harness import GenAIHarness, HarnessResult, get_ai_harness
from src.ai.memory import (
    HierarchicalMemoryManager,
    UserState,
    get_hierarchical_memory_manager,
)
from src.telegram.config import TelegramBotConfig, get_telegram_config
from src.telegram.queue import InboundMessageItem, MessageBroker, OutboundResponseItem
logger = logging.getLogger("agrivoice.telegram.worker")


class AIProcessingWorker:
    """Consumes messages from message_queue, invokes AI Harness, and pushes to response_queue."""

    def __init__(
        self,
        broker: MessageBroker,
        bot: ExtBot,
        harness: Optional[GenAIHarness] = None,
        memory_manager: Optional[HierarchicalMemoryManager] = None,
        config: Optional[TelegramBotConfig] = None,
    ):
        self.broker = broker
        self.bot = bot
        self.harness = harness or get_ai_harness()
        self.memory_manager = memory_manager or get_hierarchical_memory_manager()
        self.config = config or get_telegram_config()
        self.running = False
        self._task: Optional[asyncio.Task] = None
        self._watchdog_task: Optional[asyncio.Task] = None
        self._user_last_chat: Dict[str, int] = {}

    async def start(self) -> None:
        """Starts the worker task loop and watchdog loop."""
        if self.running:
            return
        self.running = True
        self._task = asyncio.create_task(self._run_loop())
        self._watchdog_task = asyncio.create_task(self._run_watchdog_loop())
        logger.info("AIProcessingWorker and Watchdog started.")

    async def stop(self) -> None:
        """Stops the worker and watchdog gracefully."""
        self.running = False
        for t in (self._task, self._watchdog_task):
            if t:
                t.cancel()
                try:
                    await t
                except asyncio.CancelledError:
                    pass
        logger.info("AIProcessingWorker and Watchdog stopped.")

    async def _run_watchdog_loop(self) -> None:
        """Watchdog loop: auto-submits drafts for users whose 60s clarification window expired."""
        while self.running:
            try:
                await asyncio.sleep(5.0)
                auto_submitted = self.harness.check_and_trigger_watchdog(
                    memory_manager=self.memory_manager,
                )
                for session, staged_ids in auto_submitted:
                    chat_id = self._user_last_chat.get(session.user_id)
                    if chat_id:
                        user_tag = f"@{session.username}" if session.username else session.full_name
                        notice = (
                            f"⏰ <b>{user_tag}:</b> Đã hết thời gian chờ bổ sung (60s). "
                            f"Hệ thống đã tự động gửi <b>{len(staged_ids)}</b> sự kiện đã ghi nhận cho Chủ trang trại phê duyệt."
                        )
                        await self.broker.push_outbound(
                            OutboundResponseItem(
                                inbound_id=f"watchdog_{session.user_id}",
                                chat_id=chat_id,
                                text=notice,
                            )
                        )
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error(f"Error in Watchdog loop: {exc}", exc_info=True)
                await asyncio.sleep(5.0)

    async def _run_loop(self) -> None:
        while self.running:
            try:
                # Wait for next inbound item
                item = await self.broker.message_queue.get()

                # Process item in threadpool to avoid blocking asyncio event loop
                outbound = await self._process_item(item)

                # Push to response queue
                await self.broker.push_outbound(outbound)
                self.broker.message_queue.task_done()

                # Enforce pacing delay between AI calls to protect free-tier quotas (15 RPM)
                if self.config.ai_request_interval_seconds > 0:
                    await asyncio.sleep(self.config.ai_request_interval_seconds)

            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error(f"Error in AIProcessingWorker loop: {exc}", exc_info=True)
                await asyncio.sleep(1.0)
    async def _process_item(self, item: InboundMessageItem) -> OutboundResponseItem:
        uid = str(item.user_id)
        self._user_last_chat[uid] = item.chat_id
        sender_id = f"TG_{item.user_id}"

        # 1. Audio processing
        if item.msg_type in ("VOICE", "AUDIO"):
            local_audio_path = await self._download_telegram_audio(item)
            if not local_audio_path:
                return OutboundResponseItem(
                    inbound_id=item.id,
                    chat_id=item.chat_id,
                    reply_to_message_id=item.message_id,
                    text="❌ <i>Không thể tải file âm thanh từ Telegram. Vui lòng thử lại.</i>",
                )

            # Run 2-agent voice processing with HierarchicalMemoryManager
            result: HarnessResult = await asyncio.to_thread(
                self.harness.process_voice,
                audio=local_audio_path,
                sender_id=sender_id,
                audio_path_hint=str(local_audio_path),
                user_id=uid,
                full_name=item.full_name,
                username=item.username,
                memory_manager=self.memory_manager,
                auto_stage=True,
            )

        # 2. Text processing
        else:
            text_query = item.content or ""
            result: HarnessResult = await asyncio.to_thread(
                self.harness.process_text,
                text_query=text_query,
                sender_id=sender_id,
                user_id=uid,
                full_name=item.full_name,
                username=item.username,
                memory_manager=self.memory_manager,
                auto_stage=True,
            )

        # Format beautiful Telegram response with interactive buttons
        return self._format_outbound_response(item, result)
    async def _download_telegram_audio(self, item: InboundMessageItem) -> Optional[Path]:
        """Downloads Telegram voice or audio file to local storage."""
        if not item.audio_file_id:
            return None

        try:
            storage_dir = self.config.audio_storage_dir
            storage_dir.mkdir(parents=True, exist_ok=True)
            local_path = storage_dir / f"tg_{item.chat_id}_{item.message_id}_{item.id}.ogg"

            # Download file from Telegram Bot API
            tg_file = await self.bot.get_file(item.audio_file_id)
            await tg_file.download_to_drive(custom_path=str(local_path))
            return local_path
        except Exception as exc:
            logger.error(f"Failed to download audio for item {item.id}: {exc}", exc_info=True)
            return None

    def _format_outbound_response(self, item: InboundMessageItem, result: HarnessResult) -> OutboundResponseItem:
        if not result.success:
            err_msg = html.escape(result.error or result.reply_text)
            text = f"❌ <b>Hệ thống gặp lỗi:</b>\n{err_msg}"
            return OutboundResponseItem(
                inbound_id=item.id,
                chat_id=item.chat_id,
                reply_to_message_id=item.message_id,
                text=text,
            )

        # Clean escaped reply
        lines = []
        if result.raw_transcript and item.msg_type in ("VOICE", "AUDIO"):
            safe_trans = html.escape(result.raw_transcript.strip())
            lines.append(f"🗣️ <b>Khẩu lệnh:</b> <i>\"{safe_trans}\"</i>\n")

        safe_reply = html.escape(result.reply_text.strip())
        lines.append(f"🤖 <b>Kết quả xử lý:</b>\n{safe_reply}")

        # Add interactive buttons
        reply_markup = None
        buttons = []

        # Case 1: Clarification needed -> offer immediate manual submit button
        if result.clarification_needed:
            buttons.append([
                InlineKeyboardButton("🚀 Chốt & Gửi duyệt ngay", callback_data=f"sub:{item.user_id}"),
            ])

        # Case 2: Events staged -> offer direct admin approval buttons
        if result.event_ids:
            staged_count = len(result.event_ids)
            lines.append(f"\n📦 <i>Đã tạo {staged_count} sự kiện chờ Chủ vườn duyệt trên hàng đợi.</i>")
            for eid in result.event_ids[:3]:
                buttons.append([
                    InlineKeyboardButton(f"✅ Duyệt #{eid}", callback_data=f"app:{eid}"),
                    InlineKeyboardButton(f"❌ Từ chối #{eid}", callback_data=f"rej:{eid}"),
                ])

        if buttons:
            reply_markup = InlineKeyboardMarkup(buttons)
        return OutboundResponseItem(
            inbound_id=item.id,
            chat_id=item.chat_id,
            reply_to_message_id=item.message_id,
            text="\n".join(lines),
            reply_markup=reply_markup,
        )


class ResponseDispatcherWorker:
    """Consumes outbound responses from response_queue and sends them to Telegram."""

    def __init__(self, broker: MessageBroker, bot: ExtBot):
        self.broker = broker
        self.bot = bot
        self.running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        if self.running:
            return
        self.running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("ResponseDispatcherWorker started.")

    async def stop(self) -> None:
        self.running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("ResponseDispatcherWorker stopped.")

    async def _run_loop(self) -> None:
        while self.running:
            try:
                outbound = await self.broker.response_queue.get()
                await self._dispatch(outbound)
                self.broker.response_queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error(f"Error in ResponseDispatcherWorker: {exc}", exc_info=True)
                await asyncio.sleep(0.5)

    async def _dispatch(self, outbound: OutboundResponseItem) -> None:
        try:
            await self.bot.send_message(
                chat_id=outbound.chat_id,
                text=outbound.text,
                reply_to_message_id=outbound.reply_to_message_id,
                parse_mode=outbound.parse_mode,
                reply_markup=outbound.reply_markup,
            )
        except Exception as exc:
            logger.error(f"Failed to send Telegram message to chat {outbound.chat_id}: {exc}")
