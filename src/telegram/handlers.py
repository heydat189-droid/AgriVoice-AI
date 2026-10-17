"""AgriVoice-AI: Telegram Update Handlers & Callback Router.

Filters updates strictly based on constraints:
- Only Audio (<= 90 seconds) and Text with prefix '@admin' (or from admin in private).
- Whitelist validation (only admin users and configured group chats).
- Callback query handling for inline approval / rejection buttons.
"""

from __future__ import annotations

import logging
from typing import Optional

from telegram import Update
from telegram.ext import ContextTypes

from src.admin.service import AdminService
from src.telegram.config import TelegramBotConfig, get_telegram_config
from src.telegram.queue import InboundMessageItem, MessageBroker, OutboundResponseItem

logger = logging.getLogger("agrivoice.telegram.handlers")


class TelegramUpdateHandler:
    """Handles and routes Telegram messages and callback queries."""

    def __init__(
        self,
        broker: MessageBroker,
        admin_service: Optional[AdminService] = None,
        config: Optional[TelegramBotConfig] = None,
    ):
        self.broker = broker
        self.admin_service = admin_service or AdminService()
        self.config = config or get_telegram_config()

    async def handle_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handles /start command with user-friendly instructions."""
        if not update.effective_message:
            return

        user = update.effective_user
        chat = update.effective_chat
        user_name = user.first_name if user else "Nhà nông"

        text = (
            f"🌾 <b>Xin chào {user_name}!</b> Tôi là trợ lý nông trại <b>AgriVoice-AI</b>.\n\n"
            "Tôi giúp bác ghi chép nhật ký, xuất nhập kho và theo dõi thu chi bằng giọng nói.\n\n"
            "🎙️ <b>CÁCH SỬ DỤNG:</b>\n"
            "• <b>Gửi tin nhắn thoại (Voice note):</b> Nhấn giữ nút ghi âm và nói tự nhiên (dưới 1 phút 30 giây).\n"
            "• <b>Gửi tin nhắn văn bản:</b> Bắt đầu bằng tiền tố <code>@admin</code> (ví dụ: <code>@admin xuất 2 bao phân cho khu A</code>).\n\n"
            "⚡ <i>Mọi thay đổi dữ liệu sẽ được chuyển đến hàng đợi để Chủ trang trại phê duyệt trước khi ghi sổ chính thức.</i>"
        )
        await update.effective_message.reply_text(text=text, parse_mode="HTML")

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Filters and enqueues messages strictly matching whitelist and syntax rules."""
        message = update.effective_message
        if not message or not update.effective_chat or not update.effective_user:
            return

        chat = update.effective_chat
        user = update.effective_user

        # ----------------------------------------------------------------------
        # 1. Whitelist Check: Only allowed groups and admin users
        # ----------------------------------------------------------------------
        is_allowed = self.config.is_chat_allowed(
            chat_id=chat.id,
            chat_type=chat.type,
            user_id=user.id,
        )
        if not is_allowed:
            logger.info(f"Ignored message from unauthorized chat {chat.id} / user {user.id}")
            return

        # ----------------------------------------------------------------------
        # 2. Extract Message Type & Enforce Constraints
        # ----------------------------------------------------------------------
        item: Optional[InboundMessageItem] = None

        # A. Voice Message (.ogg voice note)
        if message.voice:
            duration = message.voice.duration
            if duration > self.config.max_audio_duration_seconds:
                await message.reply_text(
                    f"⚠️ <i>File ghi âm dài {duration}s vượt quá giới hạn tối đa "
                    f"({self.config.max_audio_duration_seconds}s). Vui lòng gửi đoạn ngắn hơn.</i>",
                    parse_mode="HTML",
                )
                return

            item = InboundMessageItem(
                chat_id=chat.id,
                message_id=message.message_id,
                user_id=user.id,
                username=user.username,
                full_name=user.full_name or "",
                chat_type=chat.type,
                msg_type="VOICE",
                audio_file_id=message.voice.file_id,
                audio_duration_seconds=duration,
            )

        # B. Audio Message (uploaded audio file)
        elif message.audio:
            duration = message.audio.duration or 0
            if duration > self.config.max_audio_duration_seconds:
                await message.reply_text(
                    f"⚠️ <i>File âm thanh dài {duration}s vượt quá giới hạn cho phép ({self.config.max_audio_duration_seconds}s).</i>",
                    parse_mode="HTML",
                )
                return

            item = InboundMessageItem(
                chat_id=chat.id,
                message_id=message.message_id,
                user_id=user.id,
                username=user.username,
                full_name=user.full_name or "",
                chat_type=chat.type,
                msg_type="AUDIO",
                audio_file_id=message.audio.file_id,
                audio_duration_seconds=duration,
            )

        # C. Text Message: Only process text with prefix @admin (or any text in private admin chat)
        elif message.text:
            raw_text = message.text.strip()
            is_admin_user = self.config.is_admin(user.id)
            is_private = chat.type == "private"
            has_prefix = raw_text.lower().startswith(self.config.admin_text_prefix.lower())

            if not (has_prefix or (is_admin_user and is_private)):
                # Ignore normal chat chatter that doesn't mention @admin
                return

            # Strip @admin prefix
            clean_text = raw_text
            if has_prefix:
                clean_text = raw_text[len(self.config.admin_text_prefix):].strip()

            if not clean_text:
                return

            item = InboundMessageItem(
                chat_id=chat.id,
                message_id=message.message_id,
                user_id=user.id,
                username=user.username,
                full_name=user.full_name or "",
                chat_type=chat.type,
                msg_type="TEXT",
                content=clean_text,
            )

        else:
            # Other unsupported types (stickers, documents, videos)
            return

        # ----------------------------------------------------------------------
        # 3. Enqueue Message Item (with Queue Limit & Rate Limit Check)
        # ----------------------------------------------------------------------
        ok, err = await self.broker.push_inbound(item)
        if not ok:
            if err and err.startswith("USER_RATE_LIMIT"):
                retry_sec = err.split(":")[-1]
                await message.reply_text(
                    f"⏳ <b>Thông báo tần suất:</b> Bạn đang gửi yêu cầu quá nhanh. "
                    f"Vui lòng đợi <b>{retry_sec}s</b> trước khi gửi tiếp.",
                    parse_mode="HTML",
                )
            elif err == "QUEUE_FULL":
                await message.reply_text(
                    "🚦 <b>Hệ thống đang bận:</b> Hàng đợi xử lý đang đầy. "
                    "Vui lòng thử lại sau giây lát.",
                    parse_mode="HTML",
                )
            return

    async def handle_callback_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handles inline buttons for event approval and rejection."""
        query = update.callback_query
        if not query or not query.data or not query.from_user:
            return

        user = query.from_user
        data = query.data
        try:
            action, event_id_str = data.split(":", 1)
        except Exception:
            return

        # Action: Manual submit draft records
        if action == "sub":
            target_uid = event_id_str
            can_approve, _ = self.admin_service.collaborators.check_admin_privilege(str(user.id))
            if str(user.id) != target_uid and not can_approve:
                await query.answer("❌ Chỉ người tạo bản ghi hoặc Quản trị viên mới được chốt nạp!", show_alert=True)
                return

            await query.answer("Đang nạp các bản ghi...")
            from src.ai.harness import get_ai_harness
            harness = get_ai_harness()
            staged_ids, err = harness.submit_user_draft(
                user_id=target_uid,
                reason="Chốt chủ động bởi người dùng qua nút bấm",
            )
            if staged_ids:
                await query.edit_message_text(
                    text=f"🚀 <b>Đã chốt và nạp thành công {len(staged_ids)} sự kiện lên hàng đợi chờ Chủ trang trại duyệt!</b>\n"
                         f"<i>Mã sự kiện: {', '.join(f'#{i}' for i in staged_ids)}</i>",
                    parse_mode="HTML",
                )
            else:
                await query.answer("Không có bản ghi nào chờ gửi hoặc đã nạp trước đó.", show_alert=True)
            return

        # Actions app / rej require Admin privileges
        can_approve, reason = self.admin_service.collaborators.check_admin_privilege(str(user.id))
        if not can_approve:
            await query.answer("❌ Chỉ Chủ trang trại / Quản trị viên mới có quyền phê duyệt sự kiện!", show_alert=True)
            return

        await query.answer()
        try:
            event_id = int(event_id_str)
        except Exception:
            return
        if action == "app":
            # Approve event
            ok, err = self.admin_service.approve_event(
                event_id=event_id,
                admin_telegram_id=str(user.id),
                review_notes="Duyệt nhanh qua Telegram inline button",
            )
            if ok:
                await query.edit_message_text(
                    text=f"✅ <b>Sự kiện #{event_id} đã được phê duyệt thành công bởi {user.first_name}!</b>\n"
                         f"<i>Dữ liệu đã được nạp chính thức vào hệ thống Core DB.</i>",
                    parse_mode="HTML",
                )
            else:
                await query.edit_message_text(
                    text=f"❌ <b>Duyệt sự kiện #{event_id} thất bại:</b>\n<code>{err}</code>",
                    parse_mode="HTML",
                )

        elif action == "rej":
            # Reject event
            ok, err = self.admin_service.reject_event(
                event_id=event_id,
                review_notes=f"Từ chối bởi {user.first_name} qua Telegram button",
                admin_telegram_id=str(user.id),
            )
            if ok:
                await query.edit_message_text(
                    text=f"🚫 <b>Sự kiện #{event_id} đã bị từ chối bởi {user.first_name}.</b>\n"
                         f"<i>(Lưu vết kiểm toán REJECTED được bảo toàn).</i>",
                    parse_mode="HTML",
                )
            else:
                await query.edit_message_text(
                    text=f"❌ <b>Từ chối sự kiện #{event_id} thất bại:</b>\n<code>{err}</code>",
                    parse_mode="HTML",
                )
