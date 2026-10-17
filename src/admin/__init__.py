"""AgriVoice-AI: Admin Domain Package.

Exposes administrative services, operational managers, and RBAC security
supporting Farm Owner and Manager workflows specified in 'notes/System methods.md'.
"""

from __future__ import annotations

from src.admin.collaborators import AdminPermissionError, CollaboratorManager
from src.admin.finance import FinancialGovernanceManager
from src.admin.inventory import InventoryGovernanceManager
from src.admin.operations import OperationsManager
from src.admin.queue import QueueReviewManager
from src.admin.reports import ReportAnalyticsManager
from src.admin.service import AdminService

__all__ = [
    "AdminService",
    "AdminPermissionError",
    "CollaboratorManager",
    "QueueReviewManager",
    "OperationsManager",
    "InventoryGovernanceManager",
    "FinancialGovernanceManager",
    "ReportAnalyticsManager",
]
