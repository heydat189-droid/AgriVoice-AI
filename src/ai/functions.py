"""AgriVoice-AI: AI Action Functions.

Provides domain functions invoked by AI function calling or direct execution.
Each function instantiates and returns a concrete BaseRecord instance (excluding
VoiceRawLog and PendingEvent).
"""

from __future__ import annotations

import json
import re
import sqlite3
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union
from uuid import uuid4

from src.db.models import (
    BaseRecord,
    Collaborator,
    CollaboratorRole,
    AllowedSource,
    Zone,
    FarmSector,
    SizeUnit,
    Category,
    Unit,
    Supplier,
    Warehouse,
    StorageLocation,
    Product,
    ProductItemType,
    TrackingMethod,
    ProductStatus,
    ProductBatch,
    BatchStatus,
    InventoryTransaction,
    InventoryTransactionType,
    TransactionStatus,
    StockCount,
    StockCountStatus,
    StockCountLine,
    Project,
    ProjectStatus,
    Task,
    TaskStatus,
    TaskPriority,
    Subtask,
    Tag,
    TaskComment,
    ProductionCycle,
    ProductionCycleStatus,
    ProductionLog,
    ActivityType,
    Harvest,
    HarvestType,
    YieldRecord,
    YieldOutputType,
    ProcessedProduct,
    ProcessedProductStatus,
    ProcessingBatch,
    TransactionCategory,
    TransactionCategoryType,
    FinancialTransaction,
    FinancialTransactionType,
    PaymentMethod,
    FinancialTransactionStatus,
    Issue,
    IssueSeverity,
    IssueStatus,
    VoiceRawLog,
    PendingEvent,
)
from src.ai.response import (
    TABLE_NAME_TO_RECORD_CLASS,
    EXCLUDED_RECORD_CLASSES,
    EXCLUDED_TABLE_NAMES,
)


def _slugify(text: str) -> str:
    """Converts Vietnamese or special text into clean uppercase ASCII slug."""
    nfkd = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^A-Za-z0-9]+", "_", nfkd).strip("_").upper()
    return slug


# ==============================================================================
# V1: COLLABORATORS
# ==============================================================================


def create_collaborator(
    telegram_id: str,
    full_name: str,
    role: Union[CollaboratorRole, str] = CollaboratorRole.WORKER,
    allowed_source: Union[AllowedSource, str] = AllowedSource.PRIVATE,
    is_active: int = 1,
    notes: Optional[str] = None,
) -> Collaborator:
    """Creates a Collaborator record."""
    return Collaborator(
        telegram_id=str(telegram_id),
        full_name=full_name,
        role=role,
        allowed_source=allowed_source,
        is_active=is_active,
        notes=notes,
    )


# ==============================================================================
# V2: ZONES
# ==============================================================================


def create_new_zone(
    zone_name: str,
    sector: Union[FarmSector, str] = FarmSector.MIXED,
    area_size: Optional[float] = None,
    unit_of_size: Union[SizeUnit, str] = SizeUnit.M2,
    address: Optional[str] = None,
    current_stock_summary: Optional[str] = None,
    notes: Optional[str] = None,
    zone_id: Optional[str] = None,
    is_active: int = 1,
) -> Zone:
    """Creates a Zone record."""
    if not zone_id:
        slug = _slugify(zone_name)
        zone_id = f"ZONE_{slug}" if slug else f"ZONE_{uuid4().hex[:8].upper()}"
    return Zone(
        zone_id=zone_id,
        zone_name=zone_name,
        sector=sector,
        area_size=float(area_size) if area_size is not None else None,
        unit_of_size=unit_of_size,
        address=address,
        current_stock_summary=current_stock_summary,
        notes=notes,
        is_active=is_active,
    )


create_zone = create_new_zone  # Alias


# ==============================================================================
# V3: INVENTORY, PRODUCTS & WAREHOUSES
# ==============================================================================


def create_category(
    name: str,
    code: Optional[str] = None,
    description: Optional[str] = None,
    parent_id: Optional[int] = None,
    is_active: int = 1,
) -> Category:
    """Creates a product/material Category record."""
    if not code:
        slug = _slugify(name)
        code = f"CAT_{slug}" if slug else f"CAT_{uuid4().hex[:4].upper()}"
    return Category(
        code=code,
        name=name,
        description=description,
        parent_id=parent_id,
        is_active=is_active,
    )


def create_unit(
    name: str,
    code: Optional[str] = None,
    symbol: Optional[str] = None,
    is_active: int = 1,
) -> Unit:
    """Creates a Unit of measure record."""
    if not code:
        slug = _slugify(name)
        code = f"UNIT_{slug}" if slug else f"UNIT_{uuid4().hex[:4].upper()}"
    return Unit(
        code=code,
        name=name,
        symbol=symbol or name,
        is_active=is_active,
    )


def create_supplier(
    name: str,
    code: Optional[str] = None,
    contact_name: Optional[str] = None,
    email: Optional[str] = None,
    phone: Optional[str] = None,
    address: Optional[str] = None,
    tax_code: Optional[str] = None,
    notes: Optional[str] = None,
    is_active: int = 1,
) -> Supplier:
    """Creates a Supplier record."""
    if not code:
        slug = _slugify(name)
        code = f"SUP_{slug}" if slug else f"SUP_{uuid4().hex[:4].upper()}"
    return Supplier(
        code=code,
        name=name,
        contact_name=contact_name,
        email=email,
        phone=phone,
        address=address,
        tax_code=tax_code,
        notes=notes,
        is_active=is_active,
    )


def create_warehouse(
    name: str,
    code: Optional[str] = None,
    address: Optional[str] = None,
    description: Optional[str] = None,
    is_active: int = 1,
) -> Warehouse:
    """Creates a Warehouse record."""
    if not code:
        slug = _slugify(name)
        code = f"WH_{slug}" if slug else f"WH_{uuid4().hex[:4].upper()}"
    return Warehouse(
        code=code,
        name=name,
        address=address,
        description=description,
        is_active=is_active,
    )


def create_storage_location(
    warehouse_id: int,
    code: Optional[str] = None,
    name: Optional[str] = None,
    description: Optional[str] = None,
    is_active: int = 1,
) -> StorageLocation:
    """Creates a StorageLocation record inside a warehouse."""
    if not code:
        code = f"LOC_{uuid4().hex[:4].upper()}"
    return StorageLocation(
        warehouse_id=warehouse_id,
        code=code,
        name=name,
        description=description,
        is_active=is_active,
    )


