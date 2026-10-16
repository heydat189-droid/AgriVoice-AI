"""AgriVoice-AI: Dataclass Models & Database Insertion Test Suite.

Tests:
1. to_record() formatting and dictionary representation.
2. build_insert_query() query and parameter generation.
3. insert() execution and primary key auto-assignment.
4. insert_many() batch operations.
5. from_row() deserialization from query results.
6. Foreign key compliance when inserting models across domains.
7. Virtual / Readonly column filtering (StockCountLine variance).
"""

import sys
import tempfile
import unittest
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WORKSPACE_ROOT))

from src.db.connection import get_db
from src.db.migrate import run_migrations
from src.db.models import (
    Category,
    CategoryUnitConversion,
    Collaborator,
    FinancialTransaction,
    BarterTransaction,
    DebtRecord,
    DebtPayment,
    DebtType,
    DebtStatus,
    RunningTask,
    RunningTaskStatus,
    Harvest,
    InventoryTransaction,
    Issue,
    PendingActionType,
    PendingEvent,
    PendingEventStatus,
    ProcessedProduct,
    ProcessingBatch,
    Product,
    ProductBatch,
    ProductionCycle,
    ProductionLog,
    Project,
    StockCount,
    StockCountLine,
    Subtask,
    Supplier,
    Tag,
    Task,
    TaskComment,
    TaskTag,
    TransactionCategory,
    Unit,
    VoiceRawLog,
    Warehouse,
    YieldRecord,
    Zone,
)
from src.db.pending_service import (
    StrictOrderingViolationError,
    TargetTableExecutionError,
    approve_pending_event,
    get_error_events,
    get_pending_queue,
    get_table_with_virtual_overlay,
    reject_pending_event,
    stage_voice_event,
    update_pending_event_payload,
)

