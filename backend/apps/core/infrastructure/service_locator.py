"""Module for service locator."""

from __future__ import annotations

from apps.core.service_locator_mixins import (
    AutomationServiceLocatorMixin,
    BusinessServiceLocatorMixin,
    ContractReviewServiceLocatorMixin,
    CoreServiceLocatorMixin,
    DocumentsServiceLocatorMixin,
)

from .service_locator_base import BaseServiceLocator


class ServiceLocator(
    BaseServiceLocator,
    BusinessServiceLocatorMixin,
    AutomationServiceLocatorMixin,
    DocumentsServiceLocatorMixin,
    CoreServiceLocatorMixin,
    ContractReviewServiceLocatorMixin,
):
    pass
