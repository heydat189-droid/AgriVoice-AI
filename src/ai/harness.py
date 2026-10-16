"""AgriVoice-AI: Google GenAI Core Harness for Raspberry Pi.

Provides an edge-optimized AI harness using Google GenAI SDK (free tier compatible):
- Exponential backoff with random jitter against rate limits (HTTP 429) and peak-hour overload (HTTP 503).
- Model fallback cascade (auto-failover between gemini-2.5-flash, gemini-1.5-flash, etc.).
- Request pacer throttling to protect 15 RPM free tier quotas on edge hardware.
- Multimodal audio ingestion (raw bytes, files, base64) with low memory footprint.
- Agentic multi-turn tool calling loop using registered domain tools.
- Auto-staging of extracted business records into the V9 In-Flight buffer (pending_events).
"""

from __future__ import annotations

import base64
import json
import logging
import mimetypes
import os
import random
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple, Union

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

from google import genai
from google.genai import types
from google.genai.errors import APIError

from src.ai.functions import AVAILABLE_FUNCTIONS, execute_function
from src.ai.response import PendingEvents
from src.ai.tools import ALL_TOOLS, get_genai_tools
from src.db.connection import get_db, get_db_path
from src.db.models import BaseRecord
from src.db.pending_service import stage_voice_event

logger = logging.getLogger("agrivoice.ai.harness")


# ==============================================================================
# DEFAULT CONFIGURATION & FREE-TIER MODELS CASCADE
# ==============================================================================

# Priority list of free-tier compatible models with automatic failover
DEFAULT_MODELS_CASCADE: List[str] = [
    "gemini-3.5-flash-lite",
    "gemini-3.8-flash",
    "gemini-2.0-flash",
    "gemini-2.5-flash",
]