class TestDataclassModels(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_models.db"
        run_migrations(db_path=self.db_path, quiet=True)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_01_to_record_and_query_builder(self):
        """Test formatting dataclass into record dictionary and building parameterized query."""
        collab = Collaborator(
            telegram_id="998877",
            full_name="Trần Văn Kỹ Thuật",
            role="ADMIN",
        )

        # 1. to_record() excludes None PK
        rec = collab.to_record()
        self.assertIn("telegram_id", rec)
        self.assertEqual(rec["telegram_id"], "998877")
        self.assertEqual(rec["role"], "ADMIN")
        self.assertNotIn("collaborator_id", rec)

        # 2. build_insert_query()
        sql, params = collab.build_insert_query()
        self.assertTrue(sql.startswith("INSERT INTO collaborators"))
        self.assertIn(":telegram_id", sql)
        self.assertIn("998877", params)

    def test_02_insert_and_auto_primary_key(self):
        """Test insert method automatically updates the autoincrement primary key."""
        with get_db(self.db_path) as conn:
            collab = Collaborator(
                telegram_id="11223344",
                full_name="Lê Thị Giám Sát",
                role="WORKER",
            )
            self.assertIsNone(collab.collaborator_id)

            pk = collab.insert(conn)
            self.assertIsNotNone(pk)
            self.assertEqual(collab.collaborator_id, pk)

            # Retrieve from DB using from_row
            cur = conn.cursor()
            cur.execute("SELECT * FROM collaborators WHERE collaborator_id = ?", (pk,))
            row = cur.fetchone()
            self.assertIsNotNone(row)

            loaded = Collaborator.from_row(row)
            self.assertEqual(loaded.collaborator_id, pk)
            self.assertEqual(loaded.telegram_id, "11223344")
            self.assertEqual(loaded.full_name, "Lê Thị Giám Sát")
            self.assertEqual(loaded.role, "WORKER")

    def test_03_insert_many_batch(self):
        """Test insert_many for multiple entities."""
        with get_db(self.db_path) as conn:
            units = [
                Unit(code="KG", name="Kilogram", symbol="kg"),
                Unit(code="LIT", name="Lít", symbol="l"),
                Unit(code="GOI", name="Gói", symbol="gói"),
            ]
            count = Unit.insert_many(conn, units)
            self.assertEqual(count, 3)

            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM units")
            total = cur.fetchone()[0]
            self.assertEqual(total, 3)

    def test_04_full_domain_workflow_with_models(self):
        """Test inserting complex interconnected models across farm domains."""
        with get_db(self.db_path) as conn:
            # 1. Identity & Location
            worker = Collaborator(telegram_id="555", full_name="Bác Ba Phi", role="WORKER")
            worker_id = worker.insert(conn)

            zone = Zone(zone_id="KHU_DUA", zone_name="Vườn Dưa Lưới", sector="CROP", area_size=1200.0)
            zone.insert(conn)

            # 2. Inventory
            unit = Unit(code="BAO", name="Bao 50kg")
            unit_id = unit.insert(conn)

            wh = Warehouse(code="KHO_01", name="Kho Phân Bón")
            wh_id = wh.insert(conn)

            prod = Product(sku="PB-NPK", name="Phân NPK", base_unit_id=unit_id)
            prod_id = prod.insert(conn)

            batch = ProductBatch(
                product_id=prod_id,
                batch_number="BATCH-001",
                warehouse_id=wh_id,
                quantity_remaining=50.0,
            )
            batch_id = batch.insert(conn)

            # 3. Project & Task
            project = Project(name="Vụ Đông Xuân 2026", code="DX-2026")
            prj_id = project.insert(conn)

            task = Task(project_id=prj_id, assigned_to=worker_id, title="Bón lót đợt 1")
            task_id = task.insert(conn)

            subtask = Subtask(task_id=task_id, title="Kiểm tra độ ẩm đất")
            sub_id = subtask.insert(conn)

            tag = Tag(name="KhanCap", color="#FF0000")
            tag_id = tag.insert(conn)

            task_tag = TaskTag(task_id=task_id, tag_id=tag_id)
            task_tag.insert(conn)

            comment = TaskComment(task_id=task_id, author_id=worker_id, content="Đất đã đủ ẩm")
            comment.insert(conn)

            # 4. Production Cycle & Harvest
            cycle = ProductionCycle(
                project_id=prj_id,
                zone_id="KHU_DUA",
                name="Dưa Lưới F1",
                subject_name="Dưa lưới",
                start_date="2026-10-15",
            )
            cycle_id = cycle.insert(conn)

            log = ProductionLog(
                cycle_id=cycle_id,
                logged_by=worker_id,
                log_date="2026-10-16",
                activity_type="FERTILIZING",
                title="Bón phân lót",
            )
            log.insert(conn)

            harvest = Harvest(
                cycle_id=cycle_id,
                harvest_date="2026-12-20",
                total_quantity=1500.0,
                unit="kg",
            )
            harvest_id = harvest.insert(conn)

            yield_rec = YieldRecord(
                harvest_id=harvest_id,
                product_name="Dưa lưới loại 1",
                quantity_total=1200.0,
                quantity_grade_a=1200.0,
            )
            yield_rec.insert(conn)

            # 5. Finance
            cat = TransactionCategory(name="Bán Nông Sản", type="INCOME")
            cat_id = cat.insert(conn)

            tx = FinancialTransaction(
                cycle_id=cycle_id,
                category_id=cat_id,
                type="INCOME",
                amount=36000000,
                transaction_date="2026-12-21",
                recorded_by=worker_id,
            )
            tx.insert(conn)

            # 6. Issues & AI Voice Raw Log
            issue = Issue(
                zone_id="KHU_DUA",
                reporter_id=worker_id,
                title="Hỏng van tưới",
                severity="HIGH",
            )
            issue_id = issue.insert(conn)

            voice_log = VoiceRawLog(
                sender_id="555",
                audio_file_path="/data/audio_01.ogg",
                raw_transcript="Báo cáo hỏng van tưới ở khu dưa",
                detected_intent="REPORT_ISSUE",
                execution_status="SUCCESS",
            )
            voice_id = voice_log.insert(conn)

            # Verify all records inserted successfully
            cur = conn.cursor()
            cur.execute("PRAGMA foreign_key_check;")
            self.assertEqual(cur.fetchall(), [])

            # Check issue loaded back
            cur.execute("SELECT * FROM issues WHERE issue_id = ?", (issue_id,))
            loaded_issue = Issue.from_row(cur.fetchone())
            self.assertEqual(loaded_issue.title, "Hỏng van tưới")
            self.assertEqual(loaded_issue.severity, "HIGH")

    def test_05_readonly_virtual_column_exclusion(self):
        """Test that generated/virtual columns like stock_count_lines.variance are excluded from insert."""
        with get_db(self.db_path) as conn:
            wh = Warehouse(code="WH_TEST", name="Kho Kiểm Kê")
            wh_id = wh.insert(conn)

            unit = Unit(code="TRAI", name="Trái")
            unit_id = unit.insert(conn)

            prod = Product(sku="DUA-01", name="Dưa Lưới", base_unit_id=unit_id)
            prod_id = prod.insert(conn)

            sc = StockCount(code="SC-001", warehouse_id=wh_id)
            sc_id = sc.insert(conn)

            line = StockCountLine(
                stock_count_id=sc_id,
                product_id=prod_id,
                system_quantity=100.0,
                counted_quantity=95.0,
                variance=999.0,  # Should be ignored during insertion!
            )

            # Insert line
            line_id = line.insert(conn)
            self.assertIsNotNone(line_id)

            # Query line back from database
            cur = conn.cursor()
            cur.execute("SELECT * FROM stock_count_lines WHERE line_id = ?", (line_id,))
            row = cur.fetchone()
            loaded_line = StockCountLine.from_row(row)

            # Database generated virtual column variance should be 95 - 100 = -5.0
            self.assertEqual(loaded_line.variance, -5.0)

    def test_06_enum_usage_and_formatting(self):
        """Test using Enums directly in dataclass models, record formatting, and DB insertion."""
        from src.db import (
            CollaboratorRole,
            AllowedSource,
            FarmSector,
            TaskStatus,
            TaskPriority,
            IssueSeverity,
            IssueStatus,
        )

        with get_db(self.db_path) as conn:
            collab = Collaborator(
                telegram_id="9999",
                full_name="Nguyễn Văn Quản Lý",
                role=CollaboratorRole.ADMIN,
                allowed_source=AllowedSource.BOTH,
            )
            rec = collab.to_record()
            self.assertEqual(rec["role"], "ADMIN")
            self.assertEqual(rec["allowed_source"], "BOTH")

            collab_id = collab.insert(conn)
            self.assertIsNotNone(collab_id)

            # Zone with Enum
            zone = Zone(
                zone_id="ZONE_ENUM",
                zone_name="Khu Thủy Sản",
                sector=FarmSector.AQUACULTURE,
            )
            zone.insert(conn)

            # Issue with Enums
            issue = Issue(
                zone_id="ZONE_ENUM",
                reporter_id=collab_id,
                title="Nồng độ oxy trong ao cá giảm mạnh",
                severity=IssueSeverity.CRITICAL,
                status=IssueStatus.OPEN,
            )
            issue_id = issue.insert(conn)
            self.assertIsNotNone(issue_id)

            # Verify query and value equality
            cur = conn.cursor()
            cur.execute("SELECT severity, status FROM issues WHERE issue_id = ?", (issue_id,))
            row = cur.fetchone()
            self.assertEqual(row["severity"], IssueSeverity.CRITICAL)
            self.assertEqual(row["severity"], "CRITICAL")
            self.assertEqual(row["status"], IssueStatus.OPEN)


    def test_07_pending_event_model_and_service_workflow(self):
        """Test PendingEvent model, strict ordering check, approve/reject lifecycle and virtual overlay."""
        with get_db(self.db_path) as conn:
            # Setup base collaborator and zone
            owner = Collaborator(
                telegram_id="112233",
                full_name="Chủ Vườn Minh",
                role="OWNER",
            )
            owner_id = owner.insert(conn)

            zone = Zone(zone_id="ZONE_ORANGE", zone_name="Vườn Cam Xoàn")
            zone.insert(conn)

            # Stage Event 1 (earlier timestamp)
            ev1_id = stage_voice_event(
                conn=conn,
                target_table="issues",
                action_type=PendingActionType.INSERT,
                payload={"zone_id": "ZONE_ORANGE", "title": "Bọ trĩ cắn lá non", "severity": "MEDIUM"},
                raw_transcript="Khu vườn cam có bọ trĩ cắn lá non rồi",
                summary_text="Báo cáo bọ trĩ vườn cam",
                audio_path="/audio/orange_01.ogg",
                timestamp="2026-10-13 07:00:00",
            )

            # Stage Event 2 (later timestamp)
            ev2_id = stage_voice_event(
                conn=conn,
                target_table="issues",
                action_type=PendingActionType.INSERT,
                payload={"zone_id": "ZONE_ORANGE", "title": "Hệ thống tưới tự động rò rỉ", "severity": "HIGH"},
                raw_transcript="Van tưới vườn cam bị rò nước mạnh",
                summary_text="Rò rỉ ống tưới",
                audio_path="/audio/orange_02.ogg",
                timestamp="2026-10-13 08:30:00",
            )

            # Verify both events are queued and target table is UNTOUCHED
            issues_count = conn.execute("SELECT COUNT(*) FROM issues;").fetchone()[0]
            self.assertEqual(issues_count, 0, "Target table issues must remain untouched before approval")

            queue = get_pending_queue(conn)
            self.assertEqual(len(queue), 2)
            self.assertEqual(queue[0]["event_id"], ev1_id)

            # Test Strict Ordering: Attempting to approve Event 2 first MUST raise StrictOrderingViolationError
            with self.assertRaises(StrictOrderingViolationError):
                approve_pending_event(conn, event_id=ev2_id, reviewer_id=owner_id)

            # Test Virtual Overlay before approval
            overlay = get_table_with_virtual_overlay(
                conn=conn,
                target_table="issues",
                base_query="SELECT * FROM issues WHERE zone_id = ?",
                base_params=("ZONE_ORANGE",),
            )
            self.assertEqual(overlay["committed_count"], 0)
            self.assertEqual(overlay["pending_count"], 2)

            # Approve Event 1 in order
            approve_pending_event(
                conn=conn,
                event_id=ev1_id,
                reviewer_id=owner_id,
                review_notes="Đã kiểm tra qua audio, chuẩn xác",
            )

            # Target table now has 1 issue
            issues = conn.execute("SELECT * FROM issues WHERE zone_id = 'ZONE_ORANGE';").fetchall()
            self.assertEqual(len(issues), 1)
            self.assertEqual(issues[0]["title"], "Bọ trĩ cắn lá non")

            # Event 1 is APPROVED, not deleted (Audit Trail preserved)
            ev1_row = conn.execute("SELECT status, reviewed_by, review_notes, reviewed_at FROM pending_events WHERE event_id = ?;", (ev1_id,)).fetchone()
            self.assertEqual(ev1_row["status"], "APPROVED")
            self.assertEqual(ev1_row["reviewed_by"], owner_id)
            self.assertIsNotNone(ev1_row["reviewed_at"])

            # Reject Event 2 (e.g. bác giữ vườn nói nhầm hoặc AI nhận nhầm)
            reject_pending_event(
                conn=conn,
                event_id=ev2_id,
                reviewer_id=owner_id,
                review_notes="Nghe lại audio thấy đã sửa xong hôm qua",
            )
            ev2_row = conn.execute("SELECT status, reviewed_by, review_notes FROM pending_events WHERE event_id = ?;", (ev2_id,)).fetchone()
            self.assertEqual(ev2_row["status"], "REJECTED")
            self.assertEqual(ev2_row["reviewed_by"], owner_id)

            # Final check: Queue is now empty, target table has only 1 approved record
            queue_final = get_pending_queue(conn)
            self.assertEqual(len(queue_final), 0)

            issues_final = conn.execute("SELECT COUNT(*) FROM issues;").fetchone()[0]
            self.assertEqual(issues_final, 1)

            # 8. Test ERROR status logging when target table execution fails
            # Stage event with non-existent foreign key zone_id
            ev_err_id = stage_voice_event(
                conn=conn,
                target_table="issues",
                action_type=PendingActionType.INSERT,
                payload={"zone_id": "ZONE_NON_EXISTENT", "title": "Bẫy côn trùng bị rách"},
                summary_text="Sự cố bẫy côn trùng",
                audio_path="/audio/err_01.ogg",
            )

            # Attempting to approve must fail and update status to ERROR
            with self.assertRaises(TargetTableExecutionError):
                approve_pending_event(conn, event_id=ev_err_id, reviewer_id=owner_id)

            # Verify event in DB is now ERROR and has error_message
            err_events = get_error_events(conn)
            self.assertEqual(len(err_events), 1)
            self.assertEqual(err_events[0]["event_id"], ev_err_id)
            self.assertEqual(err_events[0]["status"], PendingEventStatus.ERROR)
            self.assertIsNotNone(err_events[0]["error_message"])
            self.assertIn("FOREIGN KEY", err_events[0]["error_message"])

            # Owner inspects, fixes payload with valid zone_id, and re-approves
            update_pending_event_payload(
                conn=conn,
                event_id=ev_err_id,
                payload={"zone_id": "ZONE_ORANGE", "title": "Bẫy côn trùng bị rách"},
                reset_status_to_pending=True,
            )

            # Re-approve succeeds cleanly
            approve_pending_event(conn, event_id=ev_err_id, reviewer_id=owner_id)
            ev_fixed = conn.execute("SELECT status, error_message FROM pending_events WHERE event_id = ?;", (ev_err_id,)).fetchone()
            self.assertEqual(ev_fixed["status"], "APPROVED")
            self.assertIsNone(ev_fixed["error_message"])

            # Issues count now incremented to 2
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM issues;").fetchone()[0], 2)

    def test_08_notes_schema_evolution_models(self):
        """Test new entities from notes: CategoryUnitConversion, RunningTask, BarterTransaction, DebtRecord, DebtPayment."""
        with get_db(self.db_path) as conn:
            # 1. Category and CategoryUnitConversion
            unit = Unit(code="BAO_50KG", name="Bao 50kg").insert(conn)
            cat = Category(
                code="CAT_FERT_ORANGE",
                name="Phân Bón Cam Xoàn",
                level=1,
                root_path="/phan-bon/",
                default_unit_id=unit,
                requires_expiry_tracking=1,
                convenient_names='["phân cam", "phân bón lót"]',
            )
            cat_id = cat.insert(conn)
            self.assertIsNotNone(cat_id)

            conv = CategoryUnitConversion(
                category_id=cat_id,
                unit_id=unit,
                factor_to_base=50.0,
                is_default_input=1,
            )
            conv_id = conv.insert(conn)
            self.assertIsNotNone(conv_id)

            # 2. Zone, Project, ProductionCycle, RunningTask
            zone = Zone(zone_id="ZONE_RUN", zone_name="Khu Thực Nghiệm SOP")
            zone.insert(conn)

            prj = Project(code="PRJ_SOP", name="Dự Án Canh Tác Chuẩn")
            prj_id = prj.insert(conn)

            cycle = ProductionCycle(
                zone_id="ZONE_RUN",
                name="Vụ Dưa Lưới Công Nghệ Cao",
                start_date="2026-10-15",
                project_id=prj_id,
                input_category_id=cat_id,
                input_quantity=100.0,
                area_size=1000.0,
                expected_yield=2500.0,
            )
            cycle_id = cycle.insert(conn)
            self.assertIsNotNone(cycle_id)

            running_task = RunningTask(
                name="Bón phân lót nhà màng đợt 1",
                cycle_id=cycle_id,
                project_id=prj_id,
                status=RunningTaskStatus.TODO,
                material_category_id=cat_id,
                quantity_used=2.0,
                material_unit="bao",
            )
            rt_id = running_task.insert(conn)
            self.assertIsNotNone(rt_id)

            # 3. BarterTransaction (Đổi hàng trực tiếp phi tiền tệ)
            cat2 = Category(code="CAT_CORN", name="Ngô Hạt Sinh Học").insert(conn)
            barter = BarterTransaction(
                partner_name="Nông hộ Chú Bảy",
                give_category_id=cat_id,
                give_quantity=5.0,
                give_unit="bao",
                receive_category_id=cat2,
                receive_quantity=200.0,
                receive_unit="kg",
                estimated_value_vnd=2500000,
                cash_difference_vnd=0,
            )
            barter_id = barter.insert(conn)
            self.assertIsNotNone(barter_id)

            # 4. DebtRecord and DebtPayment
            debt = DebtRecord(
                debt_type=DebtType.PAYABLE,
                partner_name="Đại lý phân bón Năm Lúa",
                initial_amount=15000000,
                due_date="2026-12-31",
            )
            debt_id = debt.insert(conn)
            self.assertIsNotNone(debt_id)

            # Verify virtual remaining_amount = initial_amount - paid_amount
            debt_row = conn.execute("SELECT remaining_amount, status FROM debt_records WHERE debt_id = ?;", (debt_id,)).fetchone()
            self.assertEqual(debt_row["remaining_amount"], 15000000)
            self.assertEqual(debt_row["status"], DebtStatus.UNPAID)

            # Create financial transaction for payment
            tx_cat = TransactionCategory(code="PAY_DEBT", name="Trả Nợ Đại Lý", type="EXPENSE").insert(conn)
            ft = FinancialTransaction(
                category_id=tx_cat,
                type="EXPENSE",
                amount=5000000,
                transaction_date="2026-10-15",
            )
            ft_id = ft.insert(conn)

            payment = DebtPayment(
                debt_id=debt_id,
                payment_transaction_id=ft_id,
                amount_paid=5000000,
                payment_date="2026-10-15",
            )
            pay_id = payment.insert(conn)
            self.assertIsNotNone(pay_id)

            # Update debt paid_amount
            conn.execute("UPDATE debt_records SET paid_amount = paid_amount + 5000000, status = 'PARTIAL' WHERE debt_id = ?;", (debt_id,))
            debt_updated = conn.execute("SELECT remaining_amount, status FROM debt_records WHERE debt_id = ?;", (debt_id,)).fetchone()
            self.assertEqual(debt_updated["remaining_amount"], 10000000)
            self.assertEqual(debt_updated["status"], DebtStatus.PARTIAL)

            # 5. Verify views
            yield_view = conn.execute("SELECT * FROM v_cycle_yield_performance WHERE cycle_id = ?;", (cycle_id,)).fetchone()
            self.assertIsNotNone(yield_view)
            self.assertEqual(yield_view["expected_yield"], 2500.0)

            cash_view = conn.execute("SELECT * FROM v_daily_cashflow_summary WHERE transaction_date = '2026-10-15';").fetchone()
            self.assertIsNotNone(cash_view)
            self.assertEqual(cash_view["daily_expense_vnd"], 5000000)


if __name__ == "__main__":
    unittest.main()