def create_product(
    name: str,
    sku: Optional[str] = None,
    base_unit_id: int = 1,
    barcode: Optional[str] = None,
    description: Optional[str] = None,
    category_id: Optional[int] = None,
    supplier_id: Optional[int] = None,
    item_type: Union[ProductItemType, str] = ProductItemType.CONSUMABLE,
    tracking_method: Union[TrackingMethod, str] = TrackingMethod.LOT,
    brand: Optional[str] = None,
    unit_price_vnd: float = 0,
    standard_cost_vnd: float = 0,
    min_stock: float = 0.0,
    reorder_level: float = 0.0,
    max_stock: Optional[float] = None,
    status: Union[ProductStatus, str] = ProductStatus.ACTIVE,
) -> Product:
    """Creates a Product record."""
    if not sku:
        slug = _slugify(name)
        sku = f"SKU_{slug}" if slug else f"SKU_{uuid4().hex[:6].upper()}"
    return Product(
        sku=sku,
        name=name,
        base_unit_id=base_unit_id,
        barcode=barcode,
        description=description,
        category_id=category_id,
        supplier_id=supplier_id,
        item_type=item_type,
        tracking_method=tracking_method,
        brand=brand,
        unit_price_vnd=unit_price_vnd,
        standard_cost_vnd=standard_cost_vnd,
        min_stock=min_stock,
        reorder_level=reorder_level,
        max_stock=max_stock,
        status=status,
    )


def create_product_batch(
    product_id: int,
    warehouse_id: int,
    batch_number: Optional[str] = None,
    supplier_id: Optional[int] = None,
    manufacturing_date: Optional[str] = None,
    date_received: Optional[str] = None,
    expiry_date: Optional[str] = None,
    quantity_remaining: float = 0.0,
    cost_price_vnd: Optional[float] = None,
    location_id: Optional[int] = None,
    status: Union[BatchStatus, str] = BatchStatus.AVAILABLE,
    notes: Optional[str] = None,
) -> ProductBatch:
    """Creates a ProductBatch record."""
    if not batch_number:
        batch_number = f"BATCH_{datetime.now().strftime('%Y%m%d')}_{uuid4().hex[:4].upper()}"
    return ProductBatch(
        product_id=product_id,
        batch_number=batch_number,
        warehouse_id=warehouse_id,
        supplier_id=supplier_id,
        manufacturing_date=manufacturing_date,
        date_received=date_received,
        expiry_date=expiry_date,
        quantity_remaining=quantity_remaining,
        cost_price_vnd=cost_price_vnd,
        location_id=location_id,
        status=status,
        notes=notes,
    )


def create_inventory_transaction(
    product_id: Optional[int] = None,
    warehouse_id: Optional[int] = None,
    transaction_type: Union[InventoryTransactionType, str] = InventoryTransactionType.RECEIPT,
    quantity_change: float = 0.0,
    unit_id: int = 1,
    category_id: Optional[int] = None,
    item_name: str = "",
    unit_price_vnd: int = 0,
    batch_id: Optional[int] = None,
    supplier_id: Optional[int] = None,
    cycle_id: Optional[int] = None,
    location_id: Optional[int] = None,
    unit_cost_vnd: int = 0,
    reference_type: Optional[str] = None,
    reference_number: Optional[str] = None,
    reference_note: Optional[str] = None,
    performed_by: Optional[str] = None,
    status: Union[TransactionStatus, str] = TransactionStatus.POSTED,
    notes: Optional[str] = None,
    timestamp: Optional[str] = None,
) -> InventoryTransaction:
    """Creates an InventoryTransaction record."""
    cid = category_id or product_id or 1
    cost = unit_cost_vnd or unit_price_vnd
    return InventoryTransaction(
        category_id=cid,
        product_id=cid,
        warehouse_id=warehouse_id,
        transaction_type=transaction_type,
        quantity_change=quantity_change,
        unit_id=unit_id,
        item_name=item_name or f"Item #{cid}",
        batch_id=batch_id,
        supplier_id=supplier_id,
        cycle_id=cycle_id,
        location_id=location_id,
        unit_cost_vnd=cost,
        reference_type=reference_type,
        reference_number=reference_number,
        reference_note=reference_note,
        performed_by=performed_by,
        status=status,
        notes=notes,
        timestamp=timestamp or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )


def create_stock_count(
    warehouse_id: int,
    code: Optional[str] = None,
    count_date: Optional[str] = None,
    status: Union[StockCountStatus, str] = StockCountStatus.DRAFT,
    performed_by: Optional[str] = None,
    notes: Optional[str] = None,
) -> StockCount:
    """Creates a StockCount header record."""
    if not code:
        code = f"SC_{datetime.now().strftime('%Y%m%d')}_{uuid4().hex[:4].upper()}"
    return StockCount(
        code=code,
        warehouse_id=warehouse_id,
        count_date=count_date or datetime.now().strftime("%Y-%m-%d"),
        status=status,
        performed_by=performed_by,
        notes=notes,
    )


def create_stock_count_line(
    stock_count_id: int,
    product_id: int,
    system_quantity: float,
    counted_quantity: float,
    batch_id: Optional[int] = None,
    location_id: Optional[int] = None,
    notes: Optional[str] = None,
) -> StockCountLine:
    """Creates a StockCountLine record."""
    return StockCountLine(
        stock_count_id=stock_count_id,
        product_id=product_id,
        system_quantity=system_quantity,
        counted_quantity=counted_quantity,
        batch_id=batch_id,
        location_id=location_id,
        notes=notes,
    )


# ==============================================================================
# V4: PROJECTS & TASKS
# ==============================================================================


def create_project(
    name: str,
    code: Optional[str] = None,
    description: Optional[str] = None,
    status: Union[ProjectStatus, str] = ProjectStatus.PLANNED,
    start_date: Optional[str] = None,
    due_date: Optional[str] = None,
    expected_end_date: Optional[str] = None,
) -> Project:
    """Creates a Project record."""
    if not code:
        slug = _slugify(name)
        code = f"PRJ_{slug}" if slug else f"PRJ_{uuid4().hex[:4].upper()}"
    return Project(
        name=name,
        code=code,
        description=description,
        status=status,
        start_date=start_date,
        due_date=due_date,
        expected_end_date=expected_end_date,
    )


def create_task(
    title: str,
    project_id: Optional[int] = None,
    parent_task_id: Optional[int] = None,
    assigned_to: Optional[int] = None,
    code: Optional[str] = None,
    description: Optional[str] = None,
    status: Union[TaskStatus, str] = TaskStatus.TODO,
    priority: Union[TaskPriority, str] = TaskPriority.MEDIUM,
    start_date: Optional[str] = None,
    due_date: Optional[str] = None,
    estimated_minutes: Optional[int] = None,
    actual_minutes: Optional[int] = None,
    sort_order: int = 0,
) -> Task:
    """Creates a Task record."""
    return Task(
        title=title,
        project_id=project_id,
        parent_task_id=parent_task_id,
        assigned_to=assigned_to,
        code=code,
        description=description,
        status=status,
        priority=priority,
        start_date=start_date,
        due_date=due_date,
        estimated_minutes=estimated_minutes,
        actual_minutes=actual_minutes,
        sort_order=sort_order,
    )


def create_subtask(
    task_id: int,
    title: str,
    description: Optional[str] = None,
    is_completed: int = 0,
    sort_order: int = 0,
) -> Subtask:
    """Creates a Subtask record."""
    return Subtask(
        task_id=task_id,
        title=title,
        description=description,
        is_completed=is_completed,
        sort_order=sort_order,
    )


def create_tag(
    name: str,
    color: Optional[str] = None,
) -> Tag:
    """Creates a Tag record."""
    return Tag(
        name=name,
        color=color,
    )


