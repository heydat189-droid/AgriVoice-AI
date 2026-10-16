"""AgriVoice-AI: Pending Events Staging & Approval Service.

Facade and functional helpers for pending event processing and virtual view overlays,
delegating to or mirroring DBService.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any, Dict, List, Optional, Tuple

from src.db.models import (
    PendingActionType,
    PendingEvent,
    PendingEventStatus,
)


class StrictOrderingViolationError(Exception):
    """Raised when an attempt is made to approve an event out of chronological order."""

    pass


class TargetTableExecutionError(Exception):
    """Raised when applying the payload_json to the target table fails."""

    pass


def stage_voice_event(
    conn: sqlite3.Connection,
    target_table: str,
    action_type: PendingActionType | str,
    payload: Dict[str, Any] | str,
    raw_transcript: str = "",
    summary_text: Optional[str] = None,
    audio_path: Optional[str] = None,
    log_id: Optional[int] = None,
    timestamp: Optional[str] = None,
    sender_id: str = "WORKER_1",
) -> int:
    """Stages an AI-extracted event into V9 `pending_events`."""
    payload_json = json.dumps(payload, ensure_ascii=False) if isinstance(payload, dict) else payload

    cur = conn.cursor()
    query = """
        INSERT INTO pending_events (
            target_table, action_type, payload_json, raw_transcript,
            summary_text, audio_path, log_id, timestamp, sender_id, status
        ) VALUES (
            ?, ?, ?, ?,
            ?, ?, ?, COALESCE(?, CURRENT_TIMESTAMP), ?, 'PENDING'
        )
    """
    cur.execute(
        query,
        (
            target_table,
            str(action_type),
            payload_json,
            raw_transcript,
            summary_text,
            audio_path,
            log_id,
            timestamp,
            sender_id,
        ),
    )
    event_id = cur.lastrowid
    return int(event_id)


def get_pending_queue(conn: sqlite3.Connection) -> List[sqlite3.Row]:
    """Retrieves all pending events ordered strictly by timestamp ASC, event_id ASC."""
    cur = conn.cursor()
    cur.execute("SELECT * FROM v_pending_events_queue;")
    return cur.fetchall()


def get_earliest_pending_event(conn: sqlite3.Connection) -> Optional[sqlite3.Row]:
    """Returns the earliest pending event that is next in line to be reviewed."""
    cur = conn.cursor()
    cur.execute("SELECT * FROM v_pending_events_queue LIMIT 1;")
    return cur.fetchone()


def verify_strict_ordering(conn: sqlite3.Connection, event_id: int) -> None:
    """Verifies that no earlier PENDING event exists before `event_id`."""
    cur = conn.cursor()
    cur.execute(
        "SELECT event_id, timestamp FROM pending_events WHERE event_id = ?;",
        (event_id,),
    )
    target = cur.fetchone()
    if not target:
        raise ValueError(f"Event #{event_id} does not exist.")

    cur.execute(
        """
        SELECT event_id, timestamp, summary_text
        FROM pending_events
        WHERE status IN ('PENDING', 'ERROR')
          AND (timestamp < ? OR (timestamp = ? AND event_id < ?))
        ORDER BY timestamp ASC, event_id ASC
        LIMIT 1;
        """,
        (target["timestamp"], target["timestamp"], event_id),
    )
    earlier = cur.fetchone()
    if earlier:
        raise StrictOrderingViolationError(
            f"Bắt buộc duyệt tuần tự: Sự kiện #{earlier['event_id']} ({earlier['timestamp']}) "
            f"phải được xử lý trước sự kiện #{event_id} ({target['timestamp']})."
        )


def approve_pending_event(
    conn: sqlite3.Connection,
    event_id: int,
    reviewer_id: Optional[int] = None,
    review_notes: Optional[str] = None,
    enforce_order: bool = True,
) -> int:
    """Approves a pending event and applies its payload to the target table atomically."""
    if enforce_order:
        verify_strict_ordering(conn, event_id)

    cur = conn.cursor()
    cur.execute(
        """
        SELECT event_id, target_table, action_type, payload_json, status
        FROM pending_events
        WHERE event_id = ?;
        """,
        (event_id,),
    )
    event = cur.fetchone()
    if not event:
        raise ValueError(f"Event #{event_id} does not exist.")

    if event["status"] not in ("PENDING", "ERROR"):
        raise ValueError(f"Event #{event_id} has already been {event['status']}.")

    target_table = event["target_table"]
    action_type = event["action_type"]
    payload = json.loads(event["payload_json"])

    target_row_id = None
    cur.execute("SAVEPOINT apply_pending_event;")
    try:
        if action_type == "INSERT":
            if target_table == "production_logs" and (not payload.get("cycle_id")):
                cur.execute("SELECT cycle_id FROM production_cycles WHERE status = 'ACTIVE' LIMIT 1;")
                r = cur.fetchone()
                if not r:
                    cur.execute("SELECT cycle_id FROM production_cycles LIMIT 1;")
                    r = cur.fetchone()
                if r:
                    payload["cycle_id"] = r[0] if isinstance(r, (list, tuple)) else r["cycle_id"]
                else:
                    cur.execute("SELECT zone_id FROM zones LIMIT 1;")
                    zr = cur.fetchone()
                    zid = zr[0] if zr else "ZONE_A"
                    if not zr:
                        cur.execute("INSERT OR IGNORE INTO zones (zone_id, zone_name) VALUES ('ZONE_A', 'Khu Mặc Định');")
                    cur.execute("INSERT INTO production_cycles (zone_id, name, subject_name, start_date, status) VALUES (?, 'Vụ Canh Tác Mặc Định', 'Chung', date('now'), 'ACTIVE');", (zid,))
                    payload["cycle_id"] = cur.lastrowid
            elif target_table == "issues" and (not payload.get("zone_id")):
                cur.execute("SELECT zone_id FROM zones LIMIT 1;")
                zr = cur.fetchone()
                if not zr:
                    cur.execute("INSERT OR IGNORE INTO zones (zone_id, zone_name) VALUES ('ZONE_A', 'Khu Mặc Định');")
                    payload["zone_id"] = "ZONE_A"
                else:
                    payload["zone_id"] = zr[0]
            cols = list(payload.keys())
            placeholders = ", ".join(["?"] * len(cols))
            col_names = ", ".join(cols)
            sql = f"INSERT INTO {target_table} ({col_names}) VALUES ({placeholders})"
            cur.execute(sql, [payload[c] for c in cols])
            target_row_id = cur.lastrowid
        elif action_type == "UPDATE":
            if "where" in payload and "data" in payload:
                where_clause = payload["where"]
                data_clause = payload["data"]
            else:
                pk_col = f"{target_table.rstrip('s')}_id"
                if pk_col in payload:
                    pk_val = payload[pk_col]
                    data_clause = {k: v for k, v in payload.items() if k != pk_col}
                    where_clause = {pk_col: pk_val}
                else:
                    raise TargetTableExecutionError("UPDATE payload must contain identifiable primary key or 'where'/'data' blocks.")

            set_assignments = ", ".join([f"{k} = ?" for k in data_clause.keys()])
            where_conditions = " AND ".join([f"{k} = ?" for k in where_clause.keys()])
            sql = f"UPDATE {target_table} SET {set_assignments} WHERE {where_conditions}"
            cur.execute(sql, list(data_clause.values()) + list(where_clause.values()))
            target_row_id = cur.rowcount
        elif action_type == "DELETE":
            where_conditions = " AND ".join([f"{k} = ?" for k in payload.keys()])
            sql = f"DELETE FROM {target_table} WHERE {where_conditions}"
            cur.execute(sql, list(payload.values()))
            target_row_id = cur.rowcount
        else:
            raise TargetTableExecutionError(f"Unsupported action_type: {action_type}")

        cur.execute(
            """
            UPDATE pending_events
            SET status = 'APPROVED',
                error_message = NULL,
                reviewed_by = ?,
                review_notes = ?
            WHERE event_id = ?;
            """,
            (reviewer_id, review_notes, event_id),
        )
        cur.execute("RELEASE SAVEPOINT apply_pending_event;")

    except Exception as exc:
        err_msg = str(exc)
        try:
            cur.execute("ROLLBACK TO SAVEPOINT apply_pending_event;")
            cur.execute("RELEASE SAVEPOINT apply_pending_event;")
        except Exception:
            pass

        try:
            cur.execute(
                """
                UPDATE pending_events
                SET status = 'ERROR',
                    error_message = ?,
                    reviewed_by = COALESCE(?, reviewed_by),
                    review_notes = COALESCE(?, review_notes)
                WHERE event_id = ?;
                """,
                (err_msg, reviewer_id, review_notes, event_id),
            )
            conn.commit()
        except Exception:
            pass

        raise TargetTableExecutionError(
            f"Failed to apply event #{event_id} into '{target_table}': {err_msg}"
        ) from exc

    return target_row_id or 0


def reject_pending_event(
    conn: sqlite3.Connection,
    event_id: int,
    reviewer_id: Optional[int] = None,
    review_notes: Optional[str] = None,
) -> None:
    """Rejects a pending event without deleting it (Audit Trail preserved)."""
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE pending_events
        SET status = 'REJECTED',
            reviewed_by = ?,
            review_notes = ?
        WHERE event_id = ? AND status IN ('PENDING', 'ERROR');
        """,
        (reviewer_id, review_notes, event_id),
    )
    if cur.rowcount == 0:
        raise ValueError(f"Event #{event_id} is not in PENDING/ERROR status or does not exist.")


