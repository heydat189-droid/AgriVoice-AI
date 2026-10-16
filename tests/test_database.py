"""AgriVoice-AI: Comprehensive Database & Migration Test Suite.

Tests:
1. Migration execution and Flyway compatibility
2. Schema integrity and PRAGMA foreign_key_check
3. Trigger behavior:
   - Updated_at auto-updates across tables
   - Subtasks auto-completion timestamping
   - Issues auto-closing timestamping
   - Inventory transaction posting, batch stock updates, depletion status, immutability
4. View functionality (production_locations backward compatibility)
5. Idempotent re-runs and checksum validation
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

# Ensure workspace root is in python path
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WORKSPACE_ROOT))

from src.db.connection import get_db, initialize_database
from src.db.migrate import (
    get_applied_migrations,
    load_migration_files,
    run_migrations,
    verify_checksums,
)


class TestDatabaseMigrations(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test.db"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_01_migration_execution_and_history(self):
        """Verify all 9 migrations apply in sequential rank with checksums."""
        count = run_migrations(db_path=self.db_path, quiet=True)
        self.assertEqual(count, 9, "Should apply exactly 9 migrations")

        with get_db(self.db_path) as con:
            applied = get_applied_migrations(con)
            self.assertEqual(len(applied), 9)

            versions = [m.version for m in applied]
            self.assertEqual(versions, ["1", "2", "3", "4", "5", "6", "7", "8", "9"])

            for m in applied:
                self.assertTrue(m.success, f"Migration V{m.version} should have succeeded")
                self.assertIsNotNone(m.checksum, f"Migration V{m.version} should have checksum")

            # Check foreign key integrity
            cur = con.cursor()
            cur.execute("PRAGMA foreign_key_check;")
            errors = cur.fetchall()
            self.assertEqual(len(errors), 0, f"Foreign key errors: {errors}")

    def test_02_idempotency_and_checksum_verification(self):
        """Verify re-running migrations does nothing and checksums match."""
        run_migrations(db_path=self.db_path, quiet=True)
        second_run_count = run_migrations(db_path=self.db_path, quiet=True)
        self.assertEqual(second_run_count, 0, "Second run should apply 0 migrations")

        self.assertTrue(verify_checksums(db_path=self.db_path))

    def test_03_collaborators_and_zones(self):
        """Test Collaborators, Zones, and backward-compatible production_locations view."""
        run_migrations(db_path=self.db_path, quiet=True)

        with get_db(self.db_path) as con:
            con.execute(
                """
                INSERT INTO collaborators (telegram_id, full_name, role)
                VALUES ('1001', 'Nguyễn Văn Nông', 'ADMIN');
                """
            )
            con.execute(
                """
                INSERT INTO zones (zone_id, zone_name, sector, area_size, unit_of_size)
                VALUES ('ZONE_01', 'Vườn Cam Xoàn 1', 'CROP', 5000.0, 'm2');
                """
            )

            # Check view
            row = con.execute(
                "SELECT * FROM production_locations WHERE location_id = 'ZONE_01';"
            ).fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row["name"], "Vườn Cam Xoàn 1")
            self.assertEqual(row["size_value"], 5000.0)

    def test_04_inventory_triggers_and_immutability(self):
        """Verify inventory transactions stock updates, depletion, and posted immutability."""
        run_migrations(db_path=self.db_path, quiet=True)

        with get_db(self.db_path) as con:
            # 1. Seed base data
            con.execute("INSERT INTO units (code, name) VALUES ('KG', 'Kilogram');")
            unit_id = con.execute("SELECT unit_id FROM units WHERE code = 'KG';").fetchone()[0]

            con.execute("INSERT INTO warehouses (code, name) VALUES ('WH01', 'Kho Vật Tư Chính');")
            wh_id = con.execute("SELECT warehouse_id FROM warehouses WHERE code = 'WH01';").fetchone()[0]

            con.execute(
                f"""
                INSERT INTO products (sku, name, base_unit_id, requires_batch_tracking)
                VALUES ('NPK-20-20-15', 'Phân Bón NPK Đầu Trâu', {unit_id}, 1);
                """
            )
            prod_id = con.execute("SELECT product_id FROM products WHERE sku = 'NPK-20-20-15';").fetchone()[0]

            # 2. Create batch with 100 kg
            con.execute(
                f"""
                INSERT INTO product_batches (product_id, batch_number, quantity_remaining, warehouse_id)
                VALUES ({prod_id}, 'LOT-2026-001', 100.0, {wh_id});
                """
            )
            batch_id = con.execute("SELECT batch_id FROM product_batches WHERE batch_number = 'LOT-2026-001';").fetchone()[0]

            # 3. Insert posted issue transaction (-40 kg)
            con.execute(
                f"""
                INSERT INTO inventory_transactions (
                    product_id, batch_id, warehouse_id, transaction_type,
                    quantity_change, unit_id, status
                ) VALUES ({prod_id}, {batch_id}, {wh_id}, 'ISSUE', -40.0, {unit_id}, 'POSTED');
                """
            )

            # Check batch stock reduced to 60.0
            batch = con.execute(f"SELECT quantity_remaining, status FROM product_batches WHERE batch_id = {batch_id};").fetchone()
            self.assertEqual(batch["quantity_remaining"], 60.0)
            self.assertEqual(batch["status"], "AVAILABLE")

            # 4. Check immutability: Cannot update or delete posted transaction
            tx_id = con.execute(f"SELECT transaction_id FROM inventory_transactions WHERE batch_id = {batch_id};").fetchone()[0]
            with self.assertRaises(Exception):
                con.execute(f"UPDATE inventory_transactions SET reference_note = 'hack' WHERE transaction_id = {tx_id};")

            with self.assertRaises(Exception):
                con.execute(f"DELETE FROM inventory_transactions WHERE transaction_id = {tx_id};")

            # 5. Deplete batch to 0 -> status should auto-become DEPLETED
            con.execute(
                f"""
                INSERT INTO inventory_transactions (
                    product_id, batch_id, warehouse_id, transaction_type,
                    quantity_change, unit_id, status
                ) VALUES ({prod_id}, {batch_id}, {wh_id}, 'ISSUE', -60.0, {unit_id}, 'POSTED');
                """
            )
            batch = con.execute(f"SELECT quantity_remaining, status FROM product_batches WHERE batch_id = {batch_id};").fetchone()
            self.assertEqual(batch["quantity_remaining"], 0.0)
            self.assertEqual(batch["status"], "DEPLETED")

            # 6. Negative stock tolerance: additional issue drives stock negative -> status becomes NEGATIVE_ALERT
            con.execute(
                f"""
                INSERT INTO inventory_transactions (
                    product_id, batch_id, warehouse_id, transaction_type,
                    quantity_change, unit_id, status
                ) VALUES ({prod_id}, {batch_id}, {wh_id}, 'ISSUE', -10.0, {unit_id}, 'POSTED');
                """
            )
            batch_neg = con.execute(f"SELECT quantity_remaining, status FROM product_batches WHERE batch_id = {batch_id};").fetchone()
            self.assertEqual(batch_neg["quantity_remaining"], -10.0)
            self.assertEqual(batch_neg["status"], "NEGATIVE_ALERT")
    def test_05_subtasks_and_issues_triggers(self):
        """Test subtasks auto-completion and issues auto-close triggers."""
        run_migrations(db_path=self.db_path, quiet=True)

        with get_db(self.db_path) as con:
            # Setup Zone and Project
            con.execute("INSERT INTO zones (zone_id, zone_name) VALUES ('ZONE_B', 'Khu B');")
            con.execute("INSERT INTO projects (code, name) VALUES ('PRJ01', 'Dự án Cà Chua');")
            prj_id = con.execute("SELECT project_id FROM projects WHERE code = 'PRJ01';").fetchone()[0]

            # Setup Task & Subtask
            con.execute(f"INSERT INTO tasks (project_id, title) VALUES ({prj_id}, 'Gieo hạt giống');")
            task_id = con.execute(f"SELECT task_id FROM tasks WHERE project_id = {prj_id};").fetchone()[0]

            con.execute(f"INSERT INTO subtasks (task_id, title) VALUES ({task_id}, 'Chuẩn bị khay gieo');")
            sub_id = con.execute(f"SELECT subtask_id FROM subtasks WHERE task_id = {task_id};").fetchone()[0]

            # Initially completed_at is NULL
            sub = con.execute(f"SELECT is_completed, completed_at FROM subtasks WHERE subtask_id = {sub_id};").fetchone()
            self.assertEqual(sub["is_completed"], 0)
            self.assertIsNone(sub["completed_at"])

            # Mark completed -> completed_at auto-populated
            con.execute(f"UPDATE subtasks SET is_completed = 1 WHERE subtask_id = {sub_id};")
            sub = con.execute(f"SELECT is_completed, completed_at FROM subtasks WHERE subtask_id = {sub_id};").fetchone()
            self.assertEqual(sub["is_completed"], 1)
            self.assertIsNotNone(sub["completed_at"])

            # Test Issues auto-close
            con.execute(
                """
                INSERT INTO issues (zone_id, title, status)
                VALUES ('ZONE_B', 'Hệ thống tưới nhỏ giọt rò rỉ', 'OPEN');
                """
            )
            issue_id = con.execute("SELECT issue_id FROM issues WHERE zone_id = 'ZONE_B';").fetchone()[0]

            issue = con.execute(f"SELECT status, closed_at FROM issues WHERE issue_id = {issue_id};").fetchone()
            self.assertEqual(issue["status"], "OPEN")
            self.assertIsNone(issue["closed_at"])

            # Close issue -> closed_at auto-populated
            con.execute(f"UPDATE issues SET status = 'CLOSED' WHERE issue_id = {issue_id};")
            issue = con.execute(f"SELECT status, closed_at FROM issues WHERE issue_id = {issue_id};").fetchone()
            self.assertEqual(issue["status"], "CLOSED")
            self.assertIsNotNone(issue["closed_at"])

    def test_06_pending_events_queue_triggers_and_views(self):
        """Verify pending_events staging queue, strict ordering view, and audit triggers."""
        run_migrations(db_path=self.db_path, quiet=True)

        with get_db(self.db_path) as con:
            # 1. Insert collaborator as reviewer
            con.execute(
                "INSERT INTO collaborators (telegram_id, full_name, role) "
                "VALUES ('OWNER_01', 'Chủ Trang Trại', 'OWNER');"
            )
            reviewer_id = con.execute("SELECT collaborator_id FROM collaborators WHERE telegram_id = 'OWNER_01';").fetchone()[0]

            # 2. Insert voice raw log
            con.execute(
                "INSERT INTO voice_raw_logs (sender_id, audio_file_path, raw_transcript, detected_intent, execution_status) "
                "VALUES ('123456', '/audio/rec_01.ogg', 'Vườn cam xuất hiện rầy nâu', 'REPORT_ISSUE', 'PENDING_APPROVAL');"
            )
            log_id = con.execute("SELECT log_id FROM voice_raw_logs;").fetchone()[0]

            # 3. Insert pending events with distinct timestamps to test strict ordering
            con.execute(
                """
                INSERT INTO pending_events (
                    log_id, timestamp, target_table, action_type, audio_path,
                    raw_transcript, summary_text, payload_json, status
                ) VALUES (
                    ?, '2026-10-13 08:00:00', 'issues', 'INSERT', '/audio/rec_01.ogg',
                    'Vườn cam xuất hiện rầy nâu', 'Báo cáo sâu bệnh vườn cam',
                    '{"zone_id": "ZONE_A", "title": "Rầy nâu hại cam", "severity": "HIGH"}', 'PENDING'
                );
                """,
                (log_id,),
            )
            event1_id = con.execute("SELECT last_insert_rowid();").fetchone()[0]

            con.execute(
                """
                INSERT INTO pending_events (
                    log_id, timestamp, target_table, action_type, audio_path,
                    raw_transcript, summary_text, payload_json, status
                ) VALUES (
                    ?, '2026-10-13 09:30:00', 'tasks', 'INSERT', '/audio/rec_02.ogg',
                    'Đã tưới nước khu B', 'Ghi nhận tưới nước',
                    '{"title": "Tưới nước khu B"}', 'PENDING'
                );
                """,
                (log_id,),
            )
            event2_id = con.execute("SELECT last_insert_rowid();").fetchone()[0]

            # 4. Check v_pending_events_queue: Strict Ordering (event1 first, event2 second)
            queue = con.execute("SELECT * FROM v_pending_events_queue;").fetchall()
            self.assertEqual(len(queue), 2)
            self.assertEqual(queue[0]["event_id"], event1_id)
            self.assertEqual(queue[1]["event_id"], event2_id)

            # 5. Check trigger: auto-stamp reviewed_at when approved
            ev1_before = con.execute("SELECT status, reviewed_at FROM pending_events WHERE event_id = ?;", (event1_id,)).fetchone()
            self.assertEqual(ev1_before["status"], "PENDING")
            self.assertIsNone(ev1_before["reviewed_at"])

            con.execute(
                "UPDATE pending_events SET status = 'APPROVED', reviewed_by = ? WHERE event_id = ?;",
                (reviewer_id, event1_id),
            )
            ev1_after = con.execute("SELECT status, reviewed_at, reviewed_by FROM pending_events WHERE event_id = ?;", (event1_id,)).fetchone()
            self.assertEqual(ev1_after["status"], "APPROVED")
            self.assertEqual(ev1_after["reviewed_by"], reviewer_id)
            self.assertIsNotNone(ev1_after["reviewed_at"])

            # 6. Queue now only contains event2
            queue_after = con.execute("SELECT * FROM v_pending_events_queue;").fetchall()
            self.assertEqual(len(queue_after), 1)
            self.assertEqual(queue_after[0]["event_id"], event2_id)

            # 7. Audit trail view contains both
            history = con.execute("SELECT * FROM v_pending_events_history;").fetchall()
            self.assertEqual(len(history), 2)

            # 8. Test ERROR status and error view
            con.execute(
                "UPDATE pending_events SET status = 'ERROR', error_message = 'Lỗi test vi phạm ràng buộc' WHERE event_id = ?;",
                (event2_id,),
            )
            err_events = con.execute("SELECT * FROM v_pending_events_errors;").fetchall()
            self.assertEqual(len(err_events), 1)
            self.assertEqual(err_events[0]["event_id"], event2_id)
            self.assertIn("vi phạm", err_events[0]["error_message"])


if __name__ == "__main__":
    unittest.main()