def create_task_comment(
    task_id: int,
    content: str,
    author_id: Optional[int] = None,
) -> TaskComment:
    """Creates a TaskComment record."""
    return TaskComment(
        task_id=task_id,
        content=content,
        author_id=author_id,
    )


# ==============================================================================
# V5: PRODUCTION CYCLES & HARVESTS
# ==============================================================================


def create_production_cycle(
    zone_id: str,
    name: str,
    subject_name: str = "",
    start_date: Optional[str] = None,
    project_id: Optional[int] = None,
    parent_id: Optional[int] = None,
    code: Optional[str] = None,
    description: Optional[str] = None,
    variety: Optional[str] = None,
    expected_end_date: Optional[str] = None,
    actual_end_date: Optional[str] = None,
    initial_stock: Optional[float] = None,
    initial_stock_unit: Optional[str] = None,
    input_category_id: Optional[int] = None,
    input_quantity: float = 0.0,
    input_unit: Optional[str] = None,
    area_size: Optional[float] = None,
    unit_of_size: str = "m2",
    expected_yield: Optional[float] = None,
    output_category_id: Optional[int] = None,
    output_quantity: Optional[float] = None,
    output_unit: Optional[str] = None,
    status: Union[ProductionCycleStatus, str] = ProductionCycleStatus.ACTIVE,
    notes: Optional[str] = None,
) -> ProductionCycle:
    """Creates a ProductionCycle record."""
    if not code:
        slug = _slugify(name)
        code = f"CYC_{slug}" if slug else f"CYC_{uuid4().hex[:4].upper()}"
    return ProductionCycle(
        zone_id=zone_id,
        name=name,
        subject_name=subject_name,
        start_date=start_date or datetime.now().strftime("%Y-%m-%d"),
        parent_id=parent_id,
        project_id=project_id,
        code=code,
        description=description,
        variety=variety,
        expected_end_date=expected_end_date,
        actual_end_date=actual_end_date,
        initial_stock=initial_stock,
        initial_stock_unit=initial_stock_unit,
        input_category_id=input_category_id,
        input_quantity=input_quantity,
        input_unit=input_unit,
        area_size=area_size,
        unit_of_size=unit_of_size,
        expected_yield=expected_yield,
        output_category_id=output_category_id,
        output_quantity=output_quantity,
        output_unit=output_unit,
        status=status,
        notes=notes,
    )


def create_production_log(
    cycle_id: Optional[Union[int, str]] = None,
    title: str = "",
    zone_id: Optional[str] = None,
    log_date: Optional[str] = None,
    activity_type: Union[ActivityType, str] = ActivityType.OTHER,
    description: Optional[str] = None,
    quantity: Optional[float] = None,
    unit: Optional[str] = None,
    material_name: Optional[str] = None,
    cost_amount: Optional[float] = None,
    duration_minutes: Optional[int] = None,
    notes: Optional[str] = None,
    logged_by: Optional[str] = None,
    **kwargs: Any,
) -> ProductionLog:
    """Creates a ProductionLog daily record with optional cycle_id and zone_id."""
    if isinstance(cycle_id, str) and not title:
        title = cycle_id
        cycle_id = None
    elif isinstance(cycle_id, str) and cycle_id.isdigit():
        cycle_id = int(cycle_id)
    elif not isinstance(cycle_id, int):
        cycle_id = None

    # If zone_id is provided but cycle_id is not, auto-resolve cycle for zone if possible
    if cycle_id is None and zone_id:
        try:
            from src.db.service import DBService
            svc = DBService()
            c_rec = svc.get_record("production_cycles", "zone_id = ? AND status = 'ACTIVE'", (zone_id,), limit=1)
            if not c_rec:
                c_rec = svc.get_record("production_cycles", "zone_id = ?", (zone_id,), limit=1)
            if c_rec:
                cycle_id = c_rec["cycle_id"]
        except Exception:
            pass

    return ProductionLog(
        title=title or "Nhật ký sản xuất",
        cycle_id=cycle_id,
        log_date=log_date or datetime.now().strftime("%Y-%m-%d"),
        activity_type=activity_type,
        description=description,
        quantity=quantity,
        unit=unit,
        material_name=material_name,
        cost_amount=int(cost_amount) if cost_amount is not None else None,
        duration_minutes=duration_minutes,
        notes=notes,
        logged_by=logged_by,
    )


def create_harvest(
    cycle_id: int,
    harvest_date: Optional[str] = None,
    code: Optional[str] = None,
    harvest_type: Union[HarvestType, str] = HarvestType.MAIN,
    total_quantity: Optional[float] = None,
    unit: Optional[str] = None,
    total_value: Optional[float] = None,
    labor_cost: Optional[float] = None,
    other_cost: Optional[float] = None,
    worker_name: Optional[str] = None,
    notes: Optional[str] = None,
) -> Harvest:
    """Creates a Harvest batch record."""
    if not code:
        code = f"HV_{datetime.now().strftime('%Y%m%d')}_{uuid4().hex[:4].upper()}"
    return Harvest(
        cycle_id=cycle_id,
        harvest_date=harvest_date or datetime.now().strftime("%Y-%m-%d"),
        code=code,
        harvest_type=harvest_type,
        total_quantity=total_quantity,
        unit=unit,
        total_value=total_value,
        labor_cost=labor_cost,
        other_cost=other_cost,
        worker_name=worker_name,
        notes=notes,
    )


def create_yield_record(
    harvest_id: int,
    product_name: str,
    output_type: Union[YieldOutputType, str] = YieldOutputType.HARVEST_CROP,
    quantity_total: Optional[float] = None,
    quantity_grade_a: Optional[float] = None,
    quantity_grade_b: Optional[float] = None,
    quantity_defect: Optional[float] = None,
    storage_quantity: Optional[float] = None,
    unit: Optional[str] = None,
    unit_price: Optional[float] = None,
    economic_value: Optional[float] = None,
    actual_revenue: Optional[float] = None,
    notes: Optional[str] = None,
) -> YieldRecord:
    """Creates a YieldRecord for harvested produce."""
    return YieldRecord(
        harvest_id=harvest_id,
        product_name=product_name,
        output_type=output_type,
        quantity_total=quantity_total,
        quantity_grade_a=quantity_grade_a,
        quantity_grade_b=quantity_grade_b,
        quantity_defect=quantity_defect,
        storage_quantity=storage_quantity,
        unit=unit,
        unit_price=unit_price,
        economic_value=economic_value,
        actual_revenue=actual_revenue,
        notes=notes,
    )


# ==============================================================================
# V6: PROCESSED PRODUCTS & PROCESSING BATCHES
# ==============================================================================


def create_processed_product(
    name: str,
    sku: Optional[str] = None,
    barcode: Optional[str] = None,
    category: Optional[str] = None,
    unit: Optional[str] = None,
    unit_weight: Optional[float] = None,
    unit_price: Optional[float] = None,
    quantity_in_stock: float = 0.0,
    status: Union[ProcessedProductStatus, str] = ProcessedProductStatus.ACTIVE,
) -> ProcessedProduct:
    """Creates a ProcessedProduct record."""
    if not sku:
        slug = _slugify(name)
        sku = f"PROC_{slug}" if slug else f"PROC_{uuid4().hex[:6].upper()}"
    return ProcessedProduct(
        sku=sku,
        name=name,
        barcode=barcode,
        category=category,
        unit=unit,
        unit_weight=unit_weight,
        unit_price=unit_price,
        quantity_in_stock=quantity_in_stock,
        status=status,
    )


