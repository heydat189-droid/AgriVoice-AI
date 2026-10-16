import os
import unittest
from pathlib import Path
from pydantic import ValidationError

from src.db.connection import get_db
from src.db.migrate import run_migrations
from src.db.models import (
    BaseRecord,
    Collaborator,
    Zone,
    Task,
    Issue,
    FinancialTransaction,
    ProductionLog,
    Harvest,
    VoiceRawLog,
    PendingEvent,
)
from src.ai.response import (
    PendingEvents,
    AIResponse,
    VoiceAIResponse,
    EXCLUDED_RECORD_CLASSES,
    SUPPORTED_RECORDS,
)
from src.ai.functions import (
    AVAILABLE_FUNCTIONS,
    execute_function,
    create_new_zone,
    create_task,
    create_production_log,
    create_harvest,
    create_financial_transaction,
    create_issue,
    create_record,
    get_data_with_pending_applied,
    search_zone,
    search_category,
    search_unit,
    search_supplier,
    search_issue,
    search_task,
)
from src.ai.tools import (
    ALL_TOOLS,
    GET_DATA_WITH_PENDING_APPLIED_TOOL,
    SEARCH_ZONE_TOOL,
    SEARCH_CATEGORY_TOOL,
    SEARCH_UNIT_TOOL,
    SEARCH_SUPPLIER_TOOL,
    SEARCH_ISSUE_TOOL,
    SEARCH_TASK_TOOL,
    get_genai_tools,
    dict_to_function_declaration,
)
import src.ai as ai_pkg

