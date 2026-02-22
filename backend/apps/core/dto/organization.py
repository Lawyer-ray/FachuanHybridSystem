"""Module for organization."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from apps.organization.models import AccountCredential, LawFirm, Lawyer, Team


@dataclass
class AccountCredentialDTO:
    id: int
    lawyer_id: int
    site_name: str
    url: str | None
    account: str
    password: str = field(repr=False)
    last_login_success_at: str | None = None
    login_success_count: int = 0
    login_failure_count: int = 0
    is_preferred: bool = False
    created_at: str | None = None
    updated_at: str | None = None
    lawyer: Lawyer | None = None

    @classmethod
    def from_model(cls, credential: AccountCredential) -> AccountCredentialDTO:
        return cls(
            id=credential.id,
            lawyer_id=credential.lawyer_id,
            site_name=credential.site_name,
            url=credential.url,
            account=credential.account,
            password=credential.password,
            last_login_success_at=(str(credential.last_login_success_at) if credential.last_login_success_at else None),
            login_success_count=credential.login_success_count,
            login_failure_count=credential.login_failure_count,
            is_preferred=credential.is_preferred,
            created_at=(str(credential.created_at) if credential.created_at else None),
            updated_at=(str(credential.updated_at) if credential.updated_at else None),
            lawyer=credential.lawyer,
        )


@dataclass
class LawyerDTO:
    id: int
    username: str
    real_name: str | None = None
    phone: str | None = None
    email: str | None = None
    is_admin: bool = False
    is_active: bool = True
    law_firm_id: int | None = None
    law_firm_name: str | None = None
    team_id: int | None = None
    team_name: str | None = None

    @classmethod
    def from_model(cls, lawyer: Lawyer) -> LawyerDTO:
        return cls(
            id=lawyer.id,
            username=lawyer.username,
            real_name=lawyer.real_name,
            phone=lawyer.phone,
            email=lawyer.email,
            is_admin=lawyer.is_admin,
            is_active=lawyer.is_active,
            law_firm_id=lawyer.law_firm_id,
            law_firm_name=lawyer.law_firm.name if lawyer.law_firm else None,
            team_id=None,
            team_name=None,
        )


@dataclass
class LawFirmDTO:
    id: int
    name: str
    address: str | None = None
    phone: str | None = None
    social_credit_code: str | None = None

    @classmethod
    def from_model(cls, lawfirm: LawFirm) -> LawFirmDTO:
        return cls(
            id=lawfirm.id,
            name=lawfirm.name,
            address=lawfirm.address,
            phone=lawfirm.phone,
            social_credit_code=lawfirm.social_credit_code,
        )


@dataclass
class TeamDTO:
    id: int
    name: str
    law_firm_id: int

    @classmethod
    def from_model(cls, team: Team) -> TeamDTO:
        return cls(id=team.id, name=team.name, law_firm_id=team.law_firm_id)
