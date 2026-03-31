"""Module for service locator."""

from __future__ import annotations

from .service_locator_base import BaseServiceLocator
from apps.core.service_locator_mixins import (
    AutomationServiceLocatorMixin,
    BusinessServiceLocatorMixin,
    ContractReviewServiceLocatorMixin,
    CoreServiceLocatorMixin,
    DocumentsServiceLocatorMixin,
)


class ServiceLocator(
    BaseServiceLocator,
    BusinessServiceLocatorMixin,
    AutomationServiceLocatorMixin,
    DocumentsServiceLocatorMixin,
    CoreServiceLocatorMixin,
    ContractReviewServiceLocatorMixin,
):
    pass