def create_processing_batch(
    product_id: int,
    batch_code: Optional[str] = None,
    processing_date: Optional[str] = None,
    source_cycle_id: Optional[int] = None,
    raw_material_input_qty: Optional[float] = None,
    raw_material_unit: Optional[str] = None,
    output_quantity: Optional[float] = None,
    defect_quantity: Optional[float] = None,
    processing_cost: Optional[float] = None,
    expiry_date: Optional[str] = None,
    notes: Optional[str] = None,
) -> ProcessingBatch:
    """Creates a ProcessingBatch record."""
    if not batch_code:
        batch_code = f"PB_{datetime.now().strftime('%Y%m%d')}_{uuid4().hex[:4].upper()}"
    return ProcessingBatch(
        batch_code=batch_code,
        product_id=product_id,
        processing_date=processing_date or datetime.now().strftime("%Y-%m-%d"),
        source_cycle_id=source_cycle_id,
        raw_material_input_qty=raw_material_input_qty,
        raw_material_unit=raw_material_unit,
        output_quantity=output_quantity,
        defect_quantity=defect_quantity,
        processing_cost=processing_cost,
        expiry_date=expiry_date,
        notes=notes,
    )


# ==============================================================================
# V7: FINANCIAL TRANSACTIONS
# ==============================================================================


def create_transaction_category(
    name: str,
    type: Union[TransactionCategoryType, str],
    description: Optional[str] = None,
    is_active: int = 1,
) -> TransactionCategory:
    """Creates a TransactionCategory record."""
    return TransactionCategory(
        name=name,
        type=type,
        description=description,
        is_active=is_active,
    )


def create_financial_transaction(
    category_id: int,
    type: Union[FinancialTransactionType, str],
    amount: float,
    transaction_date: Optional[str] = None,
    cycle_id: Optional[int] = None,
    recorded_by: Optional[str] = None,
    partner_name: Optional[str] = None,
    payment_method: Union[PaymentMethod, str] = PaymentMethod.CASH,
    status: Union[FinancialTransactionStatus, str] = FinancialTransactionStatus.COMPLETED,
    notes: Optional[str] = None,
) -> FinancialTransaction:
    """Creates a FinancialTransaction record."""
    return FinancialTransaction(
        category_id=category_id,
        type=type,
        amount=amount,
        transaction_date=transaction_date or datetime.now().strftime("%Y-%m-%d"),
        cycle_id=cycle_id,
        recorded_by=recorded_by,
        partner_name=partner_name,
        payment_method=payment_method,
        status=status,
        notes=notes,
    )


# ==============================================================================
# V8: FARM ISSUES
# ==============================================================================


def create_issue(
    zone_id: Optional[str] = None,
    title: str = "",
    description: Optional[str] = None,
    severity: Union[IssueSeverity, str] = IssueSeverity.MEDIUM,
    status: Union[IssueStatus, str] = IssueStatus.OPEN,
    reported_by: Optional[str] = None,
    reporter_id: Optional[int] = None,
    resolution_notes: Optional[str] = None,
    notes: Optional[str] = None,
    closed_at: Optional[str] = None,
    **kwargs: Any,
) -> Issue:
    if zone_id and not title and not zone_id.startswith("ZONE_"):
        title = zone_id
        zone_id = "ZONE_A"

    zone_id = zone_id or "ZONE_A"
    status_enum = status
    if isinstance(status, str):
        st_upper = status.upper()
        if st_upper in ("CLOSED", "RESOLVED", "RESOLVE", "CLOSE"):
            status_enum = IssueStatus.CLOSED
            closed_at = closed_at or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        elif st_upper in ("IN_PROGRESS", "START"):
            status_enum = IssueStatus.IN_PROGRESS
        else:
            status_enum = IssueStatus.OPEN

    return Issue(
        zone_id=zone_id,
        title=title or "Sự cố / Việc đột xuất",
        description=description or notes or title,
        severity=severity,
        status=status_enum,
        reported_by=reported_by or "Bác giữ vườn",
        reporter_id=reporter_id,
        resolution_notes=resolution_notes,
        notes=notes,
        closed_at=closed_at,
    )


