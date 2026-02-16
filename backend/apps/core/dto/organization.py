"""Module for organization."""

from dataclasses import dataclass, field
from typing import Any


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
    lawyer: Any | None = None

    @classmethod
    def from_model(cls, credential: Any) -> "AccountCredentialDTO":
        return cls(
            id=credential.id,
            lawyer_id=credential.lawyer_id,
            site_name=credential.site_name,
            url=credential.url if hasattr(credential, "url") else None,
            account=credential.account,
            password=credential.password,
            last_login_success_at=(
                str(credential.last_login_success_at)
                if hasattr(credential, "last_login_success_at") and credential.last_login_success_at
                else None
            ),
            login_success_count=credential.login_success_count if hasattr(credential, "login_success_count") else 0,
            login_failure_count=credential.login_failure_count if hasattr(credential, "login_failure_count") else 0,
            is_preferred=credential.is_preferred if hasattr(credential, "is_preferred") else False,
            created_at=(
                str(credential.created_at) if hasattr(credential, "created_at") and credential.created_at else None
            ),
            updated_at=(
                str(credential.updated_at) if hasattr(credential, "updated_at") and credential.updated_at else None
            ),
            lawyer=credential.lawyer if hasattr(credential, "lawyer") else None,
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
    def from_model(cls, lawyer: Any) -> "LawyerDTO":
        return cls(
            id=lawyer.id,
            username=lawyer.username if hasattr(lawyer, "username") else str(lawyer.id),
            real_name=lawyer.real_name if hasattr(lawyer, "real_name") else None,
            phone=lawyer.phone if hasattr(lawyer, "phone") else None,
            email=lawyer.email if hasattr(lawyer, "email") else None,
            is_admin=lawyer.is_admin if hasattr(lawyer, "is_admin") else False,
            is_active=lawyer.is_active if hasattr(lawyer, "is_active") else True,
            law_firm_id=lawyer.law_firm_id if hasattr(lawyer, "law_firm_id") else None,
            law_firm_name=lawyer.law_firm.name if hasattr(lawyer, "law_firm") and lawyer.law_firm else None,
            team_id=lawyer.team_id if hasattr(lawyer, "team_id") else None,
            team_name=lawyer.team.name if hasattr(lawyer, "team") and lawyer.team else None,
        )


@dataclass
class LawFirmDTO:
    id: int
    name: str
    address: str | None = None
    phone: str | None = None
    social_credit_code: str | None = None

    @classmethod
    def from_model(cls, lawfirm: Any) -> "LawFirmDTO":
        return cls(
            id=lawfirm.id,
            name=lawfirm.name,
            address=lawfirm.address if hasattr(lawfirm, "address") else None,
            phone=lawfirm.phone if hasattr(lawfirm, "phone") else None,
            social_credit_code=lawfirm.social_credit_code if hasattr(lawfirm, "social_credit_code") else None,
        )
