"""AgriVoice-AI: Admin Inventory, Stock & Batch Governance.

Handles inventory ledger adjustments, reconciliation of negative stock batches,
stock count sessions, dictionary metadata, and unit conversions.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple, Union

from src.admin.collaborators import AdminPermissionError
from src.db.service import DBService


class InventoryGovernanceManager:
    """Manages warehouse inventory, batch reconciliation, and unit conversions."""

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
        """Appends an immutable inventory adjustment record (ADJUSTMENT_IN / ADJUSTMENT_OUT).

        Enforces append-only immutable ledger rules (never mutates existing posted rows).
        """
        self._verify_admin(admin_telegram_id)

        tx_type = "ADJUSTMENT_IN" if quantity_change > 0 else "ADJUSTMENT_OUT"
        return self.service.record_inventory_transaction(
            item_name=item_name,
            category_id=category_id,
            quantity_change=quantity_change,
            unit_id=unit_id,
            transaction_type=tx_type,
            warehouse_id=warehouse_id,
            sender_id=admin_telegram_id or self.admin_telegram_id,
        )

    def reconcile_inventory(
        self,
        warehouse_id: Optional[int] = None,
        category_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Reconciles product_batches and stock, flagging anomalies and negative stock."""
        return self.service.reconcile_batches_and_stock(
            warehouse_id=warehouse_id,
            category_id=category_id,
        )

    def get_negative_stock_alerts(self, warehouse_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """Scans for active negative virtual batches (is_virtual=1 or quantity_remaining < 0)."""
        reconciled = self.reconcile_inventory(warehouse_id=warehouse_id)
        return [b for b in reconciled if b.get("is_negative_alert") or b.get("is_virtual")]

    def create_stock_count(
        self,
        warehouse_id: int,
        title: Optional[str] = None,
        creator_telegram_id: Optional[str] = None,
    ) -> Tuple[Optional[int], Optional[str]]:
        """Creates a new stock count audit session."""
        self._verify_admin(creator_telegram_id)

        data = {
            "warehouse_id": warehouse_id,
            "title": title or "Kiểm kê kho thực tế",
            "status": "DRAFT",
            "count_date": self.service._get_current_timestamp()[:10],
        }
        return self.service.insert_row("stock_counts", data)

    def add_dictionary_category(
        self,
        code: str,
        name: str,
        root_path: str = "/vat-tu/",
        parent_id: Optional[int] = None,
        convenient_names: Optional[str] = None,
        entry_type: str = "CATEGORY",
        admin_telegram_id: Optional[str] = None,
    ) -> Tuple[Optional[int], Optional[str]]:
        """Adds a category, material type, or warehouse to dictionary."""
        self._verify_admin(admin_telegram_id)

        data = {
            "code": code.upper().strip(),
            "name": name.strip(),
            "root_path": root_path,
            "parent_id": parent_id,
            "convenient_names": convenient_names,
            "entry_type": entry_type,
        }
        return self.service.insert_row("dictionary", data)

    def configure_unit_conversion(
        self,
        category_id: int,
        unit_id: int,
        factor_to_base: float,
        admin_telegram_id: Optional[str] = None,
    ) -> Tuple[bool, Optional[str]]:
        """Configures custom unit conversion ratio (e.g. 1 bao = 50 kg)."""
        self._verify_admin(admin_telegram_id)

        if factor_to_base <= 0:
            return False, "Hệ số quy đổi factor_to_base phải lớn hơn 0."

        existing = self.service.get_record(
            "category_unit_conversions",
            "category_id = ? AND unit_id = ?",
            (category_id, unit_id),
            limit=1,
        )

        if existing:
            count, err = self.service.update_row(
                "category_unit_conversions",
                {"conversion_id": existing["conversion_id"], "factor_to_base": factor_to_base},
            )
            return (count > 0, err)
        else:
            cid, err = self.service.insert_row(
                "category_unit_conversions",
                {"category_id": category_id, "unit_id": unit_id, "factor_to_base": factor_to_base},
            )
            return (cid is not None, err)
