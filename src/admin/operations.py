"""AgriVoice-AI: Admin Farm Operations & SOP Scheduling.

Handles production cycles, automated SOP task generation, ad-hoc tasks,
resource locking validation, and issue resolution/closure.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple, Union

from src.admin.collaborators import AdminPermissionError
from src.db.models import IssueSeverity, IssueStatus, ProductionCycleStatus
from src.db.service import DBService


class OperationsManager:
    """Manages cycles, SOP running tasks, field tasks, and issue lifecycle."""

    def __init__(self, service: DBService, admin_telegram_id: Optional[str] = None):
        self.service = service
        self.admin_telegram_id = admin_telegram_id

    def _verify_admin(self, telegram_id: Optional[str] = None) -> None:
        target_tid = telegram_id or self.admin_telegram_id
        if not target_tid:
            raise AdminPermissionError("Chưa cung cấp Telegram ID quản trị viên.")
        can_do, reason = self.service.check_permission(target_tid, action="APPROVE")
        if not can_do:
            raise AdminPermissionError(f"Từ chối quyền Admin: {reason}")

    # --------------------------------------------------------------------------
    # Production Cycles
    # --------------------------------------------------------------------------

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
        """Creates a new production cycle and optionally generates SOP running tasks."""
        self._verify_admin(creator_telegram_id)

        data = {
            "zone_id": zone_id,
            "name": name,
            "subject_name": subject_name,
            "start_date": start_date or self.service._get_current_timestamp()[:10],
            "project_id": project_id,
            "area_size": area_size,
            "unit_of_size": unit_of_size,
            "expected_yield": expected_yield,
            "status": str(status.value) if isinstance(status, ProductionCycleStatus) else str(status),
        }
        cycle_id, err = self.service.insert_row("production_cycles", data)
        if err or not cycle_id:
            return None, err

        if auto_build_tasks and project_id:
            self.service.build_running_tasks_for_cycle(cycle_id)

        return cycle_id, None

    def get_active_cycles(self, zone_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Retrieves all currently active production cycles."""
        conds = {"status": "ACTIVE"}
        if zone_id:
            conds["zone_id"] = zone_id
        return self.service.get_formatted_data("production_cycles", conditions=conds)

    def close_cycle(
        self,
        cycle_id: int,
        actual_end_date: Optional[str] = None,
        output_quantity: Optional[float] = None,
        output_unit: Optional[str] = None,
        notes: Optional[str] = None,
        closer_telegram_id: Optional[str] = None,
    ) -> Tuple[bool, Optional[str]]:
        """Closes a completed production cycle."""
        self._verify_admin(closer_telegram_id)

        existing = self.service.get_record("production_cycles", "cycle_id = ?", (cycle_id,), limit=1)
        if not existing:
            return False, f"Không tìm thấy vụ mùa #{cycle_id}."

        data = {
            "cycle_id": cycle_id,
            "status": "COMPLETED",
            "actual_end_date": actual_end_date or self.service._get_current_timestamp()[:10],
        }
        if output_quantity is not None:
            data["output_quantity"] = output_quantity
        if output_unit is not None:
            data["output_unit"] = output_unit
        if notes is not None:
            data["notes"] = notes

        count, err = self.service.update_row("production_cycles", data)
        return (count > 0, err)

    # --------------------------------------------------------------------------
    # SOP & Running Tasks
    # --------------------------------------------------------------------------

    def build_running_tasks_for_cycle(
        self,
        cycle_id: int,
        clear_existing: bool = False,
        admin_telegram_id: Optional[str] = None,
    ) -> Tuple[int, Optional[str]]:
        """Generates running tasks from SOP templates for the cycle."""
        self._verify_admin(admin_telegram_id)
        return self.service.build_running_tasks_for_cycle(cycle_id=cycle_id, clear_existing=clear_existing)

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
        """Creates an urgent ad-hoc field task."""
        self._verify_admin(creator_telegram_id)
        return self.service.create_adhoc_task(
            name=name,
            cycle_id=cycle_id,
            assigned_to=assigned_to,
            scheduled_start=scheduled_start,
            duration_minutes=duration_minutes,
            description=notes,
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
        """Completes a task with automatic inventory material deduction."""
        tid = admin_telegram_id or self.admin_telegram_id
        return self.service.complete_running_task(
            running_task_id=running_task_id,
            worker_telegram_id=tid,
            material_category_id=material_category_id,
            quantity_used=quantity_used,
            material_unit=material_unit,
            completion_notes=completion_notes,
            warehouse_id=warehouse_id,
        )

    def get_running_tasks(
        self,
        status: Optional[str] = None,
        cycle_id: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Queries running tasks with optional status and cycle filters."""
        conds: Dict[str, Any] = {}
        if status:
            conds["status"] = status
        if cycle_id:
            conds["cycle_id"] = cycle_id
        return self.service.get_formatted_data("running_tasks", conditions=conds or None, limit=limit)

    def check_resource_locks(
        self,
        target_ids: Union[List[str], str],
        task_id: Optional[int] = None,
    ) -> Tuple[bool, Optional[str]]:
        """Checks for local or global lock conflicts on target entities."""
        return self.service.check_resource_locks(target_ids=target_ids, task_id=task_id)

    # --------------------------------------------------------------------------
    # Issues & Field Incidents
    # --------------------------------------------------------------------------

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
        """Creates a new field issue or ad-hoc problem."""
        data = {
            "zone_id": zone_id,
            "title": title,
            "description": description,
            "severity": str(severity.value) if isinstance(severity, IssueSeverity) else str(severity),
            "status": "OPEN",
            "reported_by": reported_by or "Chủ vườn",
            "cycle_id": cycle_id,
        }
        return self.service.insert_row("issues", data)

    def update_issue_progress(
        self,
        issue_id: int,
        notes: str,
        updater_telegram_id: Optional[str] = None,
    ) -> Tuple[bool, Optional[str]]:
        """Updates progress notes on an ongoing issue (status becomes IN_PROGRESS)."""
        tid = updater_telegram_id or self.admin_telegram_id
        return self.service.manage_issue(
            issue_id=issue_id,
            action="IN_PROGRESS",
            notes=notes,
            reviewer_telegram_id=tid,
        )

    def resolve_issue(
        self,
        issue_id: int,
        resolution_notes: str,
        admin_telegram_id: Optional[str] = None,
    ) -> Tuple[bool, Optional[str]]:
        """Marks an issue as RESOLVED (exclusive admin authority)."""
        tid = admin_telegram_id or self.admin_telegram_id
        self._verify_admin(tid)
        return self.service.manage_issue(
            issue_id=issue_id,
            action="RESOLVED",
            resolution_notes=resolution_notes,
            reviewer_telegram_id=tid,
        )

    def close_issue(
        self,
        issue_id: int,
        resolution_notes: str,
        admin_telegram_id: Optional[str] = None,
    ) -> Tuple[bool, Optional[str]]:
        """Formally verifies and closes an issue dứt điểm (exclusive admin authority)."""
        tid = admin_telegram_id or self.admin_telegram_id
        self._verify_admin(tid)
        return self.service.manage_issue(
            issue_id=issue_id,
            action="CLOSED",
            resolution_notes=resolution_notes,
            reviewer_telegram_id=tid,
        )

    def get_open_issues(self, zone_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Returns all unresolved issues (OPEN or IN_PROGRESS)."""
        conds: Dict[str, Any] = {}
        if zone_id:
            conds["zone_id"] = zone_id
        all_issues = self.service.get_formatted_data("issues", conditions=conds or None)
        return [i for i in all_issues if i.get("status") in ("OPEN", "IN_PROGRESS")]
