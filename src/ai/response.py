"""AgriVoice-AI: Structured AI Response Models.

Defines the Pydantic schema for AI responses, including transcribed audio,
summary text, and a list of extracted database records (excluding VoiceRawLog and PendingEvent).
"""

from __future__ import annotations

import sqlite3
from typing import Any, Dict, List, Optional, Tuple, Type, Union
from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.db.models import (
    BaseRecord,
    Collaborator,
    Zone,
    Dictionary,
    Category,
    Unit,
    Supplier,
    Warehouse,
    StorageLocation,
    Product,
    CategoryUnitConversion,
    ProductUnitConversion,
    ProductBatch,
    InventoryTransaction,
    StockCount,
    StockCountLine,
    Project,
    Task,
    Subtask,
    RunningTask,
    Tag,
    TaskTag,
    TaskComment,
    TaskActivity,
    ProductionCycle,
    ProductionLog,
    Harvest,
    YieldRecord,
    ProcessedProduct,
    ProcessingBatch,
    TransactionCategory,
    FinancialTransaction,
    BarterTransaction,
    DebtRecord,
    DebtPayment,
    Issue,
    VoiceRawLog,
    PendingEvent,
)
from src.db.pending_service import stage_voice_event


# ==============================================================================
# EXCLUDED RECORD TYPES (V9 logs cannot be returned directly as pending records)
# ==============================================================================

EXCLUDED_RECORD_CLASSES: Tuple[Type[BaseRecord], ...] = (
    VoiceRawLog,
    PendingEvent,
)

EXCLUDED_TABLE_NAMES = {
    "voice_raw_logs",
    "voice_raw_log",
    "pending_events",
    "pending_event",
    "pendind_events",
    "pendind_event",
}


# ==============================================================================
# SUPPORTED RECORD TYPES (All 29 business domain records across V1-V8)
# ==============================================================================

SUPPORTED_RECORDS: Tuple[Type[BaseRecord], ...] = (
    Collaborator,
    Zone,
    Dictionary,
    Category,
    Unit,
    Supplier,
    Warehouse,
    StorageLocation,
    Product,
    CategoryUnitConversion,
    ProductUnitConversion,
    ProductBatch,
    InventoryTransaction,
    StockCount,
    StockCountLine,
    Project,
    Task,
    Subtask,
    RunningTask,
    Tag,
    TaskTag,
    TaskComment,
    TaskActivity,
    ProductionCycle,
    ProductionLog,
    Harvest,
    YieldRecord,
    ProcessedProduct,
    ProcessingBatch,
    TransactionCategory,
    FinancialTransaction,
    BarterTransaction,
    DebtRecord,
    DebtPayment,
    Issue,
)
# Target table lookup mapping
TABLE_NAME_TO_RECORD_CLASS: Dict[str, Type[BaseRecord]] = {}
for cls in SUPPORTED_RECORDS:
    tbl = getattr(cls, "TABLE_NAME", "")
    if tbl:
        TABLE_NAME_TO_RECORD_CLASS[tbl.lower()] = cls
        if tbl.endswith("s"):
            TABLE_NAME_TO_RECORD_CLASS[tbl[:-1].lower()] = cls
    TABLE_NAME_TO_RECORD_CLASS[cls.__name__.lower()] = cls


# Union of all supported records for Pydantic type annotation & GenAI schema
SupportedRecord = Union[
    Collaborator,
    Zone,
    Dictionary,
    Category,
    Unit,
    Supplier,
    Warehouse,
    StorageLocation,
    Product,
    CategoryUnitConversion,
    ProductUnitConversion,
    ProductBatch,
    InventoryTransaction,
    StockCount,
    StockCountLine,
    Project,
    Task,
    Subtask,
    RunningTask,
    Tag,
    TaskTag,
    TaskComment,
    TaskActivity,
    ProductionCycle,
    ProductionLog,
    Harvest,
    YieldRecord,
    ProcessedProduct,
    ProcessingBatch,
    TransactionCategory,
    FinancialTransaction,
    BarterTransaction,
    DebtRecord,
    DebtPayment,
    Issue,
]

def resolve_record_item(item: Any) -> Any:
    """Validates and coerces input items into concrete BaseRecord instances."""
    if isinstance(item, EXCLUDED_RECORD_CLASSES):
        raise ValueError(
            f"Record of type '{type(item).__name__}' is excluded from AI response records."
        )

    if isinstance(item, BaseRecord):
        return item

    if isinstance(item, dict):
        all_keys = [
            item.get("target_table"),
            item.get("table_name"),
            item.get("table"),
            item.get("record_type"),
        ]
        for val in all_keys:
            if val and str(val).strip().lower() in EXCLUDED_TABLE_NAMES:
                raise ValueError(
                    f"Table '{val}' is excluded from AI response records."
                )

        tbl = next((v for v in all_keys if v), None)
        if tbl:
            clean_tbl = str(tbl).strip().lower()
            target_cls = TABLE_NAME_TO_RECORD_CLASS.get(clean_tbl)
            if target_cls:
                clean_dict = {
                    k: v
                    for k, v in item.items()
                    if k not in ("target_table", "table_name", "table", "record_type")
                }
                return target_cls.from_row(clean_dict)

    return item


# ==============================================================================
# AI RESPONSE SCHEMAS
# ==============================================================================


class PendingEvents(BaseModel):
    """Structured response output from AI voice/text processing."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    records: List[SupportedRecord] = Field(
        default_factory=list,
        description="List of database records extracted by AI (excluding VoiceRawLog, PendingEvent).",
    )
    raw_transcript: str = Field(
        default="",
        description="Raw transcribed text converted from input voice audio.",
    )
    summary_text: Optional[str] = Field(
        default=None,
        description="Concise summary text of the raw transcript.",
    )

    @field_validator("records", mode="before")
    @classmethod
    def validate_and_resolve_records(cls, v: Any) -> Any:
        if not isinstance(v, list):
            raise ValueError("records must be a list of BaseRecord instances or dicts.")
        return [resolve_record_item(item) for item in v]

    def to_dict(self) -> Dict[str, Any]:
        """Serializes the response into a JSON-serializable dictionary."""
        return {
            "raw_transcript": self.raw_transcript,
            "summary_text": self.summary_text,
            "records": [
                r.to_record(exclude_none=False) if hasattr(r, "to_record") else r
                for r in self.records
            ],
        }

    def stage_all_events(
        self,
        conn: sqlite3.Connection,
        audio_path: Optional[str] = None,
        log_id: Optional[int] = None,
        timestamp: Optional[str] = None,
        sender_id: str = "WORKER_1",
    ) -> List[int]:
        """Stages all extracted records into the V9 pending_events table atomically."""
        staged_ids: List[int] = []
        for rec in self.records:
            if not isinstance(rec, BaseRecord):
                continue
            target_table = rec.TABLE_NAME
            payload = rec.to_record(exclude_none=True)
            ev_id = stage_voice_event(
                conn=conn,
                target_table=target_table,
                action_type="INSERT",
                payload=payload,
                raw_transcript=self.raw_transcript,
                summary_text=self.summary_text,
                audio_path=audio_path,
                log_id=log_id,
                timestamp=timestamp,
                sender_id=sender_id,
            )
            staged_ids.append(ev_id)
        return staged_ids
# Alias for intuitive naming
AIResponse = PendingEvents
VoiceAIResponse = PendingEvents
