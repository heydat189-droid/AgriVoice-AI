"""AgriVoice-AI: Database Package.

Exports database connection management, migration runner interfaces, dataclass models, and domain enums.
"""

from typing import Any

# Re-export models list
_MODEL_NAMES = {
    # Base
    "BaseRecord",
    "StrEnum",
    # Enums
    "CollaboratorRole",
    "AllowedSource",
    "FarmSector",
    "SizeUnit",
    "ProductItemType",
    "TrackingMethod",
    "ProductStatus",
    "BatchStatus",
    "InventoryTransactionType",
    "TransactionStatus",
    "StockCountStatus",
    "ProjectStatus",
    "TaskStatus",
    "TaskPriority",
    "ProductionCycleStatus",
    "ActivityType",
    "HarvestType",
    "YieldOutputType",
    "ProcessedProductStatus",
    "TransactionCategoryType",
    "FinancialTransactionType",
    "PaymentMethod",
    "FinancialTransactionStatus",
    "IssueSeverity",
    "IssueStatus",
    "ExecutionStatus",
    "PendingEventStatus",
    "PendingActionType",
    "WarehouseType",
    "BarterStatus",
    "DebtType",
    "DebtStatus",
    "RunningTaskStatus",
    "Collaborator",
    "Zone",
    "Dictionary",
    "Category",
    "Supplier",
    "Warehouse",
    "StorageLocation",
    "Product",
    "CategoryUnitConversion",
    "ProductUnitConversion",
    "InventoryTransaction",
    "StockCount",
    "StockCountLine",
    "Project",
    "Task",
    "Subtask",
    "Tag",
    "TaskTag",
    "TaskComment",
    "TaskActivity",
    "RunningTask",
    "ProductionCycle",
    "Harvest",
    "YieldRecord",
    "ProcessedProduct",
    "ProcessingBatch",
    "TransactionCategory",
    "FinancialTransaction",
    "BarterTransaction",
    "DebtRecord",
    "DebtPayment",
    "Issue",
    "VoiceRawLog",
    "PendingEvent",
}
__all__ = [
    "create_connection",
    "get_db",
    "get_cursor",
    "get_db_path",
    "initialize_database",
    "run_migrations",
    "get_migration_status",
    "verify_checksums",
    "reset_database",
    "DBService",
    "get_pending_queue",
    "get_earliest_pending_event",
    "approve_pending_event",
    "reject_pending_event",
    "get_table_with_virtual_overlay",
    "get_table_with_pending_applied",
    "StrictOrderingViolationError",
    "TargetTableExecutionError",
    "get_error_events",
    "update_pending_event_payload",
    "build_running_tasks_for_cycle",
    "create_adhoc_task",
    "complete_running_task",
    "check_resource_locks",
    "manage_issue",
    "record_barter_exchange",
    "process_debt_payment",
    *_MODEL_NAMES,
]


def __getattr__(name: str) -> Any:
    if name in _MODEL_NAMES:
        from src.db import models

        return getattr(models, name)
    if name in (
        "run_migrations",
        "get_migration_status",
        "verify_checksums",
        "reset_database",
    ):
        from src.db import migrate

        return getattr(migrate, name)
    if name == "DBService":
        from src.db.service import DBService

        return DBService
    if name in (
        "create_connection",
        "get_db",
        "get_cursor",
        "get_db_path",
        "initialize_database",
    ):
        from src.db import connection

        return getattr(connection, name)
    if name in (
        "stage_voice_event",
        "get_pending_queue",
        "get_earliest_pending_event",
        "approve_pending_event",
        "reject_pending_event",
        "get_table_with_virtual_overlay",
        "get_table_with_pending_applied",
        "StrictOrderingViolationError",
        "TargetTableExecutionError",
        "get_error_events",
        "update_pending_event_payload",
        "build_running_tasks_for_cycle",
        "create_adhoc_task",
        "complete_running_task",
        "check_resource_locks",
        "manage_issue",
        "record_barter_exchange",
        "process_debt_payment",
    ):
        from src.db import pending_service
        return getattr(pending_service, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
