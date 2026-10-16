"""AgriVoice-AI: Database Record Dataclasses, Enums & ORM Mapping.

Provides strongly-typed dataclasses and enums for all database tables in AgriVoice-AI.
Supports:
- String Enums for all CHECK constraints (e.g., CollaboratorRole, TaskStatus, etc.)
- Conversion to database-ready record dictionaries (`to_record()`)
- Dynamic parameterized SQL generation (`build_insert_query()`)
- Direct insertion into SQLite database with auto-primary-key binding (`insert()`)
- Batch insertion (`insert_many()`)
- Deserialization from sqlite3.Row or dictionaries (`from_row()`)
"""

from __future__ import annotations

import sqlite3
from dataclasses import asdict, dataclass, field, fields
from enum import Enum
from typing import Any, ClassVar, Dict, List, Optional, Set, Tuple, Type, TypeVar, Union

T = TypeVar("T", bound="BaseRecord")


# ==============================================================================
# BASE ENUM
# ==============================================================================


class StrEnum(str, Enum):
    """Base string enum for SQLite choices. Inherits from str for seamless query binding."""

    def __str__(self) -> str:
        return str(self.value)


# ==============================================================================
# DOMAIN ENUMS
# ==============================================================================


class CollaboratorRole(StrEnum):
    OWNER = "OWNER"
    ADMIN = "ADMIN"
    WORKER = "WORKER"
    VIEWER = "VIEWER"


class AllowedSource(StrEnum):
    PRIVATE = "PRIVATE"
    GROUP = "GROUP"
    BOTH = "BOTH"


class FarmSector(StrEnum):
    CROP = "CROP"
    LIVESTOCK = "LIVESTOCK"
    AQUACULTURE = "AQUACULTURE"
    MIXED = "MIXED"


class SizeUnit(StrEnum):
    M2 = "m2"
    HA = "ha"
    M3 = "m3"


class ProductItemType(StrEnum):
    TOOL = "TOOL"
    CONSUMABLE = "CONSUMABLE"
    CHEMICAL = "CHEMICAL"
    BIOLOGICAL = "BIOLOGICAL"
    SEED = "SEED"
    IRRIGATION = "IRRIGATION"
    OTHER = "OTHER"


class TrackingMethod(StrEnum):
    NONE = "NONE"
    LOT = "LOT"
    SERIAL = "SERIAL"


