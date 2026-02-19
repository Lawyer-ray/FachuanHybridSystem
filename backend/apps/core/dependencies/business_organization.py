"""Module for business organization."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from apps.core.protocols import ILawFirmService, ILawyerService, IOrganizationService, IReminderService


def build_lawyer_service() -> ILawyerService:
    from apps.organization.services import LawyerServiceAdapter

    return LawyerServiceAdapter()  # type: ignore[return-value]


def build_lawfirm_service() -> ILawFirmService:
    from apps.organization.services import LawFirmServiceAdapter

    return LawFirmServiceAdapter()


def build_organization_service() -> IOrganizationService:
    from apps.organization.services import OrganizationServiceAdapter

    return OrganizationServiceAdapter()  # type: ignore[return-value]


def build_reminder_service() -> IReminderService:
    from apps.reminders.services.reminder_service_adapter import ReminderServiceAdapter

    return ReminderServiceAdapter()