DEFAULT_SYSTEM_INSTRUCTION = (
    "Bạn là hệ thống xử lý tác vụ nông nghiệp tự động AgriVoice-AI.\n"
    "Nhiệm vụ: Phân tích khẩu lệnh thoại hoặc văn bản của nông trại, thực thi chính xác các hành động qua Tool Calling và phản hồi kết quả.\n"
    "\n"
    "1. NGUYÊN TẮC GIAO TIẾP VÀ XƯNG HÔ (MÁY MÓC, TRỰC DIỆN):\n"
    "   - TUYỆT ĐỐI KHÔNG XƯNG HÔ (không dùng 'con', 'em', 'cháu', 'tôi', 'chú', 'bác', 'anh', 'chị').\n"
    "   - KHÔNG dùng từ ngữ giao tiếp xã giao, cảm xúc, thân mật (như 'dạ', 'ạ', 'nghen', 'nhé', 'xin chào', 'rất vui').\n"
    "   - Phản hồi ngắn gọn, chính xác, khách quan như log hệ thống máy móc.\n"
    "\n"
    "2. QUY TẮC PHÂN LOẠI VÀ THỰC THI (TOOL CALLING):\n"
    "   - NHẬT KÝ SẢN XUẤT / CÔNG VIỆC CHĂM SÓC HÀNG NGÀY:\n"
    "     + Khi người dùng báo cáo công việc chăm sóc đã làm (cho ăn, tưới nước, bón phân, xịt thuốc, tỉa cành...): BẮT BUỘC dùng create_production_log (activity_type='FEEDING' khi cho ăn, 'IRRIGATION' khi tưới nước, 'FERTILIZING' khi bón phân, 'PEST_CONTROL' khi phun thuốc...). Tuyệt đối KHÔNG tạo issue cho các công việc chăm sóc bình thường này.\n"
    "     + Nếu có tiêu hao vật tư (cám, phân bón, thuốc): đồng thời gọi create_inventory_transaction để xuất kho (transaction_type='ISSUE', quantity_change < 0, item_name).\n"
    "   - MUA BÁN VẬT TƯ & THU CHI TÀI CHÍNH:\n"
    "     + Khi mua vật tư: gọi create_inventory_transaction (nhập kho RECEIPT) VÀ create_financial_transaction (chi tiền EXPENSE).\n"
    "   - SỰ CỐ, HỎNG HÓC & SỬA CHỮA ĐỘT XUẤT (ISSUE):\n"
    "     + CHỈ dùng create_issue / manage_issue cho: hỏng hóc, sự cố máy móc, rò rỉ van nước, vỡ ống, sâu bệnh dịch hại, gia cố hàng rào đột xuất.\n"
    "     + Nếu báo cáo đã sửa xong / khắc phục xong sự cố: kiểm tra search_issue / search_running_task trước; nếu không có thì gọi manage_issue hoặc create_issue với status='CLOSED' và resolution_notes.\n"
    "   - BỔ SUNG THÔNG TIN ĐA LƯỢT (MULTI-TURN FOLLOW-UP):\n"
    "     + Khi người dùng gửi thêm audio/tin nhắn bổ sung thông tin cho lượt trước (như số lượng cám, tên vụ mùa, đối tượng cụ thể...):\n"
    "       * Kế thừa toàn bộ ngữ cảnh lượt trước, hoàn thiện các bản ghi còn thiếu (ví dụ: lượt 1 ghi cho ăn nhưng chưa có số lượng -> lượt 2 bổ sung 2kg thì tạo phiếu xuất kho 2kg và hoàn tất nhật ký).\n"
    "       * Không tạo các bản ghi thừa mâu thuẫn hay lặp lại công việc đã ghi.\n"
    "       * Khi thông tin bổ sung đã đầy đủ, mục 'Thông tin cần làm rõ' PHẢI BÁO: 'Không có.'\n"
    "   - TRA CỨU & HỎI ĐÁP: Dùng search_dictionary, search_zone, search_inventory_transaction, search_financial_transaction... và trả lời trực tiếp.\n"
    "\n"
    "3. ĐỊNH DẠNG PHẢN HỒI BẮT BUỘC:\n"
    "Phản hồi gồm 2 phần rõ ràng theo cấu trúc sau:\n"
    "Hệ thống ghi nhận:\n"
    "- [Loại hành động]: Chi tiết ngắn gọn (số lượng, đối tượng, khu vực, trạng thái).\n"
    "\n"
    "Thông tin cần làm rõ:\n"
    "- Chỉ nêu thông tin thực sự trọng yếu còn thiếu (ví dụ: chưa rõ số lượng thức ăn tiêu hao, chưa rõ khu vực xảy ra sự cố).\n"
    "- KHÔNG bắt bẻ về kho lưu trữ (hệ thống tự động liên kết kho mặc định).\n"
    "- Nếu thông tin đã đầy đủ hoặc đã được bổ sung rõ ràng, GHI RÕ: 'Không có.'\n"
)


@dataclass
class HarnessResult:
    """Consolidated outcome of an AI interaction turn."""

    success: bool
    reply_text: str
    raw_transcript: str = ""
    detected_intent: Optional[str] = None
    records_created: List[BaseRecord] = field(default_factory=list)
    events_staged: int = 0
    event_ids: List[int] = field(default_factory=list)
    model_used: str = ""
    total_steps: int = 1
    execution_time_seconds: float = 0.0
    error: Optional[str] = None
    history: List[Any] = field(default_factory=list)


