"""AgriVoice-AI: Hierarchical Stateless Memory & Multi-Conversation Management.

Implements the architecture specified in 'notes/Multiconversation-stateless.md':
1. Group-level shared conversation history (`conversation_history` sliding window).
2. Isolated per-user working session memory (`person_history` by USER_ID):
   - User state lifecycle (IDLE, DRAFTING, WAITING_CLARIFICATION, SUBMITTED).
   - In-memory draft records buffer (`draft_memory["draft_records"]`).
   - Isolated user dialogue history.
   - Watchdog timeout (60s) tracking for automatic submission.
3. Memory Router & Context Builder ensuring interleaved group chats do not leak context across workers.
"""

from __future__ import annotations

import contextvars
import time
from dataclasses import dataclass, field, fields
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Type, Union
from src.db.connection import get_db, get_db_path
from src.db.models import (
    BaseRecord,
    FinancialTransaction,
    Harvest,
    InventoryTransaction,
    Issue,
    ProductionCycle,
    ProductionLog,
    Task,
)
from src.db.pending_service import stage_voice_event

# Mapping of record type names to concrete BaseRecord classes
RECORD_CLASS_MAP: Dict[str, Type[BaseRecord]] = {
    "ProductionLog": ProductionLog,
    "production_logs": ProductionLog,
    "InventoryTransaction": InventoryTransaction,
    "inventory_transactions": InventoryTransaction,
    "ProductionCycle": ProductionCycle,
    "production_cycles": ProductionCycle,
    "Issue": Issue,
    "issues": Issue,
    "FinancialTransaction": FinancialTransaction,
    "financial_transactions": FinancialTransaction,
    "Task": Task,
    "tasks": Task,
    "Harvest": Harvest,
    "harvests": Harvest,
}


class UserState(str, Enum):
    """Lifecycle states of a user's working session in group chat."""

    IDLE = "IDLE"
    DRAFTING = "DRAFTING"
    WAITING_CLARIFICATION = "WAITING_CLARIFICATION"
    SUBMITTED = "SUBMITTED"


@dataclass
class GroupMessageTurn:
    """A single turn recorded in the shared group conversation window."""

    user_id: str
    speaker_name: str
    role: str  # "user" | "model"
    text: str
    timestamp: float = field(default_factory=time.time)

    def to_display_string(self) -> str:
        if self.role == "model":
            return f"[AI Trợ Lý]: {self.text}"
        return f"[{self.user_id} - {self.speaker_name}]: {self.text}"


@dataclass
class UserSessionMemory:
    """Isolated memory context for a specific user in the farm."""

    user_id: str
    full_name: str = ""
    username: Optional[str] = None
    state: UserState = UserState.IDLE
    last_active_at: float = field(default_factory=time.time)
    draft_memory: Dict[str, Any] = field(default_factory=lambda: {"draft_records": []})
    history: List[Any] = field(default_factory=list)  # Content objects or dicts
    last_reply_text: str = ""
    clarification_needed: bool = False
    clarification_items: List[str] = field(default_factory=list)

    @property
    def draft_records(self) -> List[Dict[str, Any]]:
        return self.draft_memory.setdefault("draft_records", [])

    def reset_draft(self, new_state: UserState = UserState.IDLE) -> None:
        """Resets working draft buffer while preserving dialogue history."""
        self.draft_memory = {"draft_records": []}
        self.state = new_state
        self.clarification_needed = False
        self.clarification_items.clear()


# ==============================================================================
# Active ContextVar for Tool Execution
# ==============================================================================

_active_memory_context: contextvars.ContextVar[Optional[Dict[str, Any]]] = (
    contextvars.ContextVar("_active_memory_context", default=None)
)


def get_active_draft_memory() -> Dict[str, Any]:
    """Returns the current active in-memory draft dictionary, creating one if not set."""
    mem = _active_memory_context.get()
    if mem is None:
        mem = {"draft_records": []}
        _active_memory_context.set(mem)
    elif "draft_records" not in mem:
        mem["draft_records"] = []
    return mem


def set_active_draft_memory(mem: Dict[str, Any]):
    """Sets the active in-memory draft dictionary for the current context."""
    if "draft_records" not in mem:
        mem["draft_records"] = []
    return _active_memory_context.set(mem)