class TestAISchemaAndTools(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db_path = Path("/tmp/test_ai_suite.db")
        if cls.db_path.exists():
            cls.db_path.unlink()
        run_migrations(db_path=cls.db_path, quiet=True)

    @classmethod
    def tearDownClass(cls):
        if cls.db_path.exists():
            cls.db_path.unlink()

    def test_01_response_schema_validation(self):
        """Test PendingEvents correctly accepts BaseRecord instances and dicts."""
        zone = Zone(zone_id="ZONE_TEST_1", zone_name="Khu Thử Nghiệm", area_size=500.0)
        task = Task(title="Làm cỏ vườn cam")
        issue = Issue(zone_id="ZONE_TEST_1", title="Sâu cuốn lá")

        res = PendingEvents(
            records=[zone, task, issue],
            raw_transcript="Tạo khu thử nghiệm, làm cỏ vườn cam và phát hiện sâu cuốn lá",
            summary_text="Tạo khu thử nghiệm, làm cỏ, phát hiện sâu cuốn lá",
        )

        self.assertEqual(len(res.records), 3)
        self.assertEqual(res.records[0].zone_id, "ZONE_TEST_1")
        self.assertEqual(res.records[1].title, "Làm cỏ vườn cam")
        self.assertEqual(res.records[2].title, "Sâu cuốn lá")
        self.assertEqual(res.raw_transcript, "Tạo khu thử nghiệm, làm cỏ vườn cam và phát hiện sâu cuốn lá")
        self.assertIsNotNone(res.summary_text)

        # Check to_dict serialization
        d = res.to_dict()
        self.assertEqual(d["raw_transcript"], res.raw_transcript)
        self.assertEqual(len(d["records"]), 3)

    def test_02_exclusion_of_voice_logs_and_pending_events(self):
        """Test that VoiceRawLog and PendingEvent are strictly rejected by PendingEvents."""
        voice_log = VoiceRawLog(
            sender_id="123",
            audio_file_path="audio.ogg",
            raw_transcript="Test voice log",
        )
        pending_event = PendingEvent(
            target_table="zones",
            action_type="INSERT",
            payload_json="{}",
        )

        # 1. Instance rejection
        with self.assertRaises(ValidationError):
            PendingEvents(records=[voice_log])

        with self.assertRaises(ValidationError):
            PendingEvents(records=[pending_event])

        # 2. Dict table_name rejection
        with self.assertRaises(ValidationError):
            PendingEvents(records=[{"target_table": "voice_raw_logs", "raw_transcript": "abc"}])

        with self.assertRaises(ValidationError):
            PendingEvents(records=[{"table_name": "pending_events", "target_table": "zones"}])

    def test_03_stage_all_events_to_db(self):
        """Test stage_all_events saves all records into pending_events staging queue."""
        zone = create_new_zone(zone_name="Vườn Bưởi Hồng", area_size=1500.0)
        task = create_task(title="Bón vôi bột khử khuẩn")

        response = PendingEvents(
            records=[zone, task],
            raw_transcript="Khai báo vườn bưởi hồng 1500 mét vuông và lên lịch bón vôi",
            summary_text="Tạo vườn bưởi hồng 1500m2, lên lịch bón vôi",
        )

        with get_db(self.db_path) as conn:
            event_ids = response.stage_all_events(conn, audio_path="data/test.ogg")
            self.assertEqual(len(event_ids), 2)

            cur = conn.cursor()
            cur.execute("SELECT event_id, target_table, action_type, raw_transcript, summary_text FROM pending_events WHERE event_id IN (?, ?)", tuple(event_ids))
            rows = cur.fetchall()
            self.assertEqual(len(rows), 2)
            tables = {r["target_table"] for r in rows}
            self.assertIn("zones", tables)
            self.assertIn("tasks", tables)
            for r in rows:
                self.assertEqual(r["action_type"], "INSERT")
                self.assertEqual(r["raw_transcript"], response.raw_transcript)

    def test_04_functions_execution(self):
        """Test domain functions in functions.py return valid BaseRecords."""
        zone = create_new_zone("Khu Thanh Long", area_size=3000.0)
        self.assertIsInstance(zone, BaseRecord)
        self.assertTrue(zone.zone_id.startswith("ZONE_"))

        task = create_task("Tỉa cành nhánh")
        self.assertIsInstance(task, BaseRecord)
        self.assertEqual(task.title, "Tỉa cành nhánh")

        pl = create_production_log(cycle_id=1, title="Bón phân hữu cơ", quantity=50, unit="kg")
        self.assertIsInstance(pl, BaseRecord)
        self.assertEqual(pl.quantity, 50.0)

        ft = create_financial_transaction(category_id=1, type="EXPENSE", amount=1500000, partner_name="Đại lý phân bón A")
        self.assertIsInstance(ft, BaseRecord)
        self.assertEqual(ft.amount, 1500000)

        issue = create_issue(zone_id=zone.zone_id, title="Thiếu nước tưới")
        self.assertIsInstance(issue, BaseRecord)
        self.assertEqual(issue.zone_id, zone.zone_id)

        # Dynamic dispatch
        executed = execute_function("create_task", {"title": "Phun thuốc sinh học"})
        self.assertIsInstance(executed, Task)
        self.assertEqual(executed.title, "Phun thuốc sinh học")

        # Query function with pending overlay
        with get_db(self.db_path) as conn:
            conn.execute("INSERT OR IGNORE INTO zones (zone_id, zone_name) VALUES ('ZONE_TEST_1', 'Khu Thử Nghiệm');")
            conn.execute(
                "INSERT INTO pending_events (target_table, action_type, payload_json, status) "
                "VALUES ('issues', 'INSERT', '{\"zone_id\": \"ZONE_TEST_1\", \"title\": \"Ống nước vỡ\"}', 'PENDING');"
            )
            conn.commit()

        query_res = get_data_with_pending_applied(table="issues", db_path=self.db_path)
        self.assertEqual(query_res["target_table"], "issues")
        self.assertGreaterEqual(query_res["committed_count"], 1)
        self.assertIn("Ống nước vỡ", [r["title"] for r in query_res["committed_data"]])

        dispatch_res = execute_function(
            "get_data_with_pending_applied",
            {"table": "issues", "db_path": self.db_path},
        )
        self.assertEqual(dispatch_res["target_table"], "issues")

        # Test dedicated domain search functions with pending overlay
        issue_search = search_issue(zone_id="ZONE_TEST_1", db_path=self.db_path)
        self.assertEqual(issue_search["target_table"], "issues")
        self.assertGreaterEqual(issue_search["committed_count"], 1)
        self.assertIn("Ống nước vỡ", [r["title"] for r in issue_search["committed_data"]])

        zone_search = search_zone(keyword="Khu Thử Nghiệm", db_path=self.db_path)
        self.assertEqual(zone_search["target_table"], "zones")
        self.assertGreaterEqual(zone_search["committed_count"], 1)

        dispatch_issue = execute_function(
            "search_issue",
            {"zone_id": "ZONE_TEST_1", "db_path": self.db_path},
        )
        self.assertEqual(dispatch_issue["target_table"], "issues")

    def test_05_tools_and_genai_definitions(self):
        """Test tools.py schema definitions and GenAI conversion."""
        self.assertGreaterEqual(len(ALL_TOOLS), 20)

        genai_tools = get_genai_tools()
        self.assertEqual(len(genai_tools), 1)
        declarations = genai_tools[0].function_declarations
        self.assertEqual(len(declarations), len(ALL_TOOLS))

        decl_names = {d.name for d in declarations}
        self.assertIn("create_new_zone", decl_names)
        self.assertIn("create_task", decl_names)
        self.assertIn("create_issue", decl_names)
        self.assertIn("create_financial_transaction", decl_names)
        self.assertIn("create_production_log", decl_names)
        self.assertIn("search_zone", decl_names)
        self.assertIn("search_category", decl_names)
        self.assertIn("search_unit", decl_names)
        self.assertIn("search_supplier", decl_names)
        self.assertIn("search_issue", decl_names)
        self.assertIn("search_task", decl_names)

    def test_06_package_exports_and_harness_integration(self):
        """Test src.ai root package exports GenAIHarness and core interfaces."""
        self.assertTrue(hasattr(ai_pkg, "GenAIHarness"))
        self.assertTrue(hasattr(ai_pkg, "get_ai_harness"))
        self.assertTrue(hasattr(ai_pkg, "DEFAULT_MODELS_CASCADE"))
        self.assertTrue(hasattr(ai_pkg, "PendingEvents"))
        self.assertTrue(hasattr(ai_pkg, "ALL_TOOLS"))
        self.assertTrue(hasattr(ai_pkg, "AVAILABLE_FUNCTIONS"))
        self.assertTrue(hasattr(ai_pkg, "execute_function"))


if __name__ == "__main__":
    unittest.main()