class GenAIHarness:
    """Core Google GenAI harness tailored for resource-constrained edge devices (Raspberry Pi)."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        models: Optional[List[str]] = None,
        system_instruction: str = DEFAULT_SYSTEM_INSTRUCTION,
        temperature: float = 0.1,
        max_retries: int = 4,
        base_delay: float = 2.0,
        max_delay: float = 30.0,
        min_request_interval: float = 1.0,
        tools_list: Optional[List[Dict[str, Any]]] = None,
        client: Optional[genai.Client] = None,
    ) -> None:
        """Initializes the GenAI Harness with resilient retry and rate-limiting policies."""
        self.api_key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        self.models_cascade = list(models) if models else list(DEFAULT_MODELS_CASCADE)
        self.system_instruction = system_instruction
        self.temperature = temperature
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.min_request_interval = min_request_interval
        self._last_request_time: float = 0.0

        # Build tools declarations
        self.raw_tools = tools_list if tools_list is not None else ALL_TOOLS
        self.genai_tools = get_genai_tools(self.raw_tools)

        # Initialize Google GenAI client
        if client is not None:
            self.client = client
        else:
            if not self.api_key:
                logger.warning(
                    "No GEMINI_API_KEY or GOOGLE_API_KEY detected. Calls will fail unless client is injected."
                )
            self.client = genai.Client(api_key=self.api_key) if self.api_key else None

    # --------------------------------------------------------------------------
    # Resilience & Throttling
    # --------------------------------------------------------------------------

    def _pace_request(self) -> None:
        """Throttles outgoing requests to prevent hitting the 15 RPM free tier ceiling."""
        now = time.time()
        elapsed = now - self._last_request_time
        if elapsed < self.min_request_interval:
            time.sleep(self.min_request_interval - elapsed)
        self._last_request_time = time.time()

    def _is_transient_error(self, exc: Exception) -> bool:
        """Determines if an error is eligible for retry (rate limits, 503 overload, timeouts)."""
        msg = str(exc).lower()
        if isinstance(exc, APIError):
            if exc.code in (429, 500, 503, 504):
                return True
        transient_markers = [
            "429",
            "resourceexhausted",
            "quota",
            "rate limit",
            "503",
            "overloaded",
            "unavailable",
            "temporarily unavailable",
            "deadline exceeded",
            "timed out",
            "internal server error",
            "500",
        ]
        return any(m in msg for m in transient_markers)

    def _call_with_resilience(
        self,
        api_fn: Callable[[str], Any],
        operation_name: str = "generate_content",
    ) -> Tuple[Any, str]:
        """Executes a GenAI call with exponential backoff, jitter, and model cascade failover."""
        current_model_idx = 0
        consecutive_model_failures = 0

        for attempt in range(self.max_retries + 1):
            current_model = self.models_cascade[current_model_idx]
            self._pace_request()

            try:
                result = api_fn(current_model)
                return result, current_model
            except Exception as exc:
                is_transient = self._is_transient_error(exc)
                logger.warning(
                    f"[{operation_name}] Attempt {attempt + 1}/{self.max_retries + 1} on model '{current_model}' "
                    f"failed: {exc} (transient={is_transient})"
                )

                if attempt == self.max_retries:
                    raise exc

                consecutive_model_failures += 1
                # If model failed twice consecutively, failover to next model in cascade
                if consecutive_model_failures >= 2 and len(self.models_cascade) > 1:
                    current_model_idx = (current_model_idx + 1) % len(self.models_cascade)
                    consecutive_model_failures = 0
                    new_model = self.models_cascade[current_model_idx]
                    logger.info(f"Failing over to fallback model: '{new_model}'")

                # Exponential backoff with random jitter
                backoff = min(self.max_delay, self.base_delay * (2**attempt))
                jitter = random.uniform(0.1, 1.0)
                sleep_duration = backoff + jitter
                time.sleep(sleep_duration)

        raise RuntimeError("Unreachable retry loop exit.")

    # --------------------------------------------------------------------------
    # Multimodal Input Preparation
    # --------------------------------------------------------------------------

    @staticmethod
    def prepare_audio_part(
        audio: Union[str, Path, bytes],
        mime_type: Optional[str] = None,
    ) -> types.Part:
        """Converts audio file path, raw bytes, or base64 into a lightweight GenAI Part."""
        data_bytes: bytes = b""
        resolved_mime = mime_type or "audio/ogg"

        if isinstance(audio, (str, Path)):
            p = Path(audio)
            if p.exists() and p.is_file():
                data_bytes = p.read_bytes()
                guessed_mime, _ = mimetypes.guess_type(str(p))
                if guessed_mime:
                    resolved_mime = guessed_mime
            else:
                # Might be base64 string
                try:
                    data_bytes = base64.b64decode(str(audio))
                except Exception as exc:
                    raise ValueError(f"Invalid audio file path or base64 data: {exc}") from exc
        elif isinstance(audio, bytes):
            data_bytes = audio
        else:
            raise TypeError(f"Unsupported audio input type: {type(audio)}")

        if not data_bytes:
            raise ValueError("Audio data is empty.")

        return types.Part.from_bytes(data=data_bytes, mime_type=resolved_mime)

    # --------------------------------------------------------------------------
    # Agentic Tool Execution Loop
    # --------------------------------------------------------------------------

    def execute_agentic_loop(
        self,
        contents: List[types.Content],
        max_tool_steps: int = 5,
    ) -> Tuple[str, List[BaseRecord], str, int]:
        """Runs the multi-turn agentic function calling loop until final text is synthesized."""
        if self.client is None:
            raise RuntimeError("GenAI client is not initialized. Please provide a valid API key.")

        config = types.GenerateContentConfig(
            system_instruction=self.system_instruction,
            temperature=self.temperature,
            tools=self.genai_tools,
        )

        records_created: List[BaseRecord] = []
        final_text = ""
        last_model_used = self.models_cascade[0]
        step_count = 0

        for step in range(max_tool_steps):
            step_count += 1

            def _call(model_name: str) -> Any:
                return self.client.models.generate_content(
                    model=model_name,
                    contents=contents,
                    config=config,
                )

            response, last_model_used = self._call_with_resilience(_call, "agentic_loop")

            # Check for candidate and function calls
            if not response.candidates or not response.candidates[0].content:
                break

            candidate = response.candidates[0]
            model_content = candidate.content
            contents.append(model_content)

            # Check if model requested function calls
            function_calls = response.function_calls
            if not function_calls:
                # Final response reached
                final_text = response.text or ""
                break

            # Execute function calls and assemble response parts
            tool_response_parts: List[types.Part] = []
            for call in function_calls:
                fn_name = call.name
                fn_args = dict(call.args or {})
                logger.info(f"Invoking tool '{fn_name}' with args: {fn_args}")

                try:
                    exec_result = execute_function(fn_name, fn_args)
                    if isinstance(exec_result, BaseRecord):
                        records_created.append(exec_result)
                        res_payload = exec_result.to_record()
                    elif hasattr(exec_result, "to_dict"):
                        res_payload = exec_result.to_dict()
                    elif isinstance(exec_result, (dict, list, str, int, float, bool)):
                        res_payload = exec_result
                    else:
                        res_payload = str(exec_result)
                except Exception as exc:
                    logger.error(f"Error executing tool '{fn_name}': {exc}")
                    res_payload = {"error": str(exc)}

                tool_response_parts.append(
                    types.Part.from_function_response(
                        name=fn_name,
                        response={"result": res_payload},
                    )
                )

            # Feed tool responses back as user content
            contents.append(types.Content(role="user", parts=tool_response_parts))

        return final_text, records_created, last_model_used, step_count

    # --------------------------------------------------------------------------
    # High-Level One-Touch Pipelines
    # --------------------------------------------------------------------------

    def process_voice(
        self,
        audio: Union[str, Path, bytes],
        sender_id: str = "WORKER_1",
        audio_path_hint: Optional[str] = None,
        user_prompt: str = "Trích xuất toàn bộ nội dung khẩu lệnh trong âm thanh, thực thi đầy đủ các tool tương ứng (kho hàng, thu chi, sự cố, tác vụ) và phản hồi theo định dạng hệ thống kèm mục thông tin cần làm rõ nếu có.",
        db_path: Optional[Union[str, Path]] = None,
        auto_stage: bool = True,
        conversation_history: Optional[List[Any]] = None,
    ) -> HarnessResult:
        """End-to-end voice processing: converts audio, runs agentic loop, and auto-stages to In-Flight buffer."""
        start_time = time.time()
        try:
            audio_part = self.prepare_audio_part(audio)
            initial_parts = [
                audio_part,
                types.Part.from_text(text=user_prompt),
            ]
            contents = list(conversation_history) if conversation_history else []
            contents.append(types.Content(role="user", parts=initial_parts))

            final_text, records, model_used, steps = self.execute_agentic_loop(contents)

            # Auto-stage records into pending_events if requested
            staged_ids: List[int] = []
            if auto_stage and records:
                target_db = Path(db_path) if db_path else get_db_path()
                stored_path = audio_path_hint or (str(audio) if isinstance(audio, (str, Path)) else None)

                with get_db(target_db) as conn:
                    container = PendingEvents(
                        records=records,
                        raw_transcript=final_text,
                        summary_text=f"AI voice event by {sender_id}",
                    )
                    staged_ids = container.stage_all_events(
                        conn=conn,
                        audio_path=stored_path,
                        sender_id=sender_id,
                    )

            elapsed = time.time() - start_time
            return HarnessResult(
                success=True,
                reply_text=final_text,
                raw_transcript=final_text,
                records_created=records,
                events_staged=len(staged_ids),
                event_ids=staged_ids,
                model_used=model_used,
                total_steps=steps,
                execution_time_seconds=round(elapsed, 3),
                history=contents,
            )
        except Exception as exc:
            elapsed = time.time() - start_time
            logger.error(f"Voice processing failed: {exc}", exc_info=True)
            return HarnessResult(
                success=False,
                reply_text=f"Xin lỗi, hệ thống gặp lỗi khi xử lý giọng nói: {exc}",
                execution_time_seconds=round(elapsed, 3),
                error=str(exc),
            )

    def process_text(
        self,
        text_query: str,
        sender_id: str = "WORKER_1",
        db_path: Optional[Union[str, Path]] = None,
        auto_stage: bool = True,
        conversation_history: Optional[List[Any]] = None,
    ) -> HarnessResult:
        """End-to-end text processing for farmer Q&A and ad-hoc task assignment."""
        start_time = time.time()
        try:
            contents = list(conversation_history) if conversation_history else []
            contents.append(types.Content(role="user", parts=[types.Part.from_text(text=text_query)]))
            final_text, records, model_used, steps = self.execute_agentic_loop(contents)
            staged_ids: List[int] = []
            if auto_stage and records:
                target_db = Path(db_path) if db_path else get_db_path()
                with get_db(target_db) as conn:
                    container = PendingEvents(
                        records=records,
                        raw_transcript=text_query,
                        summary_text=f"Text instruction by {sender_id}",
                    )
                    staged_ids = container.stage_all_events(
                        conn=conn,
                        sender_id=sender_id,
                    )

            elapsed = time.time() - start_time
            return HarnessResult(
                success=True,
                reply_text=final_text,
                raw_transcript=text_query,
                records_created=records,
                events_staged=len(staged_ids),
                event_ids=staged_ids,
                model_used=model_used,
                total_steps=steps,
                execution_time_seconds=round(elapsed, 3),
                history=contents,
            )
        except Exception as exc:
            elapsed = time.time() - start_time
            return HarnessResult(
                success=False,
                reply_text=f"Xin lỗi, hệ thống gặp lỗi: {exc}",
                execution_time_seconds=round(elapsed, 3),
                error=str(exc),
            )


# Global singleton access
_default_harness: Optional[GenAIHarness] = None


def get_ai_harness() -> GenAIHarness:
    """Returns the singleton instance of GenAIHarness."""
    global _default_harness
    if _default_harness is None:
        _default_harness = GenAIHarness()
    return _default_harness
