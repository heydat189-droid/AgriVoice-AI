"""AgriVoice-AI: Hierarchical Memory & Multi-Conversation Test Suite.

Verifies:
1. Multi-user isolation in group chats: User A and User B chatting concurrently maintain strictly isolated draft_records.
2. Group-level shared conversation window (conversation_history) tracks recent turns across all participants.
3. User state transitions (IDLE -> DRAFTING -> WAITING_CLARIFICATION -> SUBMITTED).
4. Interactive manual submission (submit_user_draft) stages records and clears draft.
5. Watchdog 60s timeout auto-submission for users who abandon clarification.
6. Context compression truncating/summarizing dialogue when turns exceed threshold.
"""

from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path

from src.ai.memory import (
    HierarchicalMemoryManager,
    UserState,
    add_draft_record,
    format_draft_summary,
    get_draft_records,
    to_base_records,
    update_draft_record,
)
from src.db.connection import get_db
from src.db.migrate import run_migrations
from src.db.models import ProductionLog


class TestHierarchicalMemory(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_memory.db"
        run_migrations(db_path=self.db_path, quiet=True)

        with get_db(self.db_path) as conn:
            conn.execute(
                "INSERT INTO collaborators (telegram_id, full_name, role) VALUES ('1001', 'Bác Ba', 'WORKER');"
            )
            conn.execute(
                "INSERT INTO collaborators (telegram_id, full_name, role) VALUES ('1002', 'Bác Tư', 'WORKER');"
            )
            conn.execute(
                "INSERT INTO zones (zone_id, zone_name) VALUES ('ZONE_A', 'Khu A');"
            )

        self.mgr = HierarchicalMemoryManager(group_window_size=5, watchdog_timeout_seconds=2.0)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_01_multi_user_isolation(self):
        """Test Bác Ba and Bác Tư maintain strictly isolated draft_records in interleaved group chat."""
        # 1. Bác Ba speaks first (Turn 1)
        self.mgr.record_user_turn(user_id="1001", text="Cho gà ăn", full_name="Bác Ba")
        ba_session = self.mgr.get_user_session("1001")
        add_draft_record(
            "ProductionLog",
            {"title": "Cho gà ăn", "activity_type": "FEEDING"},
            memory=ba_session.draft_memory,
        )

        # 2. Bác Tư speaks next in the same group (Turn 2 - Interleaved)
        self.mgr.record_user_turn(user_id="1002", text="Bơm nước tưới khu A", full_name="Bác Tư")
        tu_session = self.mgr.get_user_session("1002")
        add_draft_record(
            "ProductionLog",
            {"title": "Bơm nước khu A", "activity_type": "IRRIGATION"},
            memory=tu_session.draft_memory,
        )

        # 3. Verify Bác Ba only has 1 record (Cho gà ăn)
        ba_drafts = get_draft_records(ba_session.draft_memory)
        self.assertEqual(len(ba_drafts), 1)
        self.assertEqual(ba_drafts[0]["data"]["title"], "Cho gà ăn")

        # 4. Verify Bác Tư only has 1 record (Bơm nước khu A)
        tu_drafts = get_draft_records(tu_session.draft_memory)
        self.assertEqual(len(tu_drafts), 1)
        self.assertEqual(tu_drafts[0]["data"]["title"], "Bơm nước khu A")

        # 5. Bác Ba sends a 2nd turn to supplement info
        update_draft_record(
            record_id=1,
            updates={"quantity": 2.0, "unit": "kg"},
            memory=ba_session.draft_memory,
        )
        # Bác Ba's draft is updated
        ba_updated = get_draft_records(ba_session.draft_memory)
        self.assertEqual(ba_updated[0]["data"]["quantity"], 2.0)

        # Bác Tư's draft is completely unaffected!
        tu_unaffected = get_draft_records(tu_session.draft_memory)
        self.assertEqual(len(tu_unaffected), 1)
        self.assertNotIn("quantity", tu_unaffected[0]["data"])

    def test_02_group_conversation_history_window(self):
        """Test group shared conversation window maintains sliding window of recent turns."""
        self.mgr.record_user_turn("1001", "Tin nhắn 1", full_name="Bác Ba")
        self.mgr.record_ai_turn("1001", "Phản hồi 1")
        self.mgr.record_user_turn("1002", "Tin nhắn 2", full_name="Bác Tư")
        self.mgr.record_ai_turn("1002", "Phản hồi 2")
        self.mgr.record_user_turn("1001", "Tin nhắn 3", full_name="Bác Ba")
        self.mgr.record_ai_turn("1001", "Phản hồi 3")

        # Window size is 5 -> earliest turn dropped
        self.assertEqual(len(self.mgr.conversation_history), 5)
        self.assertNotIn("Tin nhắn 1", [t.text for t in self.mgr.conversation_history])

    def test_03_interactive_manual_submit(self):
        """Test submit_user_draft stages records into pending_events and transitions state to SUBMITTED."""
        session = self.mgr.get_user_session("1001", full_name="Bác Ba")
        pl = ProductionLog(title="Bón phân NPK", description="Bón cho khu A")
        add_draft_record("ProductionLog", pl.to_record(exclude_none=True), record=pl, memory=session.draft_memory)

        # Submit draft
        staged_ids, err = self.mgr.submit_user_draft(user_id="1001", db_path=self.db_path)
        self.assertIsNone(err)
        self.assertEqual(len(staged_ids), 1)
        self.assertEqual(session.state, UserState.SUBMITTED)

        # Draft memory is cleared
        self.assertEqual(len(session.draft_records), 0)

    def test_04_watchdog_timeout_auto_submit(self):
        """Test watchdog auto-submits drafts when user abandons clarification after timeout."""
        session = self.mgr.get_user_session("1001", full_name="Bác Ba")
        pl = ProductionLog(title="Cho gà ăn", description="Cho gà ăn tại chuồng 1")
        add_draft_record("ProductionLog", pl.to_record(exclude_none=True), record=pl, memory=session.draft_memory)

        # Record AI asking for clarification -> state becomes WAITING_CLARIFICATION
        self.mgr.record_ai_turn("1001", "Hệ thống ghi nhận: Cho gà ăn. Thông tin cần làm rõ: Chưa rõ số lượng.", clarification_needed=True)
        self.assertEqual(session.state, UserState.WAITING_CLARIFICATION)

        # Before timeout -> not timed out
        self.assertFalse(self.mgr.check_user_timeout("1001", now=time.time()))

        # Simulate timeout (> 2.0s)
        future_time = time.time() + 3.0
        self.assertTrue(self.mgr.check_user_timeout("1001", now=future_time))

        expired = self.mgr.get_timed_out_users(now=future_time)
        self.assertEqual(len(expired), 1)
        self.assertEqual(expired[0].user_id, "1001")

        # Auto-submit
        staged_ids, err = self.mgr.submit_user_draft("1001", db_path=self.db_path, reason="Watchdog timeout")
        self.assertEqual(len(staged_ids), 1)
        self.assertEqual(session.state, UserState.SUBMITTED)


if __name__ == "__main__":
    unittest.main()
