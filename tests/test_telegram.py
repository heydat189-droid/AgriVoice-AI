"""AgriVoice-AI: Telegram Integration Test Suite.

Verifies:
1. TelegramBotConfig whitelist validation and content limits.
2. Dual Queue architecture (message_queue and response_queue).
3. Queue fullness constraint enforcement and rejection.
4. Sliding-window user rate limiting and retry-after calculation.
5. Inbound filtering (audio duration <= 90s, text @admin prefix).
6. Outbound response generation with interactive inline approval buttons.
"""

from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from src.telegram.config import TelegramBotConfig
from src.telegram.handlers import TelegramUpdateHandler
from src.telegram.queue import (
    InboundMessageItem,
    MessageBroker,
    OutboundResponseItem,
    SlidingWindowRateLimiter,
)
from src.telegram.worker import AIProcessingWorker


class TestTelegramIntegration(unittest.TestCase):
    def setUp(self):
        self.config = TelegramBotConfig(
            token="DUMMY_TOKEN_FOR_TESTING_12345",
            username="@test_bot",
            admin_user_ids={"1001", "1002"},
            allowed_group_ids={"-100999"},
            max_audio_duration_seconds=90,
            admin_text_prefix="@admin",
            message_queue_maxsize=3,
            response_queue_maxsize=10,
            rate_limit_window_seconds=2.0,
            rate_limit_max_requests=2,
            ai_request_interval_seconds=0.0,
        )
        self.broker = MessageBroker(config=self.config)

    def test_01_whitelist_filtering(self):
        """Test chat and user whitelist verification."""
        # 1. Admin in private chat -> ALLOWED
        self.assertTrue(self.config.is_chat_allowed(chat_id=1001, chat_type="private", user_id=1001))

        # 2. Non-admin in private chat -> DENIED
        self.assertFalse(self.config.is_chat_allowed(chat_id=5555, chat_type="private", user_id=5555))

        # 3. Allowed group -> ALLOWED
        self.assertTrue(self.config.is_chat_allowed(chat_id=-100999, chat_type="supergroup", user_id=5555))

        # 4. Unlisted group -> DENIED
        self.assertFalse(self.config.is_chat_allowed(chat_id=-100888, chat_type="supergroup", user_id=5555))

    def test_02_sliding_window_rate_limiter(self):
        """Test sliding window rate limiting limits requests and calculates retry_after."""
        async def _test():
            limiter = SlidingWindowRateLimiter(window_seconds=1.0, max_requests=2)
            key = "user_123"

            # 1st request -> allowed
            ok1, _ = await limiter.is_allowed(key)
            self.assertTrue(ok1)

            # 2nd request -> allowed
            ok2, _ = await limiter.is_allowed(key)
            self.assertTrue(ok2)

            # 3rd request -> rate limit exceeded
            ok3, retry = await limiter.is_allowed(key)
            self.assertFalse(ok3)
            self.assertGreater(retry, 0.0)

            # Wait window expiry
            await asyncio.sleep(1.1)
            ok4, _ = await limiter.is_allowed(key)
            self.assertTrue(ok4)

        asyncio.run(_test())

    def test_03_queue_fullness_and_push_inbound(self):
        """Test broker rejects new items with QUEUE_FULL when capacity is reached."""
        async def _test():
            # maxsize is 3
            item1 = InboundMessageItem(chat_id=1001, user_id=1001, msg_type="TEXT", content="msg 1")
            item2 = InboundMessageItem(chat_id=1001, user_id=1001, msg_type="TEXT", content="msg 2")
            item3 = InboundMessageItem(chat_id=1001, user_id=1001, msg_type="TEXT", content="msg 3")
            item4 = InboundMessageItem(chat_id=1001, user_id=1001, msg_type="TEXT", content="msg 4")

            ok1, _ = await self.broker.push_inbound(item1)
            ok2, _ = await self.broker.push_inbound(item2)
            ok3, _ = await self.broker.push_inbound(item3)
            self.assertTrue(ok1 and ok2 and ok3)
            self.assertEqual(self.broker.message_queue.qsize(), 3)

            # 4th item hits QUEUE_FULL
            ok4, err4 = await self.broker.push_inbound(item4)
            self.assertFalse(ok4)
            self.assertEqual(err4, "QUEUE_FULL")

        asyncio.run(_test())

    def test_04_message_filter_rules(self):
        """Test handler filters: ignores non-prefix text, rejects audio > 90s."""
        async def _test():
            handler = TelegramUpdateHandler(broker=self.broker, config=self.config)

            # 1. Non-admin text without @admin prefix -> IGNORED (not pushed to queue)
            mock_update1 = MagicMock()
            mock_update1.effective_chat.id = -100999
            mock_update1.effective_chat.type = "supergroup"
            mock_update1.effective_user.id = 5555
            mock_update1.effective_message.text = "Chào buổi sáng cả nhà"
            mock_update1.effective_message.voice = None
            mock_update1.effective_message.audio = None

            await handler.handle_message(mock_update1, MagicMock())
            self.assertEqual(self.broker.message_queue.qsize(), 0)

            # 2. Audio > 90 seconds -> REJECTED with reply warning
            mock_update2 = MagicMock()
            mock_update2.effective_chat.id = -100999
            mock_update2.effective_chat.type = "supergroup"
            mock_update2.effective_user.id = 5555
            mock_update2.effective_message.text = None
            mock_update2.effective_message.voice.duration = 120  # 2 minutes > 90s
            mock_update2.effective_message.audio = None
            mock_update2.effective_message.reply_text = AsyncMock()

            await handler.handle_message(mock_update2, MagicMock())
            mock_update2.effective_message.reply_text.assert_called_once()
            self.assertEqual(self.broker.message_queue.qsize(), 0)

            # 3. Text with @admin prefix in allowed group -> ACCEPTED into queue
            mock_update3 = MagicMock()
            mock_update3.effective_chat.id = -100999
            mock_update3.effective_chat.type = "supergroup"
            mock_update3.effective_user.id = 5555
            mock_update3.effective_message.text = "@admin xuất 2 bao phân cho khu A"
            mock_update3.effective_message.voice = None
            mock_update3.effective_message.audio = None

            await handler.handle_message(mock_update3, MagicMock())
            self.assertEqual(self.broker.message_queue.qsize(), 1)
            queued_item = await self.broker.message_queue.get()
            self.assertEqual(queued_item.content, "xuất 2 bao phân cho khu A")

        asyncio.run(_test())

    def test_05_outbound_formatting_and_inline_buttons(self):
        """Test AIProcessingWorker formats response and attaches approval inline buttons for staged events."""
        from src.ai.harness import HarnessResult

        worker = AIProcessingWorker(
            broker=self.broker,
            bot=MagicMock(),
            harness=MagicMock(),
            config=self.config,
        )

        inbound = InboundMessageItem(
            id="item123",
            chat_id=-100999,
            message_id=42,
            user_id=1001,
            msg_type="VOICE",
        )

        result = HarnessResult(
            success=True,
            reply_text="Hệ thống ghi nhận:\n- [Nhập kho]: 10 bao phân Quế Lâm.",
            raw_transcript="Mua 10 bao phân Quế Lâm",
            event_ids=[101, 102],
        )

        outbound = worker._format_outbound_response(inbound, result)
        self.assertIn("Khẩu lệnh:", outbound.text)
        self.assertIn("10 bao phân Quế Lâm", outbound.text)
        self.assertIn("Đã tạo 2 sự kiện", outbound.text)

        # Has inline buttons for approving event #101
        self.assertIsNotNone(outbound.reply_markup)
        buttons = outbound.reply_markup.inline_keyboard
        self.assertEqual(buttons[0][0].callback_data, "app:101")
        self.assertEqual(buttons[0][1].callback_data, "rej:101")


if __name__ == "__main__":
    unittest.main()
