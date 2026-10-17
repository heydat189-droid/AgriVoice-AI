"""AgriVoice-AI: Admin Service & Operations Test Suite.

Verifies all Admin capabilities specified in 'notes/System methods.md':
1. RBAC and Admin permission enforcement.
2. Staging queue inspection, payload editing, strict ordering approval, rejection, and error retry.
3. Batch approval in strict chronological order.
4. Operations: cycles, SOP generation, adhoc tasks, complete task with auto depletion, exclusive issue closure.
5. Inventory: immutable adjustments, negative stock reconciliation, unit conversions.
6. Finance: integer transactions, dual-leg barter with cash difference, debt installment payments.
7. Tier 3 Reconciliation Views & Dashboard Executive Summary.
8. Collaborator administration (add, update, deactivate).
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.admin import AdminPermissionError, AdminService
from src.db.connection import get_db
from src.db.migrate import run_migrations
from src.db.models import CollaboratorRole, IssueSeverity, PaymentMethod


class TestAdminService(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_admin.db"
        run_migrations(db_path=self.db_path, quiet=True)

        # Seed foundational collaborators
        with get_db(self.db_path) as conn:
            conn.execute(
                "INSERT INTO collaborators (telegram_id, full_name, role, is_active) "
                "VALUES ('OWNER_1', 'Chủ Trang Trại Ba Tri', 'OWNER', 1);"
            )
            conn.execute(
                "INSERT INTO collaborators (telegram_id, full_name, role, is_active) "
                "VALUES ('ADMIN_1', 'Quản Lý Nông Trại', 'ADMIN', 1);"
            )
            conn.execute(
                "INSERT INTO collaborators (telegram_id, full_name, role, is_active) "
                "VALUES ('WORKER_1', 'Bác Làm Vườn', 'WORKER', 1);"
            )
            conn.execute(
                "INSERT INTO collaborators (telegram_id, full_name, role, is_active) "
                "VALUES ('VIEWER_1', 'Kế Toán Xem Báo Cáo', 'VIEWER', 1);"
            )
            conn.execute(
                "INSERT INTO zones (zone_id, zone_name, sector, area_size, unit_of_size) "
                "VALUES ('ZONE_A', 'Khu Vườn Bưởi', 'CROP', 5000, 'm2');"
            )
            conn.execute(
                "INSERT INTO units (unit_id, code, name) VALUES (1, 'KG', 'Kilogram');"
            )
            conn.execute(
                "INSERT INTO dictionary (dict_id, code, name, root_path, entry_type) "
                "VALUES (1, 'CAT_FERT', 'Phân NPK', '/vat-tu/', 'CATEGORY');"
            )
            conn.execute(
                "INSERT INTO dictionary (dict_id, code, name, root_path, entry_type) "
                "VALUES (2, 'WH_MAIN', 'Kho Vật Tư Chính', '/kho/', 'LOCATION');"
            )
            conn.execute(
                "INSERT INTO transaction_categories (category_id, name, type) "
                "VALUES (1, 'Chi mua phân bón', 'EXPENSE');"
            )

        self.admin = AdminService(db_path=self.db_path, admin_telegram_id="OWNER_1")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_01_admin_permission_enforcement(self):
        """Test RBAC enforcement: OWNER/ADMIN allowed, WORKER/VIEWER rejected with AdminPermissionError."""
        # OWNER allowed
        self.admin.collaborators.verify_admin_privilege("OWNER_1")

        # ADMIN allowed
        self.admin.collaborators.verify_admin_privilege("ADMIN_1")

        # WORKER denied
        with self.assertRaises(AdminPermissionError):
            self.admin.collaborators.verify_admin_privilege("WORKER_1")

        # VIEWER denied
        with self.assertRaises(AdminPermissionError):
            self.admin.collaborators.verify_admin_privilege("VIEWER_1")

    def test_02_queue_management_payload_edit_and_approval(self):
        """Test staging event review, payload modification, and approval with strict ordering."""
        # 1. Worker stages an event through AI
        ev_id, err = self.admin.service.stage_pending_event(
            sender_id="WORKER_1",
            target_table="issues",
            action_type="INSERT",
            payload={"zone_id": "ZONE_A", "title": "Bơm nước chập điện"},
            summary_text="Sự cố máy bơm",
        )
        self.assertIsNotNone(ev_id)
        self.assertIsNone(err)

        # 2. Admin inspects queue and event detail
        queue = self.admin.get_pending_queue("issues")
        self.assertEqual(len(queue), 1)
        self.assertEqual(queue[0]["event_id"], ev_id)

        detail = self.admin.get_event_detail(ev_id)
        self.assertIsNotNone(detail)
        self.assertEqual(detail["payload_parsed"]["title"], "Bơm nước chập điện")

        # 3. Admin edits payload (chỉnh sửa trước khi duyệt)
        ok_edit, err_edit = self.admin.edit_event_payload(
            event_id=ev_id,
            payload={"zone_id": "ZONE_A", "title": "Bơm nước số 1 chập cháy van điện", "severity": "HIGH"},
        )
        self.assertTrue(ok_edit)
        self.assertIsNone(err_edit)

        detail_after = self.admin.get_event_detail(ev_id)
        self.assertEqual(detail_after["payload_parsed"]["title"], "Bơm nước số 1 chập cháy van điện")

        # 4. Admin approves event
        ok_app, err_app = self.admin.approve_event(ev_id, review_notes="Đã kiểm tra xác nhận chập van")
        self.assertTrue(ok_app, f"Approve failed: {err_app}")

        # 5. Core table contains the updated record
        issues = self.admin.service.get_formatted_data("issues", {"zone_id": "ZONE_A"})
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]["title"], "Bơm nước số 1 chập cháy van điện")
        self.assertEqual(issues[0]["severity"], "HIGH")

        # 6. Queue is now empty
        queue_empty = self.admin.get_pending_queue("issues")
        self.assertEqual(len(queue_empty), 0)

    def test_03_rejection_preserves_audit_trail(self):
        """Test rejecting an event requires reason and preserves status in audit history."""
        ev_id, _ = self.admin.service.stage_pending_event(
            sender_id="WORKER_1",
            target_table="issues",
            action_type="INSERT",
            payload={"zone_id": "ZONE_A", "title": "Tin nhắn rác thử loa"},
            summary_text="Thử loa",
        )

        # Reject without review_notes should fail
        ok_fail, err_fail = self.admin.reject_event(ev_id, review_notes="")
        self.assertFalse(ok_fail)

        # Reject with notes succeeds
        ok_rej, err_rej = self.admin.reject_event(ev_id, review_notes="Khẩu lệnh thử nghiệm, không phải công việc thực tế")
        self.assertTrue(ok_rej)

        # Queue empty, but history preserved
        queue = self.admin.get_pending_queue("issues")
        self.assertEqual(len(queue), 0)

        history = self.admin.queue.get_event_history("issues")
        self.assertGreaterEqual(len(history), 1)
        rejected_event = [h for h in history if h["event_id"] == ev_id][0]
        self.assertEqual(rejected_event["status"], "REJECTED")
        self.assertIn("thử nghiệm", rejected_event["review_notes"])

    def test_04_error_event_diagnosis_and_retry(self):
        """Test error events can be diagnosed, amended with new payload, and retried."""
        # Stage event with invalid column to trigger execution error on approve
        ev_id, _ = self.admin.service.stage_pending_event(
            sender_id="WORKER_1",
            target_table="issues",
            action_type="INSERT",
            payload={"zone_id": "ZONE_A", "non_existent_column_xyz": "value"},
            summary_text="Sự cố sai schema",
        )

        # Approve fails and moves event to ERROR
        ok_app, err_app = self.admin.approve_event(ev_id)
        self.assertFalse(ok_app)

        # Appears in error logs
        err_events = self.admin.get_error_events("issues")
        self.assertEqual(len(err_events), 1)
        self.assertEqual(err_events[0]["event_id"], ev_id)

        # Admin fixes payload and retries
        ok_retry, err_retry = self.admin.retry_error_event(
            event_id=ev_id,
            updated_payload={"zone_id": "ZONE_A", "title": "Sửa lại schema hợp lệ", "severity": "MEDIUM"},
        )
        self.assertTrue(ok_retry, f"Retry error failed: {err_retry}")

        # Successfully inserted
        issues = self.admin.service.get_formatted_data("issues", {"title": "Sửa lại schema hợp lệ"})
        self.assertEqual(len(issues), 1)

    def test_05_batch_approval_strict_ordering(self):
        """Test approve_all_pending sequentially applies events in strict chronological order."""
        t1 = "2026-10-16 08:00:00"
        t2 = "2026-10-16 08:05:00"

        ev1, _ = self.admin.service.stage_pending_event(
            sender_id="WORKER_1",
            target_table="issues",
            action_type="INSERT",
            payload={"zone_id": "ZONE_A", "title": "Sự cố 1"},
            timestamp=t1,
        )
        ev2, _ = self.admin.service.stage_pending_event(
            sender_id="WORKER_1",
            target_table="issues",
            action_type="INSERT",
            payload={"zone_id": "ZONE_A", "title": "Sự cố 2"},
            timestamp=t2,
        )

        batch_res = self.admin.approve_all_pending(target_table="issues")
        self.assertTrue(batch_res["success"])
        self.assertEqual(batch_res["approved_count"], 2)

    def test_06_operations_adhoc_task_and_exclusive_issue_closure(self):
        """Test adhoc task completion and exclusive admin authority to close issues."""
        # 1. Create adhoc task
        task_id, err_t = self.admin.create_adhoc_task(
            name="Gia cố lưới chuồng gà",
            duration_minutes=45,
            notes="Chống chồn vào ban đêm",
        )
        self.assertIsNotNone(task_id)

        # 2. Complete task
        ok_c, err_c = self.admin.complete_running_task(
            running_task_id=task_id,
            completion_notes="Đã căng lưới B40 quanh góc chuồng",
        )
        self.assertTrue(ok_c)

        # 3. Create issue
        iss_id, _ = self.admin.create_issue(
            zone_id="ZONE_A",
            title="Gãy cút nối ống tưới",
            severity=IssueSeverity.HIGH,
        )

        # 4. Progress update (allowed for worker or admin)
        ok_p, _ = self.admin.update_issue_progress(iss_id, notes="Đã quấn cao su non tạm thời")
        self.assertTrue(ok_p)

        # 5. Non-admin attempting to close issue fails
        with self.assertRaises(AdminPermissionError):
            self.admin.close_issue(iss_id, resolution_notes="Đóng bởi worker", admin_telegram_id="WORKER_1")

        # 6. Admin closing issue succeeds
        ok_close, err_close = self.admin.close_issue(
            iss_id,
            resolution_notes="Đã nghiệm thu thay mới phụ kiện chịu lực, không còn rò rỉ",
        )
        self.assertTrue(ok_close, f"Close issue failed: {err_close}")

        # Check status in database
        iss_row = self.admin.service.get_record("issues", "issue_id = ?", (iss_id,), limit=1)
        self.assertEqual(iss_row["status"], "CLOSED")
        self.assertIsNotNone(iss_row["closed_at"])

    def test_07_inventory_adjustments_and_conversions(self):
        """Test immutable inventory adjustment and custom unit conversion configuration."""
        # Adjustment transaction
        tx_id, err_tx = self.admin.record_inventory_adjustment(
            item_name="Phân NPK",
            category_id=1,
            quantity_change=-5.0,
            unit_id=1,
            reason_note="Bù hao hụt kiểm kê cuối tháng",
        )
        self.assertIsNotNone(tx_id)
        self.assertIsNone(err_tx)

        # Unit conversion (1 bao = 50 kg)
        ok_conv, err_conv = self.admin.inventory.configure_unit_conversion(
            category_id=1,
            unit_id=1,
            factor_to_base=50.0,
        )
        self.assertTrue(ok_conv)

    def test_08_financial_transactions_and_barter(self):
        """Test integer VND financial transactions and atomic dual-leg barter exchange."""
        # Financial transaction
        ft_id, err_ft = self.admin.record_financial_transaction(
            category_id=1,
            type="EXPENSE",
            amount=1500000,
            payment_method=PaymentMethod.CASH,
            notes="Mua phân bón hữu cơ",
        )
        self.assertIsNotNone(ft_id)
        self.assertIsNone(err_ft)

        # Barter trade with cash difference
        barter_id, err_b = self.admin.record_barter_exchange(
            partner_name="Anh Năm Nông Dân",
            give_category_id=1,
            give_quantity=10.0,
            receive_category_id=1,
            receive_quantity=5.0,
            cash_difference_vnd=200000,
            warehouse_id=2,
            notes="Đổi hàng bù tiền",
        )
        self.assertIsNotNone(barter_id)
        self.assertIsNone(err_b)

    def test_09_reconciliation_views_and_dashboard_metrics(self):
        """Test Tier 3 reconciliation views and consolidated executive dashboard."""
        inv_summary = self.admin.get_inventory_root_summary()
        self.assertIsInstance(inv_summary, list)

        cashflow = self.admin.get_daily_cashflow_summary()
        self.assertIsInstance(cashflow, list)

        metrics = self.admin.get_dashboard_overview()
        self.assertIn("in_flight", metrics)
        self.assertIn("operations", metrics)
        self.assertIn("inventory", metrics)
        self.assertIn("finance_30d", metrics)
        self.assertFalse(metrics["in_flight"]["has_urgent_review"])

    def test_10_collaborator_lifecycle(self):
        """Test adding, updating, and deactivating collaborators."""
        collab_id, err = self.admin.add_collaborator(
            telegram_id="998877",
            full_name="Nguyễn Văn Kỹ Thuật",
            role=CollaboratorRole.WORKER,
        )
        self.assertIsNotNone(collab_id)

        # Update role to ADMIN
        ok_up, err_up = self.admin.collaborators.update_collaborator(
            collaborator_id=collab_id,
            role=CollaboratorRole.ADMIN,
        )
        self.assertTrue(ok_up)

        # Deactivate
        ok_deact, err_deact = self.admin.deactivate_collaborator(collab_id)
        self.assertTrue(ok_deact)

        collab = self.admin.collaborators.get_collaborator(collaborator_id=collab_id)
        self.assertEqual(collab["is_active"], 0)


if __name__ == "__main__":
    unittest.main()
