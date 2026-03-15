"""Module for business organization."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from apps.core.protocols import ILawFirmService, ILawyerService, IOrganizationService, IReminderService


def build_lawyer_service() -> ILawyerService:
    from apps.organization.services import LawyerServiceAdapter

    return LawyerServiceAdapter()  # type: ignore[abstract]  # 适配器实现了所有抽象方法


def build_lawfirm_service() -> ILawFirmService:
    from apps.organization.services import LawFirmServiceAdapter

    return LawFirmServiceAdapter()


def build_organization_service() -> IOrganizationService:
    from apps.organization.services import OrganizationServiceAdapter

    return OrganizationServiceAdapter()


def build_reminder_service() -> IReminderService:
    from apps.reminders.services.wiring import get_reminder_service

    return get_reminder_service()