def manage_issue(
    issue_id: Optional[int] = None,
    action: str = "IN_PROGRESS",
    notes: Optional[str] = None,
    resolution_notes: Optional[str] = None,
    reviewer_telegram_id: Optional[str] = None,
    title: Optional[str] = None,
    zone_id: Optional[str] = None,
    keyword: Optional[str] = None,
    db_path: Optional[Union[str, Path]] = None,
    conn: Optional[sqlite3.Connection] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """Updates issue notes/progress or resolves/closes an issue.

    Inspects both tasks and issues:
    - If issue_id is given, applies update directly.
    - If issue_id is not given, searches running_tasks and issues.
    - If neither matches, automatically creates a new issue and updates it immediately.
    """
    from src.db.service import DBService

    service = DBService(db_path=db_path, conn=conn)

    # 1. If issue_id is directly given, try to update it
    if issue_id:
        success, err = service.manage_issue(
            issue_id=issue_id,
            action=action,
            resolution_notes=resolution_notes,
            notes=notes,
            reviewer_telegram_id=reviewer_telegram_id,
        )
        if success:
            return {"success": True, "issue_id": issue_id, "action": action}

    search_term = keyword or title or notes or ""

    # 2. Check running_tasks
    if search_term:
        rts = service.get_formatted_data("running_tasks", conditions={"status": "TODO"}, limit=5)
        for rt in rts:
            rt_title = rt.get("title", "").lower()
            if any(w in rt_title for w in search_term.lower().split() if len(w) > 3):
                service.complete_running_task(
                    running_task_id=rt["running_task_id"],
                    completion_notes=notes or resolution_notes or "Hoàn thành qua báo cáo",
                )
                return {
                    "success": True,
                    "matched_type": "running_task",
                    "running_task_id": rt["running_task_id"],
                    "status": "DONE",
                    "notes": notes,
                }

    # 3. Check existing issues
    iss_list = service.get_formatted_data("issues", conditions={"status": "OPEN"}, limit=5)
    if not iss_list:
        iss_list = service.get_formatted_data("issues", conditions={"status": "IN_PROGRESS"}, limit=5)
    for iss in iss_list:
        iss_title = iss.get("title", "").lower()
        if search_term and any(w in iss_title for w in search_term.lower().split() if len(w) > 3):
            target_id = iss["issue_id"]
            service.manage_issue(
                issue_id=target_id,
                action=action,
                resolution_notes=resolution_notes,
                notes=notes,
                reviewer_telegram_id=reviewer_telegram_id,
            )
            return {"success": True, "issue_id": target_id, "action": action}

    # 4. Neither matches: Auto-create new issue and update it immediately
    action_upper = action.upper()
    is_closed = action_upper in ("CLOSE", "CLOSED", "RESOLVE", "RESOLVED")
    status = "CLOSED" if is_closed else "IN_PROGRESS"
    auto_title = title or keyword or (notes[:50] if notes else "Báo cáo công việc / sự cố thực địa")
    auto_zone = zone_id or "ZONE_A"

    new_iss_id, err = service.insert_row(
        "issues",
        {
            "zone_id": auto_zone,
            "title": auto_title,
            "description": notes or resolution_notes or auto_title,
            "status": status,
            "notes": notes,
            "resolution_notes": resolution_notes,
            "closed_at": service._get_current_timestamp() if is_closed else None,
            "reported_by": reviewer_telegram_id or "Bác giữ vườn",
        },
    )
    if not new_iss_id:
        return {"success": False, "error": err or "Failed to auto-create issue"}
    return {
        "success": True,
        "issue_id": new_iss_id,
        "action": action,
        "auto_created": True,
        "status": status,
    }


def complete_running_task(
    running_task_id: Optional[int] = None,
    task_name: Optional[str] = None,
    material_category_id: Optional[int] = None,
    quantity_used: Optional[float] = None,
    material_unit: Optional[str] = None,
    completion_notes: Optional[str] = None,
    warehouse_id: Optional[int] = None,
    db_path: Optional[Union[str, Path]] = None,
    conn: Optional[sqlite3.Connection] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """Marks a running task as completed and automatically issues materials if specified.

    If running_task_id is not given, searches running_tasks. If none found, delegates to manage_issue
    to search issues or auto-create an issue and close it.
    """

    service = DBService(db_path=db_path, conn=conn)

    if not running_task_id:
        search_kw = task_name or completion_notes or ""
        rts = service.get_formatted_data("running_tasks", conditions={"status": "TODO"}, limit=5)
        for rt in rts:
            if search_kw and any(w in rt.get("title", "").lower() for w in search_kw.lower().split() if len(w) > 3):
                running_task_id = rt["running_task_id"]
                break
        if not running_task_id and rts:
            running_task_id = rts[0]["running_task_id"]

    if running_task_id:
        success, err = service.complete_running_task(
            running_task_id=running_task_id,
            material_category_id=material_category_id,
            quantity_used=quantity_used,
            material_unit=material_unit,
            completion_notes=completion_notes,
            warehouse_id=warehouse_id,
        )
        if not success:
            return {"success": False, "error": err, "running_task_id": running_task_id}
        return {"success": True, "running_task_id": running_task_id, "status": "DONE"}
    else:
        return manage_issue(
            title=task_name or completion_notes or "Công việc thực địa hoàn thành",
            action="CLOSED",
            notes=completion_notes,
            resolution_notes=completion_notes,
            db_path=db_path,
            conn=conn,
        )


def record_barter_exchange(
    partner_name: str,
    give_category_id: int,
    give_quantity: float,
    give_unit: str,
    receive_category_id: int,
    receive_quantity: float,
    receive_unit: str,
    estimated_value_vnd: int = 0,
    cash_difference_vnd: int = 0,
    give_cycle_id: Optional[int] = None,
    receive_cycle_id: Optional[int] = None,
    warehouse_id: Optional[int] = None,
    notes: Optional[str] = None,
    sender_id: Optional[str] = None,
    db_path: Optional[Union[str, Path]] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> Dict[str, Any]:
    """Records an atomic barter exchange."""
    from src.db.service import DBService

    service = DBService(db_path=db_path, conn=conn)
    barter_id, err = service.record_barter_exchange(
        partner_name=partner_name,
        give_category_id=give_category_id,
        give_quantity=give_quantity,
        give_unit=give_unit,
        receive_category_id=receive_category_id,
        receive_quantity=receive_quantity,
        receive_unit=receive_unit,
        estimated_value_vnd=estimated_value_vnd,
        cash_difference_vnd=cash_difference_vnd,
        give_cycle_id=give_cycle_id,
        receive_cycle_id=receive_cycle_id,
        warehouse_id=warehouse_id,
        notes=notes,
        sender_id=sender_id,
    )
    if err or barter_id is None:
        return {"success": False, "error": err}
    return {"success": True, "barter_id": barter_id}


def process_debt_payment(
    debt_id: int,
    amount_paid: int,
    payment_date: Optional[str] = None,
    payment_method: str = "CASH",
    notes: Optional[str] = None,
    sender_id: Optional[str] = None,
    db_path: Optional[Union[str, Path]] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> Dict[str, Any]:
    """Processes an installment payment towards a debt."""
    from src.db.service import DBService

    service = DBService(db_path=db_path, conn=conn)
    payment_id, err = service.process_debt_payment(
        debt_id=debt_id,
        amount_paid=amount_paid,
        payment_date=payment_date,
        payment_method=payment_method,
        notes=notes,
        sender_id=sender_id,
    )
    if err or payment_id is None:
        return {"success": False, "error": err, "debt_id": debt_id}
    return {"success": True, "debt_id": debt_id, "payment_id": payment_id}
# GENERIC & DISPATCH FACTORIES
# ==============================================================================


def create_record(target_table: str, **kwargs: Any) -> BaseRecord:
    """Dynamically instantiates a BaseRecord subclass by its target table name."""
    clean_table = target_table.strip().lower()
    if clean_table in EXCLUDED_TABLE_NAMES:
        raise ValueError(
            f"Table '{target_table}' is excluded from AI creation functions."
        )
    target_cls = TABLE_NAME_TO_RECORD_CLASS.get(clean_table)
    if not target_cls:
        raise ValueError(f"Unknown target table '{target_table}'.")
    return target_cls.from_row(kwargs)


# ==============================================================================
# DATA QUERY & AUDITING FUNCTIONS
# ==============================================================================


def get_data_with_pending_applied(
    table: str,
    conditions: Optional[Union[Dict[str, Any], str]] = None,
    limit: Optional[int] = None,
    order_by: Optional[str] = None,
    as_list: bool = False,
    db_path: Optional[Union[str, Path]] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> Union[Dict[str, Any], List[Dict[str, Any]]]:
    """Retrieves committed table data combined with unapproved pending changes sequentially applied.

    Fetches current committed data and sequentially applies unapproved pending events
    (INSERT, UPDATE, DELETE) in strict chronological order (timestamp ASC, event_id ASC).
    Returns clean, consolidated data ready for AI reasoning, reporting, or analytics.
    """
    from src.db.service import DBService

    # Defensive parsing for AI callers that might pass conditions as JSON string
    parsed_conditions: Optional[Dict[str, Any]] = None
    if isinstance(conditions, str):
        try:
            parsed_conditions = json.loads(conditions)
        except Exception:
            parsed_conditions = None
    elif isinstance(conditions, dict):
        parsed_conditions = conditions

    service = DBService(db_path=db_path, conn=conn)
    return service.get_data_with_pending_applied(
        table=table,
        conditions=parsed_conditions,
        limit=limit,
        order_by=order_by,
        as_list=as_list,
    )


def _search_entity_with_overlay(
    table: str,
    conditions: Optional[Dict[str, Any]] = None,
    keyword: Optional[str] = None,
    limit: Optional[int] = None,
    order_by: Optional[str] = None,
    as_list: bool = False,
    db_path: Optional[Union[str, Path]] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> Union[Dict[str, Any], List[Dict[str, Any]]]:
    """Internal helper to query table with pending overlay and optional in-memory keyword filtering."""
    res = get_data_with_pending_applied(
        table=table,
        conditions=conditions,
        limit=None if keyword else limit,
        order_by=order_by,
        as_list=False,
        db_path=db_path,
        conn=conn,
    )
    if keyword and isinstance(res, dict) and "committed_data" in res:
        kw = str(keyword).strip().lower()
        filtered = [
            r
            for r in res["committed_data"]
            if any(kw in str(v).lower() for v in r.values() if v is not None)
        ]
        if limit is not None and limit > 0:
            filtered = filtered[:limit]
        res["committed_data"] = filtered
        res["data"] = filtered
        res["committed_count"] = len(filtered)

    if as_list and isinstance(res, dict) and "committed_data" in res:
        return res["committed_data"]
    return res


def search_zone(
    zone_id: Optional[str] = None,
    sector: Optional[str] = None,
    keyword: Optional[str] = None,
    limit: Optional[int] = None,
    order_by: Optional[str] = None,
    as_list: bool = False,
    conditions: Optional[Dict[str, Any]] = None,
    db_path: Optional[Union[str, Path]] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> Union[Dict[str, Any], List[Dict[str, Any]]]:
    """Searches zones/farm sectors with pending overlay applied."""
    conds = dict(conditions) if isinstance(conditions, dict) else {}
    if zone_id:
        conds["zone_id"] = zone_id
    if sector:
        conds["sector"] = sector
    return _search_entity_with_overlay("zones", conds or None, keyword, limit, order_by, as_list, db_path, conn)


def search_category(
    category_id: Optional[int] = None,
    name: Optional[str] = None,
    code: Optional[str] = None,
    keyword: Optional[str] = None,
    limit: Optional[int] = None,
    order_by: Optional[str] = None,
    as_list: bool = False,
    conditions: Optional[Dict[str, Any]] = None,
    db_path: Optional[Union[str, Path]] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> Union[Dict[str, Any], List[Dict[str, Any]]]:
    """Searches product/material categories with pending overlay applied."""
    conds = dict(conditions) if isinstance(conditions, dict) else {}
    if category_id is not None:
        conds["category_id"] = category_id
    if name:
        conds["name"] = name
    if code:
        conds["code"] = code
    return _search_entity_with_overlay("categories", conds or None, keyword, limit, order_by, as_list, db_path, conn)
def search_dictionary(
    dict_id: Optional[int] = None,
    code: Optional[str] = None,
    name: Optional[str] = None,
    entry_type: Optional[str] = None,
    keyword: Optional[str] = None,
    limit: Optional[int] = None,
    order_by: Optional[str] = None,
    as_list: bool = False,
    conditions: Optional[Dict[str, Any]] = None,
    db_path: Optional[Union[str, Path]] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> Union[Dict[str, Any], List[Dict[str, Any]]]:
    """Searches unified farm dictionary (categories, warehouses, items) with pending overlay applied."""
    conds = dict(conditions) if isinstance(conditions, dict) else {}
    if dict_id is not None:
        conds["dict_id"] = dict_id
    if code:
        conds["code"] = code
    if name:
        conds["name"] = name
    if entry_type:
        conds["entry_type"] = entry_type
    return _search_entity_with_overlay("dictionary", conds or None, keyword, limit, order_by, as_list, db_path, conn)


def search_unit(
    unit_id: Optional[int] = None,
    code: Optional[str] = None,
    name: Optional[str] = None,
    unit_type: Optional[str] = None,
    keyword: Optional[str] = None,
    limit: Optional[int] = None,
    order_by: Optional[str] = None,
    as_list: bool = False,
    conditions: Optional[Dict[str, Any]] = None,
    db_path: Optional[Union[str, Path]] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> Union[Dict[str, Any], List[Dict[str, Any]]]:
    """Searches units of measurement with pending overlay applied."""
    conds = dict(conditions) if isinstance(conditions, dict) else {}
    if unit_id is not None:
        conds["unit_id"] = unit_id
    if code:
        conds["code"] = code
    if name:
        conds["name"] = name
    if unit_type:
        conds["unit_type"] = unit_type
    return _search_entity_with_overlay("units", conds or None, keyword, limit, order_by, as_list, db_path, conn)


def search_supplier(
    supplier_id: Optional[int] = None,
    name: Optional[str] = None,
    phone: Optional[str] = None,
    keyword: Optional[str] = None,
    limit: Optional[int] = None,
    order_by: Optional[str] = None,
    as_list: bool = False,
    conditions: Optional[Dict[str, Any]] = None,
    db_path: Optional[Union[str, Path]] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> Union[Dict[str, Any], List[Dict[str, Any]]]:
    """Searches suppliers and vendors with pending overlay applied."""
    conds = dict(conditions) if isinstance(conditions, dict) else {}
    if supplier_id is not None:
        conds["supplier_id"] = supplier_id
    if name:
        conds["name"] = name
    if phone:
        conds["phone"] = phone
    return _search_entity_with_overlay("suppliers", conds or None, keyword, limit, order_by, as_list, db_path, conn)


def search_warehouse(
    warehouse_id: Optional[int] = None,
    name: Optional[str] = None,
    code: Optional[str] = None,
    warehouse_type: Optional[str] = None,
    keyword: Optional[str] = None,
    limit: Optional[int] = None,
    order_by: Optional[str] = None,
    as_list: bool = False,
    conditions: Optional[Dict[str, Any]] = None,
    db_path: Optional[Union[str, Path]] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> Union[Dict[str, Any], List[Dict[str, Any]]]:
    """Searches warehouses and storage facilities with pending overlay applied."""
    conds = dict(conditions) if isinstance(conditions, dict) else {}
    if warehouse_id is not None:
        conds["warehouse_id"] = warehouse_id
    if name:
        conds["name"] = name
    if code:
        conds["code"] = code
    if warehouse_type:
        conds["warehouse_type"] = warehouse_type
    return _search_entity_with_overlay("warehouses", conds or None, keyword, limit, order_by, as_list, db_path, conn)


def search_product(
    product_id: Optional[int] = None,
    name: Optional[str] = None,
    sku: Optional[str] = None,
    category_id: Optional[int] = None,
    item_type: Optional[str] = None,
    keyword: Optional[str] = None,
    limit: Optional[int] = None,
    order_by: Optional[str] = None,
    as_list: bool = False,
    conditions: Optional[Dict[str, Any]] = None,
    db_path: Optional[Union[str, Path]] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> Union[Dict[str, Any], List[Dict[str, Any]]]:
    """Searches products, seeds, fertilizers, chemicals with pending overlay applied."""
    conds = dict(conditions) if isinstance(conditions, dict) else {}
    if product_id is not None:
        conds["product_id"] = product_id
    if name:
        conds["name"] = name
    if sku:
        conds["sku"] = sku
    if category_id is not None:
        conds["category_id"] = category_id
    if item_type:
        conds["item_type"] = item_type
    return _search_entity_with_overlay("products", conds or None, keyword, limit, order_by, as_list, db_path, conn)


def search_task(
    task_id: Optional[int] = None,
    title: Optional[str] = None,
    status: Optional[str] = None,
    priority: Optional[str] = None,
    project_id: Optional[int] = None,
    assigned_to: Optional[str] = None,
    keyword: Optional[str] = None,
    limit: Optional[int] = None,
    order_by: Optional[str] = None,
    as_list: bool = False,
    conditions: Optional[Dict[str, Any]] = None,
    db_path: Optional[Union[str, Path]] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> Union[Dict[str, Any], List[Dict[str, Any]]]:
    """Searches farm tasks and work assignments with pending overlay applied."""
    conds = dict(conditions) if isinstance(conditions, dict) else {}
    if task_id is not None:
        conds["task_id"] = task_id
    if title:
        conds["title"] = title
    if status:
        conds["status"] = status
    if priority:
        conds["priority"] = priority
    if project_id is not None:
        conds["project_id"] = project_id
    if assigned_to:
        conds["assigned_to"] = assigned_to
    return _search_entity_with_overlay("tasks", conds or None, keyword, limit, order_by, as_list, db_path, conn)


def search_issue(
    issue_id: Optional[int] = None,
    zone_id: Optional[str] = None,
    title: Optional[str] = None,
    severity: Optional[str] = None,
    status: Optional[str] = None,
    keyword: Optional[str] = None,
    limit: Optional[int] = None,
    order_by: Optional[str] = None,
    as_list: bool = False,
    conditions: Optional[Dict[str, Any]] = None,
    db_path: Optional[Union[str, Path]] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> Union[Dict[str, Any], List[Dict[str, Any]]]:
    """Searches farm issues, pests, damages, and equipment failures with pending overlay applied."""
    conds = dict(conditions) if isinstance(conditions, dict) else {}
    if issue_id is not None:
        conds["issue_id"] = issue_id
    if zone_id:
        conds["zone_id"] = zone_id
    if title:
        conds["title"] = title
    if severity:
        conds["severity"] = severity
    if status:
        conds["status"] = status
    return _search_entity_with_overlay("issues", conds or None, keyword, limit, order_by, as_list, db_path, conn)


def search_production_cycle(
    cycle_id: Optional[int] = None,
    zone_id: Optional[str] = None,
    name: Optional[str] = None,
    subject_name: Optional[str] = None,
    status: Optional[str] = None,
    keyword: Optional[str] = None,
    limit: Optional[int] = None,
    order_by: Optional[str] = None,
    as_list: bool = False,
    conditions: Optional[Dict[str, Any]] = None,
    db_path: Optional[Union[str, Path]] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> Union[Dict[str, Any], List[Dict[str, Any]]]:
    """Searches production cycles and crop seasons with pending overlay applied."""
    conds = dict(conditions) if isinstance(conditions, dict) else {}
    if cycle_id is not None:
        conds["cycle_id"] = cycle_id
    if zone_id:
        conds["zone_id"] = zone_id
    if name:
        conds["name"] = name
    if subject_name:
        conds["subject_name"] = subject_name
    if status:
        conds["status"] = status
    return _search_entity_with_overlay("production_cycles", conds or None, keyword, limit, order_by, as_list, db_path, conn)


def search_production_log(
    log_id: Optional[int] = None,
    cycle_id: Optional[int] = None,
    activity_type: Optional[str] = None,
    log_date: Optional[str] = None,
    keyword: Optional[str] = None,
    limit: Optional[int] = None,
    order_by: Optional[str] = None,
    as_list: bool = False,
    conditions: Optional[Dict[str, Any]] = None,
    db_path: Optional[Union[str, Path]] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> Union[Dict[str, Any], List[Dict[str, Any]]]:
    """Searches daily production logs with pending overlay applied."""
    conds = dict(conditions) if isinstance(conditions, dict) else {}
    if log_id is not None:
        conds["log_id"] = log_id
    if cycle_id is not None:
        conds["cycle_id"] = cycle_id
    if activity_type:
        conds["activity_type"] = activity_type
    if log_date:
        conds["log_date"] = log_date
    return _search_entity_with_overlay("production_logs", conds or None, keyword, limit, order_by, as_list, db_path, conn)


def search_harvest(
    harvest_id: Optional[int] = None,
    cycle_id: Optional[int] = None,
    harvest_date: Optional[str] = None,
    harvest_type: Optional[str] = None,
    keyword: Optional[str] = None,
    limit: Optional[int] = None,
    order_by: Optional[str] = None,
    as_list: bool = False,
    conditions: Optional[Dict[str, Any]] = None,
    db_path: Optional[Union[str, Path]] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> Union[Dict[str, Any], List[Dict[str, Any]]]:
    """Searches harvest records with pending overlay applied."""
    conds = dict(conditions) if isinstance(conditions, dict) else {}
    if harvest_id is not None:
        conds["harvest_id"] = harvest_id
    if cycle_id is not None:
        conds["cycle_id"] = cycle_id
    if harvest_date:
        conds["harvest_date"] = harvest_date
    if harvest_type:
        conds["harvest_type"] = harvest_type
    return _search_entity_with_overlay("harvests", conds or None, keyword, limit, order_by, as_list, db_path, conn)


def search_inventory_transaction(
    transaction_id: Optional[int] = None,
    product_id: Optional[int] = None,
    warehouse_id: Optional[int] = None,
    transaction_type: Optional[str] = None,
    keyword: Optional[str] = None,
    limit: Optional[int] = None,
    order_by: Optional[str] = None,
    as_list: bool = False,
    conditions: Optional[Dict[str, Any]] = None,
    db_path: Optional[Union[str, Path]] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> Union[Dict[str, Any], List[Dict[str, Any]]]:
    """Searches inventory transactions with pending overlay applied."""
    conds = dict(conditions) if isinstance(conditions, dict) else {}
    if transaction_id is not None:
        conds["transaction_id"] = transaction_id
    if product_id is not None:
        conds["product_id"] = product_id
    if warehouse_id is not None:
        conds["warehouse_id"] = warehouse_id
    if transaction_type:
        conds["transaction_type"] = transaction_type
    return _search_entity_with_overlay("inventory_transactions", conds or None, keyword, limit, order_by, as_list, db_path, conn)


def search_financial_transaction(
    transaction_id: Optional[int] = None,
    category_id: Optional[int] = None,
    type: Optional[str] = None,
    cycle_id: Optional[int] = None,
    partner_name: Optional[str] = None,
    keyword: Optional[str] = None,
    limit: Optional[int] = None,
    order_by: Optional[str] = None,
    as_list: bool = False,
    conditions: Optional[Dict[str, Any]] = None,
    db_path: Optional[Union[str, Path]] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> Union[Dict[str, Any], List[Dict[str, Any]]]:
    """Searches financial income/expense transactions with pending overlay applied."""
    conds = dict(conditions) if isinstance(conditions, dict) else {}
    if transaction_id is not None:
        conds["transaction_id"] = transaction_id
    if category_id is not None:
        conds["category_id"] = category_id
    if type:
        conds["type"] = type
    if cycle_id is not None:
        conds["cycle_id"] = cycle_id
    if partner_name:
        conds["partner_name"] = partner_name
    return _search_entity_with_overlay("financial_transactions", conds or None, keyword, limit, order_by, as_list, db_path, conn)


def search_collaborator(
    collaborator_id: Optional[int] = None,
    telegram_id: Optional[str] = None,
    full_name: Optional[str] = None,
    role: Optional[str] = None,
    keyword: Optional[str] = None,
    limit: Optional[int] = None,
    order_by: Optional[str] = None,
    as_list: bool = False,
    conditions: Optional[Dict[str, Any]] = None,
    db_path: Optional[Union[str, Path]] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> Union[Dict[str, Any], List[Dict[str, Any]]]:
    """Searches collaborators and farm workers with pending overlay applied."""
    conds = dict(conditions) if isinstance(conditions, dict) else {}
    if collaborator_id is not None:
        conds["collaborator_id"] = collaborator_id
    if telegram_id:
        conds["telegram_id"] = telegram_id
    if full_name:
        conds["full_name"] = full_name
    if role:
        conds["role"] = role
    return _search_entity_with_overlay("collaborators", conds or None, keyword, limit, order_by, as_list, db_path, conn)


def search_barter_transaction(
    barter_id: Optional[int] = None,
    partner_name: Optional[str] = None,
    status: Optional[str] = None,
    keyword: Optional[str] = None,
    limit: Optional[int] = None,
    order_by: Optional[str] = None,
    as_list: bool = False,
    conditions: Optional[Dict[str, Any]] = None,
    db_path: Optional[Union[str, Path]] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> Union[Dict[str, Any], List[Dict[str, Any]]]:
    """Searches direct barter exchange transactions with pending overlay applied."""
    conds = dict(conditions) if isinstance(conditions, dict) else {}
    if barter_id is not None:
        conds["barter_id"] = barter_id
    if partner_name:
        conds["partner_name"] = partner_name
    if status:
        conds["status"] = status
    return _search_entity_with_overlay("barter_transactions", conds or None, keyword, limit, order_by, as_list, db_path, conn)


def search_debt_record(
    debt_id: Optional[int] = None,
    debt_type: Optional[str] = None,
    partner_name: Optional[str] = None,
    status: Optional[str] = None,
    keyword: Optional[str] = None,
    limit: Optional[int] = None,
    order_by: Optional[str] = None,
    as_list: bool = False,
    conditions: Optional[Dict[str, Any]] = None,
    db_path: Optional[Union[str, Path]] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> Union[Dict[str, Any], List[Dict[str, Any]]]:
    """Searches debt records (payables/receivables) with pending overlay applied."""
    conds = dict(conditions) if isinstance(conditions, dict) else {}
    if debt_id is not None:
        conds["debt_id"] = debt_id
    if debt_type:
        conds["debt_type"] = debt_type
    if partner_name:
        conds["partner_name"] = partner_name
    if status:
        conds["status"] = status
    return _search_entity_with_overlay("debt_records", conds or None, keyword, limit, order_by, as_list, db_path, conn)


def search_running_task(
    running_task_id: Optional[int] = None,
    cycle_id: Optional[int] = None,
    status: Optional[str] = None,
    assigned_to: Optional[int] = None,
    keyword: Optional[str] = None,
    limit: Optional[int] = None,
    order_by: Optional[str] = None,
    as_list: bool = False,
    conditions: Optional[Dict[str, Any]] = None,
    db_path: Optional[Union[str, Path]] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> Union[Dict[str, Any], List[Dict[str, Any]]]:
    """Searches active field running tasks with pending overlay applied."""
    conds = dict(conditions) if isinstance(conditions, dict) else {}
    if running_task_id is not None:
        conds["running_task_id"] = running_task_id
    if cycle_id is not None:
        conds["cycle_id"] = cycle_id
    if status:
        conds["status"] = status
    if assigned_to is not None:
        conds["assigned_to"] = assigned_to
    return _search_entity_with_overlay("running_tasks", conds or None, keyword, limit, order_by, as_list, db_path, conn)


# Registry of available functions for tool calling
AVAILABLE_FUNCTIONS: Dict[str, Callable[..., Any]] = {
    "create_new_zone": create_new_zone,
    "create_zone": create_new_zone,
    "create_task": create_task,
    "create_subtask": create_subtask,
    "create_project": create_project,
    "create_tag": create_tag,
    "create_task_comment": create_task_comment,
    "create_production_cycle": create_production_cycle,
    "create_production_log": create_production_log,
    "create_harvest": create_harvest,
    "create_yield_record": create_yield_record,
    "create_category": create_category,
    "create_unit": create_unit,
    "create_supplier": create_supplier,
    "create_warehouse": create_warehouse,
    "create_storage_location": create_storage_location,
    "create_product": create_product,
    "create_product_batch": create_product_batch,
    "create_inventory_transaction": create_inventory_transaction,
    "create_stock_count": create_stock_count,
    "create_stock_count_line": create_stock_count_line,
    "create_processed_product": create_processed_product,
    "create_processing_batch": create_processing_batch,
    "create_transaction_category": create_transaction_category,
    "create_financial_transaction": create_financial_transaction,
    "create_issue": create_issue,
    "manage_issue": manage_issue,
    "complete_running_task": complete_running_task,
    "record_barter_exchange": record_barter_exchange,
    "process_debt_payment": process_debt_payment,
    "get_data_with_pending_applied": get_data_with_pending_applied,
    # Dedicated domain search functions
    "search_zone": search_zone,
    "search_zones": search_zone,
    "search_category": search_category,
    "search_categories": search_category,
    "search_unit": search_unit,
    "search_units": search_unit,
    "search_supplier": search_supplier,
    "search_suppliers": search_supplier,
    "search_warehouse": search_warehouse,
    "search_warehouses": search_warehouse,
    "search_product": search_product,
    "search_products": search_product,
    "search_task": search_task,
    "search_tasks": search_task,
    "search_issue": search_issue,
    "search_issues": search_issue,
    "search_production_cycle": search_production_cycle,
    "search_production_cycles": search_production_cycle,
    "search_production_log": search_production_log,
    "search_production_logs": search_production_log,
    "search_harvest": search_harvest,
    "search_harvests": search_harvest,
    "search_inventory_transaction": search_inventory_transaction,
    "search_inventory_transactions": search_inventory_transaction,
    "search_financial_transaction": search_financial_transaction,
    "search_financial_transactions": search_financial_transaction,
    "search_collaborator": search_collaborator,
    "search_collaborators": search_collaborator,
    "search_barter_transaction": search_barter_transaction,
    "search_barter_transactions": search_barter_transaction,
    "search_debt_record": search_debt_record,
    "search_debt_records": search_debt_record,
    "search_running_task": search_running_task,
    "search_running_tasks": search_running_task,
    "search_dictionary": search_dictionary,
    "search_dictionaries": search_dictionary,
}


def execute_function(func_name: str, arguments: Dict[str, Any]) -> Any:
    """Executes a registered function by name with parsed arguments."""
    func = AVAILABLE_FUNCTIONS.get(func_name)
    if not func:
        raise ValueError(
            f"Function '{func_name}' is not registered in AVAILABLE_FUNCTIONS."
        )
    return func(**arguments)