def add_draft_record(
    record_type: str,
    data: Dict[str, Any],
    record: Optional[BaseRecord] = None,
    memory: Optional[Dict[str, Any]] = None,
) -> int:
    """Adds a new draft record into working memory and returns its unique draft ID."""
    target_mem = memory if memory is not None else get_active_draft_memory()
    records: List[Dict[str, Any]] = target_mem.setdefault("draft_records", [])

    next_id = max([r.get("id", 0) for r in records], default=0) + 1
    clean_data = {k: v for k, v in data.items() if v is not None and k not in ("created_at", "updated_at")}

    entry = {
        "id": next_id,
        "type": record_type,
        "data": clean_data,
        "_record": record,
    }
    records.append(entry)
    return next_id


def update_draft_record(
    record_id: int,
    updates: Dict[str, Any],
    memory: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Updates fields of an existing draft record in working memory."""
    target_mem = memory if memory is not None else get_active_draft_memory()
    records: List[Dict[str, Any]] = target_mem.setdefault("draft_records", [])

    for r in records:
        if r.get("id") == record_id:
            r["data"].update(updates)
            cls = RECORD_CLASS_MAP.get(r.get("type", ""))
            if cls:
                try:
                    valid_keys = {f.name for f in fields(cls)}
                    filtered_data = {k: v for k, v in r["data"].items() if k in valid_keys}
                    r["_record"] = cls(**filtered_data)
                except Exception:
                    pass
            return {
                "success": True,
                "record_id": record_id,
                "type": r.get("type"),
                "updated_fields": list(updates.keys()),
                "current_data": r["data"],
            }

    return {
        "success": False,
        "error": f"Không tìm thấy bản ghi draft #{record_id} trong bộ nhớ.",
    }


def remove_draft_record(
    record_id: int,
    reason: Optional[str] = None,
    memory: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Removes a draft record from working memory."""
    target_mem = memory if memory is not None else get_active_draft_memory()
    records: List[Dict[str, Any]] = target_mem.setdefault("draft_records", [])

    for idx, r in enumerate(records):
        if r.get("id") == record_id:
            removed = records.pop(idx)
            return {
                "success": True,
                "removed_id": record_id,
                "removed_type": removed.get("type"),
                "reason": reason or "Người dùng yêu cầu xóa hoặc thay thế",
            }

    return {
        "success": False,
        "error": f"Không tìm thấy bản ghi draft #{record_id} trong bộ nhớ để xóa.",
    }


def get_draft_records(memory: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """Returns list of active draft records in working memory."""
    target_mem = memory if memory is not None else get_active_draft_memory()
    records: List[Dict[str, Any]] = target_mem.get("draft_records", [])
    return [
        {
            "id": r.get("id"),
            "type": r.get("type"),
            "data": dict(r.get("data", {})),
        }
        for r in records
    ]


def to_base_records(memory: Optional[Dict[str, Any]] = None) -> List[BaseRecord]:
    """Converts active draft records in memory into concrete BaseRecord instances."""
    target_mem = memory if memory is not None else get_active_draft_memory()
    records: List[Dict[str, Any]] = target_mem.get("draft_records", [])
    output: List[BaseRecord] = []

    for r in records:
        if r.get("_record") and isinstance(r["_record"], BaseRecord):
            output.append(r["_record"])
            continue

        rtype = r.get("type", "")
        cls = RECORD_CLASS_MAP.get(rtype)
        if cls:
            try:
                valid_keys = {f.name for f in fields(cls)}
                filtered_data = {k: v for k, v in r.get("data", {}).items() if k in valid_keys}
                inst = cls(**filtered_data)
                output.append(inst)
            except Exception:
                pass

    return output


def format_draft_summary(memory: Optional[Dict[str, Any]] = None) -> str:
    """Formats current draft memory into a clean context block for Agent 2."""
    target_mem = memory if memory is not None else get_active_draft_memory()
    records: List[Dict[str, Any]] = target_mem.get("draft_records", [])
    if not records:
        return ""

    lines = ["DANH SÁCH BẢN GHI ĐANG TỔNG HỢP TRONG BỘ NHỚ (DRAFT MEMORY):"]
    for r in records:
        clean_vals = {k: v for k, v in r.get("data", {}).items() if v is not None}
        lines.append(f"  #{r.get('id')} [{r.get('type')}]: {clean_vals}")
    lines.append(
        "--> Hướng dẫn: Dùng tool `update_draft_record` để bổ sung/sửa đổi bản ghi đã có (ví dụ: bổ sung số lượng, đơn vị, vật tư); "
        "dùng `remove_draft_record` nếu người dùng hủy; dùng các tool `create_...` để tạo thêm bản ghi mới."
    )
    return "\n".join(lines)


# ==============================================================================
# Hierarchical Memory Manager (Multi-Conversation & Group Chat Stateless Router)
# ==============================================================================


class HierarchicalMemoryManager:
    """Manages two-tier hierarchical memory:
    1. Group conversation sliding window (conversation_history).
    2. Isolated per-user working memory (person_history by USER_ID).
    """

    def __init__(self, group_window_size: int = 10, watchdog_timeout_seconds: float = 60.0):
        self.group_window_size = group_window_size
        self.watchdog_timeout_seconds = watchdog_timeout_seconds

        # Group shared sliding window
        self.conversation_history: List[GroupMessageTurn] = []

        # Isolated user memories: USER_ID -> UserSessionMemory
        self.person_history: Dict[str, UserSessionMemory] = {}

    def get_user_session(
        self,
        user_id: Union[str, int],
        full_name: str = "",
        username: Optional[str] = None,
    ) -> UserSessionMemory:
        """Retrieves or creates an isolated working memory session for the given user."""
        uid = str(user_id)
        if uid not in self.person_history:
            self.person_history[uid] = UserSessionMemory(
                user_id=uid,
                full_name=full_name or f"User {uid}",
                username=username,
                state=UserState.IDLE,
                last_active_at=time.time(),
            )
        else:
            session = self.person_history[uid]
            if full_name:
                session.full_name = full_name
            if username:
                session.username = username
        return self.person_history[uid]

    def record_user_turn(
        self,
        user_id: Union[str, int],
        text: str,
        full_name: str = "",
        username: Optional[str] = None,
    ) -> UserSessionMemory:
        """Records an incoming user speech/text turn in both group history and user session."""
        session = self.get_user_session(user_id, full_name, username)
        session.last_active_at = time.time()
        session.state = UserState.DRAFTING

        # Append to group shared sliding window
        turn = GroupMessageTurn(
            user_id=session.user_id,
            speaker_name=session.full_name,
            role="user",
            text=text.strip(),
            timestamp=session.last_active_at,
        )
        self.conversation_history.append(turn)
        if len(self.conversation_history) > self.group_window_size:
            self.conversation_history.pop(0)

        return session

    def record_ai_turn(
        self,
        user_id: Union[str, int],
        reply_text: str,
        clarification_needed: bool = False,
        clarification_items: Optional[List[str]] = None,
    ) -> UserSessionMemory:
        """Records AI response turn, updates clarification state, and appends to group history."""
        session = self.get_user_session(user_id)
        session.last_active_at = time.time()
        session.last_reply_text = reply_text
        session.clarification_needed = clarification_needed
        session.clarification_items = list(clarification_items or [])

        if clarification_needed:
            session.state = UserState.WAITING_CLARIFICATION
        else:
            session.state = UserState.DRAFTING

        # Append to group shared sliding window
        target_name = session.username or session.full_name or session.user_id
        ai_turn_text = f"@{target_name}: {reply_text.strip()}"
        turn = GroupMessageTurn(
            user_id=session.user_id,
            speaker_name="AI Trợ Lý",
            role="model",
            text=ai_turn_text,
            timestamp=session.last_active_at,
        )
        self.conversation_history.append(turn)
        if len(self.conversation_history) > self.group_window_size:
            self.conversation_history.pop(0)

        return session

    def build_agent2_context(
        self,
        user_id: Union[str, int],
        current_user_text: str,
    ) -> str:
        """Assembles prompt context for Agent 2:
        - Draft memory of this user.
        - Recent shared group conversation window.
        - Current incoming text.
        """
        session = self.get_user_session(user_id)
        parts = []

        # 1. Draft memory summary for this user
        draft_summary = format_draft_summary(session.draft_memory)
        if draft_summary:
            parts.append(f"[BỘ NHỚ ĐANG TỔNG HỢP CỦA {session.full_name} ({session.user_id})]:\n{draft_summary}")

        # 2. Recent group conversations (to understand farm context without mixing up user data)
        recent_group = [t.to_display_string() for t in self.conversation_history[-4:] if t.text != current_user_text]
        if recent_group:
            parts.append("[CÁC TRAO ĐỔI GẦN NHẤT TRONG NHÓM]:\n" + "\n".join(recent_group))

        # 3. Current user speech / text
        parts.append(f"[KHẨU LỆNH MỚI CỦA {session.full_name} ({session.user_id})]:\n\"{current_user_text}\"")

        return "\n\n".join(parts)

    def check_user_timeout(
        self,
        user_id: Union[str, int],
        now: Optional[float] = None,
    ) -> bool:
        """Checks if a user waiting for clarification has exceeded the watchdog timeout (60s)."""
        session = self.get_user_session(user_id)
        current_time = now if now is not None else time.time()
        if session.state == UserState.WAITING_CLARIFICATION:
            return (current_time - session.last_active_at) >= self.watchdog_timeout_seconds
        return False

    def get_timed_out_users(self, now: Optional[float] = None) -> List[UserSessionMemory]:
        """Returns list of user sessions that have timed out and require auto-submission."""
        current_time = now if now is not None else time.time()
        expired = []
        for session in self.person_history.values():
            if session.state == UserState.WAITING_CLARIFICATION:
                if (current_time - session.last_active_at) >= self.watchdog_timeout_seconds:
                    expired.append(session)
        return expired

    def submit_user_draft(
        self,
        user_id: Union[str, int],
        db_path: Optional[Union[str, Path]] = None,
        audio_path: Optional[str] = None,
        reason: str = "Submitted by user or watchdog timeout",
    ) -> Tuple[List[int], Optional[str]]:
        """Stages all working draft records of a user into pending_events and resets draft buffer."""
        session = self.get_user_session(user_id)
        records = to_base_records(session.draft_memory)
        if not records:
            session.reset_draft()
            return [], None

        target_db = Path(db_path) if db_path else get_db_path()
        staged_ids: List[int] = []

        try:
            with get_db(target_db) as conn:
                for rec in records:
                    target_table = rec.TABLE_NAME
                    payload = rec.to_record(exclude_none=True)
                    summary = f"{rec.__class__.__name__} ({session.full_name}): {reason}"
                    ev_id = stage_voice_event(
                        conn=conn,
                        target_table=target_table,
                        action_type="INSERT",
                        payload=payload,
                        raw_transcript=session.last_reply_text or summary,
                        summary_text=summary,
                        audio_path=audio_path,
                        sender_id=session.user_id,
                    )
                    staged_ids.append(ev_id)
                conn.commit()

            session.reset_draft(new_state=UserState.SUBMITTED)
            return staged_ids, None
        except Exception as exc:
            return [], str(exc)

    def compress_user_history(
        self,
        user_id: Union[str, int],
        summarizer_fn: Optional[Callable[[List[Any]], str]] = None,
        max_turns: int = 10,
    ) -> bool:
        """Compresses old conversation turns for a user when dialogue history exceeds max_turns."""
        session = self.get_user_session(user_id)
        if len(session.history) <= max_turns:
            return False

        if summarizer_fn:
            try:
                summary_text = summarizer_fn(session.history[:-2])
                # Keep latest 2 turns and prepend summary
                session.history = [{"role": "system", "text": f"[TÓM TẮT HỘI THOẠI TRƯỚC ĐÓ]: {summary_text}"}] + session.history[-2:]
                return True
            except Exception:
                pass

        # Default sliding window truncation
        session.history = session.history[-max_turns:]
        return True


# Global singleton instance
_default_memory_manager: Optional[HierarchicalMemoryManager] = None


def get_hierarchical_memory_manager() -> HierarchicalMemoryManager:
    """Returns the process-wide singleton HierarchicalMemoryManager instance."""
    global _default_memory_manager
    if _default_memory_manager is None:
        _default_memory_manager = HierarchicalMemoryManager()
    return _default_memory_manager
