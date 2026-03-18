"""Minimal test factories for app-level regression tests.

These helpers intentionally avoid extra dependencies (e.g. factory_boy)
and only cover the model combinations required by current tests.
"""

from __future__ import annotations

from itertools import count
from typing import Any

from apps.cases.models import Case, CaseLog
from apps.client.models import Client, ClientIdentityDoc
from apps.contracts.models import Contract
from apps.core.enums import CaseType, SimpleCaseType
from apps.organization.models import Lawyer

_SEQUENCE = count(1)


def _token(prefix: str) -> str:
    return f"{prefix}-{next(_SEQUENCE)}"


def LawyerFactory(**kwargs: Any) -> Lawyer:
    username = str(kwargs.pop("username", _token("lawyer")))
    defaults: dict[str, Any] = {
        "username": username,
        "real_name": kwargs.pop("real_name", username),
    }
    defaults.update(kwargs)
    return Lawyer.objects.create(**defaults)


def ContractFactory(**kwargs: Any) -> Contract:
    defaults: dict[str, Any] = {
        "name": _token("contract"),
        "case_type": CaseType.CIVIL,
    }
    defaults.update(kwargs)
    return Contract.objects.create(**defaults)


def CaseFactory(**kwargs: Any) -> Case:
    contract = kwargs.pop("contract", None) or ContractFactory()
    defaults: dict[str, Any] = {
        "name": _token("case"),
        "contract": contract,
        "case_type": SimpleCaseType.CIVIL,
    }
    defaults.update(kwargs)
    return Case.objects.create(**defaults)


def CaseLogFactory(**kwargs: Any) -> CaseLog:
    case = kwargs.pop("case", None) or CaseFactory()
    actor = kwargs.pop("actor", None) or LawyerFactory()
    defaults: dict[str, Any] = {
        "case": case,
        "actor": actor,
        "content": _token("case-log"),
    }
    defaults.update(kwargs)
    return CaseLog.objects.create(**defaults)


def ClientFactory(**kwargs: Any) -> Client:
    client_type = str(kwargs.get("client_type", Client.LEGAL))
    defaults: dict[str, Any] = {
        "name": _token("client"),
        "client_type": client_type,
    }
    if client_type in {Client.LEGAL, Client.NON_LEGAL_ORG} and "legal_representative" not in kwargs:
        defaults["legal_representative"] = "Test Representative"
    defaults.update(kwargs)
    return Client.objects.create(**defaults)


def ClientIdentityDocFactory(**kwargs: Any) -> ClientIdentityDoc:
    client = kwargs.pop("client", None) or ClientFactory()
    doc_type = kwargs.pop("doc_type", None)
    if doc_type is None:
        doc_type = (
            ClientIdentityDoc.ID_CARD if client.client_type == Client.NATURAL else ClientIdentityDoc.BUSINESS_LICENSE
        )
    defaults: dict[str, Any] = {
        "client": client,
        "doc_type": doc_type,
        "file_path": f"identity_docs/{_token('doc')}.pdf",
    }
    defaults.update(kwargs)
    return ClientIdentityDoc.objects.create(**defaults)


__all__ = [
    "CaseFactory",
    "CaseLogFactory",
    "ClientFactory",
    "ClientIdentityDocFactory",
    "ContractFactory",
    "LawyerFactory",
]
