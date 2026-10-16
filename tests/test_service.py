"""AgriVoice-AI: Central DBService Test Suite.

Tests:
1. Low-level service operations:
   - _validate_record (schema, columns, types)
   - _normalize_table_name (alias mapping, pendind_event -> pending_events)
   - get_record (raw SELECT, WHERE conditions, limits)
   - _check_pending_update (strict ordering enforcement)
   - insert_record, update_record, delete_record
   - update_by_log_id (atomic apply, error logging on failure, retry)
2. High-level service operations:
   - check_permission (OWNER, ADMIN, WORKER, VIEWER, inactive accounts)
   - stage_pending_event (staging voice logs into queue)
   - approve_event & reject_event
   - insert_row, update_row, delete_row
   - get_formatted_data with conditions
   - get_pending_queue & get_error_logs
   - get_data_with_pending_overlay
"""

import sys
import tempfile
import unittest
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WORKSPACE_ROOT))

from src.db.connection import get_db
from src.db.migrate import run_migrations
from src.db.service import DBService


class TestDBService(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_service.db"
        run_migrations(db_path=self.db_path, quiet=True)
        self.service = DBService(db_path=self.db_path)

        # Pre-seed collaborators
        with get_db(self.db_path) as conn:
            conn.execute(
                "INSERT INTO collaborators (telegram_id, full_name, role, is_active) "
                "VALUES ('OWNER_1', 'Chủ Trang Trại', 'OWNER', 1);"
            )
            conn.execute(
                "INSERT INTO collaborators (telegram_id, full_name, role, is_active) "
                "VALUES ('WORKER_1', 'Bác Giữ Vườn', 'WORKER', 1);"
            )
            conn.execute(
                "INSERT INTO collaborators (telegram_id, full_name, role, is_active) "
                "VALUES ('VIEWER_1', 'Khách Xem', 'VIEWER', 1);"
            )
            conn.execute(
                "INSERT INTO collaborators (telegram_id, full_name, role, is_active) "
                "VALUES ('BLOCKED_1', 'Nhân viên nghỉ việc', 'WORKER', 0);"
            )
            conn.execute("INSERT INTO zones (zone_id, zone_name) VALUES ('ZONE_A', 'Khu A');")

    def tearDown(self):
        self.temp_dir.cleanup()

    # --------------------------------------------------------------------------
    # Low-level service tests
    # --------------------------------------------------------------------------

    def test_01_validate_record(self):
        """Test record schema validation against table metadata."""
        # Non-existent table
        err = self.service._validate_record("non_existent_table", {"a": 1})
        self.assertIsNotNone(err)
        self.assertIn("does not exist", err)

        # Unknown column
        err = self.service._validate_record("zones", {"zone_id": "Z1", "unknown_col": 123})
        self.assertIsNotNone(err)
        self.assertIn("unknown_col", err)

        # Valid record
        err = self.service._validate_record("zones", {"zone_id": "Z1", "zone_name": "Vườn Bơ"})
        self.assertIsNone(err)

    def test_02_get_record_and_aliases(self):
        """Test get_record with table aliases, WHERE conditions, and raw SELECT syntax."""
        # Insert a zone
        self.service.insert_record("zones", {"zone_id": "ZONE_TEST", "zone_name": "Khu Test"})

        # Get with singular alias
        res = self.service.get_record("zone", "zone_id = ?", ("ZONE_TEST",), limit=1)
        self.assertIsNotNone(res)
        self.assertEqual(res["zone_id"], "ZONE_TEST")

        # Get with user typo "pendind_event"
        self.service.insert_record(
            "pendind_event",
            {
                "target_table": "issues",
                "action_type": "INSERT",
                "payload_json": '{"title": "Test"}',
            },
        )
        res_pending = self.service.get_record("pendind_event", limit=1)
        self.assertIsNotNone(res_pending)
        self.assertEqual(res_pending["target_table"], "issues")

        # Get with pseudo-select: SELECT event_id WHERE target_table = issues
        res_pseudo = self.service.get_record("pending_events", "SELECT event_id WHERE target_table = 'issues'", limit=None)
        self.assertIsInstance(res_pseudo, list)
        self.assertGreaterEqual(len(res_pseudo), 1)

    def test_03_strict_ordering_check(self):
        """Test _check_pending_update enforces sequential processing."""
        # 1. No pending events -> clean
        err = self.service._check_pending_update("issues", ts="2026-10-13 12:00:00")
        self.assertIsNone(err)

        # 2. Stage earlier pending event at 08:00
        self.service.insert_record(
            "pending_events",
            {
                "target_table": "issues",
                "action_type": "INSERT",
                "payload_json": '{"zone_id": "ZONE_A", "title": "Sự cố sớm"}',
                "timestamp": "2026-10-13 08:00:00",
                "status": "PENDING",
            },
        )

        # 3. Direct insert or checking at 09:00 must detect earlier pending event
        err = self.service._check_pending_update("issues", ts="2026-10-13 09:00:00")
        self.assertIsNotNone(err)
        self.assertIn("Process pending before insert new", err)

        # 4. Checking with timestamp earlier than 08:00 (e.g. 07:00) should be clean
        err_early = self.service._check_pending_update("issues", ts="2026-10-13 07:00:00")
        self.assertIsNone(err_early)

    def test_04_insert_update_delete_record(self):
        """Test primitive insert_record, update_record, and delete_record."""
        # Insert
        err = self.service.insert_record("zones", {"zone_id": "ZONE_C", "zone_name": "Khu C"})
        self.assertIsNone(err)

        # Update
        err = self.service.update_record("zones", {"zone_name": "Khu C Mới"}, {"zone_id": "ZONE_C"})
        self.assertIsNone(err)
        rec = self.service.get_record("zones", "zone_id = 'ZONE_C'", limit=1)
        self.assertEqual(rec["zone_name"], "Khu C Mới")

        # Delete
        err = self.service.delete_record("zones", {"zone_id": "ZONE_C"})
        self.assertIsNone(err)
        rec_after = self.service.get_record("zones", "zone_id = 'ZONE_C'", limit=1)
        self.assertIsNone(rec_after)

    def test_05_update_by_log_id_approval_and_error_handling(self):
        """Test update_by_log_id: atomic approval on success, ERROR status on failure."""
        # Stage event that will succeed
        self.service.insert_record(
            "pending_events",
            {
                "target_table": "issues",
                "action_type": "INSERT",
                "payload_json": '{"zone_id": "ZONE_A", "title": "Bẫy côn trùng hư"}',
                "timestamp": "2026-10-13 06:00:00",
                "status": "PENDING",
            },
        )
        log_good = self.service.get_record("pending_events", "payload_json LIKE '%Bẫy côn trùng%'", limit=1)
        log_id_good = log_good["event_id"]

        # Approve valid event
        err = self.service.update_by_log_id(log_id_good, reviewer_id=1, review_notes="Duyệt")
        self.assertIsNone(err)
        approved_log = self.service.get_record("pending_events", "event_id = ?", (log_id_good,), limit=1)
        self.assertEqual(approved_log["status"], "APPROVED")

        # Stage event that will fail (foreign key violation: non-existent zone)
        self.service.insert_record(
            "pending_events",
            {
                "target_table": "issues",
                "action_type": "INSERT",
                "payload_json": '{"zone_id": "ZONE_GHOST", "title": "Sự cố ma"}',
                "timestamp": "2026-10-13 06:30:00",
                "status": "PENDING",
            },
        )
        log_bad = self.service.get_record("pending_events", "payload_json LIKE '%Sự cố ma%'", limit=1)
        log_id_bad = log_bad["event_id"]

        # Approve failing event -> must return error and update status to ERROR
        err_bad = self.service.update_by_log_id(log_id_bad)
        self.assertIsNotNone(err_bad)
        error_log = self.service.get_record("pending_events", "event_id = ?", (log_id_bad,), limit=1)
        self.assertEqual(error_log["status"], "ERROR")
        self.assertIsNotNone(error_log["error_message"])

    # --------------------------------------------------------------------------
    # High-level service tests
    # --------------------------------------------------------------------------

    def test_06_check_permission(self):
        """Test collaborator permission checks based on role and active state."""
        # Unregistered user
        ok, reason = self.service.check_permission("UNKNOWN_USER", "PUSH")
        self.assertFalse(ok)
        self.assertIn("chưa được đăng ký", reason)

        # Blocked / inactive user
        ok, reason = self.service.check_permission("BLOCKED_1", "PUSH")
        self.assertFalse(ok)
        self.assertIn("bị khóa", reason)

        # Worker: can STAGE voice events
        ok, _ = self.service.check_permission("WORKER_1", "STAGE")
        self.assertTrue(ok)

        # Worker: CANNOT APPROVE or DIRECT_DELETE
        ok, reason = self.service.check_permission("WORKER_1", "APPROVE")
        self.assertFalse(ok)
        self.assertIn("không có quyền phê duyệt", reason)

        # Viewer: can READ, cannot PUSH
        ok, _ = self.service.check_permission("VIEWER_1", "READ")
        self.assertTrue(ok)
        ok, reason = self.service.check_permission("VIEWER_1", "PUSH")
        self.assertFalse(ok)

        # Owner: full access
        ok, _ = self.service.check_permission("OWNER_1", "APPROVE")
        self.assertTrue(ok)

    def test_07_stage_approve_reject_event_workflow(self):
        """Test full high-level voice event staging, approval, and rejection."""
        # Worker stages a voice event
        event_id, err = self.service.stage_pending_event(
            sender_id="WORKER_1",
            target_table="issues",
            action_type="INSERT",
            payload={"zone_id": "ZONE_A", "title": "Bơm nước chập điện", "severity": "HIGH"},
            audio_path="/audio/pump_01.ogg",
            raw_transcript="Máy bơm nước khu A bị chập điện",
            summary_text="Sự cố máy bơm",
            detected_intent="REPORT_ISSUE",
        )
        self.assertIsNone(err)
        self.assertIsNotNone(event_id)

        # Pending queue should contain the event
        queue = self.service.get_pending_queue("issues")
        self.assertEqual(len(queue), 1)
        self.assertEqual(queue[0]["event_id"], event_id)

        # Worker tries to approve -> rejected by permission check
        ok, reason = self.service.approve_event(event_id, reviewer_telegram_id="WORKER_1")
        self.assertFalse(ok)
        self.assertIn("không có quyền", reason)

        # Owner approves
        ok, reason = self.service.approve_event(event_id, reviewer_telegram_id="OWNER_1", review_notes="Đã xử lý")
        self.assertTrue(ok)
        self.assertIsNone(reason)

        # Queue is now empty, issues table has the new row
        queue_after = self.service.get_pending_queue("issues")
        self.assertEqual(len(queue_after), 0)

        issues = self.service.get_formatted_data("issues", {"zone_id": "ZONE_A"})
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]["title"], "Bơm nước chập điện")

    def test_08_virtual_overlay_and_error_views(self):
        """Test virtual overlay combining committed and pending data, and error log retrieval."""
        # Stage pending event
        self.service.stage_pending_event(
            sender_id="WORKER_1",
            target_table="issues",
            action_type="INSERT",
            payload={"zone_id": "ZONE_A", "title": "Rò rỉ ống nước"},
            summary_text="Rò rỉ ống",
        )

        overlay = self.service.get_data_with_pending_overlay("issues")
        self.assertEqual(overlay["target_table"], "issues")
        self.assertGreaterEqual(overlay["pending_count"], 1)

        # Errors list initially empty
        err_logs = self.service.get_error_logs("issues")
        self.assertEqual(len(err_logs), 0)

    def test_09_get_data_with_pending_applied_workflow(self):
        """Test sequential SQL-like pending events overlay on committed table data."""
        # 1. Base committed row in issues
        self.service.insert_row(
            table="issues",
            data={"zone_id": "ZONE_A", "title": "Bơm nước chập điện", "severity": "HIGH", "status": "OPEN"},
        )
        committed_rows = self.service.get_formatted_data("issues")
        self.assertEqual(len(committed_rows), 1)
        base_issue_id = committed_rows[0]["issue_id"]

        # 2. Stage pending event 1: INSERT new issue
        self.service.stage_pending_event(
            sender_id="WORKER_1",
            target_table="issues",
            action_type="INSERT",
            payload={"zone_id": "ZONE_A", "title": "Rò rỉ ống tưới", "severity": "LOW", "status": "OPEN"},
            timestamp="2026-10-13 08:00:00",
        )

        # Verify INSERT applied
        res1 = self.service.get_data_with_pending_applied("issues")
        self.assertEqual(res1["target_table"], "issues")
        self.assertEqual(res1["committed_count"], 2)
        self.assertEqual(res1["pending_count"], 1)
        self.assertEqual(res1["applied_pending_count"], 1)
        self.assertEqual(len(res1["committed_data"]), 2)
        self.assertEqual(res1["committed_data"], res1["data"])
        titles = [r["title"] for r in res1["committed_data"]]
        self.assertIn("Bơm nước chập điện", titles)
        self.assertIn("Rò rỉ ống tưới", titles)

        # 3. Stage pending event 2: UPDATE base issue by primary key
        self.service.stage_pending_event(
            sender_id="WORKER_1",
            target_table="issues",
            action_type="UPDATE",
            payload={"issue_id": base_issue_id, "severity": "CRITICAL"},
            timestamp="2026-10-13 08:30:00",
        )

        # Verify UPDATE by PK applied
        res2 = self.service.get_data_with_pending_applied("issues")
        self.assertEqual(res2["committed_count"], 2)
        self.assertEqual(res2["pending_count"], 2)
        base_row = next(r for r in res2["committed_data"] if r["issue_id"] == base_issue_id)
        self.assertEqual(base_row["severity"], "CRITICAL")

        # 4. Stage pending event 3: UPDATE inserted issue using where/data syntax
        self.service.stage_pending_event(
            sender_id="WORKER_1",
            target_table="issues",
            action_type="UPDATE",
            payload={"where": {"title": "Rò rỉ ống tưới"}, "data": {"status": "IN_PROGRESS"}},
            timestamp="2026-10-13 09:00:00",
        )

        # Verify UPDATE by WHERE applied
        res3 = self.service.get_data_with_pending_applied("issues")
        inserted_row = next(r for r in res3["committed_data"] if r["title"] == "Rò rỉ ống tưới")
        self.assertEqual(inserted_row["status"], "IN_PROGRESS")

        # 5. Stage pending event 4: DELETE base issue
        self.service.stage_pending_event(
            sender_id="WORKER_1",
            target_table="issues",
            action_type="DELETE",
            payload={"issue_id": base_issue_id},
            timestamp="2026-10-13 09:30:00",
        )

        # Verify DELETE applied (only inserted row remains)
        res4 = self.service.get_data_with_pending_applied("issues")
        self.assertEqual(res4["committed_count"], 1)
        self.assertEqual(res4["committed_data"][0]["title"], "Rò rỉ ống tưới")

        # 6. Conditions filtering
        self.service.stage_pending_event(
            sender_id="WORKER_1",
            target_table="issues",
            action_type="INSERT",
            payload={"zone_id": "ZONE_B", "title": "Sâu hại khu B", "severity": "HIGH"},
            timestamp="2026-10-13 10:00:00",
        )

        res_zone_a = self.service.get_data_with_pending_applied("issues", conditions={"zone_id": "ZONE_A"})
        self.assertEqual(res_zone_a["committed_count"], 1)
        self.assertEqual(res_zone_a["committed_data"][0]["zone_id"], "ZONE_A")

        res_zone_b = self.service.get_data_with_pending_applied("issues", conditions={"zone_id": "ZONE_B"})
        self.assertEqual(res_zone_b["committed_count"], 1)
        self.assertEqual(res_zone_b["committed_data"][0]["zone_id"], "ZONE_B")

        # 7. Test get_data_with_pending_overlay with apply_pending=True
        overlay_applied = self.service.get_data_with_pending_overlay("issues", apply_pending=True)
        self.assertEqual(overlay_applied["committed_count"], 2)

        # 8. Test as_list=True
        list_res = self.service.get_data_with_pending_applied("issues", as_list=True)
        self.assertIsInstance(list_res, list)
        self.assertEqual(len(list_res), 2)

        # 9. Test robustness with malformed / unknown action
        self.service.stage_pending_event(
            sender_id="WORKER_1",
            target_table="issues",
            action_type="UNKNOWN_ACTION",
            payload={"garbage": True},
            timestamp="2026-10-13 10:30:00",
        )
        res_safe = self.service.get_data_with_pending_applied("issues")
        self.assertEqual(res_safe["committed_count"], 2)

        # 10. Test method aliases
        self.assertEqual(self.service.get_data_with_pending_merged, self.service.get_data_with_pending_applied)
        self.assertEqual(self.service.get_clean_data_with_pending, self.service.get_data_with_pending_applied)


    def test_10_sop_and_running_tasks_engine(self):
        """Test SOP engine: build running tasks from templates, ad-hoc task, resource locks, and completion with auto-material issue."""
        # 1. Setup Zone, Project, Task, Subtask
        self.service.insert_row("zones", {"zone_id": "ZONE_SOP", "zone_name": "Khu SOP"})
        p_id, _ = self.service.insert_row("projects", {"code": "PRJ_TOMATO", "name": "Vụ Cà Chua Bi"})

        t_id, _ = self.service.insert_row(
            "tasks",
            {
                "project_id": p_id,
                "title": "Bón phân và tưới nước",
                "time_delta": "14 days",
                "delay": "0 days",
                "last": "28 days",
            },
        )

        st_id, _ = self.service.insert_row(
            "subtasks",
            {
                "task_id": t_id,
                "project_id": p_id,
                "title": "Bón lót gốc cà chua",
                "open_at": "06:00:00",
                "duration_minutes": 45,
                "target_ids": '["ZONE_SOP"]',
                "lock": 1,
                "glock": 1,
            },
        )

        c_id, _ = self.service.insert_row(
            "production_cycles",
            {
                "project_id": p_id,
                "zone_id": "ZONE_SOP",
                "name": "Lứa Cà Chua Xuân Hè",
                "start_date": "2026-10-15",
            },
        )

        # 2. Build running tasks: 0, 14, 28 days = 3 running tasks
        count, err = self.service.build_running_tasks_for_cycle(c_id)
        self.assertIsNone(err)
        self.assertEqual(count, 3)

        running_tasks = self.service.get_formatted_data("running_tasks", {"cycle_id": c_id})
        self.assertEqual(len(running_tasks), 3)
        first_rt = running_tasks[0]
        self.assertIn("Bón phân và tưới nước", first_rt["name"])

        # 3. Create Ad-hoc Task
        adhoc_id, err_ad = self.service.create_adhoc_task(
            name="Gia cố cọc tiêu khu SOP",
            cycle_id=c_id,
            project_id=p_id,
            duration_minutes=60,
        )
        self.assertIsNone(err_ad)
        self.assertIsNotNone(adhoc_id)

        # 4. Resource lock check
        # Mark first running task IN_PROGRESS
        self.service.update_row("running_tasks", {"status": "IN_PROGRESS"}, {"running_task_id": first_rt["running_task_id"]})
        is_locked, reason = self.service.check_resource_locks("ZONE_SOP", task_id=t_id)
        self.assertTrue(is_locked)
        self.assertIn("Global Lock", reason)

        # Target without lock
        is_locked_other, _ = self.service.check_resource_locks("ZONE_OTHER")
        self.assertFalse(is_locked_other)
        # 5. Complete running task with auto-material depletion
        u_id, _ = self.service.insert_row("units", {"code": "BAO_SOP", "name": "Bao"})
        cat_id, _ = self.service.insert_row("categories", {"code": "FERT_NPK_SOP", "name": "Phân NPK Đầu Trâu SOP", "default_unit_id": u_id})
        self.service.insert_row("category_unit_conversions", {"category_id": cat_id, "unit_id": u_id, "factor_to_base": 50.0})
        success, err_comp = self.service.complete_running_task(
            running_task_id=first_rt["running_task_id"],
            material_category_id=cat_id,
            quantity_used=2.0,
            material_unit="bao",
            completion_notes="Bón xong 2 bao quanh gốc, cây phát triển tốt",
        )
        self.assertTrue(success)
        self.assertIsNone(err_comp)

        # Verify running task updated
        rt_done = self.service.get_record("running_tasks", "running_task_id = ?", (first_rt["running_task_id"],), limit=1)
        self.assertEqual(rt_done["status"], "DONE")
        self.assertIsNotNone(rt_done["report_complete_at"])
        self.assertIsNotNone(rt_done["inventory_transaction_id"])

        # Verify auto-generated inventory transaction
        inv_tx = self.service.get_record("inventory_transactions", "transaction_id = ?", (rt_done["inventory_transaction_id"],), limit=1)
        self.assertIsNotNone(inv_tx)
        self.assertEqual(inv_tx["transaction_type"], "ISSUE")
        self.assertEqual(inv_tx["quantity_change"], -2.0)
        self.assertEqual(inv_tx["quantity_base"], 100.0)  # 2 * 50

    def test_11_issue_management_permissions(self):
        """Test issue management: worker cannot close issue, admin/owner can close."""
        iss_id, _ = self.service.insert_row(
            "issues",
            {
                "zone_id": "ZONE_A",
                "title": "Bơm nước nhỏ giọt bị kẹt",
                "severity": "MEDIUM",
                "status": "OPEN",
            },
        )

        # Worker attempts to close -> must be rejected
        ok_worker, err_w = self.service.manage_issue(
            issue_id=iss_id,
            action="CLOSE",
            reviewer_telegram_id="WORKER_1",
            resolution_notes="Tự ý đóng",
        )
        self.assertFalse(ok_worker)
        self.assertIn("Chỉ chủ vườn", err_w)

        # Owner closes -> succeeds
        ok_owner, err_o = self.service.manage_issue(
            issue_id=iss_id,
            action="CLOSE",
            reviewer_telegram_id="OWNER_1",
            resolution_notes="Đã thay van bơm mới",
        )
        self.assertTrue(ok_owner)
        self.assertIsNone(err_o)

        iss_closed = self.service.get_record("issues", "issue_id = ?", (iss_id,), limit=1)
        self.assertEqual(iss_closed["status"], "CLOSED")
        self.assertIsNotNone(iss_closed["closed_at"])
        self.assertEqual(iss_closed["resolution_notes"], "Đã thay van bơm mới")

    def test_12_inventory_transactions_and_reconciliation(self):
        """Test record_inventory_transaction with conversion, auto-batch creation, and reconciliation."""
        cat_id, _ = self.service.insert_row("categories", {"code": "LIME_POWDER", "name": "Vôi Bột Khử Khuẩn"})
        wh_id, _ = self.service.insert_row("warehouses", {"code": "WH_MAIN_TEST", "name": "Kho Chính Test"})

        # Receipt of 10 bao
        tx_id, err = self.service.record_inventory_transaction(
            item_name="Vôi Bột",
            category_id=cat_id,
            warehouse_id=wh_id,
            transaction_type="RECEIPT",
            quantity_change=10.0,
            unit_id=1,
        )
        self.assertIsNone(err)
        self.assertIsNotNone(tx_id)

        # Reconcile summary
        summary = self.service.reconcile_batches_and_stock(warehouse_id=wh_id)
        self.assertIsInstance(summary, list)

    def test_13_barter_exchange_atomic_sync(self):
        """Test record_barter_exchange performs dual-leg stock movement and financial cash difference."""
        cat_give, _ = self.service.insert_row("categories", {"code": "CORN_GRAIN", "name": "Ngô Hạt"})
        cat_receive, _ = self.service.insert_row("categories", {"code": "CHICKEN_FEED", "name": "Cám Gà"})
        wh_id, _ = self.service.insert_row("warehouses", {"code": "WH_BARTER", "name": "Kho Barter"})

        # Barter with cash difference = 500,000 (trang trại bù tiền)
        barter_id, err = self.service.record_barter_exchange(
            partner_name="Đại Lý Bảy Cò",
            give_category_id=cat_give,
            give_quantity=5.0,
            give_unit="bao",
            receive_category_id=cat_receive,
            receive_quantity=100.0,
            receive_unit="kg",
            estimated_value_vnd=2000000,
            cash_difference_vnd=500000,
            warehouse_id=wh_id,
            notes="Đổi 5 bao ngô lấy 100kg cám bù thêm 500k",
        )
        self.assertIsNone(err)
        self.assertIsNotNone(barter_id)

        barter_row = self.service.get_record("barter_transactions", "barter_id = ?", (barter_id,), limit=1)
        self.assertEqual(barter_row["partner_name"], "Đại Lý Bảy Cò")
        self.assertEqual(barter_row["cash_difference_vnd"], 500000)
        self.assertIsNotNone(barter_row["give_inventory_tx_id"])
        self.assertIsNotNone(barter_row["receive_inventory_tx_id"])
        self.assertIsNotNone(barter_row["payment_transaction_id"])

        # Check outbound transaction
        out_tx = self.service.get_record("inventory_transactions", "transaction_id = ?", (barter_row["give_inventory_tx_id"],), limit=1)
        self.assertEqual(out_tx["quantity_change"], -5.0)
        self.assertEqual(out_tx["transaction_type"], "ISSUE")

        # Check inbound transaction
        in_tx = self.service.get_record("inventory_transactions", "transaction_id = ?", (barter_row["receive_inventory_tx_id"],), limit=1)
        self.assertEqual(in_tx["quantity_change"], 100.0)
        self.assertEqual(in_tx["transaction_type"], "RECEIPT")

        # Check financial cash difference transaction
        fin_tx = self.service.get_record("financial_transactions", "transaction_id = ?", (barter_row["payment_transaction_id"],), limit=1)
        self.assertEqual(fin_tx["amount"], 500000)
        self.assertEqual(fin_tx["type"], "EXPENSE")

    def test_14_debt_payment_lifecycle(self):
        """Test debt tracking and installment payment lifecycle."""
        tx_cat, _ = self.service.insert_row("transaction_categories", {"code": "DEBT_SEED", "name": "Tiền Giống Cây", "type": "EXPENSE"})
        debt_id, _ = self.service.insert_row(
            "debt_records",
            {
                "debt_type": "PAYABLE",
                "partner_name": "Đại Lý Giống Năm Lúa",
                "initial_amount": 10000000,
            },
        )

        # 1. Partial payment 4,000,000
        pay1_id, err1 = self.service.process_debt_payment(
            debt_id=debt_id,
            amount_paid=4000000,
            notes="Thanh toán đợt 1",
        )
        self.assertIsNone(err1)
        self.assertIsNotNone(pay1_id)

        debt1 = self.service.get_record("debt_records", "debt_id = ?", (debt_id,), limit=1)
        self.assertEqual(debt1["paid_amount"], 4000000)
        self.assertEqual(debt1["remaining_amount"], 6000000)
        self.assertEqual(debt1["status"], "PARTIAL")

        # 2. Final settlement 6,000,000
        pay2_id, err2 = self.service.process_debt_payment(
            debt_id=debt_id,
            amount_paid=6000000,
            notes="Tất toán nợ còn lại",
        )
        self.assertIsNone(err2)
        self.assertIsNotNone(pay2_id)

        debt2 = self.service.get_record("debt_records", "debt_id = ?", (debt_id,), limit=1)
        self.assertEqual(debt2["paid_amount"], 10000000)
        self.assertEqual(debt2["remaining_amount"], 0)
        self.assertEqual(debt2["status"], "SETTLED")

    def test_15_pending_service_functional_helpers(self):
        """Test functional helpers exported by pending_service."""
        from src.db.pending_service import (
            create_adhoc_task,
            complete_running_task,
            check_resource_locks,
            record_barter_exchange,
            process_debt_payment,
        )
        with get_db(self.db_path) as conn:
            # Ad-hoc task
            rt_id = create_adhoc_task(conn, name="Đắp bờ chống tràn ao cá")
            self.assertIsInstance(rt_id, int)

            # Complete task
            ok = complete_running_task(conn, running_task_id=rt_id, completion_notes="Hoàn thành bờ ao")
            self.assertTrue(ok)

            # Check locks
            locked, _ = check_resource_locks(conn, target_ids="AO_CA")
            self.assertFalse(locked)


if __name__ == "__main__":
    unittest.main()
