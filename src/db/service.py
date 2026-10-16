"""AgriVoice-AI: Central Database Service (DBService).

Provides both low-level transactional primitive operations and high-level domain services:
- Low-level service:
    - Schema validation (_validate_record)
    - Strict chronological ordering check (_check_pending_update)
    - Raw & Parameterized CRUD (get_record, insert_record, update_record, delete_record)
    - Staged log processing (update_by_log_id, _set_log_to_error_status)
- High-level service:
    - Collaborator role-based access control (check_permission)
    - Specific table row CRUD with permission checks (insert_row, update_row, delete_row)
    - Voice assistant staging queue management (stage_pending_event, approve_event, reject_event)
    - Clean formatted data queries with condition builders (get_formatted_data)
    - Queue and Error auditing views (get_pending_queue, get_error_logs)
    - Virtual view overlay previewing pending changes on committed data (get_data_with_pending_overlay)
    - Clean dataset with pending changes applied sequentially (get_data_with_pending_applied)
"""

from __future__ import annotations
import copy
import json
import re
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from src.db.connection import create_connection, get_db, get_db_path

class DBService:
    """Core database service providing low-level and high-level operations for AgriVoice-AI."""

    # Table aliases and plural normalization map
    TABLE_ALIASES: Dict[str, str] = {
        "pendind_event": "pending_events",
        "pending_event": "pending_events",
        "pendind_events": "pending_events",
        "collaborator": "collaborators",
        "dictionary": "dictionary",
        "dict": "dictionary",
        "dictionaries": "dictionary",
        "zone": "zones",
        "category": "dictionary",
        "categories": "dictionary",
        "unit": "units",
        "supplier": "suppliers",
        "warehouse": "dictionary",
        "warehouses": "dictionary",
        "product": "dictionary",
        "products": "dictionary",
        "product_batch": "product_batches",
        "inventory_transaction": "inventory_transactions",
        "stock_count": "stock_counts",
        "stock_count_line": "stock_count_lines",
        "project": "projects",
        "task": "tasks",
        "subtask": "subtasks",
        "running_task": "running_tasks",
        "production_cycle": "production_cycles",
        "production_log": "production_logs",
        "harvest": "harvests",
        "yield_record": "yield_records",
        "processed_product": "processed_products",
        "processing_batch": "processing_batches",
        "transaction_category": "transaction_categories",
        "financial_transaction": "financial_transactions",
        "barter_transaction": "barter_transactions",
        "barter": "barter_transactions",
        "debt_record": "debt_records",
        "debt": "debt_records",
        "debt_payment": "debt_payments",
        "category_unit_conversion": "category_unit_conversions",
        "area": "zones",
        "issue": "issues",
        "voice_raw_log": "voice_raw_logs",
    }

    def __init__(
        self,
        db_path: Optional[Union[Path, str]] = None,
        conn: Optional[sqlite3.Connection] = None,
    ) -> None:
        """Initializes DBService with an optional database path or existing connection."""
        self.db_path = Path(db_path) if db_path else get_db_path()
        self._external_conn = conn
        self._local_conn: Optional[sqlite3.Connection] = None

    def __enter__(self) -> DBService:
        if self._external_conn is None and self._local_conn is None:
            self._local_conn = create_connection(self.db_path)
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if self._local_conn is not None:
            if exc_type is None:
                self._local_conn.commit()
            else:
                self._local_conn.rollback()
            self._local_conn.close()
            self._local_conn = None

    def _get_connection(self) -> sqlite3.Connection:
        """Returns the active database connection or creates a new one."""
        if self._external_conn is not None:
            return self._external_conn
        if self._local_conn is not None:
            return self._local_conn
        return create_connection(self.db_path)
    # --------------------------------------------------------------------------
    # Low level service
    # --------------------------------------------------------------------------

    def _get_current_timestamp(self) -> str:
        """Returns the current timestamp in ISO YYYY-MM-DD HH:MM:SS format."""
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def _normalize_table_name(self, table: str) -> str:
        """Normalizes table names and handles aliases/typos (e.g. pendind_event -> pending_events)."""
        clean_table = table.strip().lower()
        return self.TABLE_ALIASES.get(clean_table, clean_table)

    def _get_table_columns(self, conn: sqlite3.Connection, table: str) -> Dict[str, Dict[str, Any]]:
        """Retrieves column metadata for a given table via PRAGMA table_info."""
        norm_table = self._normalize_table_name(table)
        cur = conn.cursor()
        cur.execute(f"PRAGMA table_info({norm_table});")
        rows = cur.fetchall()
        cols = {}
        for r in rows:
            cols[r["name"]] = {
                "cid": r["cid"],
                "name": r["name"],
                "type": (r["type"] or "").upper(),
                "notnull": bool(r["notnull"]),
                "dflt_value": r["dflt_value"],
                "pk": bool(r["pk"]),
            }
        return cols

    def _validate_record(self, table: str, record: dict) -> Optional[str]:
        """Validates that record keys match table schema and satisfy required columns.

        Returns None if valid, or an error string if invalid.
        """
        if not isinstance(record, dict) or not record:
            return "Record must be a non-empty dictionary"

        norm_table = self._normalize_table_name(table)
        conn = self._get_connection()
        should_close = conn is not self._external_conn and conn is not self._local_conn

        try:
            cols = self._get_table_columns(conn, norm_table)
            if not cols:
                return f"Table '{norm_table}' does not exist in database"

            # Auto-sync dictionary fields if inserting into dictionary
            if norm_table == "dictionary":
                if "sku" in record and "code" not in record:
                    record["code"] = record["sku"]
                elif "code" in record and "sku" not in record:
                    record["sku"] = record["code"]
                if "entry_type" not in record:
                    if "warehouse_type" in record or ("address" in record and "root_path" not in record):
                        record["entry_type"] = "LOCATION"
                    else:
                        record["entry_type"] = "CATEGORY"

            # Check for invalid/unknown columns
            for key in record.keys():
                if key not in cols:
                    return f"Column '{key}' does not exist in table '{norm_table}'"

            # Check JSON validation for json columns
            for json_col in ("payload_json", "ai_response_json"):
                if json_col in record and record[json_col] is not None:
                    val = record[json_col]
                    if isinstance(val, str):
                        try:
                            json.loads(val)
                        except Exception as e:
                            return f"Invalid JSON string in '{json_col}': {e}"

            return None
        finally:
            if should_close:
                conn.close()

    def _extract_content_from_log(
        self, log: Union[dict, sqlite3.Row]
    ) -> Tuple[str, dict, str, str]:
        """Extracts (target_table, data_to_insert, timestamp, action_type) from a pending log."""
        if log is None:
            raise ValueError("Log record is None")

        log_dict = dict(log) if isinstance(log, sqlite3.Row) else log

        target_table = log_dict.get("target_table")
        if not target_table:
            raise ValueError("Log is missing 'target_table'")

        payload_raw = log_dict.get("payload_json")
        if isinstance(payload_raw, str):
            try:
                data_to_insert = json.loads(payload_raw)
            except Exception as e:
                raise ValueError(f"Failed to parse payload_json from log: {e}") from e
        elif isinstance(payload_raw, dict):
            data_to_insert = payload_raw
        else:
            data_to_insert = {}

        ts = log_dict.get("timestamp") or self._get_current_timestamp()
        action_type = log_dict.get("action_type") or "INSERT"

        return target_table, data_to_insert, ts, action_type

    def _set_log_to_error_status(
        self,
        log: Union[int, dict, sqlite3.Row],
        msg: str,
    ) -> Optional[dict]:
        """Sets a log record's status to 'ERROR' and stores the error_message in pending_events."""
        log_id = None
        log_dict = None

        if isinstance(log, int):
            log_id = log
        elif isinstance(log, (dict, sqlite3.Row)):
            log_dict = dict(log)
            log_dict["status"] = "ERROR"
            log_dict["error_message"] = msg
            log_id = log_dict.get("event_id") or log_dict.get("log_id")

        if log_id is not None:
            conn = self._get_connection()
            should_close = conn is not self._external_conn and conn is not self._local_conn
            try:
                cur = conn.cursor()
                cur.execute(
                    """
                    UPDATE pending_events
                    SET status = 'ERROR',
                        error_message = ?
                    WHERE event_id = ? OR log_id = ?
                    """,
                    (msg, log_id, log_id),
                )
                conn.commit()
            finally:
                if should_close:
                    conn.close()

        return log_dict

    def _set_log_to_approved_status(
        self,
        log_id: int,
        reviewer_id: Optional[int] = None,
        review_notes: Optional[str] = None,
    ) -> None:
        """Sets a log record's status to 'APPROVED', clearing error_message."""
        conn = self._get_connection()
        should_close = conn is not self._external_conn and conn is not self._local_conn
        try:
            cur = conn.cursor()
            cur.execute(
                """
                UPDATE pending_events
                SET status = 'APPROVED',
                    error_message = NULL,
                    reviewed_by = ?,
                    review_notes = ?
                WHERE event_id = ? OR log_id = ?
                """,
                (reviewer_id, review_notes, log_id, log_id),
            )
            conn.commit()
        finally:
            if should_close:
                conn.close()

    def get_record(
        self,
        table: str,
        query: Optional[str] = None,
        params: Union[Tuple[Any, ...], List[Any]] = (),
        limit: Optional[int] = 1,
        order_by: Optional[str] = None,
    ) -> Optional[Union[dict, List[dict]]]:
        """Queries records from a table with flexible query clauses, parameters, and limit."""
        norm_table = self._normalize_table_name(table)
        conn = self._get_connection()
        should_close = conn is not self._external_conn and conn is not self._local_conn

        try:
            cur = conn.cursor()
            # If a raw SELECT query was passed
            if query and query.strip().upper().startswith("SELECT"):
                clean_query = query.strip()
                if " FROM " not in clean_query.upper():
                    # Format: SELECT log_id WHERE ... -> SELECT log_id FROM {norm_table} WHERE ...
                    parts = clean_query.split("WHERE", 1)
                    select_cols = parts[0].strip()
                    where_part = f"WHERE {parts[1]}" if len(parts) > 1 else ""
                    clean_query = f"{select_cols} FROM {norm_table} {where_part}"

                # Replace double equals == with standard SQL =
                clean_query = clean_query.replace("==", "=")
                if order_by and "ORDER BY" not in clean_query.upper():
                    clean_query += f" ORDER BY {order_by}"
                if limit is not None and "LIMIT" not in clean_query.upper():
                    clean_query += f" LIMIT {limit}"
                cur.execute(clean_query, params)
            else:
                # Build standard SELECT query
                sql = f"SELECT * FROM {norm_table}"
                if query and query.strip():
                    where_part = query.strip()
                    if not where_part.upper().startswith("WHERE"):
                        where_part = f"WHERE {where_part}"
                    sql += f" {where_part.replace('==', '=')}"
                if order_by:
                    sql += f" ORDER BY {order_by}"
                if limit is not None:
                    sql += f" LIMIT {limit}"
                cur.execute(sql, params)

            rows = cur.fetchall()
            results = [dict(r) for r in rows]

            if limit == 1:
                return results[0] if results else None
            return results
        finally:
            if should_close:
                conn.close()

    def _check_pending_update(self, table: str, ts: Optional[str] = None) -> Optional[str]:
        """Enforces Strict Ordering: checks if unprocessed pending events exist before ts.

        Returns None if safe to proceed, or an error string if prior pending updates exist.
        """
        norm_table = self._normalize_table_name(table)
        # Skip check when operating directly on queue tables
        if norm_table in ("pending_events", "voice_raw_logs"):
            return None

        ts = ts or self._get_current_timestamp()

        # Query pending or error logs with earlier timestamp for the same target table
        conn = self._get_connection()
        should_close = conn is not self._external_conn and conn is not self._local_conn

        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT event_id, timestamp, status, summary_text
                FROM pending_events
                WHERE target_table = ?
                  AND timestamp < ?
                  AND status IN ('PENDING', 'ERROR')
                ORDER BY timestamp ASC, event_id ASC
                LIMIT 1
                """,
                (norm_table, ts),
            )
            row = cur.fetchone()
            if row:
                return (
                    f"Process pending before insert new: Sự kiện #{row['event_id']} ({row['timestamp']}) "
                    f"đang ở trạng thái '{row['status']}' trên bảng '{norm_table}' cần được xử lý trước."
                )
            return None
        finally:
            if should_close:
                conn.close()

    def insert_record(
        self,
        table: str,
        record: dict,
        ts: Optional[str] = None,
        check_pending: bool = True,
    ) -> Optional[str]:
        """Inserts a record into the target table with schema and pending queue validation.

        Returns None on success, or an error string on failure.
        """
        norm_table = self._normalize_table_name(table)
        if norm_table == "production_logs" and (not record.get("cycle_id")):
            active_c = self.get_record("production_cycles", "status = 'ACTIVE'", limit=1)
            if not active_c:
                active_c = self.get_record("production_cycles", limit=1)
            if active_c:
                record["cycle_id"] = active_c["cycle_id"]
            else:
                c_conn = self._get_connection()
                try:
                    c_cur = c_conn.cursor()
                    c_cur.execute("SELECT zone_id FROM zones LIMIT 1;")
                    zr = c_cur.fetchone()
                    zid = zr[0] if zr else "ZONE_A"
                    if not zr:
                        c_cur.execute("INSERT OR IGNORE INTO zones (zone_id, zone_name) VALUES ('ZONE_A', 'Khu Mặc Định');")
                    c_cur.execute("INSERT INTO production_cycles (zone_id, name, subject_name, start_date, status) VALUES (?, 'Vụ Canh Tác Mặc Định', 'Chung', date('now'), 'ACTIVE');", (zid,))
                    c_conn.commit()
                    record["cycle_id"] = c_cur.lastrowid
                finally:
                    if c_conn is not self._external_conn and c_conn is not self._local_conn:
                        c_conn.close()
        elif norm_table == "issues" and (not record.get("zone_id")):
            c_conn = self._get_connection()
            try:
                c_cur = c_conn.cursor()
                c_cur.execute("SELECT zone_id FROM zones LIMIT 1;")
                zr = c_cur.fetchone()
                if not zr:
                    c_cur.execute("INSERT OR IGNORE INTO zones (zone_id, zone_name) VALUES ('ZONE_A', 'Khu Mặc Định');")
                    record["zone_id"] = "ZONE_A"
                else:
                    record["zone_id"] = zr[0]
                c_conn.commit()
            finally:
                if c_conn is not self._external_conn and c_conn is not self._local_conn:
                    c_conn.close()
        error = self._validate_record(norm_table, record)
        if error:
            return error

        # 2. Strict Ordering Validation
        if check_pending and norm_table != "pending_events":
            error = self._check_pending_update(norm_table, ts)
            if error:
                return error

        # 3. Execution
        conn = self._get_connection()
        should_close = conn is not self._external_conn and conn is not self._local_conn

        try:
            cur = conn.cursor()
            cols = list(record.keys())
            placeholders = ", ".join(["?"] * len(cols))
            col_names = ", ".join(cols)
            sql = f"INSERT INTO {norm_table} ({col_names}) VALUES ({placeholders})"
            cur.execute(sql, [record[c] for c in cols])
            conn.commit()
            return None
        except Exception as e:
            conn.rollback()
            return str(e)
        finally:
            if should_close:
                conn.close()

    def update_record(self, table: str, record: dict, where: dict) -> Optional[str]:
        """Updates records in table matching where conditions.

        Returns None on success, or an error string on failure.
        """
        norm_table = self._normalize_table_name(table)
        if not record or not where:
            return "Both 'record' and 'where' must be non-empty dictionaries"

        conn = self._get_connection()
        should_close = conn is not self._external_conn and conn is not self._local_conn

        try:
            cur = conn.cursor()
            set_clause = ", ".join([f"{k} = ?" for k in record.keys()])
            where_clause = " AND ".join([f"{k} = ?" for k in where.keys()])
            sql = f"UPDATE {norm_table} SET {set_clause} WHERE {where_clause}"
            values = list(record.values()) + list(where.values())
            cur.execute(sql, values)
            conn.commit()
            return None
        except Exception as e:
            conn.rollback()
            return str(e)
        finally:
            if should_close:
                conn.close()

    def delete_record(self, table: str, where: dict) -> Optional[str]:
        """Deletes records from table matching where conditions.

        Returns None on success, or an error string on failure.
        """
        norm_table = self._normalize_table_name(table)
        if not where:
            return "'where' condition cannot be empty for delete"

        conn = self._get_connection()
        should_close = conn is not self._external_conn and conn is not self._local_conn

        try:
            cur = conn.cursor()
            where_clause = " AND ".join([f"{k} = ?" for k in where.keys()])
            sql = f"DELETE FROM {norm_table} WHERE {where_clause}"
            cur.execute(sql, list(where.values()))
            conn.commit()
            return None
        except Exception as e:
            conn.rollback()
            return str(e)
        finally:
            if should_close:
                conn.close()

    def update_by_log_id(
        self,
        log_id: int,
        reviewer_id: Optional[int] = None,
        review_notes: Optional[str] = None,
    ) -> Optional[str]:
        """Approves and executes a pending log event onto its target table atomically.

        On failure: updates log status to 'ERROR', records error_message, and returns error.
        On success: updates log status to 'APPROVED', clears error_message, and returns None.
        """
        # Fetch log record
        log = self.get_record("pending_events", "event_id = ? OR log_id = ?", (log_id, log_id), limit=1)
        if not log:
            return f"Log #{log_id} not found in pending_events"

        if log["status"] == "APPROVED":
            return f"Log #{log_id} has already been APPROVED"

        event_id = log["event_id"]

        try:
            target_table, data_to_insert, ts, action_type = self._extract_content_from_log(log)
        except Exception as e:
            err = f"Failed to parse log payload: {e}"
            self._set_log_to_error_status(event_id, err)
            return err

        # Check strict ordering among pending events
        order_error = self._check_pending_update(target_table, ts)
        if order_error:
            # If the blocking event is not this event itself
            conn = self._get_connection()
            should_close = conn is not self._external_conn and conn is not self._local_conn
            try:
                cur = conn.cursor()
                cur.execute(
                    """
                    SELECT event_id FROM pending_events
                    WHERE target_table = ? AND timestamp < ? AND status IN ('PENDING', 'ERROR') AND event_id != ?
                    LIMIT 1
                    """,
                    (target_table, ts, event_id),
                )
                earlier = cur.fetchone()
                if earlier:
                    err = f"Process pending before insert new: Cần duyệt sự kiện #{earlier['event_id']} trước."
                    self._set_log_to_error_status(event_id, err)
                    return err
            finally:
                if should_close:
                    conn.close()

        # Atomic apply
        error = None
        if action_type == "INSERT":
            error = self.insert_record(target_table, data_to_insert, ts=ts, check_pending=False)
        elif action_type == "UPDATE":
            if "where" in data_to_insert and "data" in data_to_insert:
                error = self.update_record(target_table, data_to_insert["data"], data_to_insert["where"])
            else:
                pk_col = f"{target_table.rstrip('s')}_id"
                if pk_col in data_to_insert:
                    pk_val = data_to_insert[pk_col]
                    data_part = {k: v for k, v in data_to_insert.items() if k != pk_col}
                    where_part = {pk_col: pk_val}
                    error = self.update_record(target_table, data_part, where_part)
                else:
                    error = "UPDATE payload must contain primary key or 'where'/'data' blocks"
        elif action_type == "DELETE":
            error = self.delete_record(target_table, data_to_insert)
        else:
            error = f"Unsupported action_type: {action_type}"

        if error:
            self._set_log_to_error_status(event_id, error)
            return error

        # Success: mark as APPROVED
        self._set_log_to_approved_status(event_id, reviewer_id=reviewer_id, review_notes=review_notes)
        return None

    # --------------------------------------------------------------------------
    # High level service
    # --------------------------------------------------------------------------

    def check_permission(
        self,
        telegram_id: str,
        action: str = "PUSH",
    ) -> Tuple[bool, Optional[str]]:
        """Validates collaborator permissions based on role and active status.

        Roles:
        - OWNER / ADMIN: All privileges (PUSH, APPROVE, REJECT, INSERT, UPDATE, DELETE, READ).
        - WORKER: Can stage voice events, report issues, and log daily activities. Cannot approve.
        - VIEWER: Read-only access.
        """
        conn = self._get_connection()
        should_close = conn is not self._external_conn and conn is not self._local_conn

        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT collaborator_id, full_name, role, is_active
                FROM collaborators
                WHERE telegram_id = ?
                """,
                (str(telegram_id),),
            )
            collab = cur.fetchone()
            if not collab:
                return False, f"Telegram ID '{telegram_id}' chưa được đăng ký trong hệ thống cộng tác viên."

            if not collab["is_active"]:
                return False, f"Tài khoản của '{collab['full_name']}' đang bị khóa (is_active = 0)."

            role = collab["role"]
            action_upper = action.upper()

            # READ action is permitted for all active collaborators
            if action_upper in ("READ", "GET", "VIEW"):
                return True, None

            # STAGE action (voice logs) permitted for WORKER, ADMIN, OWNER
            if action_upper in ("STAGE", "VOICE", "LOG"):
                return True, None

            # OWNER and ADMIN have full access
            if role in ("OWNER", "ADMIN"):
                return True, None

            # WORKER has limited push access
            if role == "WORKER":
                if action_upper in ("APPROVE", "REJECT", "DIRECT_DELETE", "CLOSE_ISSUE", "RESOLVE_ISSUE"):
                    return False, f"Vai trò '{role}' không có quyền phê duyệt hoặc thực hiện hành động '{action}'."
                return True, None

            # VIEWER has no write permissions
            return False, f"Vai trò VIEWER chỉ có quyền xem, không được phép thực hiện hành động '{action}'."
        finally:
            if should_close:
                conn.close()

    def stage_pending_event(
        self,
        sender_id: str,
        target_table: str,
        action_type: str,
        payload: Union[dict, str],
        audio_path: Optional[str] = None,
        raw_transcript: str = "",
        summary_text: Optional[str] = None,
        detected_intent: Optional[str] = None,
        ai_response_json: Optional[str] = None,
        timestamp: Optional[str] = None,
    ) -> Tuple[Optional[int], Optional[str]]:
        """Stages an incoming AI-transcribed voice event into pending_events."""
        # 1. Check sender permission
        can_stage, reason = self.check_permission(sender_id, action="STAGE")
        if not can_stage:
            return None, reason

        norm_table = self._normalize_table_name(target_table)
        payload_str = json.dumps(payload, ensure_ascii=False) if isinstance(payload, dict) else payload

        conn = self._get_connection()
        should_close = conn is not self._external_conn and conn is not self._local_conn

        try:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO pending_events (
                    sender_id, target_table, action_type, payload_json,
                    audio_path, raw_transcript, summary_text, timestamp, status
                ) VALUES (
                    ?, ?, ?, ?,
                    ?, ?, ?, COALESCE(?, CURRENT_TIMESTAMP), 'PENDING'
                )
                """,
                (
                    str(sender_id),
                    norm_table,
                    action_type.upper(),
                    payload_str,
                    audio_path,
                    raw_transcript,
                    summary_text,
                    timestamp,
                ),
            )
            event_id = cur.lastrowid

            cur.execute(
                "UPDATE pending_events SET log_id = ? WHERE event_id = ?",
                (event_id, event_id),
            )

            conn.commit()
            return event_id, None
        except Exception as e:
            conn.rollback()
            return None, str(e)
        finally:
            if should_close:
                conn.close()

    def approve_event(
        self,
        log_id: int,
        reviewer_telegram_id: Optional[str] = None,
        review_notes: Optional[str] = None,
    ) -> Tuple[bool, Optional[str]]:
        """Approves a pending event with reviewer permission checking."""
        reviewer_id = None
        if reviewer_telegram_id:
            can_approve, reason = self.check_permission(reviewer_telegram_id, action="APPROVE")
            if not can_approve:
                return False, reason

            collab = self.get_record("collaborators", "telegram_id = ?", (str(reviewer_telegram_id),), limit=1)
            if collab:
                reviewer_id = collab["collaborator_id"]

        error = self.update_by_log_id(log_id, reviewer_id=reviewer_id, review_notes=review_notes)
        if error:
            return False, error
        return True, None

    def reject_event(
        self,
        log_id: int,
        reviewer_telegram_id: Optional[str] = None,
        review_notes: Optional[str] = None,
    ) -> Tuple[bool, Optional[str]]:
        """Rejects a pending event without deleting it (Audit Trail preserved)."""
        reviewer_id = None
        if reviewer_telegram_id:
            can_reject, reason = self.check_permission(reviewer_telegram_id, action="REJECT")
            if not can_reject:
                return False, reason

            collab = self.get_record("collaborators", "telegram_id = ?", (str(reviewer_telegram_id),), limit=1)
            if collab:
                reviewer_id = collab["collaborator_id"]

        conn = self._get_connection()
        should_close = conn is not self._external_conn and conn is not self._local_conn

        try:
            cur = conn.cursor()
            cur.execute(
                """
                UPDATE pending_events
                SET status = 'REJECTED',
                    reviewed_by = ?,
                    review_notes = ?
                WHERE (event_id = ? OR log_id = ?) AND status IN ('PENDING', 'ERROR')
                """,
                (reviewer_id, review_notes, log_id, log_id),
            )
            if cur.rowcount == 0:
                return False, f"Event #{log_id} không tồn tại hoặc không ở trạng thái PENDING/ERROR."
            conn.commit()
            return True, None
        except Exception as e:
            conn.rollback()
            return False, str(e)
        finally:
            if should_close:
                conn.close()

    def insert_row(
        self,
        table: str,
        data: dict,
        sender_id: Optional[str] = None,
        ts: Optional[str] = None,
    ) -> Tuple[Optional[int], Optional[str]]:
        """Inserts a row into a specific table with optional collaborator permission check."""
        if sender_id:
            can_push, reason = self.check_permission(sender_id, action="PUSH")
            if not can_push:
                return None, reason

        norm_table = self._normalize_table_name(table)

        # 1. Schema Validation
        error = self._validate_record(norm_table, data)
        if error:
            return None, error

        # 2. Strict Ordering Validation
        if norm_table != "pending_events":
            error = self._check_pending_update(norm_table, ts)
            if error:
                return None, error

        # 3. Execution on connection
        conn = self._get_connection()
        should_close = conn is not self._external_conn and conn is not self._local_conn
        try:
            cur = conn.cursor()
            cols = list(data.keys())
            placeholders = ", ".join(["?"] * len(cols))
            col_names = ", ".join(cols)
            sql = f"INSERT INTO {norm_table} ({col_names}) VALUES ({placeholders})"
            cur.execute(sql, [data[c] for c in cols])
            row_id = cur.lastrowid
            conn.commit()
            return row_id, None
        except Exception as e:
            conn.rollback()
            return None, str(e)
        finally:
            if should_close:
                conn.close()

    def update_row(
        self,
        table: str,
        data: dict,
        where: dict,
        sender_id: Optional[str] = None,
    ) -> Tuple[int, Optional[str]]:
        if sender_id:
            can_push, reason = self.check_permission(sender_id, action="PUSH")
            if not can_push:
                return 0, reason

        norm_table = self._normalize_table_name(table)
        error = self.update_record(norm_table, data, where)
        if error:
            return 0, error
        return 1, None

    def delete_row(
        self,
        table: str,
        where: dict,
        sender_id: Optional[str] = None,
    ) -> Tuple[int, Optional[str]]:
        """Deletes rows in a specific table with optional collaborator permission check."""
        if sender_id:
            can_delete, reason = self.check_permission(sender_id, action="DIRECT_DELETE")
            if not can_delete:
                return 0, reason

        norm_table = self._normalize_table_name(table)
        error = self.delete_record(norm_table, where)
        if error:
            return 0, error
        return 1, None

    def get_formatted_data(
        self,
        table: str,
        conditions: Optional[Dict[str, Any]] = None,
        limit: Optional[int] = None,
        order_by: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Fetches and formats records from a table with condition filtering."""
        norm_table = self._normalize_table_name(table)
        where_clauses = []
        params: List[Any] = []

        if conditions:
            for k, v in conditions.items():
                if v is None:
                    where_clauses.append(f"{k} IS NULL")
                else:
                    where_clauses.append(f"{k} = ?")
                    params.append(v)

        where_sql = " AND ".join(where_clauses) if where_clauses else None
        res = self.get_record(norm_table, query=where_sql, params=params, limit=limit, order_by=order_by)

        if res is None:
            return []
        if isinstance(res, dict):
            return [res]
        return res

    def get_pending_queue(
        self,
        target_table: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Returns all events currently awaiting approval ordered by timestamp ASC."""
        conds = {"target_table": self._normalize_table_name(target_table)} if target_table else None
        return self.get_formatted_data("v_pending_events_queue", conditions=conds, limit=limit)

    def get_error_logs(
        self,
        target_table: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Returns all events in ERROR status for owner inspection and diagnosis."""
        conds = {"target_table": self._normalize_table_name(target_table)} if target_table else None
        return self.get_formatted_data("v_pending_events_errors", conditions=conds, limit=limit)

    def get_data_with_pending_overlay(
        self,
        table: str,
        conditions: Optional[Dict[str, Any]] = None,
        apply_pending: bool = False,
    ) -> Dict[str, Any]:
        """Provides a virtual overlay combining committed table data with unapproved pending changes.

        If apply_pending is True, applies unapproved changes directly onto committed_data.
        """
        if apply_pending:
            return self.get_data_with_pending_applied(table, conditions=conditions)

        norm_table = self._normalize_table_name(table)
        committed = self.get_formatted_data(norm_table, conditions=conditions)
        pending = self.get_pending_queue(target_table=norm_table)

        return {
            "target_table": norm_table,
            "committed_count": len(committed),
            "pending_count": len(pending),
            "committed_data": committed,
            "pending_overlays": pending,
        }

    def verify_strict_ordering(self, event_id: int) -> Tuple[bool, Optional[str]]:
        """Verifies that no earlier PENDING or ERROR event exists before event_id."""
        conn = self._get_connection()
        should_close = conn is not self._external_conn and conn is not self._local_conn
        try:
            cur = conn.cursor()
            cur.execute("SELECT event_id, timestamp FROM pending_events WHERE event_id = ?;", (event_id,))
            target = cur.fetchone()
            if not target:
                return False, f"Event #{event_id} does not exist."

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
                return (
                    False,
                    f"Bắt buộc duyệt tuần tự: Sự kiện #{earlier['event_id']} ({earlier['timestamp']}) "
                    f"phải được xử lý trước sự kiện #{event_id} ({target['timestamp']}).",
                )
            return True, None
        finally:
            if should_close:
                conn.close()

    def update_pending_event_payload(
        self,
        event_id: int,
        payload: Union[dict, str],
        reset_status_to_pending: bool = True,
    ) -> Tuple[bool, Optional[str]]:
        """Updates the payload_json of an event and optionally resets its status to PENDING."""
        payload_json = json.dumps(payload, ensure_ascii=False) if isinstance(payload, dict) else payload
        conn = self._get_connection()
        should_close = conn is not self._external_conn and conn is not self._local_conn
        try:
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
            if cur.rowcount == 0:
                return False, f"Event #{event_id} not found"
            conn.commit()
            return True, None
        except Exception as e:
            conn.rollback()
            return False, str(e)
        finally:
            if should_close:
                conn.close()

    def approve_pending_event(
        self,
        event_id: int,
        reviewer_telegram_id: Optional[str] = None,
        reviewer_id: Optional[int] = None,
        review_notes: Optional[str] = None,
        enforce_order: bool = True,
    ) -> Tuple[bool, Optional[str]]:
        """Approves a pending event with optional strict ordering and reviewer verification."""
        r_id = reviewer_id
        if reviewer_telegram_id:
            can_approve, reason = self.check_permission(reviewer_telegram_id, action="APPROVE")
            if not can_approve:
                return False, reason
            collab = self.get_record("collaborators", "telegram_id = ?", (str(reviewer_telegram_id),), limit=1)
            if collab:
                r_id = collab["collaborator_id"]

        if enforce_order:
            valid, err = self.verify_strict_ordering(event_id)
            if not valid:
                return False, err

        error = self.update_by_log_id(event_id, reviewer_id=r_id, review_notes=review_notes)
        if error:
            return False, error
        return True, None

    def reject_pending_event(
        self,
        event_id: int,
        reviewer_telegram_id: Optional[str] = None,
        reviewer_id: Optional[int] = None,
        review_notes: Optional[str] = None,
    ) -> Tuple[bool, Optional[str]]:
        """Rejects a pending event without deleting it (Audit Trail preserved)."""
        return self.reject_event(event_id, reviewer_telegram_id=reviewer_telegram_id, review_notes=review_notes)

    @staticmethod
    def _parse_time_delta_days(delta_str: Optional[str], default_days: int = 1) -> int:
        """Parses duration string like '1 day', '7 days', '2 weeks', '1 month' into total days."""
        if not delta_str:
            return default_days
        s = str(delta_str).strip().lower()
        m = re.match(r"^(\d+)\s*(day|d|ngay|ngày|week|w|tuan|tuần|month|m|thang|tháng|hour|h|gio|giờ)?", s)
        if not m:
            return default_days
        val = int(m.group(1))
        unit = (m.group(2) or "day").lower()
        if unit in ("week", "w", "tuan", "tuần"):
            return val * 7
        elif unit in ("month", "m", "thang", "tháng"):
            return val * 30
        elif unit in ("hour", "h", "gio", "giờ"):
            return max(1, val // 24)
        return val

    def build_running_tasks_for_cycle(
        self, cycle_id: int, clear_existing: bool = False, sender_id: Optional[str] = None
    ) -> Tuple[int, Optional[str]]:
        """Generates running_tasks from SOP templates (tasks, subtasks) for a production cycle."""
        if sender_id:
            can_build, reason = self.check_permission(sender_id, action="PUSH")
            if not can_build:
                return 0, reason

        cycle = self.get_record("production_cycles", "cycle_id = ?", (cycle_id,), limit=1)
        if not cycle:
            return 0, f"Cycle #{cycle_id} not found"

        project_id = cycle.get("project_id")
        if not project_id:
            return 0, f"Cycle #{cycle_id} does not have an associated project_id"

        base_date_str = cycle.get("start_date") or cycle.get("created_at") or self._get_current_timestamp()
        try:
            base_date = datetime.strptime(str(base_date_str)[:10], "%Y-%m-%d")
        except Exception:
            base_date = datetime.now()

        tasks = self.get_formatted_data("tasks", {"project_id": project_id, "is_active": 1})
        if not tasks:
            return 0, None

        conn = self._get_connection()
        should_close = conn is not self._external_conn and conn is not self._local_conn
        created_count = 0

        try:
            cur = conn.cursor()
            if clear_existing:
                cur.execute("DELETE FROM running_tasks WHERE cycle_id = ? AND status = 'TODO';", (cycle_id,))

            for t in tasks:
                t_id = t["task_id"]
                delay_days = self._parse_time_delta_days(t.get("delay"), 0)
                last_days = self._parse_time_delta_days(t.get("last"), 90)
                time_delta_days = max(1, self._parse_time_delta_days(t.get("time_delta"), 1))

                subtasks = self.get_formatted_data(
                    "subtasks", {"task_id": t_id, "is_active": 1}, order_by="sort_order ASC"
                )

                current_day_offset = delay_days
                while current_day_offset <= last_days:
                    step_date = base_date + timedelta(days=current_day_offset)
                    step_date_str = step_date.strftime("%Y-%m-%d")

                    if subtasks:
                        for st in subtasks:
                            open_time = st.get("open_at") or "05:00:00"
                            scheduled_start = f"{step_date_str} {str(open_time)[:8]}"
                            name = f"{t.get('title') or t.get('name')} - {st.get('title') or st.get('name')}"
                            cur.execute(
                                """
                                INSERT INTO running_tasks (
                                    cycle_id, project_id, task_id, subtask_id,
                                    name, description, scheduled_start, duration_minutes, status
                                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'TODO');
                                """,
                                (
                                    cycle_id,
                                    project_id,
                                    t_id,
                                    st["subtask_id"],
                                    name,
                                    st.get("description"),
                                    scheduled_start,
                                    st.get("duration_minutes") or 30,
                                ),
                            )
                            created_count += 1
                    else:
                        scheduled_start = f"{step_date_str} 06:00:00"
                        name = str(t.get("title") or t.get("name"))
                        cur.execute(
                            """
                            INSERT INTO running_tasks (
                                cycle_id, project_id, task_id,
                                name, description, scheduled_start, duration_minutes, status
                            ) VALUES (?, ?, ?, ?, ?, ?, 30, 'TODO');
                            """,
                            (
                                cycle_id,
                                project_id,
                                t_id,
                                name,
                                t.get("description"),
                                scheduled_start,
                            ),
                        )
                        created_count += 1

                    current_day_offset += time_delta_days

            conn.commit()
            return created_count, None
        except Exception as e:
            conn.rollback()
            return 0, str(e)
        finally:
            if should_close:
                conn.close()

    def create_adhoc_task(
        self,
        name: str,
        cycle_id: Optional[int] = None,
        project_id: Optional[int] = None,
        assigned_to: Optional[int] = None,
        scheduled_start: Optional[str] = None,
        duration_minutes: int = 30,
        description: Optional[str] = None,
        sender_id: Optional[str] = None,
    ) -> Tuple[Optional[int], Optional[str]]:
        """Quick ad-hoc task creation for day-to-day farm operations."""
        if sender_id:
            can_push, reason = self.check_permission(sender_id, action="PUSH")
            if not can_push:
                return None, reason

        data = {
            "name": name,
            "cycle_id": cycle_id,
            "project_id": project_id,
            "assigned_to": assigned_to,
            "scheduled_start": scheduled_start or self._get_current_timestamp(),
            "duration_minutes": duration_minutes,
            "description": description,
            "status": "TODO",
        }
        return self.insert_row("running_tasks", data)

    def complete_running_task(
        self,
        running_task_id: int,
        worker_telegram_id: Optional[str] = None,
        material_category_id: Optional[int] = None,
        quantity_used: Optional[float] = None,
        material_unit: Optional[str] = None,
        completion_notes: Optional[str] = None,
        warehouse_id: Optional[int] = None,
    ) -> Tuple[bool, Optional[str]]:
        """Marks running_task as DONE and automatically issues materials from inventory if specified."""
        task = self.get_record("running_tasks", "running_task_id = ?", (running_task_id,), limit=1)
        if not task:
            return False, f"Running task #{running_task_id} not found"

        conn = self._get_connection()
        should_close = conn is not self._external_conn and conn is not self._local_conn
        try:
            cur = conn.cursor()
            inv_tx_id = None
            if material_category_id and quantity_used and quantity_used > 0:
                item_name = f"Vật tư task #{running_task_id}"
                cat = self.get_record("categories", "category_id = ?", (material_category_id,), limit=1)
                unit_id = cat.get("default_unit_id") if cat else None
                if cat and cat.get("name"):
                    item_name = cat["name"]

                if not unit_id:
                    existing_u = self.get_record("units", limit=1)
                    if existing_u:
                        unit_id = existing_u["unit_id"]
                    else:
                        cur.execute("INSERT INTO units (code, name) VALUES ('UNIT_DEFAULT', 'Đơn vị mặc định');")
                        unit_id = cur.lastrowid

                wh_id = None
                if warehouse_id is not None:
                    wh = self.get_record("warehouses", "warehouse_id = ?", (warehouse_id,), limit=1)
                    if wh:
                        wh_id = wh["warehouse_id"]
                    else:
                        wh_dict = self.get_record("dictionary", "dict_id = ?", (warehouse_id,), limit=1)
                        if wh_dict:
                            wh_id = wh_dict["dict_id"]

                factor = 1.0
                conv = self.get_record(
                    "category_unit_conversions",
                    "category_id = ? AND unit_id = ?",
                    (material_category_id, unit_id),
                    limit=1,
                )
                if conv:
                    factor = float(conv.get("factor_to_base") or 1.0)
                qty_base = float(quantity_used) * factor

                cur.execute(
                    """
                    INSERT INTO inventory_transactions (
                        item_name, category_id, warehouse_id, cycle_id,
                        transaction_type, quantity_change, unit_id, quantity_base,
                        reference_type, reference_note, status
                    ) VALUES (?, ?, ?, ?, 'ISSUE', ?, ?, ?, 'TASK_EXECUTION', ?, 'POSTED');
                    """,
                    (
                        item_name,
                        material_category_id,
                        wh_id,
                        task.get("cycle_id"),
                        -abs(float(quantity_used)),
                        unit_id,
                        qty_base,
                        f"Tiêu hao cho task: {task.get('name')}",
                    ),
                )
                inv_tx_id = cur.lastrowid
            now_ts = self._get_current_timestamp()
            cur.execute(
                """
                UPDATE running_tasks
                SET status = 'DONE',
                    report_complete_at = ?,
                    material_category_id = COALESCE(?, material_category_id),
                    quantity_used = COALESCE(?, quantity_used),
                    material_unit = COALESCE(?, material_unit),
                    inventory_transaction_id = COALESCE(?, inventory_transaction_id),
                    completion_notes = COALESCE(?, completion_notes)
                WHERE running_task_id = ?;
                """,
                (
                    now_ts,
                    material_category_id,
                    quantity_used,
                    material_unit,
                    inv_tx_id,
                    completion_notes,
                    running_task_id,
                ),
            )
            conn.commit()
            return True, None
        except Exception as e:
            conn.rollback()
            return False, str(e)
        finally:
            if should_close:
                conn.close()

    def check_resource_locks(
        self, target_ids: Union[List[str], str], task_id: Optional[int] = None
    ) -> Tuple[bool, Optional[str]]:
        """Checks for local or global lock conflicts on target entities."""
        targets = [
            t.strip()
            for t in (target_ids if isinstance(target_ids, list) else str(target_ids).split(","))
            if t.strip()
        ]
        if not targets:
            return False, None

        running = self.get_formatted_data("running_tasks", {"status": "IN_PROGRESS"})
        if not running:
            return False, None

        for r in running:
            st_id = r.get("subtask_id")
            if not st_id:
                continue
            st = self.get_record("subtasks", "subtask_id = ?", (st_id,), limit=1)
            if not st:
                continue

            st_targets_raw = st.get("target_ids") or "[]"
            try:
                st_targets = json.loads(st_targets_raw) if isinstance(st_targets_raw, str) else st_targets_raw
            except Exception:
                st_targets = []

            overlap = set(targets).intersection(set(st_targets))
            if overlap:
                target_str = ", ".join(overlap)
                if st.get("glock") == 1:
                    return True, f"Global Lock: Đối tượng [{target_str}] đang bị khóa toàn cục bởi task '{r.get('name')}'"
                if st.get("lock") == 1 and task_id is not None and r.get("task_id") == task_id:
                    return True, f"Local Lock: Đối tượng [{target_str}] đang bị khóa nội bộ bởi subtask '{r.get('name')}'"

        return False, None

    def manage_issue(
        self,
        issue_id: int,
        action: str,
        resolution_notes: Optional[str] = None,
        notes: Optional[str] = None,
        reviewer_telegram_id: Optional[str] = None,
    ) -> Tuple[bool, Optional[str]]:
        """Updates issue status and resolution notes, enforcing Admin role for resolution/closure."""
        action_upper = action.upper()
        if action_upper in ("CLOSE", "CLOSED", "RESOLVE", "RESOLVED"):
            if reviewer_telegram_id:
                can_close, reason = self.check_permission(reviewer_telegram_id, action="CLOSE_ISSUE")
                if not can_close:
                    return False, f"Chỉ chủ vườn / quản lý mới có quyền nghiệm thu và đóng sự cố: {reason}"

        issue = self.get_record("issues", "issue_id = ?", (issue_id,), limit=1)
        if not issue:
            return False, f"Issue #{issue_id} not found"

        now_ts = self._get_current_timestamp()
        new_status = (
            "CLOSED"
            if action_upper in ("CLOSE", "CLOSED")
            else (
                "RESOLVED"
                if action_upper in ("RESOLVE", "RESOLVED")
                else ("IN_PROGRESS" if action_upper in ("IN_PROGRESS", "START") else issue.get("status", "OPEN"))
            )
        )
        closed_at = now_ts if new_status in ("CLOSED", "RESOLVED") else None

        conn = self._get_connection()
        should_close = conn is not self._external_conn and conn is not self._local_conn
        try:
            cur = conn.cursor()
            cur.execute(
                """
                UPDATE issues
                SET status = ?,
                    closed_at = COALESCE(?, closed_at),
                    resolution_notes = COALESCE(?, resolution_notes),
                    notes = COALESCE(?, notes),
                    updated_at = ?
                WHERE issue_id = ?;
                """,
                (
                    new_status,
                    closed_at,
                    resolution_notes,
                    notes,
                    now_ts,
                    issue_id,
                ),
            )
            conn.commit()
            return True, None
        except Exception as e:
            conn.rollback()
            return False, str(e)
        finally:
            if should_close:
                conn.close()

    def record_inventory_transaction(
        self,
        item_name: str,
        category_id: int,
        transaction_type: str = "RECEIPT",
        quantity_change: float = 0.0,
        warehouse_id: Optional[int] = None,
        unit_id: Optional[int] = None,
        batch_id: Optional[int] = None,
        supplier_id: Optional[int] = None,
        cycle_id: Optional[int] = None,
        unit_price_vnd: int = 0,
        is_price_estimated: int = 0,
        status: str = "POSTED",
        sender_id: Optional[str] = None,
    ) -> Tuple[Optional[int], Optional[str]]:
        """Records an inventory transaction with unit conversion and auto-batch handling."""
        if sender_id:
            can_push, reason = self.check_permission(sender_id, action="PUSH")
            if not can_push:
                return None, reason

        u = self.get_record("units", "unit_id = ?", (unit_id,), limit=1) if unit_id else None
        if u:
            u_id = u["unit_id"]
        else:
            existing_u = self.get_record("units", limit=1)
            if existing_u:
                u_id = existing_u["unit_id"]
            else:
                u_id, _ = self.insert_row("units", {"code": "KG_DEF", "name": "Kilogram"})

        wh_id = None
        if warehouse_id is not None:
            wh = self.get_record("warehouses", "warehouse_id = ?", (warehouse_id,), limit=1)
            if wh:
                wh_id = wh["warehouse_id"]
            else:
                wh_dict = self.get_record("dictionary", "dict_id = ?", (warehouse_id,), limit=1)
                if wh_dict:
                    wh_id = wh_dict["dict_id"]

        factor = 1.0
        conv = self.get_record(
            "category_unit_conversions",
            "category_id = ? AND unit_id = ?",
            (category_id, u_id),
            limit=1,
        )
        if conv:
            factor = float(conv.get("factor_to_base") or 1.0)
        qty_base = abs(float(quantity_change)) * factor

        b_id = batch_id
        if b_id is None:
            if wh_id is not None:
                existing_batch = self.get_record(
                    "product_batches",
                    "category_id = ? AND warehouse_id = ?",
                    (category_id, wh_id),
                    limit=1,
                )
            else:
                existing_batch = self.get_record(
                    "product_batches",
                    "category_id = ? AND warehouse_id IS NULL",
                    (category_id,),
                    limit=1,
                )
            if existing_batch:
                b_id = existing_batch.get("batch_id")
            else:
                date_str = datetime.now().strftime("%Y%m%d")
                batch_code = f"CAT_{category_id}-WH_{wh_id or 'NONE'}-{date_str}"
                res_b, err_b = self.insert_row(
                    "product_batches",
                    {
                        "batch_code": batch_code,
                        "category_id": category_id,
                        "warehouse_id": wh_id,
                        "supplier_id": supplier_id,
                        "base_unit_id": u_id,
                        "quantity_remaining": 0.0,
                    },
                )
                if not err_b and res_b:
                    b_id = res_b

        data = {
            "item_name": item_name,
            "category_id": category_id,
            "warehouse_id": wh_id,
            "batch_id": b_id,
            "transaction_type": transaction_type.upper(),
            "quantity_change": quantity_change,
            "unit_id": u_id,
            "quantity_base": qty_base,
            "unit_price_vnd": unit_price_vnd,
            "is_price_estimated": is_price_estimated,
            "supplier_id": supplier_id,
            "cycle_id": cycle_id,
            "status": status.upper(),
        }
        return self.insert_row("inventory_transactions", data)

    def reconcile_batches_and_stock(
        self, warehouse_id: Optional[int] = None, category_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Returns stock summary highlighting negative stock or depletion anomalies."""
        conds = {}
        if warehouse_id is not None:
            conds["warehouse_id"] = warehouse_id
        if category_id is not None:
            conds["category_id"] = category_id
        return self.get_formatted_data("v_inventory_root_summary", conditions=conds or None)

    def record_financial_transaction(
        self,
        category_id: int,
        type: str,
        amount: int,
        transaction_date: Optional[str] = None,
        cycle_id: Optional[int] = None,
        supplier_id: Optional[int] = None,
        partner_name: Optional[str] = None,
        payment_method: str = "CASH",
        status: str = "COMPLETED",
        invoice_image_path: Optional[str] = None,
        inventory_transaction_id: Optional[int] = None,
        notes: Optional[str] = None,
        sender_id: Optional[str] = None,
    ) -> Tuple[Optional[int], Optional[str]]:
        """Records a financial transaction ensuring integer-based currency."""
        if sender_id:
            can_push, reason = self.check_permission(sender_id, action="PUSH")
            if not can_push:
                return None, reason

        if amount < 0:
            return None, "Amount must be a non-negative integer"

        data = {
            "category_id": category_id,
            "type": type.upper(),
            "amount": int(amount),
            "transaction_date": transaction_date or datetime.now().strftime("%Y-%m-%d"),
            "cycle_id": cycle_id,
            "supplier_id": supplier_id,
            "partner_name": partner_name,
            "payment_method": payment_method.upper(),
            "status": status.upper(),
            "invoice_image_path": invoice_image_path,
            "inventory_transaction_id": inventory_transaction_id,
            "notes": notes,
        }
        return self.insert_row("financial_transactions", data)

    def record_barter_exchange(
        self,
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
    ) -> Tuple[Optional[int], Optional[str]]:
        """Executes an atomic dual-leg barter exchange (outbound issue, inbound receipt, financial offset)."""
        if sender_id:
            can_push, reason = self.check_permission(sender_id, action="PUSH")
            if not can_push:
                return None, reason

        conn = self._get_connection()
        should_close = conn is not self._external_conn and conn is not self._local_conn
        try:
            cur = conn.cursor()
            # Ensure valid unit
            existing_u = self.get_record("units", limit=1)
            if existing_u:
                u_id = existing_u["unit_id"]
            else:
                cur.execute("INSERT INTO units (code, name) VALUES ('UNIT_KG', 'Kilogram');")
                u_id = cur.lastrowid

            # Resolve warehouse if provided, else keep None
            wh_id = None
            if warehouse_id is not None:
                wh = self.get_record("warehouses", "warehouse_id = ?", (warehouse_id,), limit=1)
                if wh:
                    wh_id = wh["warehouse_id"]
                else:
                    wh_dict = self.get_record("dictionary", "dict_id = ?", (warehouse_id,), limit=1)
                    if wh_dict:
                        wh_id = wh_dict["dict_id"]
            # 1. Outbound issue transaction
            cur.execute(
                """
                INSERT INTO inventory_transactions (
                    item_name, category_id, warehouse_id, cycle_id,
                    transaction_type, quantity_change, unit_id, quantity_base,
                    reference_type, reference_note, status
                ) VALUES (?, ?, ?, ?, 'ISSUE', ?, ?, ?, 'BARTER_GIVE', ?, 'POSTED');
                """,
                (
                    f"Barter give: {partner_name}",
                    give_category_id,
                    wh_id,
                    give_cycle_id,
                    -abs(float(give_quantity)),
                    u_id,
                    abs(float(give_quantity)),
                    f"Đổi hàng cho: {partner_name}",
                ),
            )
            give_tx_id = cur.lastrowid

            # 2. Inbound receipt transaction
            cur.execute(
                """
                INSERT INTO inventory_transactions (
                    item_name, category_id, warehouse_id, cycle_id,
                    transaction_type, quantity_change, unit_id, quantity_base,
                    reference_type, reference_note, status
                ) VALUES (?, ?, ?, ?, 'RECEIPT', ?, ?, ?, 'BARTER_RECEIVE', ?, 'POSTED');
                """,
                (
                    f"Barter receive: {partner_name}",
                    receive_category_id,
                    wh_id,
                    receive_cycle_id,
                    abs(float(receive_quantity)),
                    u_id,
                    abs(float(receive_quantity)),
                    f"Nhận hàng đổi từ: {partner_name}",
                ),
            )
            receive_tx_id = cur.lastrowid

            # 3. Cash difference financial transaction if any
            pay_tx_id = None
            if cash_difference_vnd != 0:
                existing_tx_cat = self.get_record("transaction_categories", limit=1)
                if existing_tx_cat:
                    tx_cat_id = existing_tx_cat["category_id"]
                else:
                    cur.execute("INSERT INTO transaction_categories (code, name, type) VALUES ('BARTER_DIFF', 'Chênh Lệch Đổi Hàng', 'EXPENSE');")
                    tx_cat_id = cur.lastrowid

                tx_type = "EXPENSE" if cash_difference_vnd > 0 else "INCOME"
                cur.execute(
                    """
                    INSERT INTO financial_transactions (
                        category_id, type, amount, transaction_date, partner_name,
                        payment_method, status, notes
                    ) VALUES (?, ?, ?, date('now'), ?, 'CASH', 'COMPLETED', ?);
                    """,
                    (
                        tx_cat_id,
                        tx_type,
                        abs(int(cash_difference_vnd)),
                        partner_name,
                        f"Chênh lệch tiền mặt đổi hàng với {partner_name}",
                    ),
                )
                pay_tx_id = cur.lastrowid

            # 4. Insert barter_transactions
            cur.execute(
                """
                INSERT INTO barter_transactions (
                    partner_name, give_category_id, give_quantity, give_unit, give_cycle_id, give_inventory_tx_id,
                    receive_category_id, receive_quantity, receive_unit, receive_cycle_id, receive_inventory_tx_id,
                    estimated_value_vnd, cash_difference_vnd, payment_transaction_id, status, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'COMPLETED', ?);
                """,
                (
                    partner_name,
                    give_category_id,
                    give_quantity,
                    give_unit,
                    give_cycle_id,
                    give_tx_id,
                    receive_category_id,
                    receive_quantity,
                    receive_unit,
                    receive_cycle_id,
                    receive_tx_id,
                    estimated_value_vnd,
                    cash_difference_vnd,
                    pay_tx_id,
                    notes,
                ),
            )
            barter_id = cur.lastrowid
            conn.commit()
            return barter_id, None
        except Exception as e:
            conn.rollback()
            return None, str(e)
        finally:
            if should_close:
                conn.close()

    def process_debt_payment(
        self,
        debt_id: int,
        amount_paid: int,
        payment_date: Optional[str] = None,
        payment_method: str = "CASH",
        notes: Optional[str] = None,
        recorded_by: Optional[int] = None,
        sender_id: Optional[str] = None,
    ) -> Tuple[Optional[int], Optional[str]]:
        """Processes an installment payment towards a debt, updating remaining amount and debt status."""
        if sender_id:
            can_push, reason = self.check_permission(sender_id, action="PUSH")
            if not can_push:
                return None, reason

        debt = self.get_record("debt_records", "debt_id = ?", (debt_id,), limit=1)
        if not debt:
            return None, f"Debt #{debt_id} not found"

        if amount_paid <= 0:
            return None, "Payment amount must be greater than zero"

        conn = self._get_connection()
        should_close = conn is not self._external_conn and conn is not self._local_conn
        try:
            cur = conn.cursor()
            date_str = payment_date or datetime.now().strftime("%Y-%m-%d")
            tx_type = "EXPENSE" if debt.get("debt_type") == "PAYABLE" else "INCOME"

            # 1. Financial transaction for the payment
            cur.execute(
                """
                INSERT INTO financial_transactions (
                    category_id, type, amount, transaction_date, partner_name,
                    payment_method, status, notes
                ) VALUES (1, ?, ?, ?, ?, ?, 'COMPLETED', ?);
                """,
                (
                    tx_type,
                    int(amount_paid),
                    date_str,
                    debt.get("partner_name"),
                    payment_method.upper(),
                    notes or f"Thanh toán nợ #{debt_id}",
                ),
            )
            ft_id = cur.lastrowid

            # 2. Debt payment record
            cur.execute(
                """
                INSERT INTO debt_payments (
                    debt_id, payment_transaction_id, amount_paid, payment_date, notes
                ) VALUES (?, ?, ?, ?, ?);
                """,
                (debt_id, ft_id, int(amount_paid), date_str, notes),
            )
            payment_id = cur.lastrowid

            # 3. Update debt_records
            new_paid = (debt.get("paid_amount") or 0) + int(amount_paid)
            initial = debt.get("initial_amount") or 0
            new_status = "SETTLED" if new_paid >= initial else "PARTIAL"
            cur.execute(
                """
                UPDATE debt_records
                SET paid_amount = ?,
                    status = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE debt_id = ?;
                """,
                (new_paid, new_status, debt_id),
            )
            conn.commit()
            return payment_id, None
        except Exception as e:
            conn.rollback()
            return None, str(e)
        finally:
            if should_close:
                conn.close()
    def _apply_pending_events_to_dataset(
        self,
        table: str,
        records: List[Dict[str, Any]],
        pending_events: List[Dict[str, Any]],
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Applies pending events to a list of records in chronological order using SQL semantics.

        Executes INSERT, UPDATE, DELETE in strict timestamp ASC, event_id ASC sequence.
        Gracefully skips malformed or non-executable payloads.

        Returns:
            Tuple of (updated_records, applied_count).
        """
        norm_table = self._normalize_table_name(table)
        current_data = [copy.deepcopy(r) for r in records]

        # Strictly sort pending events by timestamp ASC, event_id ASC
        sorted_events = sorted(
            pending_events,
            key=lambda x: (str(x.get("timestamp") or ""), int(x.get("event_id") or 0)),
        )

        # Retrieve table schema metadata if available
        conn = self._get_connection()
        should_close = conn is not self._external_conn and conn is not self._local_conn
        try:
            cols = self._get_table_columns(conn, norm_table)
        except Exception:
            cols = {}
        finally:
            if should_close:
                conn.close()

        pk_cols = [name for name, meta in cols.items() if meta.get("pk")]
        if not pk_cols:
            candidate = f"{norm_table.rstrip('s')}_id"
            if candidate in cols:
                pk_cols = [candidate]
            elif "id" in cols:
                pk_cols = ["id"]

        def _val_eq(v1: Any, v2: Any) -> bool:
            if v1 == v2:
                return True
            if v1 is None or v2 is None:
                return False
            if isinstance(v1, bool) or isinstance(v2, bool):
                return bool(v1) == bool(v2)
            try:
                if isinstance(v1, (int, float, str)) and isinstance(v2, (int, float, str)):
                    if str(v1).strip() == str(v2).strip():
                        return True
                    return float(v1) == float(v2)
            except (ValueError, TypeError):
                pass
            return False

        def _matches(row: Dict[str, Any], where: Dict[str, Any]) -> bool:
            if not where:
                return True
            for k, v in where.items():
                if k not in row and v is not None:
                    return False
                if not _val_eq(row.get(k), v):
                    return False
            return True

        applied_count = 0
        for ev in sorted_events:
            try:
                payload_raw = ev.get("payload_json")
                if isinstance(payload_raw, str):
                    try:
                        payload = json.loads(payload_raw)
                    except Exception:
                        continue
                elif isinstance(payload_raw, dict):
                    payload = dict(payload_raw)
                else:
                    continue

                action = str(ev.get("action_type") or "INSERT").upper().strip()
                ev_ts = str(ev.get("timestamp") or self._get_current_timestamp())

                if action == "INSERT":
                    if "data" in payload and isinstance(payload["data"], dict) and len(payload) == 1:
                        row_data = dict(payload["data"])
                    else:
                        row_data = dict(payload)

                    if not row_data:
                        continue

                    # Auto-assign primary key if autoincrement integer and missing
                    if pk_cols:
                        for pk in pk_cols:
                            if pk not in row_data or row_data[pk] is None:
                                existing_ids = [
                                    r.get(pk)
                                    for r in current_data
                                    if isinstance(r.get(pk), int)
                                ]
                                next_id = (max(existing_ids) + 1) if existing_ids else 1
                                row_data[pk] = next_id

                    # Populate default schema values
                    for col_name, meta in cols.items():
                        if col_name not in row_data:
                            dflt = meta.get("dflt_value")
                            if dflt is not None:
                                clean_dflt = str(dflt).strip()
                                if (clean_dflt.startswith("'") and clean_dflt.endswith("'")) or (
                                    clean_dflt.startswith('"') and clean_dflt.endswith('"')
                                ):
                                    row_data[col_name] = clean_dflt[1:-1]
                                elif clean_dflt.upper() in (
                                    "CURRENT_TIMESTAMP",
                                    "CURRENT_DATE",
                                    "CURRENT_TIME",
                                ):
                                    row_data[col_name] = ev_ts
                                elif clean_dflt.upper() == "NULL":
                                    row_data[col_name] = None
                                else:
                                    try:
                                        row_data[col_name] = (
                                            float(clean_dflt)
                                            if "." in clean_dflt
                                            else int(clean_dflt)
                                        )
                                    except ValueError:
                                        row_data[col_name] = clean_dflt
                            elif col_name in ("created_at", "updated_at"):
                                row_data[col_name] = ev_ts

                    current_data.append(row_data)
                    applied_count += 1

                elif action == "UPDATE":
                    where_clause: Dict[str, Any] = {}
                    data_clause: Dict[str, Any] = {}

                    if "where" in payload:
                        where_clause = (
                            payload["where"] if isinstance(payload["where"], dict) else {}
                        )
                        data_part = payload.get("data") or payload.get("set")
                        if isinstance(data_part, dict):
                            data_clause = data_part
                        else:
                            data_clause = {k: v for k, v in payload.items() if k != "where"}
                    else:
                        matching_pks = [pk for pk in pk_cols if pk in payload]
                        if matching_pks:
                            where_clause = {pk: payload[pk] for pk in matching_pks}
                            data_clause = {
                                k: v for k, v in payload.items() if k not in matching_pks
                            }
                        else:
                            fallback_pk = f"{norm_table.rstrip('s')}_id"
                            if fallback_pk in payload:
                                where_clause = {fallback_pk: payload[fallback_pk]}
                                data_clause = {
                                    k: v for k, v in payload.items() if k != fallback_pk
                                }
                            elif "id" in payload:
                                where_clause = {"id": payload["id"]}
                                data_clause = {k: v for k, v in payload.items() if k != "id"}

                    if not where_clause or not data_clause:
                        continue

                    matched_any = False
                    for row in current_data:
                        if _matches(row, where_clause):
                            matched_any = True
                            for k, v in data_clause.items():
                                row[k] = v
                            if "updated_at" in cols and "updated_at" not in data_clause:
                                row["updated_at"] = ev_ts

                    if matched_any:
                        applied_count += 1

                elif action == "DELETE":
                    if "where" in payload and isinstance(payload["where"], dict):
                        where_clause = payload["where"]
                    else:
                        where_clause = payload

                    if not where_clause:
                        continue

                    orig_len = len(current_data)
                    current_data = [
                        row for row in current_data if not _matches(row, where_clause)
                    ]
                    if len(current_data) < orig_len:
                        applied_count += 1

                elif action == "UPSERT":
                    where_clause = {}
                    data_clause = {}
                    if "where" in payload:
                        where_clause = (
                            payload["where"] if isinstance(payload["where"], dict) else {}
                        )
                        data_clause = payload.get("data") or {
                            k: v for k, v in payload.items() if k != "where"
                        }
                    elif pk_cols:
                        matching_pks = [pk for pk in pk_cols if pk in payload]
                        if matching_pks:
                            where_clause = {pk: payload[pk] for pk in matching_pks}
                            data_clause = {
                                k: v for k, v in payload.items() if k not in matching_pks
                            }

                    matched = False
                    if where_clause:
                        for row in current_data:
                            if _matches(row, where_clause):
                                matched = True
                                for k, v in data_clause.items():
                                    row[k] = v
                                if "updated_at" in cols and "updated_at" not in data_clause:
                                    row["updated_at"] = ev_ts

                    if not matched:
                        row_data = dict(payload.get("data", payload))
                        current_data.append(row_data)
                    applied_count += 1

            except Exception:
                # Graceful degradation: continue with next pending event
                continue

        return current_data, applied_count

    def get_data_with_pending_applied(
        self,
        table: str,
        conditions: Optional[Dict[str, Any]] = None,
        limit: Optional[int] = None,
        order_by: Optional[str] = None,
        as_list: bool = False,
    ) -> Union[Dict[str, Any], List[Dict[str, Any]]]:
        """Fetches committed data from db and updates it with unapproved pending changes.

        Pending events are applied sequentially in chronological order (timestamp ASC, event_id ASC)
        matching SQL semantics (INSERT, UPDATE, DELETE). Resulting data is unified and clean,
        ready for AI ingestion, reporting, or downstream processing.

        Args:
            table: Target database table name.
            conditions: Optional dictionary of conditions to filter the final dataset.
            limit: Optional maximum number of records to return.
            order_by: Optional column name for ordering, optionally followed by ASC or DESC.
            as_list: If True, returns only the records list instead of the response dict.

        Returns:
            Dictionary matching get_data_with_pending_overlay format where "committed_data"
            (and alias "data") holds the updated records with pending overlays applied.
        """
        norm_table = self._normalize_table_name(table)
        all_committed = self.get_formatted_data(norm_table, conditions=None)
        pending = self.get_pending_queue(target_table=norm_table)

        updated_data, applied_count = self._apply_pending_events_to_dataset(
            norm_table, all_committed, pending
        )

        if conditions:
            filtered_data = []
            for row in updated_data:
                match = True
                for k, v in conditions.items():
                    r_val = row.get(k)
                    if v is None:
                        if r_val is not None:
                            match = False
                            break
                    else:
                        if r_val != v:
                            if (
                                isinstance(v, (int, str))
                                and isinstance(r_val, (int, str))
                                and str(v) == str(r_val)
                            ):
                                pass
                            else:
                                match = False
                                break
                if match:
                    filtered_data.append(row)
            updated_data = filtered_data

        if order_by:
            parts = order_by.strip().split()
            col = parts[0]
            reverse = len(parts) > 1 and parts[1].upper() == "DESC"
            updated_data.sort(
                key=lambda r: (r.get(col) is not None, r.get(col)),
                reverse=reverse,
            )

        if limit is not None and limit > 0:
            updated_data = updated_data[:limit]

        if as_list:
            return updated_data

        return {
            "target_table": norm_table,
            "committed_count": len(updated_data),
            "pending_count": len(pending),
            "applied_pending_count": applied_count,
            "committed_data": updated_data,
            "data": updated_data,
        }

    # Aliases for convenience and flexible naming conventions
    get_data_with_pending_merged = get_data_with_pending_applied
    get_merged_data_with_pending = get_data_with_pending_applied
    get_clean_data_with_pending = get_data_with_pending_applied
    get_clean_data_with_pending_overlay = get_data_with_pending_applied
    get_data_with_pending_overlay_applied = get_data_with_pending_applied

