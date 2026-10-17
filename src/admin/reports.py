"""AgriVoice-AI: Admin Audit, Reconciliation & Farm Analytics Reports.

Provides high-level analytical queries over the 4 reconciliation views (Tier 3)
and aggregates real-time farm health metrics for farm owners.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from src.db.service import DBService


class ReportAnalyticsManager:
    """Provides high-level reporting over SQLite reconciliation views and dashboard metrics."""

    def __init__(self, service: DBService, admin_telegram_id: Optional[str] = None):
        self.service = service
        self.admin_telegram_id = admin_telegram_id

    # --------------------------------------------------------------------------
    # 4 Reconciliation Views (Tầng 3 Đối Soát Sau Ghi Sổ)
    # --------------------------------------------------------------------------

    def get_inventory_root_summary(
        self,
        anomaly_only: bool = False,
    ) -> List[Dict[str, Any]]:
        """Queries v_inventory_root_summary to review material categories, stock levels, and negative alerts."""
        data = self.service.get_formatted_data("v_inventory_root_summary")
        if anomaly_only:
            return [row for row in data if row.get("inventory_health") == "NEGATIVE_ANOMALY"]
        return data

    def get_cycle_yield_performance(
        self,
        cycle_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Queries v_cycle_yield_performance to evaluate actual vs expected yield and ROI performance."""
        conds = {"cycle_id": cycle_id} if cycle_id is not None else None
        return self.service.get_formatted_data("v_cycle_yield_performance", conditions=conds)

    def get_cycle_financial_summary(
        self,
        cycle_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Queries v_cycle_financial_summary to assess revenue, expenses, net profit, and ROI % per cycle."""
        conds = {"cycle_id": cycle_id} if cycle_id is not None else None
        return self.service.get_formatted_data("v_cycle_financial_summary", conditions=conds)

    def get_daily_cashflow_summary(
        self,
        limit_days: int = 30,
        payment_method: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Queries v_daily_cashflow_summary for daily cash and bank account net flows."""
        conds = {"payment_method": payment_method.upper()} if payment_method else None
        return self.service.get_formatted_data(
            "v_daily_cashflow_summary",
            conditions=conds,
            limit=limit_days,
            order_by="transaction_date DESC",
        )

    # --------------------------------------------------------------------------
    # Consolidated Executive Dashboard Overview
    # --------------------------------------------------------------------------

    def get_dashboard_overview(self) -> Dict[str, Any]:
        """Consolidates cross-domain operational and financial metrics into an executive farm summary."""
        # 1. In-Flight Queue
        pending_queue = self.service.get_pending_queue()
        error_events = self.service.get_error_logs()

        # 2. Field Issues & Tasks
        open_issues = self.service.get_formatted_data("issues", conditions={"status": "OPEN"})
        in_progress_issues = self.service.get_formatted_data("issues", conditions={"status": "IN_PROGRESS"})
        todo_tasks = self.service.get_formatted_data("running_tasks", conditions={"status": "TODO"})
        done_tasks = self.service.get_formatted_data("running_tasks", conditions={"status": "DONE"})

        # 3. Active Cycles
        active_cycles = self.service.get_formatted_data("production_cycles", conditions={"status": "ACTIVE"})

        # 4. Inventory Health (Negative anomalies)
        inv_summary = self.get_inventory_root_summary()
        negative_anomalies = [r for r in inv_summary if r.get("inventory_health") == "NEGATIVE_ANOMALY"]

        # 5. Financial Overview
        cashflow = self.get_daily_cashflow_summary(limit_days=30)
        total_income = sum(r.get("daily_income_vnd", 0) for r in cashflow)
        total_expense = sum(r.get("daily_expense_vnd", 0) for r in cashflow)
        net_cashflow = total_income - total_expense

        # 6. Unsettled Debts
        unsettled_debts = self.service.get_formatted_data("debt_records", conditions={"status": "ACTIVE"})

        return {
            "in_flight": {
                "pending_events_count": len(pending_queue),
                "error_events_count": len(error_events),
                "has_urgent_review": len(pending_queue) > 0 or len(error_events) > 0,
            },
            "operations": {
                "active_cycles_count": len(active_cycles),
                "open_issues_count": len(open_issues) + len(in_progress_issues),
                "critical_issues_count": sum(1 for i in open_issues if i.get("severity") in ("CRITICAL", "HIGH")),
                "tasks_todo_count": len(todo_tasks),
                "tasks_done_count": len(done_tasks),
            },
            "inventory": {
                "total_categories_tracked": len(inv_summary),
                "negative_stock_anomalies_count": len(negative_anomalies),
                "has_negative_stock_alert": len(negative_anomalies) > 0,
            },
            "finance_30d": {
                "total_income_vnd": total_income,
                "total_expense_vnd": total_expense,
                "net_cashflow_vnd": net_cashflow,
                "unsettled_debt_count": len(unsettled_debts),
            },
        }
