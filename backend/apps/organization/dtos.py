"""Data transfer objects."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TeamUpsertDTO:
    name: str
    team_type: str
    law_firm_id: int


@dataclass(frozen=True)
class LawFirmCreateDTO:
    name: str
    address: str | None = None
    phone: str | None = None
    social_credit_code: str | None = None


@dataclass(frozen=True)
class LawFirmUpdateDTO:
    name: str | None = None
    address: str | None = None
    phone: str | None = None
    social_credit_code: str | None = None


@dataclass(frozen=True)
class LawyerCreateDTO:
    username: str
    password: str
    real_name: str | None = None
    phone: str | None = None
    license_no: str | None = None
    id_card: str | None = None
    law_firm_id: int | None = None
    is_admin: bool = False
    lawyer_team_ids: list[int] | None = None
    biz_team_ids: list[int] | None = None


@dataclass(frozen=True)
class LawyerUpdateDTO:
    real_name: str | None = None
    phone: str | None = None
    license_no: str | None = None
    id_card: str | None = None
    law_firm_id: int | None = None
    is_admin: bool | None = None
    password: str | None = None
    lawyer_team_ids: list[int] | None = None
    biz_team_ids: list[int] | None = None
