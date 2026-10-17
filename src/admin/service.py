"""AgriVoice-AI: Central Admin Service & Operations Facade.

Integrates all administrative capabilities for Farm Owners and Managers
as specified in 'notes/System methods.md':
1. Staging Queue Review, Strict Ordering & Approvals
2. Farm Operations, SOP Scheduling & Issue Closure
3. Inventory Governance, Negative Stock Tolerance & Adjustments
4. Financial Ledger, Dual-Leg Barter & Debt Settlement
5. Tier 3 Reconciliation Views & Executive Dashboard Analytics
6. Personnel Management & Role-Based Access Control
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from src.admin.collaborators import AdminPermissionError, CollaboratorManager
from src.admin.finance import FinancialGovernanceManager
from src.admin.inventory import InventoryGovernanceManager
from src.admin.operations import OperationsManager
from src.admin.queue import QueueReviewManager
from src.admin.reports import ReportAnalyticsManager
from src.db.connection import get_db_path
from src.db.models import (
    CollaboratorRole,
    FinancialTransactionType,
    IssueSeverity,
    PaymentMethod,
    ProductionCycleStatus,
)
from src.db.service import DBService


class AdminService:
    """Unified service providing all administrative capabilities for farm owners and managers."""

    def __init__(
        self,
        db_path: Optional[Union[Path, str]] = None,
        conn: Optional[sqlite3.Connection] = None,
        admin_telegram_id: str = "OWNER_1",
    ):
        self.db_path = Path(db_path) if db_path else get_db_path()
        self.service = DBService(db_path=self.db_path, conn=conn)
        self.admin_telegram_id = admin_telegram_id

        # Domain Managers
        self.collaborators = CollaboratorManager(self.service, admin_telegram_id=self.admin_telegram_id)
        self.queue = QueueReviewManager(self.service, admin_telegram_id=self.admin_telegram_id)
        self.operations = OperationsManager(self.service, admin_telegram_id=self.admin_telegram_id)
        self.inventory = InventoryGovernanceManager(self.service, admin_telegram_id=self.admin_telegram_id)
        self.finance = FinancialGovernanceManager(self.service, admin_telegram_id=self.admin_telegram_id)
        self.reports = ReportAnalyticsManager(self.service, admin_telegram_id=self.admin_telegram_id)

    def __enter__(self) -> AdminService:
        self.service.__enter__()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.service.__exit__(exc_type, exc_val, exc_tb)

    # ==========================================================================
    # 1. Staging Queue & Approvals (Section 3.1)
    # ==========================================================================

    def get_pending_queue(
        self,
        target_table: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Returns all events currently awaiting approval ordered by timestamp ASC."""
        return self.queue.get_pending_queue(target_table=target_table, limit=limit)

    def get_error_events(
        self,
        target_table: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Returns all events in ERROR status for diagnostic inspection."""
        return self.queue.get_error_events(target_table=target_table, limit=limit)

    def get_event_detail(self, event_id: int) -> Optional[Dict[str, Any]]:
        """Retrieves full details of a pending event including audio_path and parsed payload."""
        return self.queue.get_event_detail(event_id=event_id)

    def edit_event_payload(
        self,
        event_id: int,
        payload: Union[Dict[str, Any], str],
        reset_status_to_pending: bool = True,
        admin_telegram_id: Optional[str] = None,
    ) -> Tuple[bool, Optional[str]]:
        """Modifies payload_json of a pending or error event before approving."""
        return self.queue.edit_event_payload(
            event_id=event_id,
            payload=payload,
            reset_status_to_pending=reset_status_to_pending,
            admin_telegram_id=admin_telegram_id or self.admin_telegram_id,
        )

    def approve_event(
        self,
        event_id: int,
        review_notes: Optional[str] = None,
        admin_telegram_id: Optional[str] = None,
    ) -> Tuple[bool, Optional[str]]:
        """Formally approves a pending event with strict chronological ordering enforcement."""
        return self.queue.approve_event(
            event_id=event_id,
            review_notes=review_notes,
            admin_telegram_id=admin_telegram_id or self.admin_telegram_id,
        )

    def approve_all_pending(
        self,
        target_table: Optional[str] = None,
        admin_telegram_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Approves all pending events in strictly sequential chronological order."""
        return self.queue.approve_all_pending(
            target_table=target_table,
            admin_telegram_id=admin_telegram_id or self.admin_telegram_id,
        )

    def reject_event(
        self,
        event_id: int,
        review_notes: str,
        admin_telegram_id: Optional[str] = None,
    ) -> Tuple[bool, Optional[str]]:
        """Rejects a pending event without deleting it, preserving the audit trail."""
        return self.queue.reject_event(
            event_id=event_id,
            review_notes=review_notes,
            admin_telegram_id=admin_telegram_id or self.admin_telegram_id,
        )

    def retry_error_event(
        self,
        event_id: int,
        updated_payload: Optional[Union[Dict[str, Any], str]] = None,
        admin_telegram_id: Optional[str] = None,
    ) -> Tuple[bool, Optional[str]]:
        """Fixes and re-approves an ERROR event."""
        return self.queue.retry_error_event(
            event_id=event_id,
            updated_payload=updated_payload,
            admin_telegram_id=admin_telegram_id or self.admin_telegram_id,
        )

    # ==========================================================================
    # 2. Operations & SOP Management (Section 3.2)
    # ==========================================================================

    def create_production_cycle(
        self,
        zone_id: str,
        name: str,
        subject_name: str,
        start_date: Optional[str] = None,
        project_id: Optional[int] = None,
        area_size: Optional[float] = None,
        unit_of_size: str = "m2",
        expected_yield: Optional[float] = None,
        status: Union[ProductionCycleStatus, str] = ProductionCycleStatus.ACTIVE,
        auto_build_tasks: bool = True,
        creator_telegram_id: Optional[str] = None,
    ) -> Tuple[Optional[int], Optional[str]]:
        """Creates a production cycle and optionally generates running tasks from SOP."""
        return self.operations.create_production_cycle(
            zone_id=zone_id,
            name=name,
            subject_name=subject_name,
            start_date=start_date,
            project_id=project_id,
            area_size=area_size,
            unit_of_size=unit_of_size,
            expected_yield=expected_yield,
            status=status,
            auto_build_tasks=auto_build_tasks,
            creator_telegram_id=creator_telegram_id or self.admin_telegram_id,
        )

    def build_running_tasks(
        self,
        cycle_id: int,
        clear_existing: bool = False,
        admin_telegram_id: Optional[str] = None,
    ) -> Tuple[int, Optional[str]]:
        """Builds running tasks for a cycle from its project SOP template."""
        return self.operations.build_running_tasks_for_cycle(
            cycle_id=cycle_id,
            clear_existing=clear_existing,
            admin_telegram_id=admin_telegram_id or self.admin_telegram_id,
        )

    def create_adhoc_task(
        self,
        name: str,
        cycle_id: Optional[int] = None,
        assigned_to: Optional[int] = None,
        scheduled_start: Optional[str] = None,
        duration_minutes: int = 60,
        notes: Optional[str] = None,
        creator_telegram_id: Optional[str] = None,
    ) -> Tuple[Optional[int], Optional[str]]:
        """Directly assigns an urgent, ad-hoc field task."""
        return self.operations.create_adhoc_task(
            name=name,
            cycle_id=cycle_id,
            assigned_to=assigned_to,
            scheduled_start=scheduled_start,
            duration_minutes=duration_minutes,
            notes=notes,
            creator_telegram_id=creator_telegram_id or self.admin_telegram_id,
        )

    def complete_running_task(
        self,
        running_task_id: int,
        material_category_id: Optional[int] = None,
        quantity_used: Optional[float] = None,
        material_unit: Optional[str] = None,
        completion_notes: Optional[str] = None,
        warehouse_id: Optional[int] = None,
        admin_telegram_id: Optional[str] = None,
    ) -> Tuple[bool, Optional[str]]:
        """Completes a task with automatic inventory depletion."""
        return self.operations.complete_running_task(
            running_task_id=running_task_id,
            material_category_id=material_category_id,
            quantity_used=quantity_used,
            material_unit=material_unit,
            completion_notes=completion_notes,
            warehouse_id=warehouse_id,
            admin_telegram_id=admin_telegram_id or self.admin_telegram_id,
        )

    def create_issue(
        self,
        zone_id: str,
        title: str,
        description: Optional[str] = None,
        severity: Union[IssueSeverity, str] = IssueSeverity.MEDIUM,
        reported_by: Optional[str] = None,
        cycle_id: Optional[int] = None,
        creator_telegram_id: Optional[str] = None,
    ) -> Tuple[Optional[int], Optional[str]]:
        """Creates a field issue or problem notification."""
        return self.operations.create_issue(
            zone_id=zone_id,
            title=title,
            description=description,
            severity=severity,
            reported_by=reported_by,
            cycle_id=cycle_id,
            creator_telegram_id=creator_telegram_id or self.admin_telegram_id,
        )

    def update_issue_progress(
        self,
        issue_id: int,
        notes: str,
        updater_telegram_id: Optional[str] = None,
    ) -> Tuple[bool, Optional[str]]:
        """Appends progress notes to an issue."""
        return self.operations.update_issue_progress(
            issue_id=issue_id,
            notes=notes,
            updater_telegram_id=updater_telegram_id or self.admin_telegram_id,
        )

    def resolve_issue(
        self,
        issue_id: int,
        resolution_notes: str,
        admin_telegram_id: Optional[str] = None,
    ) -> Tuple[bool, Optional[str]]:
        """Marks an issue as RESOLVED (exclusive admin authority)."""
        return self.operations.resolve_issue(
            issue_id=issue_id,
            resolution_notes=resolution_notes,
            admin_telegram_id=admin_telegram_id or self.admin_telegram_id,
        )

    def close_issue(
        self,
        issue_id: int,
        resolution_notes: str,
        admin_telegram_id: Optional[str] = None,
    ) -> Tuple[bool, Optional[str]]:
        """Verifies and formally closes an issue (exclusive admin authority)."""
        return self.operations.close_issue(
            issue_id=issue_id,
            resolution_notes=resolution_notes,
            admin_telegram_id=admin_telegram_id or self.admin_telegram_id,
        )

    # ==========================================================================
    # 3. Inventory Governance & Adjustments (Section 3.3)
    # ==========================================================================

    def record_inventory_adjustment(
        self,
        item_name: str,
        category_id: int,
        quantity_change: float,
        unit_id: int,
        warehouse_id: Optional[int] = None,
        reason_note: Optional[str] = None,
        admin_telegram_id: Optional[str] = None,
    ) -> Tuple[Optional[int], Optional[str]]:
        """Appends an immutable adjustment transaction to reconcile stock differences."""
        return self.inventory.record_inventory_adjustment(
            item_name=item_name,
            category_id=category_id,
            quantity_change=quantity_change,
            unit_id=unit_id,
            warehouse_id=warehouse_id,
            reason_note=reason_note,
            admin_telegram_id=admin_telegram_id or self.admin_telegram_id,
        )

    def reconcile_inventory(
        self,
        warehouse_id: Optional[int] = None,
        category_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Reconciles product_batches and stock, flagging negative stock anomalies."""
        return self.inventory.reconcile_inventory(warehouse_id=warehouse_id, category_id=category_id)

    def get_negative_stock_alerts(self, warehouse_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """Scans for active virtual negative batches requiring owner reconciliation."""
        return self.inventory.get_negative_stock_alerts(warehouse_id=warehouse_id)

    # ==========================================================================
    # 4. Financial & Barter Governance (Section 3.4)
    # ==========================================================================

    def record_financial_transaction(
        self,
        category_id: int,
        type: Union[FinancialTransactionType, str],
        amount: int,
        payment_method: Union[PaymentMethod, str] = PaymentMethod.CASH,
        partner_name: Optional[str] = None,
        cycle_id: Optional[int] = None,
        notes: Optional[str] = None,
        transaction_date: Optional[str] = None,
        admin_telegram_id: Optional[str] = None,
    ) -> Tuple[Optional[int], Optional[str]]:
        """Records an income or expense transaction with strict integer VND amount."""
        return self.finance.record_financial_transaction(
            category_id=category_id,
            type=type,
            amount=amount,
            payment_method=payment_method,
            partner_name=partner_name,
            cycle_id=cycle_id,
            notes=notes,
            transaction_date=transaction_date,
            admin_telegram_id=admin_telegram_id or self.admin_telegram_id,
        )

    def record_barter_exchange(
        self,
        partner_name: str,
        give_category_id: int,
        give_quantity: float,
        receive_category_id: int,
        receive_quantity: float,
        give_unit: str = "kg",
        receive_unit: str = "kg",
        cash_difference_vnd: int = 0,
        estimated_value_vnd: int = 0,
        warehouse_id: Optional[int] = None,
        give_cycle_id: Optional[int] = None,
        receive_cycle_id: Optional[int] = None,
        notes: Optional[str] = None,
        admin_telegram_id: Optional[str] = None,
    ) -> Tuple[Optional[int], Optional[str]]:
        """Executes atomic dual-leg barter trade (goods-for-goods) with cash difference."""
        return self.finance.record_barter_exchange(
            partner_name=partner_name,
            give_category_id=give_category_id,
            give_quantity=give_quantity,
            receive_category_id=receive_category_id,
            receive_quantity=receive_quantity,
            give_unit=give_unit,
            receive_unit=receive_unit,
            cash_difference_vnd=cash_difference_vnd,
            estimated_value_vnd=estimated_value_vnd,
            warehouse_id=warehouse_id,
            give_cycle_id=give_cycle_id,
            receive_cycle_id=receive_cycle_id,
            notes=notes,
            admin_telegram_id=admin_telegram_id or self.admin_telegram_id,
        )
    def process_debt_payment(
        self,
        debt_id: int,
        amount_paid: int,
        payment_method: Union[PaymentMethod, str] = PaymentMethod.CASH,
        notes: Optional[str] = None,
        admin_telegram_id: Optional[str] = None,
    ) -> Tuple[Optional[int], Optional[str]]:
        """Processes an installment payment towards a debt, auto-settling when balance hits 0."""
        return self.finance.process_debt_payment(
            debt_id=debt_id,
            amount_paid=amount_paid,
            payment_method=payment_method,
            notes=notes,
            admin_telegram_id=admin_telegram_id or self.admin_telegram_id,
        )

    # ==========================================================================
    # 5. Audit & Reconciliation Reporting (Section 3.5 & Section 5 Tầng 3)
    # ==========================================================================

    def get_inventory_root_summary(self, anomaly_only: bool = False) -> List[Dict[str, Any]]:
        """Queries v_inventory_root_summary for material categories and negative stock alerts."""
        return self.reports.get_inventory_root_summary(anomaly_only=anomaly_only)

    def get_cycle_yield_performance(self, cycle_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """Queries v_cycle_yield_performance for actual vs expected yield achievement rate."""
        return self.reports.get_cycle_yield_performance(cycle_id=cycle_id)

    def get_cycle_financial_summary(self, cycle_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """Queries v_cycle_financial_summary for revenue, expenses, net profit, and ROI %."""
        return self.reports.get_cycle_financial_summary(cycle_id=cycle_id)

    def get_daily_cashflow_summary(
        self,
        limit_days: int = 30,
        payment_method: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Queries v_daily_cashflow_summary for daily cash vs bank transfer cash flows."""
        return self.reports.get_daily_cashflow_summary(limit_days=limit_days, payment_method=payment_method)

    def get_dashboard_overview(self) -> Dict[str, Any]:
        """Returns consolidated farm executive health metrics across all domains."""
        return self.reports.get_dashboard_overview()

    # ==========================================================================
    # 6. Collaborators & Access Control
    # ==========================================================================

    def get_collaborators(
        self,
        role: Optional[Union[CollaboratorRole, str]] = None,
        is_active: Optional[bool] = None,
    ) -> List[Dict[str, Any]]:
        """Returns list of farm collaborators."""
        return self.collaborators.get_collaborators(role=role, is_active=is_active)

    def add_collaborator(
        self,
        telegram_id: str,
        full_name: str,
        role: Union[CollaboratorRole, str] = CollaboratorRole.WORKER,
        is_active: bool = True,
        creator_telegram_id: Optional[str] = None,
    ) -> Tuple[Optional[int], Optional[str]]:
        """Registers a new collaborator."""
        return self.collaborators.add_collaborator(
            telegram_id=telegram_id,
            full_name=full_name,
            role=role,
            is_active=is_active,
            creator_telegram_id=creator_telegram_id or self.admin_telegram_id,
        )

    def deactivate_collaborator(
        self,
        telegram_id_or_id: Union[str, int],
        admin_telegram_id: Optional[str] = None,
    ) -> Tuple[bool, Optional[str]]:
        """Deactivates a collaborator."""
        return self.collaborators.deactivate_collaborator(
            telegram_id_or_id=telegram_id_or_id,
            admin_telegram_id=admin_telegram_id or self.admin_telegram_id,
        )
