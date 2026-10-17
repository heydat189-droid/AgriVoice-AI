"""AgriVoice-AI: Telegram Bot Configuration.

Reads environment variables and defines whitelist boundaries, queue size limits,
rate limits, and audio duration limits as specified.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Set, Union
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass


def _parse_id_set(raw: Optional[str]) -> Set[str]:
    """Parses a comma/semicolon-separated string of IDs into a normalized string set."""
    if not raw:
        return set()
    return {
        item.strip()
        for item in raw.replace(";", ",").split(",")
        if item.strip()
    }


@dataclass
class TelegramBotConfig:
    """Consolidated configuration for AgriVoice Telegram Bot."""

    token: str = field(
        default_factory=lambda: os.getenv("TELEGRAM_TOKEN", "").strip()
    )
    username: str = field(
        default_factory=lambda: os.getenv("TELEGRAM_USERNAME", "@argi_voice_bot").strip()
    )

    # Whitelist boundaries: Admin users and allowed group chat IDs
    admin_user_ids: Set[str] = field(
        default_factory=lambda: _parse_id_set(os.getenv("TELEGRAM_ADMIN_IDS", "OWNER_1,ADMIN_1"))
    )
    allowed_group_ids: Set[str] = field(
        default_factory=lambda: _parse_id_set(os.getenv("TELEGRAM_ALLOWED_GROUPS", ""))
    )

    # If allow_all_private is True, any registered admin or collaborator can chat privately
    allow_db_collaborators: bool = True

    # Content limits
    max_audio_duration_seconds: int = 90  # Max 1m30s per requirement
    admin_text_prefix: str = "@admin"     # Only text starting with this prefix is processed

    # Async Queue & Rate Limiter Configuration
    message_queue_maxsize: int = 30       # Limit on message queue capacity
    response_queue_maxsize: int = 100     # Limit on response queue capacity
    rate_limit_window_seconds: float = 60.0  # Sliding window for user rate limiting
    rate_limit_max_requests: int = 5      # Max requests per window per user/chat

    # Pacing to protect Google GenAI 15 RPM free tier on Raspberry Pi
    ai_request_interval_seconds: float = 2.0

    # Local audio storage directory
    audio_storage_dir: Path = field(
        default_factory=lambda: Path(os.getenv("TELEGRAM_AUDIO_DIR", "data/telegram_audio")).resolve()
    )

    def is_chat_allowed(self, chat_id: Union[int, str], chat_type: str, user_id: Union[int, str]) -> bool:
        """Determines if a message from chat_id/user_id is permitted by whitelist."""
        s_user_id = str(user_id)
        s_chat_id = str(chat_id)

        # 1. Admin users are always allowed (in private or in groups)
        if s_user_id in self.admin_user_ids:
            return True

        # 2. In groups / supergroups: check if group is in allowed whitelist
        if chat_type in ("group", "supergroup"):
            return s_chat_id in self.allowed_group_ids

        # 3. In private chat: only admins (or collaborators if configured)
        if chat_type == "private":
            return s_user_id in self.admin_user_ids

        return False

    def is_admin(self, user_id: Union[int, str]) -> bool:
        """Checks if a user is an admin."""
        return str(user_id) in self.admin_user_ids


_default_config: Optional[TelegramBotConfig] = None


def get_telegram_config() -> TelegramBotConfig:
    """Returns the singleton TelegramBotConfig instance."""
    global _default_config
    if _default_config is None:
        _default_config = TelegramBotConfig()
    return _default_config