class ProductStatus(StrEnum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    DISCONTINUED = "DISCONTINUED"


class BatchStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    QUARANTINE = "QUARANTINE"
    BLOCKED = "BLOCKED"
    EXPIRED = "EXPIRED"
    DEPLETED = "DEPLETED"


class InventoryTransactionType(StrEnum):
    RECEIPT = "RECEIPT"
    ISSUE = "ISSUE"
    RETURN_IN = "RETURN_IN"
    RETURN_OUT = "RETURN_OUT"
    ADJUSTMENT_IN = "ADJUSTMENT_IN"
    ADJUSTMENT_OUT = "ADJUSTMENT_OUT"
    TRANSFER_IN = "TRANSFER_IN"
    TRANSFER_OUT = "TRANSFER_OUT"
    EXPIRED_WRITE_OFF = "EXPIRED_WRITE_OFF"


class TransactionStatus(StrEnum):
    DRAFT = "DRAFT"
    POSTED = "POSTED"
    CANCELLED = "CANCELLED"


class StockCountStatus(StrEnum):
    DRAFT = "DRAFT"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class ProjectStatus(StrEnum):
    PLANNED = "PLANNED"
    ACTIVE = "ACTIVE"
    ON_HOLD = "ON_HOLD"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    ARCHIVED = "ARCHIVED"


class TaskStatus(StrEnum):
    TODO = "TODO"
    IN_PROGRESS = "IN_PROGRESS"
    IN_REVIEW = "IN_REVIEW"
    BLOCKED = "BLOCKED"
    DONE = "DONE"
    CANCELLED = "CANCELLED"


class TaskPriority(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    URGENT = "URGENT"


class ProductionCycleStatus(StrEnum):
    PLANNED = "PLANNED"
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class ActivityType(StrEnum):
    SOWING = "SOWING"
    PLANTING = "PLANTING"
    FERTILIZING = "FERTILIZING"
    PEST_CONTROL = "PEST_CONTROL"
    IRRIGATION = "IRRIGATION"
    FEEDING = "FEEDING"
    VACCINATION = "VACCINATION"
    WATER_QUALITY = "WATER_QUALITY"
    PRUNING = "PRUNING"
    WEEDING = "WEEDING"
    HARVEST_PREP = "HARVEST_PREP"
    OTHER = "OTHER"


class HarvestType(StrEnum):
    MAIN = "MAIN"
    PARTIAL = "PARTIAL"
    FINAL = "FINAL"


class YieldOutputType(StrEnum):
    HARVEST_CROP = "HARVEST_CROP"
    MILK = "MILK"
    EGGS = "EGGS"
    MEAT = "MEAT"
    FISH = "FISH"
    OTHER = "OTHER"


class ProcessedProductStatus(StrEnum):
    ACTIVE = "ACTIVE"
    OUT_OF_STOCK = "OUT_OF_STOCK"
    DISCONTINUED = "DISCONTINUED"


class TransactionCategoryType(StrEnum):
    INCOME = "INCOME"
    EXPENSE = "EXPENSE"


class FinancialTransactionType(StrEnum):
    INCOME = "INCOME"
    EXPENSE = "EXPENSE"


class PaymentMethod(StrEnum):
    CASH = "CASH"
    TRANSFER = "TRANSFER"
    DEBT = "DEBT"
    BARTER = "BARTER"


class WarehouseType(StrEnum):
    STANDARD = "STANDARD"
    SHED = "SHED"
    COLD = "COLD"
    KITCHEN = "KITCHEN"
    OTHER = "OTHER"


class BarterStatus(StrEnum):
    COMPLETED = "COMPLETED"
    PENDING = "PENDING"
    CANCELLED = "CANCELLED"


class DebtType(StrEnum):
    PAYABLE = "PAYABLE"
    RECEIVABLE = "RECEIVABLE"


class DebtStatus(StrEnum):
    UNPAID = "UNPAID"
    PARTIAL = "PARTIAL"
    SETTLED = "SETTLED"
    CANCELLED = "CANCELLED"


class RunningTaskStatus(StrEnum):
    TODO = "TODO"
    IN_PROGRESS = "IN_PROGRESS"
    DONE = "DONE"
    SKIPPED = "SKIPPED"
    CANCELLED = "CANCELLED"

class FinancialTransactionStatus(StrEnum):
    COMPLETED = "COMPLETED"
    PENDING = "PENDING"
    CANCELLED = "CANCELLED"


class IssueSeverity(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class IssueStatus(StrEnum):
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"


class ExecutionStatus(StrEnum):
    SUCCESS = "SUCCESS"
    PARTIAL = "PARTIAL"
    ERROR = "ERROR"
    PENDING_APPROVAL = "PENDING_APPROVAL"


class PendingEventStatus(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    ERROR = "ERROR"

class PendingActionType(StrEnum):
    INSERT = "INSERT"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    UPSERT = "UPSERT"

# ==============================================================================
# BASE RECORD
# ==============================================================================


@dataclass
class BaseRecord:
    """Base class for all database record dataclasses."""

    TABLE_NAME: ClassVar[str] = ""
    PRIMARY_KEY: ClassVar[str] = ""
    READONLY_FIELDS: ClassVar[Set[str]] = set()

    def to_record(
        self,
        exclude_none: bool = True,
        exclude_pk_if_none: bool = True,
    ) -> Dict[str, Any]:
        """Formats the dataclass into a column -> value dictionary for database operations."""
        record: Dict[str, Any] = {}
        for f in fields(self):
            col_name = f.name
            if col_name in self.READONLY_FIELDS:
                continue

            val = getattr(self, col_name)

            if exclude_pk_if_none and col_name == self.PRIMARY_KEY and val is None:
                continue

            if exclude_none and val is None:
                continue

            if isinstance(val, Enum):
                val = val.value

            record[col_name] = val

        return record

    def build_insert_query(
        self,
        or_replace: bool = False,
        or_ignore: bool = False,
        exclude_none: bool = True,
        exclude_pk_if_none: bool = True,
    ) -> Tuple[str, Tuple[Any, ...]]:
        """Constructs parameterized INSERT query and parameter tuple."""
        record = self.to_record(
            exclude_none=exclude_none,
            exclude_pk_if_none=exclude_pk_if_none,
        )
        if not record:
            raise ValueError(f"Cannot build insert query for empty record in {self.TABLE_NAME}")

        columns = list(record.keys())
        placeholders = [":" + col for col in columns]

        prefix = "INSERT"
        if or_replace:
            prefix = "INSERT OR REPLACE"
        elif or_ignore:
            prefix = "INSERT OR IGNORE"

        sql = f"{prefix} INTO {self.TABLE_NAME} ({', '.join(columns)}) VALUES ({', '.join(placeholders)})"
        return sql, tuple(record[c] for c in columns)

    def insert(
        self,
        conn: sqlite3.Connection,
        or_replace: bool = False,
        or_ignore: bool = False,
        exclude_none: bool = True,
        exclude_pk_if_none: bool = True,
    ) -> Any:
        """Inserts record into database connection and updates PK if autoincremented."""
        record = self.to_record(
            exclude_none=exclude_none,
            exclude_pk_if_none=exclude_pk_if_none,
        )
        columns = list(record.keys())
        placeholders = [":" + col for col in columns]

        prefix = "INSERT"
        if or_replace:
            prefix = "INSERT OR REPLACE"
        elif or_ignore:
            prefix = "INSERT OR IGNORE"

        sql = f"{prefix} INTO {self.TABLE_NAME} ({', '.join(columns)}) VALUES ({', '.join(placeholders)})"

        cur = conn.cursor()
        cur.execute(sql, record)

        if self.PRIMARY_KEY:
            pk_val = getattr(self, self.PRIMARY_KEY, None)
            if pk_val is None and cur.lastrowid is not None:
                setattr(self, self.PRIMARY_KEY, cur.lastrowid)
                return cur.lastrowid
            return pk_val
        return cur.lastrowid

    @classmethod
    def insert_many(
        cls: Type[T],
        conn: sqlite3.Connection,
        records: List[T],
        or_replace: bool = False,
        or_ignore: bool = False,
        exclude_none: bool = True,
        exclude_pk_if_none: bool = True,
    ) -> int:
        """Batch-inserts multiple records of the same type."""
        if not records:
            return 0

        dict_records = [
            r.to_record(
                exclude_none=exclude_none,
                exclude_pk_if_none=exclude_pk_if_none,
            )
            for r in records
        ]

        # Collect unique columns across all records maintaining insertion order
        all_columns = []
        seen = set()
        for r_dict in dict_records:
            for k in r_dict.keys():
                if k not in seen:
                    seen.add(k)
                    all_columns.append(k)

        standardized_records = [
            {col: r_dict.get(col, None) for col in all_columns}
            for r_dict in dict_records
        ]

        placeholders = [":" + col for col in all_columns]
        prefix = "INSERT"
        if or_replace:
            prefix = "INSERT OR REPLACE"
        elif or_ignore:
            prefix = "INSERT OR IGNORE"

        sql = f"{prefix} INTO {cls.TABLE_NAME} ({', '.join(all_columns)}) VALUES ({', '.join(placeholders)})"
        cur = conn.cursor()
        cur.executemany(sql, standardized_records)
        return cur.rowcount

    @classmethod
    def from_row(cls: Type[T], row: sqlite3.Row | Dict[str, Any]) -> T:
        """Instantiates dataclass from a sqlite3.Row or dictionary."""
        row_dict = dict(row)
        valid_field_names = {f.name for f in fields(cls)}
        filtered_kwargs = {k: v for k, v in row_dict.items() if k in valid_field_names}
        return cls(**filtered_kwargs)


# ==============================================================================
# V1: COLLABORATORS & WHITELIST
# ==============================================================================


@dataclass
class Collaborator(BaseRecord):
    TABLE_NAME: ClassVar[str] = "collaborators"
    PRIMARY_KEY: ClassVar[str] = "collaborator_id"

    telegram_id: str
    full_name: str
    collaborator_id: Optional[int] = None
    role: Union[CollaboratorRole, str] = CollaboratorRole.WORKER
    allowed_source: Union[AllowedSource, str] = AllowedSource.GROUP
    is_active: int = 1
    notes: Optional[str] = None
    created_id: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


# ==============================================================================
# V2: FARM ZONES & LOCATIONS
# ==============================================================================


@dataclass
class Zone(BaseRecord):
    TABLE_NAME: ClassVar[str] = "zones"
    PRIMARY_KEY: ClassVar[str] = "zone_id"

    zone_id: str
    zone_name: str
    sector: Union[FarmSector, str] = FarmSector.MIXED
    area_size: Optional[float] = None
    unit_of_size: Union[SizeUnit, str] = SizeUnit.M2
    address: Optional[str] = None
    current_stock_summary: Optional[str] = None
    neighboring_zone_ids: Optional[str] = None
    convenient_names: Optional[str] = None
    notes: Optional[str] = None
    is_active: int = 1
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


# ==============================================================================
# V3: INVENTORY & WAREHOUSES
# ==============================================================================


@dataclass
class Dictionary(BaseRecord):
    TABLE_NAME: ClassVar[str] = "dictionary"
    PRIMARY_KEY: ClassVar[str] = "dict_id"

    code: str
    name: str
    dict_id: Optional[int] = None
    category_id: Optional[int] = None
    warehouse_id: Optional[int] = None
    description: Optional[str] = None
    parent_id: Optional[int] = None
    level: int = 0
    root_path: str = "/"
    entry_type: str = "CATEGORY"
    zone_id: Optional[str] = None
    default_unit_id: Optional[int] = None
    requires_expiry_tracking: int = 0
    convenient_names: Optional[str] = None
    is_active: int = 1
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    def __post_init__(self):
        if self.dict_id is not None:
            if self.category_id is None:
                self.category_id = self.dict_id
            if self.warehouse_id is None:
                self.warehouse_id = self.dict_id
        elif self.category_id is not None and self.dict_id is None:
            self.dict_id = self.category_id
        elif self.warehouse_id is not None and self.dict_id is None:
            self.dict_id = self.warehouse_id


@dataclass
class Category(BaseRecord):
    TABLE_NAME: ClassVar[str] = "dictionary"
    PRIMARY_KEY: ClassVar[str] = "category_id"

    code: str
    name: str
    category_id: Optional[int] = None
    description: Optional[str] = None
    parent_id: Optional[int] = None
    level: int = 0
    root_path: str = "/"
    default_unit_id: Optional[int] = None
    requires_expiry_tracking: int = 0
    convenient_names: Optional[str] = None
    is_active: int = 1
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

@dataclass
class Unit(BaseRecord):
    TABLE_NAME: ClassVar[str] = "units"
    PRIMARY_KEY: ClassVar[str] = "unit_id"

    code: str
    name: str
    unit_id: Optional[int] = None
    symbol: Optional[str] = None
    is_active: int = 1


@dataclass
class CategoryUnitConversion(BaseRecord):
    TABLE_NAME: ClassVar[str] = "category_unit_conversions"
    PRIMARY_KEY: ClassVar[str] = "conversion_id"

    category_id: int
    unit_id: int
    factor_to_base: float
    conversion_id: Optional[int] = None
    is_default_input: int = 0
    is_default_output: int = 0


@dataclass
class Supplier(BaseRecord):
    TABLE_NAME: ClassVar[str] = "suppliers"
    PRIMARY_KEY: ClassVar[str] = "supplier_id"

    code: str
    name: str
    supplier_id: Optional[int] = None
    contact_name: Optional[str] = None
    contact_info: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    tax_code: Optional[str] = None
    resources_path: Optional[str] = None
    convenient_names: Optional[str] = None
    reliability_rating: float = 5.0
    notes: Optional[str] = None
    description: Optional[str] = None
    is_active: int = 1
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


@dataclass
class Warehouse(BaseRecord):
    TABLE_NAME: ClassVar[str] = "dictionary"
    PRIMARY_KEY: ClassVar[str] = "warehouse_id"

    code: str
    name: str
    warehouse_id: Optional[int] = None
    zone_id: Optional[str] = None
    warehouse_type: Union[WarehouseType, str] = WarehouseType.STANDARD
    address: Optional[str] = None
    description: Optional[str] = None
    convenient_names: Optional[str] = None
    is_active: int = 1
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
@dataclass
class StorageLocation(BaseRecord):
    TABLE_NAME: ClassVar[str] = "storage_locations"
    PRIMARY_KEY: ClassVar[str] = "location_id"

    warehouse_id: int
    code: str
    location_id: Optional[int] = None
    name: Optional[str] = None
    description: Optional[str] = None
    is_active: int = 1


@dataclass
class Product(BaseRecord):
    TABLE_NAME: ClassVar[str] = "dictionary"
    PRIMARY_KEY: ClassVar[str] = "product_id"

    sku: str
    name: str
    base_unit_id: int
    product_id: Optional[int] = None
    code: Optional[str] = None
    description: Optional[str] = None
    category_id: Optional[int] = None
    supplier_id: Optional[int] = None
    item_type: Union[ProductItemType, str] = ProductItemType.CONSUMABLE
    tracking_method: Union[TrackingMethod, str] = TrackingMethod.LOT
    brand: Optional[str] = None
    specification: Optional[str] = None
    manufacturer: Optional[str] = None
    country_of_origin: Optional[str] = None
    unit_price_vnd: int = 0
    standard_cost_vnd: int = 0
    min_stock: float = 0.0
    reorder_level: float = 0.0
    max_stock: Optional[float] = None
    requires_batch_tracking: int = 1
    requires_expiry_tracking: int = 0
    storage_instructions: Optional[str] = None
    registration_number: Optional[str] = None
    active_ingredient: Optional[str] = None
    formulation: Optional[str] = None
    status: Union[ProductStatus, str] = ProductStatus.ACTIVE
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    def __post_init__(self):
        if not self.code and self.sku:
            self.code = self.sku
        elif not self.sku and self.code:
            self.sku = self.code

@dataclass
class ProductUnitConversion(BaseRecord):
    TABLE_NAME: ClassVar[str] = "product_unit_conversions"
    PRIMARY_KEY: ClassVar[str] = "conversion_id"

    product_id: int
    unit_id: int
    factor_to_base: float
    conversion_id: Optional[int] = None
    is_purchase_unit: int = 0
    is_issue_unit: int = 0


@dataclass
class ProductBatch(BaseRecord):
    TABLE_NAME: ClassVar[str] = "product_batches"
    PRIMARY_KEY: ClassVar[str] = "batch_id"

    batch_code: str = ""
    category_id: int = 1
    warehouse_id: Optional[int] = None
    base_unit_id: int = 1
    quantity_remaining: float = 0.0
    batch_id: Optional[int] = None
    supplier_id: Optional[int] = None
    location_id: Optional[int] = None
    manufacturing_date: Optional[str] = None
    date_received: Optional[str] = None
    expiry_date: Optional[str] = None
    cost_price_vnd: int = 0
    is_virtual: int = 0
    status: Union[BatchStatus, str] = BatchStatus.AVAILABLE
    notes: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    # Backward compatibility
    product_id: Optional[int] = None
    batch_number: Optional[str] = None

    def __post_init__(self):
        if not self.batch_code and self.batch_number:
            self.batch_code = self.batch_number
        elif not self.batch_number and self.batch_code:
            self.batch_number = self.batch_code
        if (not self.category_id or self.category_id == 1) and self.product_id is not None:
            self.category_id = self.product_id
        elif self.product_id is None and self.category_id:
            self.product_id = self.category_id


@dataclass
class InventoryTransaction(BaseRecord):
    TABLE_NAME: ClassVar[str] = "inventory_transactions"
    PRIMARY_KEY: ClassVar[str] = "transaction_id"

    category_id: int = 1
    warehouse_id: Optional[int] = None
    transaction_type: Union[InventoryTransactionType, str] = InventoryTransactionType.RECEIPT
    quantity_change: float = 0.0
    unit_id: int = 1
    item_name: str = ""
    quantity_base: float = 0.0
    transaction_id: Optional[int] = None
    batch_id: Optional[int] = None
    supplier_id: Optional[int] = None
    cycle_id: Optional[int] = None
    financial_transaction_id: Optional[int] = None
    pending_event_id: Optional[int] = None
    location_id: Optional[int] = None
    unit_cost_vnd: int = 0
    unit_price_vnd: int = 0
    is_price_estimated: int = 0
    expiry_date: Optional[str] = None
    reference_type: Optional[str] = None
    reference_number: Optional[str] = None
    reference_note: Optional[str] = None
    performed_by: Optional[str] = None
    status: Union[TransactionStatus, str] = TransactionStatus.DRAFT
    notes: Optional[str] = None
    timestamp: Optional[str] = None
    # Backward compatibility
    product_id: Optional[int] = None

    def __post_init__(self):
        if not self.item_name:
            self.item_name = f"Item #{self.category_id or self.product_id or 0}"
        if (not self.category_id or self.category_id == 1) and self.product_id is not None:
            self.category_id = self.product_id
        elif self.product_id is None and self.category_id:
            self.product_id = self.category_id
        if not self.unit_price_vnd and self.unit_cost_vnd:
            self.unit_price_vnd = self.unit_cost_vnd
        elif not self.unit_cost_vnd and self.unit_price_vnd:
            self.unit_cost_vnd = self.unit_price_vnd
        if self.quantity_base == 0.0:
            self.quantity_base = abs(self.quantity_change)

@dataclass
class StockCount(BaseRecord):
    TABLE_NAME: ClassVar[str] = "stock_counts"
    PRIMARY_KEY: ClassVar[str] = "stock_count_id"

    code: str
    warehouse_id: Optional[int] = None
    stock_count_id: Optional[int] = None
    count_date: Optional[str] = None
    status: Union[StockCountStatus, str] = StockCountStatus.DRAFT
    performed_by: Optional[str] = None
    notes: Optional[str] = None
    created_at: Optional[str] = None


@dataclass
class StockCountLine(BaseRecord):
    TABLE_NAME: ClassVar[str] = "stock_count_lines"
    PRIMARY_KEY: ClassVar[str] = "line_id"
    READONLY_FIELDS: ClassVar[Set[str]] = {"variance"}  # Virtual generated column

    stock_count_id: int
    system_quantity: float
    counted_quantity: float
    category_id: int = 1
    line_id: Optional[int] = None
    batch_id: Optional[int] = None
    location_id: Optional[int] = None
    notes: Optional[str] = None
    variance: Optional[float] = None
    # Backward compatibility
    product_id: Optional[int] = None

    def __post_init__(self):
        if (not self.category_id or self.category_id == 1) and self.product_id is not None:
            self.category_id = self.product_id
        elif self.product_id is None and self.category_id:
            self.product_id = self.category_id

# ==============================================================================
# V4: PROJECTS & TASKS
# ==============================================================================


@dataclass
class Project(BaseRecord):
    TABLE_NAME: ClassVar[str] = "projects"
    PRIMARY_KEY: ClassVar[str] = "project_id"

    name: str
    project_id: Optional[int] = None
    code: Optional[str] = None
    description: Optional[str] = None
    status: Union[ProjectStatus, str] = ProjectStatus.ACTIVE
    start_date: Optional[str] = None
    due_date: Optional[str] = None
    expected_end_date: Optional[str] = None
    actual_end_date: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


@dataclass
class Task(BaseRecord):
    TABLE_NAME: ClassVar[str] = "tasks"
    PRIMARY_KEY: ClassVar[str] = "task_id"

    title: str
    task_id: Optional[int] = None
    project_id: Optional[int] = None
    parent_task_id: Optional[int] = None
    assigned_to: Optional[int] = None
    code: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    status: Union[TaskStatus, str] = TaskStatus.TODO
    priority: Union[TaskPriority, str] = TaskPriority.MEDIUM
    time_delta: str = "1 day"
    delay: str = "0 days"
    last: str = "90 days"
    min_repeats_ratio: Optional[float] = 0.8
    max_repeats_ratio: Optional[float] = 1.2
    start_date: Optional[str] = None
    due_date: Optional[str] = None
    completed_at: Optional[str] = None
    estimated_minutes: Optional[int] = None
    actual_minutes: Optional[int] = None
    sort_order: int = 0
    is_active: int = 1
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    def __post_init__(self):
        if not self.name and self.title:
            self.name = self.title
        elif not self.title and self.name:
            self.title = self.name


@dataclass
class Subtask(BaseRecord):
    TABLE_NAME: ClassVar[str] = "subtasks"
    PRIMARY_KEY: ClassVar[str] = "subtask_id"

    task_id: int
    title: str
    subtask_id: Optional[int] = None
    project_id: Optional[int] = None
    name: Optional[str] = None
    description: Optional[str] = None
    open_at: str = "05:00:00"
    close_at: str = "18:00:00"
    duration_minutes: Optional[int] = 30
    target_ids: str = "[]"
    lock: int = 0
    glock: int = 0
    is_completed: int = 0
    is_active: int = 1
    sort_order: int = 0
    completed_at: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    def __post_init__(self):
        if not self.name and self.title:
            self.name = self.title
        elif not self.title and self.name:
            self.title = self.name

@dataclass
class Tag(BaseRecord):
    TABLE_NAME: ClassVar[str] = "tags"
    PRIMARY_KEY: ClassVar[str] = "tag_id"

    name: str
    tag_id: Optional[int] = None
    color: Optional[str] = None


@dataclass
class TaskTag(BaseRecord):
    TABLE_NAME: ClassVar[str] = "task_tags"
    PRIMARY_KEY: ClassVar[str] = ""  # Composite PK: (task_id, tag_id)

    task_id: int
    tag_id: int


@dataclass
class TaskComment(BaseRecord):
    TABLE_NAME: ClassVar[str] = "task_comments"
    PRIMARY_KEY: ClassVar[str] = "comment_id"

    task_id: int
    content: str
    comment_id: Optional[int] = None
    author_id: Optional[int] = None
    created_at: Optional[str] = None


@dataclass
class TaskActivity(BaseRecord):
    TABLE_NAME: ClassVar[str] = "task_activities"
    PRIMARY_KEY: ClassVar[str] = "activity_id"

    task_id: int
    action: str
    activity_id: Optional[int] = None
    performed_by: Optional[int] = None
    field_name: Optional[str] = None
    old_value: Optional[str] = None
    new_value: Optional[str] = None
    created_at: Optional[str] = None


# ==============================================================================
# V5: PRODUCTION CYCLES & HARVESTS
# ==============================================================================


@dataclass
class ProductionCycle(BaseRecord):
    TABLE_NAME: ClassVar[str] = "production_cycles"
    PRIMARY_KEY: ClassVar[str] = "cycle_id"

    zone_id: str
    name: str
    start_date: str
    subject_name: str = ""
    cycle_id: Optional[int] = None
    parent_id: Optional[int] = None
    project_id: Optional[int] = None
    code: Optional[str] = None
    description: Optional[str] = None
    variety: Optional[str] = None
    expected_end_date: Optional[str] = None
    actual_end_date: Optional[str] = None
    initial_stock: Optional[float] = None
    initial_stock_unit: Optional[str] = None
    input_category_id: Optional[int] = None
    input_quantity: float = 0.0
    input_unit: Optional[str] = None
    area_size: Optional[float] = None
    unit_of_size: str = "m2"
    expected_yield: Optional[float] = None
    output_category_id: Optional[int] = None
    output_quantity: Optional[float] = None
    output_unit: Optional[str] = None
    status: Union[ProductionCycleStatus, str] = ProductionCycleStatus.ACTIVE
    notes: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


@dataclass
class RunningTask(BaseRecord):
    TABLE_NAME: ClassVar[str] = "running_tasks"
    PRIMARY_KEY: ClassVar[str] = "running_task_id"

    name: str
    running_task_id: Optional[int] = None
    cycle_id: Optional[int] = None
    project_id: Optional[int] = None
    task_id: Optional[int] = None
    subtask_id: Optional[int] = None
    assigned_to: Optional[int] = None
    description: Optional[str] = None
    scheduled_start: Optional[str] = None
    duration_minutes: int = 30
    status: Union[RunningTaskStatus, str] = RunningTaskStatus.TODO
    material_category_id: Optional[int] = None
    quantity_used: Optional[float] = None
    material_unit: Optional[str] = None
    inventory_transaction_id: Optional[int] = None
    pending_event_id: Optional[int] = None
    report_complete_at: Optional[str] = None
    completion_notes: Optional[str] = None
    is_active: int = 1
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

@dataclass
class ProductionLog(BaseRecord):
    TABLE_NAME: ClassVar[str] = "production_logs"
    PRIMARY_KEY: ClassVar[str] = "log_id"

    title: str = ""
    cycle_id: Optional[int] = None
    log_date: Optional[str] = None
    log_id: Optional[int] = None
    logged_by: Optional[int] = None
    activity_type: Union[ActivityType, str] = ActivityType.OTHER
    description: Optional[str] = None
    quantity: Optional[float] = None
    unit: Optional[str] = None
    material_name: Optional[str] = None
    cost_amount: Optional[int] = None
    duration_minutes: Optional[int] = None
    notes: Optional[str] = None
    created_at: Optional[str] = None

    def __post_init__(self):
        if not self.title:
            self.title = "Nhật ký sản xuất"
        if not self.log_date:
            self.log_date = datetime.now().strftime("%Y-%m-%d")

    def insert(
        self,
        conn: sqlite3.Connection,
        or_replace: bool = False,
        or_ignore: bool = False,
        exclude_none: bool = True,
        exclude_pk_if_none: bool = True,
    ) -> Any:
        if self.cycle_id is None or self.cycle_id == 0:
            cur = conn.cursor()
            cur.execute("SELECT cycle_id FROM production_cycles WHERE status = 'ACTIVE' LIMIT 1;")
            row = cur.fetchone()
            if not row:
                cur.execute("SELECT cycle_id FROM production_cycles LIMIT 1;")
                row = cur.fetchone()
            if row:
                self.cycle_id = row[0]
            else:
                cur.execute("SELECT zone_id FROM zones LIMIT 1;")
                z_row = cur.fetchone()
                if z_row:
                    z_id = z_row[0]
                else:
                    cur.execute("INSERT OR IGNORE INTO zones (zone_id, zone_name) VALUES ('ZONE_A', 'Khu Mặc Định');")
                    z_id = "ZONE_A"
                cur.execute(
                    "INSERT INTO production_cycles (zone_id, name, subject_name, start_date, status) "
                    "VALUES (?, 'Vụ Canh Tác Mặc Định', 'Chung', date('now'), 'ACTIVE');",
                    (z_id,),
                )
                self.cycle_id = cur.lastrowid
        return super().insert(
            conn,
            or_replace=or_replace,
            or_ignore=or_ignore,
            exclude_none=exclude_none,
            exclude_pk_if_none=exclude_pk_if_none,
        )

@dataclass
class Harvest(BaseRecord):
    TABLE_NAME: ClassVar[str] = "harvests"
    PRIMARY_KEY: ClassVar[str] = "harvest_id"

    cycle_id: int
    harvest_date: str
    harvest_id: Optional[int] = None
    code: Optional[str] = None
    harvest_type: Union[HarvestType, str] = HarvestType.MAIN
    total_quantity: float = 0.0
    unit: str = "kg"
    total_value: Optional[int] = None
    labor_cost: int = 0
    other_cost: int = 0
    worker_name: Optional[str] = None
    notes: Optional[str] = None
    created_at: Optional[str] = None


@dataclass
class YieldRecord(BaseRecord):
    TABLE_NAME: ClassVar[str] = "yield_records"
    PRIMARY_KEY: ClassVar[str] = "record_id"

    harvest_id: int
    product_name: str
    record_id: Optional[int] = None
    output_type: Union[YieldOutputType, str] = YieldOutputType.HARVEST_CROP
    quantity_total: float = 0.0
    quantity_grade_a: float = 0.0
    quantity_grade_b: float = 0.0
    quantity_defect: float = 0.0
    storage_quantity: float = 0.0
    unit: str = "kg"
    unit_price: Optional[int] = None
    economic_value: Optional[int] = None
    actual_revenue: Optional[int] = None
    notes: Optional[str] = None
    created_at: Optional[str] = None


# ==============================================================================
# V6: PROCESSED PRODUCTS & BATCHES
# ==============================================================================


@dataclass
class ProcessedProduct(BaseRecord):
    TABLE_NAME: ClassVar[str] = "processed_products"
    PRIMARY_KEY: ClassVar[str] = "product_id"

    sku: str
    name: str
    product_id: Optional[int] = None
    barcode: Optional[str] = None
    category: Optional[str] = None
    unit: str = "gói"
    unit_weight: Optional[float] = None
    unit_price: Optional[int] = None
    quantity_in_stock: float = 0.0
    status: Union[ProcessedProductStatus, str] = ProcessedProductStatus.ACTIVE
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


@dataclass
class ProcessingBatch(BaseRecord):
    TABLE_NAME: ClassVar[str] = "processing_batches"
    PRIMARY_KEY: ClassVar[str] = "batch_id"

    batch_code: str
    product_id: int
    processing_date: str
    batch_id: Optional[int] = None
    source_cycle_id: Optional[int] = None
    raw_material_input_qty: float = 0.0
    raw_material_unit: str = "kg"
    output_quantity: float = 0.0
    defect_quantity: float = 0.0
    processing_cost: int = 0
    expiry_date: Optional[str] = None
    notes: Optional[str] = None
    created_at: Optional[str] = None


# ==============================================================================
# V7: FINANCIAL TRANSACTIONS
# ==============================================================================


@dataclass
class TransactionCategory(BaseRecord):
    TABLE_NAME: ClassVar[str] = "transaction_categories"
    PRIMARY_KEY: ClassVar[str] = "category_id"

    name: str
    type: Union[TransactionCategoryType, str]
    category_id: Optional[int] = None
    code: Optional[str] = None
    parent_id: Optional[int] = None
    is_cycle_mandatory: int = 0
    convenient_names: Optional[str] = None
    description: Optional[str] = None
    is_active: int = 1
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


@dataclass
class FinancialTransaction(BaseRecord):
    TABLE_NAME: ClassVar[str] = "financial_transactions"
    PRIMARY_KEY: ClassVar[str] = "transaction_id"

    category_id: int
    type: Union[FinancialTransactionType, str]
    amount: int  # >= 0
    transaction_date: str
    transaction_id: Optional[int] = None
    cycle_id: Optional[int] = None
    supplier_id: Optional[int] = None
    recorded_by: Optional[int] = None
    partner_name: Optional[str] = None
    payment_method: Union[PaymentMethod, str] = PaymentMethod.CASH
    status: Union[FinancialTransactionStatus, str] = FinancialTransactionStatus.COMPLETED
    barter_id: Optional[int] = None
    invoice_image_path: Optional[str] = None
    inventory_transaction_id: Optional[int] = None
    pending_event_id: Optional[int] = None
    is_estimated: int = 0
    notes: Optional[str] = None
    created_at: Optional[str] = None


@dataclass
class BarterTransaction(BaseRecord):
    TABLE_NAME: ClassVar[str] = "barter_transactions"
    PRIMARY_KEY: ClassVar[str] = "barter_id"

    partner_name: str
    give_category_id: int
    give_quantity: float
    give_unit: str
    receive_category_id: int
    receive_quantity: float
    receive_unit: str
    barter_id: Optional[int] = None
    give_cycle_id: Optional[int] = None
    give_inventory_tx_id: Optional[int] = None
    receive_cycle_id: Optional[int] = None
    receive_inventory_tx_id: Optional[int] = None
    estimated_value_vnd: int = 0
    cash_difference_vnd: int = 0
    payment_transaction_id: Optional[int] = None
    status: Union[BarterStatus, str] = BarterStatus.COMPLETED
    notes: Optional[str] = None
    pending_event_id: Optional[int] = None
    created_at: Optional[str] = None


@dataclass
class DebtRecord(BaseRecord):
    TABLE_NAME: ClassVar[str] = "debt_records"
    PRIMARY_KEY: ClassVar[str] = "debt_id"
    READONLY_FIELDS: ClassVar[Set[str]] = {"remaining_amount"}

    debt_type: Union[DebtType, str]
    partner_name: str
    initial_amount: int
    debt_id: Optional[int] = None
    initial_transaction_id: Optional[int] = None
    supplier_id: Optional[int] = None
    collaborator_id: Optional[int] = None
    paid_amount: int = 0
    remaining_amount: Optional[int] = None
    due_date: Optional[str] = None
    status: Union[DebtStatus, str] = DebtStatus.UNPAID
    notes: Optional[str] = None
    pending_event_id: Optional[int] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


@dataclass
class DebtPayment(BaseRecord):
    TABLE_NAME: ClassVar[str] = "debt_payments"
    PRIMARY_KEY: ClassVar[str] = "payment_id"

    debt_id: int
    payment_transaction_id: int
    amount_paid: int
    payment_date: str
    payment_id: Optional[int] = None
    notes: Optional[str] = None
    created_at: Optional[str] = None


@dataclass
class Issue(BaseRecord):
    TABLE_NAME: ClassVar[str] = "issues"
    PRIMARY_KEY: ClassVar[str] = "issue_id"

    title: str = ""
    zone_id: str = "ZONE_A"
    issue_id: Optional[int] = None
    reporter_id: Optional[int] = None
    cycle_id: Optional[int] = None
    project_id: Optional[int] = None
    task_id: Optional[int] = None
    description: Optional[str] = None
    severity: Union[IssueSeverity, str] = IssueSeverity.MEDIUM
    status: Union[IssueStatus, str] = IssueStatus.OPEN
    reported_by: Optional[str] = "Bác giữ vườn"
    resolution_notes: Optional[str] = None
    notes: Optional[str] = None
    pending_event_id: Optional[int] = None
    closed_at: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    def __post_init__(self):
        if not self.zone_id:
            self.zone_id = "ZONE_A"
        if not self.title:
            self.title = "Sự cố / Việc phát sinh"
        if isinstance(self.status, str) and self.status.upper() in ("CLOSED", "RESOLVED") and not self.closed_at:
            self.closed_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
# ==============================================================================
# V9: VOICE ASSISTANT LOGS
# ==============================================================================


@dataclass
class VoiceRawLog(BaseRecord):
    TABLE_NAME: ClassVar[str] = "voice_raw_logs"
    PRIMARY_KEY: ClassVar[str] = "log_id"

    sender_id: str
    audio_file_path: str
    log_id: Optional[int] = None
    timestamp: Optional[str] = None
    raw_transcript: str = ""
    detected_intent: Optional[str] = None
    ai_response_json: Optional[str] = None
    execution_status: Union[ExecutionStatus, str] = ExecutionStatus.SUCCESS
    error_message: Optional[str] = None


@dataclass
class PendingEvent(BaseRecord):
    TABLE_NAME: ClassVar[str] = "pending_events"
    PRIMARY_KEY: ClassVar[str] = "event_id"

    target_table: str
    action_type: Union[PendingActionType, str]
    payload_json: str
    event_id: Optional[int] = None
    log_id: Optional[int] = None
    sender_id: Optional[str] = None
    timestamp: Optional[str] = None
    audio_path: Optional[str] = None
    raw_transcript: str = ""
    summary_text: Optional[str] = None
    status: Union[PendingEventStatus, str] = PendingEventStatus.PENDING
    error_message: Optional[str] = None
    reviewed_by: Optional[int] = None
    reviewed_at: Optional[str] = None
    review_notes: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
