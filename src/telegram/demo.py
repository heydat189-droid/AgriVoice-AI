"""AgriVoice-AI: Telegram Bot Runner Script.

Runs the AgriVoice Telegram Bot with asynchronous message/response queues,
rate limiting, audio duration limits, and 2-Agent AI processing.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

# Ensure project root is in sys.path
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(WORKSPACE_ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(WORKSPACE_ROOT / ".env")
except ImportError:
    pass

from src.telegram.bot import AgriVoiceTelegramBot
from src.telegram.config import get_telegram_config

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("agrivoice.telegram")


def main():
    config = get_telegram_config()
    print("=" * 70)
    print("🌾 KHỞI CHẠY TELEGRAM BOT: AGRIVOICE-AI")
    print(f"🤖 Bot Username: {config.username}")
    print(f"👥 Admin IDs: {config.admin_user_ids or 'Mặc định (OWNER_1, ADMIN_1)'}")
    print(f"💬 Nhóm cho phép: {config.allowed_group_ids or 'Tất cả nhóm đã kích hoạt'}")
    print(f"⏱️ Giới hạn thời lượng Audio: {config.max_audio_duration_seconds} giây")
    print(f"🏷️ Tiền tố tin nhắn Text: '{config.admin_text_prefix}'")
    print(f"🚦 Hàng đợi Message: tối đa {config.message_queue_maxsize} tin")
    print("=" * 70)

    try:
        bot = AgriVoiceTelegramBot(config=config)
        print("✓ Đã khởi tạo thành công các Worker và Hàng đợi Queue.")
        print("Đang lắng nghe tin nhắn từ Telegram (Nhấn Ctrl+C để dừng)...")
        bot.run_polling()
    except Exception as exc:
        logger.error(f"Lỗi khởi chạy Bot: {exc}", exc_info=True)


if __name__ == "__main__":
    main()
