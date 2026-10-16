"""AgriVoice-AI: AI Harness Test Suite.

Tests:
1. Harness initialization, API key discovery, and default configuration.
2. Transient error detection (429, 503, 500, ResourceExhausted, Overloaded).
3. Exponential backoff and model cascade failover under simulated rate limits.
4. Multimodal audio preparation (bytes, file, base64).
5. Agentic tool calling loop with mock client.
6. End-to-end process_voice and process_text with auto-staging into pending_events.
"""

import base64
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from google.genai import types
from google.genai.errors import APIError

from src.ai.harness import (
    DEFAULT_MODELS_CASCADE,
    GenAIHarness,
    HarnessResult,
    get_ai_harness,
)
from src.db.connection import get_db
from src.db.migrate import run_migrations


class TestGenAIHarness(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_harness.db"
        run_migrations(db_path=self.db_path, quiet=True)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_01_initialization_and_config(self):
        """Test harness config, defaults, and API key handling."""
        harness = GenAIHarness(
            api_key="AIzaTestKey123",
            models=["gemini-2.5-flash", "gemini-1.5-flash"],
            temperature=0.2,
            max_retries=3,
        )
        self.assertEqual(harness.api_key, "AIzaTestKey123")
        self.assertEqual(harness.models_cascade, ["gemini-2.5-flash", "gemini-1.5-flash"])
        self.assertEqual(harness.temperature, 0.2)
        self.assertEqual(harness.max_retries, 3)
        self.assertGreaterEqual(len(harness.raw_tools), 20)

        # Singleton accessor
        singleton = get_ai_harness()
        self.assertIsInstance(singleton, GenAIHarness)

    def test_02_transient_error_detection(self):
        """Test transient error detection for 429, 503, 500, ResourceExhausted, Overloaded."""
        harness = GenAIHarness(api_key="AIzaTestKey")

        # Mock APIError with code 429
        err_429 = APIError(code=429, response_json={"error": {"message": "Resource has been exhausted (e.g. check quota)."}})
        self.assertTrue(harness._is_transient_error(err_429))

        # Mock APIError with code 503
        err_503 = APIError(code=503, response_json={"error": {"message": "The model is overloaded. Please try again later."}})
        self.assertTrue(harness._is_transient_error(err_503))

        # String exception with rate limit marker
        err_str = RuntimeError("Error 429: Too Many Requests on free tier.")
        self.assertTrue(harness._is_transient_error(err_str))

        # Non-transient error (400 Bad Request, invalid argument)
        err_400 = APIError(code=400, response_json={"error": {"message": "Invalid argument provided."}})
        self.assertFalse(harness._is_transient_error(err_400))

    def test_03_audio_preparation(self):
        """Test prepare_audio_part with bytes, file path, and base64 string."""
        dummy_audio = b"OGG_HEADER_DATA_12345"

        # 1. From raw bytes
        part_bytes = GenAIHarness.prepare_audio_part(dummy_audio, mime_type="audio/ogg")
        self.assertEqual(part_bytes.inline_data.data, dummy_audio)
        self.assertEqual(part_bytes.inline_data.mime_type, "audio/ogg")

        # 2. From file path
        audio_file = Path(self.temp_dir.name) / "test_sample.ogg"
        audio_file.write_bytes(dummy_audio)

        part_file = GenAIHarness.prepare_audio_part(audio_file)
        self.assertEqual(part_file.inline_data.data, dummy_audio)
        self.assertEqual(part_file.inline_data.mime_type, "audio/ogg")

        # 3. From base64 string
        b64_str = base64.b64encode(dummy_audio).decode("utf-8")
        part_b64 = GenAIHarness.prepare_audio_part(b64_str, mime_type="audio/ogg")
        self.assertEqual(part_b64.inline_data.data, dummy_audio)

    def test_04_request_pacing(self):
        """Test _pace_request throttles consecutive calls."""
        harness = GenAIHarness(api_key="AIzaTestKey", min_request_interval=0.1)
        t1 = time.time()
        harness._pace_request()
        harness._pace_request()
        t2 = time.time()
        self.assertGreaterEqual(t2 - t1, 0.08)

    def test_05_resilient_retry_and_model_cascade_failover(self):
        """Test automatic retry and failover to secondary model when primary model is overloaded."""
        mock_client = MagicMock()
        harness = GenAIHarness(
            api_key="AIzaTestKey",
            models=["primary-model", "fallback-model"],
            max_retries=3,
            base_delay=0.01,
            max_delay=0.05,
            min_request_interval=0.0,
            client=mock_client,
        )

        attempts = []
        def fake_call(model_name: str):
            attempts.append(model_name)
            if len(attempts) <= 2:
                # First two attempts on primary model fail with 503
                raise APIError(code=503, response_json={"error": {"message": "Model is overloaded"}})
            # Third attempt on fallback model succeeds
            return "SUCCESS_RESPONSE"
        result, used_model = harness._call_with_resilience(fake_call, "test_op")
        self.assertEqual(result, "SUCCESS_RESPONSE")
        self.assertEqual(used_model, "fallback-model")
        self.assertIn("primary-model", attempts)
        self.assertIn("fallback-model", attempts)

    def test_06_agentic_loop_and_tool_execution(self):
        """Test agentic function calling loop with mock client response."""
        mock_client = MagicMock()
        harness = GenAIHarness(
            api_key="AIzaTestKey",
            client=mock_client,
            max_retries=1,
            base_delay=0.01,
            min_request_interval=0.0,
        )

        # Step 1: Model requests a tool call (create_task)
        call_part = types.Part.from_function_call(
            name="create_task",
            args={"title": "Kiểm tra sâu rầy vườn chuối"},
        )
        step1_candidate = MagicMock()
        step1_candidate.content = types.Content(role="model", parts=[call_part])
        step1_resp = MagicMock()
        step1_resp.candidates = [step1_candidate]
        step1_resp.function_calls = [call_part.function_call]
        step1_resp.text = None

        # Step 2: Model finishes with synthesized text
        final_part = types.Part.from_text(text="Dạ đã lên lịch công việc: Kiểm tra sâu rầy vườn chuối.")
        step2_candidate = MagicMock()
        step2_candidate.content = types.Content(role="model", parts=[final_part])
        step2_resp = MagicMock()
        step2_resp.candidates = [step2_candidate]
        step2_resp.function_calls = None
        step2_resp.text = "Dạ đã lên lịch công việc: Kiểm tra sâu rầy vườn chuối."

        mock_client.models.generate_content.side_effect = [step1_resp, step2_resp]

        contents = [types.Content(role="user", parts=[types.Part.from_text(text="Nhắc tôi kiểm tra sâu rầy vườn chuối")])]
        final_text, records, model_used, steps = harness.execute_agentic_loop(contents)

        self.assertEqual(steps, 2)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].title, "Kiểm tra sâu rầy vườn chuối")
        self.assertIn("lên lịch công việc", final_text)

    def test_07_process_voice_and_auto_stage(self):
        """Test process_voice pipeline automatically creates and stages events into pending_events."""
        mock_client = MagicMock()
        harness = GenAIHarness(
            api_key="AIzaTestKey",
            client=mock_client,
            min_request_interval=0.0,
        )

        # Setup mock response creating an issue
        call_part = types.Part.from_function_call(
            name="create_issue",
            args={"zone_id": "ZONE_A", "title": "Bẫy đèn bị hỏng"},
        )
        resp1 = MagicMock()
        resp1.candidates = [MagicMock(content=types.Content(role="model", parts=[call_part]))]
        resp1.function_calls = [call_part.function_call]
        resp1.text = None

        resp2 = MagicMock()
        resp2.candidates = [MagicMock(content=types.Content(role="model", parts=[types.Part.from_text(text="Đã ghi nhận sự cố bẫy đèn.")]))]
        resp2.function_calls = None
        resp2.text = "Đã ghi nhận sự cố bẫy đèn."

        mock_client.models.generate_content.side_effect = [resp1, resp2]

        dummy_audio = b"DUMMY_OGG_VOICE"
        result = harness.process_voice(
            audio=dummy_audio,
            sender_id="WORKER_BA_BA",
            user_prompt="Báo cáo sự cố bẫy đèn",
            db_path=self.db_path,
            auto_stage=True,
        )

        self.assertTrue(result.success)
        self.assertEqual(result.events_staged, 1)
        self.assertEqual(len(result.event_ids), 1)
        self.assertIn("bẫy đèn", result.reply_text)

        # Verify staged event in pending_events table
        with get_db(self.db_path) as conn:
            ev = conn.execute("SELECT event_id, target_table, sender_id, status FROM pending_events WHERE event_id = ?;", (result.event_ids[0],)).fetchone()
            self.assertIsNotNone(ev)
            self.assertEqual(ev["target_table"], "issues")
            self.assertEqual(ev["sender_id"], "WORKER_BA_BA")
            self.assertEqual(ev["status"], "PENDING")

    def test_08_process_text_pipeline(self):
        """Test process_text query pipeline."""
        mock_client = MagicMock()
        harness = GenAIHarness(
            api_key="AIzaTestKey",
            client=mock_client,
            min_request_interval=0.0,
        )

        # Mock query response without action
        resp = MagicMock()
        resp.candidates = [MagicMock(content=types.Content(role="model", parts=[types.Part.from_text(text="Khu A có diện tích 5000 m2.")]))]
        resp.function_calls = None
        resp.text = "Khu A có diện tích 5000 m2."

        mock_client.models.generate_content.return_value = resp

        result = harness.process_text("Khu A diện tích bao nhiêu?", db_path=self.db_path)
        self.assertTrue(result.success)
        self.assertEqual(result.events_staged, 0)
        self.assertIn("5000 m2", result.reply_text)

    def test_09_agentic_loop_ad_hoc_issue_and_manage_issue(self):
        """Test agentic tool execution for ad-hoc task creation via create_issue and managing issue notes."""
        from src.ai.functions import execute_function

        # 1. Create ad-hoc task as an issue
        issue_rec = execute_function(
            "create_issue",
            {
                "zone_id": "ZONE_TEST",
                "title": "Gia cố hàng rào khu nuôi gà",
                "description": "Ước tính 60 phút, giao anh Ba",
                "severity": "LOW",
            },
        )
        self.assertEqual(issue_rec.title, "Gia cố hàng rào khu nuôi gà")
        self.assertEqual(issue_rec.severity, "LOW")

        # Insert into test db
        with get_db(self.db_path) as conn:
            conn.execute("INSERT OR IGNORE INTO zones (zone_id, zone_name) VALUES ('ZONE_TEST', 'Khu Test');")
            iss_id = issue_rec.insert(conn)

        # 2. Update issue notes via manage_issue
        res_update = execute_function(
            "manage_issue",
            {
                "issue_id": iss_id,
                "action": "IN_PROGRESS",
                "notes": "Đã mua dây kẽm gai chuẩn bị rào",
                "db_path": self.db_path,
            },
        )
        self.assertTrue(res_update["success"])

        with get_db(self.db_path) as conn:
            row = conn.execute("SELECT status, notes FROM issues WHERE issue_id = ?;", (iss_id,)).fetchone()
            self.assertEqual(row["status"], "IN_PROGRESS")
            self.assertIn("dây kẽm gai", row["notes"])

        # 3. Close issue via manage_issue
        res_close = execute_function(
            "manage_issue",
            {
                "issue_id": iss_id,
                "action": "CLOSED",
                "resolution_notes": "Đã gia cố xong hàng rào kiên cố",
                "db_path": self.db_path,
            },
        )
        self.assertTrue(res_close["success"])

        with get_db(self.db_path) as conn:
            row_closed = conn.execute("SELECT status, closed_at, resolution_notes FROM issues WHERE issue_id = ?;", (iss_id,)).fetchone()
            self.assertEqual(row_closed["status"], "CLOSED")
            self.assertIsNotNone(row_closed["closed_at"])
            self.assertEqual(row_closed["resolution_notes"], "Đã gia cố xong hàng rào kiên cố")


if __name__ == "__main__":
    unittest.main()
