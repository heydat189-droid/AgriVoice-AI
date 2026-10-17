"""AgriVoice-AI: In-Flight Staging Queue & Event Approval Management.

Handles inspection of voice logs, chronological ordering enforcement,
payload editing, single and batch approvals, rejections, and error retries.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple, Union

from src.admin.collaborators import AdminPermissionError
from src.db.service import DBService


class QueueReviewManager:
    """Manages In-Flight pending events review, validation, editing, and approvals."""

    def __init__(self, service: DBService, admin_telegram_id: Optional[str] = None):
        self.service = service
        self.admin_telegram_id = admin_telegram_id

    def _verify_admin(self, telegram_id: Optional[str] = None) -> None:
        target_tid = telegram_id or self.admin_telegram_id
        if not target_tid:
            raise AdminPermissionError("Chưa cung cấp Telegram ID quản trị viên.")
        can_do, reason = self.service.check_permission(target_tid, action="APPROVE")
        if not can_do:
            raise AdminPermissionError(f"Từ chối quyền duyệt Admin: {reason}")

    def get_pending_queue(
        self,
        target_table: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Returns all events currently awaiting approval ordered strictly by timestamp ASC, event_id ASC."""
        return self.service.get_pending_queue(target_table=target_table, limit=limit)

    def get_error_events(
        self,
        target_table: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Returns all events currently in ERROR status for diagnostic inspection."""
        return self.service.get_error_logs(target_table=target_table, limit=limit)

    def get_event_history(
        self,
        target_table: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Returns audit trail of approved, rejected, and error events from v_pending_events_history."""
        conds = {"target_table": self.service._normalize_table_name(target_table)} if target_table else None
        return self.service.get_formatted_data("v_pending_events_history", conditions=conds, limit=limit)

    def get_event_detail(self, event_id: int) -> Optional[Dict[str, Any]]:
        """Retrieves complete details of an event in pending_events including parsed payload."""
        event = self.service.get_record("pending_events", "event_id = ?", (event_id,), limit=1)
        if not event:
            return None

        event_dict = dict(event)
        raw_payload = event_dict.get("payload_json")
        if raw_payload and isinstance(raw_payload, str):
            try:
                event_dict["payload_parsed"] = json.loads(raw_payload)
            except Exception:
                event_dict["payload_parsed"] = None
        else:
            event_dict["payload_parsed"] = raw_payload

        return event_dict

    def edit_event_payload(
        self,
        event_id: int,
        payload: Union[Dict[str, Any], str],
        reset_status_to_pending: bool = True,
        admin_telegram_id: Optional[str] = None,
    ) -> Tuple[bool, Optional[str]]:
        """Allows admin to amend payload_json before approving (e.g. to fix AI mis-transcription or schema error)."""
        self._verify_admin(admin_telegram_id)

        target_event = self.service.get_record("pending_events", "event_id = ?", (event_id,), limit=1)
        if not target_event:
            return False, f"Không tìm thấy sự kiện #{event_id}."

        if target_event["status"] not in ("PENDING", "ERROR"):
            return False, f"Sự kiện #{event_id} đang ở trạng thái {target_event['status']}, không thể chỉnh sửa."

        ok, err = self.service.update_pending_event_payload(
            event_id=event_id,
            payload=payload,
            reset_status_to_pending=reset_status_to_pending,
        )
        return ok, err

    def approve_event(
        self,
        event_id: int,
        review_notes: Optional[str] = None,
        admin_telegram_id: Optional[str] = None,
    ) -> Tuple[bool, Optional[str]]:
        """Approves a pending event and applies its payload atomically to the target table."""
        tid = admin_telegram_id or self.admin_telegram_id
        self._verify_admin(tid)

        return self.service.approve_pending_event(
            event_id=event_id,
            reviewer_telegram_id=tid,
            review_notes=review_notes,
        )

    def reject_event(
        self,
        event_id: int,
        review_notes: str,
        admin_telegram_id: Optional[str] = None,
    ) -> Tuple[bool, Optional[str]]:
        """Rejects a pending event without deleting it (Audit Trail preserved)."""
        tid = admin_telegram_id or self.admin_telegram_id
        self._verify_admin(tid)

        if not review_notes or not review_notes.strip():
            return False, "Bắt buộc phải cung cấp lý do từ chối (review_notes)."

        return self.service.reject_pending_event(
            event_id=event_id,
            reviewer_telegram_id=tid,
            review_notes=review_notes.strip(),
        )

    def approve_all_pending(
        self,
        target_table: Optional[str] = None,
        admin_telegram_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Approves all currently pending events strictly in chronological order.

        Halts immediately on first error to prevent data cascade corruption.
        """
        tid = admin_telegram_id or self.admin_telegram_id
        self._verify_admin(tid)

        queue = self.get_pending_queue(target_table=target_table)
        approved_count = 0
        failed_event_id = None
        error_message = None

        for item in queue:
            eid = item["event_id"]
            ok, err = self.approve_event(event_id=eid, admin_telegram_id=tid)
            if not ok:
                failed_event_id = eid
                error_message = err
                break
            approved_count += 1

        return {
            "total_in_queue": len(queue),
            "approved_count": approved_count,
            "failed_event_id": failed_event_id,
            "error_message": error_message,
            "success": failed_event_id is None,
        }

    def retry_error_event(
        self,
        event_id: int,
        updated_payload: Optional[Union[Dict[str, Any], str]] = None,
        admin_telegram_id: Optional[str] = None,
    ) -> Tuple[bool, Optional[str]]:
        """Fixes an ERROR event (optionally updating payload) and re-executes approval."""
        tid = admin_telegram_id or self.admin_telegram_id
        self._verify_admin(tid)

        event = self.service.get_record("pending_events", "event_id = ?", (event_id,), limit=1)
        if not event:
            return False, f"Không tìm thấy sự kiện #{event_id}."

        if event["status"] != "ERROR":
            return False, f"Sự kiện #{event_id} không ở trạng thái ERROR (hiện tại: {event['status']})."

        # Update payload if provided, resetting to PENDING
        if updated_payload is not None:
            ok, err = self.edit_event_payload(
                event_id=event_id,
                payload=updated_payload,
                reset_status_to_pending=True,
                admin_telegram_id=tid,
            )
            if not ok:
                return False, f"Lỗi cập nhật payload trước khi duyệt lại: {err}"
        else:
            # Just reset status to PENDING
            self.service.update_row("pending_events", {"event_id": event_id, "status": "PENDING", "error_message": None})

        # Re-approve
        return self.approve_event(event_id=event_id, admin_telegram_id=tid)
