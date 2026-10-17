"""AgriVoice-AI: Admin Personnel & Collaborator Management.

Manages farm workers, managers, and access control (RBAC).
Enforces owner/admin authority for load-bearing administrative operations.
"""

from __future__ import annotations

import sqlite3
from typing import Any, Dict, List, Optional, Tuple, Union

from src.db.connection import get_db
from src.db.models import Collaborator, CollaboratorRole
from src.db.service import DBService


class AdminPermissionError(PermissionError):
    """Raised when an operation is attempted by a non-admin or unauthorized user."""

    pass


class CollaboratorManager:
    """Manages farm collaborators, role permissions, and access states."""

    def __init__(self, service: DBService, admin_telegram_id: Optional[str] = None):
        self.service = service
        self.admin_telegram_id = admin_telegram_id

    def check_admin_privilege(self, telegram_id: Optional[str] = None) -> Tuple[bool, Optional[str]]:
        """Verifies if the specified telegram_id has ADMIN or OWNER privileges."""
        target_tid = telegram_id or self.admin_telegram_id
        if not target_tid:
            return False, "Chưa cung cấp Telegram ID quản trị viên."

        can_do, reason = self.service.check_permission(target_tid, action="APPROVE")
        if not can_do:
            return False, f"Từ chối quyền Admin: {reason}"
        return True, None

    def verify_admin_privilege(self, telegram_id: Optional[str] = None) -> None:
        """Enforces admin privilege, raising AdminPermissionError if unauthorized."""
        can_do, reason = self.check_admin_privilege(telegram_id)
        if not can_do:
            raise AdminPermissionError(reason)

    def get_collaborators(
        self,
        role: Optional[Union[CollaboratorRole, str]] = None,
        is_active: Optional[bool] = None,
    ) -> List[Dict[str, Any]]:
        """Returns list of collaborators filtered by role and active status."""
        conds: Dict[str, Any] = {}
        if role is not None:
            conds["role"] = str(role.value) if isinstance(role, CollaboratorRole) else str(role)
        if is_active is not None:
            conds["is_active"] = 1 if is_active else 0

        return self.service.get_formatted_data("collaborators", conditions=conds or None)

    def get_collaborator(
        self,
        telegram_id: Optional[str] = None,
        collaborator_id: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        """Retrieves a single collaborator record by telegram_id or collaborator_id."""
        if telegram_id:
            return self.service.get_record("collaborators", "telegram_id = ?", (str(telegram_id),), limit=1)
        if collaborator_id:
            return self.service.get_record("collaborators", "collaborator_id = ?", (collaborator_id,), limit=1)
        return None

    def add_collaborator(
        self,
        telegram_id: str,
        full_name: str,
        role: Union[CollaboratorRole, str] = CollaboratorRole.WORKER,
        is_active: bool = True,
        creator_telegram_id: Optional[str] = None,
    ) -> Tuple[Optional[int], Optional[str]]:
        """Registers a new collaborator into the system."""
        self.verify_admin_privilege(creator_telegram_id)

        role_str = str(role.value) if isinstance(role, CollaboratorRole) else str(role).upper()
        if role_str not in ("OWNER", "ADMIN", "WORKER", "VIEWER"):
            return None, f"Vai trò không hợp lệ: '{role}'. Phải thuộc (OWNER, ADMIN, WORKER, VIEWER)."

        existing = self.get_collaborator(telegram_id=telegram_id)
        if existing:
            return None, f"Cộng tác viên với Telegram ID {telegram_id} đã tồn tại trong hệ thống."

        rec_data = {
            "telegram_id": str(telegram_id),
            "full_name": full_name.strip(),
            "role": role_str,
            "is_active": 1 if is_active else 0,
        }
        collab_id, err = self.service.insert_row("collaborators", rec_data)
        return collab_id, err

    def update_collaborator(
        self,
        collaborator_id: int,
        full_name: Optional[str] = None,
        role: Optional[Union[CollaboratorRole, str]] = None,
        is_active: Optional[bool] = None,
        updater_telegram_id: Optional[str] = None,
    ) -> Tuple[bool, Optional[str]]:
        """Updates full_name, role, or active status of a collaborator."""
        self.verify_admin_privilege(updater_telegram_id)

        existing = self.get_collaborator(collaborator_id=collaborator_id)
        if not existing:
            return False, f"Không tìm thấy cộng tác viên ID #{collaborator_id}."

        data: Dict[str, Any] = {}
        if full_name is not None:
            data["full_name"] = full_name.strip()
        if role is not None:
            r_str = str(role.value) if isinstance(role, CollaboratorRole) else str(role).upper()
            if r_str not in ("OWNER", "ADMIN", "WORKER", "VIEWER"):
                return False, f"Vai trò không hợp lệ: '{role}'."
            data["role"] = r_str
        if is_active is not None:
            data["is_active"] = 1 if is_active else 0

        if not data:
            return True, None
        count, err = self.service.update_row(
            "collaborators",
            data=data,
            where={"collaborator_id": collaborator_id},
        )
        if err or count == 0:
            return False, err or "Không có bản ghi nào được cập nhật."
        return True, None
    def deactivate_collaborator(
        self,
        telegram_id_or_id: Union[str, int],
        admin_telegram_id: Optional[str] = None,
    ) -> Tuple[bool, Optional[str]]:
        """Deactivates a collaborator (marks is_active = 0) preventing further actions."""
        self.verify_admin_privilege(admin_telegram_id)

        if isinstance(telegram_id_or_id, int):
            collab = self.get_collaborator(collaborator_id=telegram_id_or_id)
        else:
            collab = self.get_collaborator(telegram_id=str(telegram_id_or_id))

        if not collab:
            return False, f"Không tìm thấy cộng tác viên: '{telegram_id_or_id}'."

        return self.update_collaborator(
            collaborator_id=collab["collaborator_id"],
            is_active=False,
            updater_telegram_id=admin_telegram_id,
        )
