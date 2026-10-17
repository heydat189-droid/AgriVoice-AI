"""AgriVoice-AI: Admin Financial, Barter & Debt Governance.

Enforces integer-only currency constraints (VND), dual-leg atomic barter sync,
and multi-stage debt tracking.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple, Union

from src.admin.collaborators import AdminPermissionError
from src.db.models import FinancialTransactionType, PaymentMethod
from src.db.service import DBService


class FinancialGovernanceManager:
    """Manages farm cashflow, barter exchanges, and debt settlement."""

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
        self._verify_admin(admin_telegram_id)

        type_str = str(type.value) if isinstance(type, FinancialTransactionType) else str(type).upper()
        method_str = str(payment_method.value) if isinstance(payment_method, PaymentMethod) else str(payment_method).upper()

        return self.service.record_financial_transaction(
            category_id=category_id,
            type=type_str,
            amount=int(amount),
            payment_method=method_str,
            partner_name=partner_name,
            cycle_id=cycle_id,
            notes=notes,
            transaction_date=transaction_date,
            sender_id=admin_telegram_id or self.admin_telegram_id,
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
        """Executes atomic dual-leg barter trade (goods-for-goods) with optional cash difference."""
        self._verify_admin(admin_telegram_id)

        return self.service.record_barter_exchange(
            partner_name=partner_name,
            give_category_id=give_category_id,
            give_quantity=give_quantity,
            give_unit=give_unit,
            receive_category_id=receive_category_id,
            receive_quantity=receive_quantity,
            receive_unit=receive_unit,
            estimated_value_vnd=estimated_value_vnd,
            cash_difference_vnd=int(cash_difference_vnd),
            give_cycle_id=give_cycle_id,
            receive_cycle_id=receive_cycle_id,
            warehouse_id=warehouse_id,
            notes=notes,
            sender_id=admin_telegram_id or self.admin_telegram_id,
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
        self._verify_admin(admin_telegram_id)

        method_str = str(payment_method.value) if isinstance(payment_method, PaymentMethod) else str(payment_method).upper()
        return self.service.process_debt_payment(
            debt_id=debt_id,
            amount_paid=int(amount_paid),
            payment_method=method_str,
            notes=notes,
        )

    def get_debt_records(
        self,
        debt_type: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Returns list of receivables / payables with current balances."""
        conds: Dict[str, Any] = {}
        if debt_type:
            conds["debt_type"] = debt_type.upper()
        if status:
            conds["status"] = status.upper()
        return self.service.get_formatted_data("debt_records", conditions=conds or None)

    def get_financial_transactions(
        self,
        type: Optional[str] = None,
        cycle_id: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Returns financial transaction records."""
        conds: Dict[str, Any] = {}
        if type:
            conds["type"] = type.upper()
        if cycle_id:
            conds["cycle_id"] = cycle_id
        return self.service.get_formatted_data("financial_transactions", conditions=conds or None, limit=limit)