def get_table_with_virtual_overlay(
    conn: sqlite3.Connection,
    target_table: str,
    base_query: str,
    base_params: Tuple[Any, ...] = (),
    apply_pending: bool = False,
) -> Dict[str, Any]:
    """Fetches committed data from the database along with unapproved pending events for preview."""
    if apply_pending:
        from src.db.service import DBService
        service = DBService(conn=conn)
        return service.get_data_with_pending_applied(target_table)

    cur = conn.cursor()
    cur.execute(base_query, base_params)
    committed = [dict(row) for row in cur.fetchall()]

    cur.execute(
        """
        SELECT event_id, timestamp, action_type, summary_text, raw_transcript, payload_json, audio_path
        FROM pending_events
        WHERE target_table = ? AND status = 'PENDING'
        ORDER BY timestamp ASC, event_id ASC;
        """,
        (target_table,),
    )
    pending = [dict(row) for row in cur.fetchall()]

    return {
        "target_table": target_table,
        "committed_count": len(committed),
        "pending_count": len(pending),
        "committed_data": committed,
        "pending_overlays": pending,
    }


def get_table_with_pending_applied(
    conn: sqlite3.Connection,
    target_table: str,
    conditions: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Fetches committed data and sequentially applies unapproved pending events using SQL semantics."""
    from src.db.service import DBService
    service = DBService(conn=conn)
    return service.get_data_with_pending_applied(target_table, conditions=conditions)

def get_error_events(conn: sqlite3.Connection) -> List[sqlite3.Row]:
    """Retrieves all events that failed execution (status='ERROR') for owner inspection."""
    cur = conn.cursor()
    cur.execute("SELECT * FROM v_pending_events_errors;")
    return cur.fetchall()


def update_pending_event_payload(
    conn: sqlite3.Connection,
    event_id: int,
    payload: Dict[str, Any] | str,
    reset_status_to_pending: bool = True,
) -> None:
    """Updates the payload_json of an event (e.g. to fix errors before re-approving)."""
    payload_json = json.dumps(payload, ensure_ascii=False) if isinstance(payload, dict) else payload
    cur = conn.cursor()
    if reset_status_to_pending:
        cur.execute(
            """
            UPDATE pending_events
            SET payload_json = ?,
                status = 'PENDING',
                error_message = NULL
            WHERE event_id = ?;
            """,
            (payload_json, event_id),
        )
    else:
        cur.execute(
            "UPDATE pending_events SET payload_json = ? WHERE event_id = ?;",
            (payload_json, event_id),
        )

def build_running_tasks_for_cycle(
    conn: sqlite3.Connection,
    cycle_id: int,
    clear_existing: bool = False,
) -> int:
    """Builds running tasks for a cycle from SOP templates."""
    from src.db.service import DBService
    service = DBService(conn=conn)
    count, err = service.build_running_tasks_for_cycle(cycle_id, clear_existing=clear_existing)
    if err:
        raise ValueError(err)
    return count


def create_adhoc_task(
    conn: sqlite3.Connection,
    name: str,
    cycle_id: Optional[int] = None,
    project_id: Optional[int] = None,
    assigned_to: Optional[int] = None,
    scheduled_start: Optional[str] = None,
    duration_minutes: int = 30,
    description: Optional[str] = None,
) -> int:
    """Creates an ad-hoc field task."""
    from src.db.service import DBService
    service = DBService(conn=conn)
    rt_id, err = service.create_adhoc_task(
        name=name,
        cycle_id=cycle_id,
        project_id=project_id,
        assigned_to=assigned_to,
        scheduled_start=scheduled_start,
        duration_minutes=duration_minutes,
        description=description,
    )
    if err or rt_id is None:
        raise ValueError(err or "Failed to create ad-hoc task")
    return rt_id


def complete_running_task(
    conn: sqlite3.Connection,
    running_task_id: int,
    material_category_id: Optional[int] = None,
    quantity_used: Optional[float] = None,
    material_unit: Optional[str] = None,
    completion_notes: Optional[str] = None,
    warehouse_id: int = 1,
) -> bool:
    """Marks a running task as done and issues material if specified."""
    from src.db.service import DBService
    service = DBService(conn=conn)
    success, err = service.complete_running_task(
        running_task_id=running_task_id,
        material_category_id=material_category_id,
        quantity_used=quantity_used,
        material_unit=material_unit,
        completion_notes=completion_notes,
        warehouse_id=warehouse_id,
    )
    if not success:
        raise ValueError(err or "Failed to complete running task")
    return success


def check_resource_locks(
    conn: sqlite3.Connection,
    target_ids: Union[List[str], str],
    task_id: Optional[int] = None,
) -> Tuple[bool, Optional[str]]:
    """Checks for lock conflicts on target entities."""
    from src.db.service import DBService
    service = DBService(conn=conn)
    return service.check_resource_locks(target_ids=target_ids, task_id=task_id)


def manage_issue(
    conn: sqlite3.Connection,
    issue_id: int,
    action: str,
    resolution_notes: Optional[str] = None,
    notes: Optional[str] = None,
    reviewer_telegram_id: Optional[str] = None,
) -> bool:
    """Updates issue status and resolution notes."""
    from src.db.service import DBService
    service = DBService(conn=conn)
    success, err = service.manage_issue(
        issue_id=issue_id,
        action=action,
        resolution_notes=resolution_notes,
        notes=notes,
        reviewer_telegram_id=reviewer_telegram_id,
    )
    if not success:
        raise ValueError(err or "Failed to manage issue")
    return success


def record_barter_exchange(
    conn: sqlite3.Connection,
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
    warehouse_id: int = 1,
    notes: Optional[str] = None,
) -> int:
    """Executes an atomic barter exchange."""
    from src.db.service import DBService
    service = DBService(conn=conn)
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
    )
    if err or barter_id is None:
        raise ValueError(err or "Failed to record barter exchange")
    return barter_id


def process_debt_payment(
    conn: sqlite3.Connection,
    debt_id: int,
    amount_paid: int,
    payment_date: Optional[str] = None,
    payment_method: str = "CASH",
    notes: Optional[str] = None,
) -> int:
    """Processes a debt payment installment."""
    from src.db.service import DBService
    service = DBService(conn=conn)
    payment_id, err = service.process_debt_payment(
        debt_id=debt_id,
        amount_paid=amount_paid,
        payment_date=payment_date,
        payment_method=payment_method,
        notes=notes,
    )
    if err or payment_id is None:
        raise ValueError(err or "Failed to process debt payment")
    return payment_id
