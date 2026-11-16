"""企业信息预填 Schema。"""

from __future__ import annotations

from ninja import Schema


class EnterpriseCompanyCandidateOut(Schema):
    """企业搜索候选项。"""

    company_id: str
    company_name: str
    legal_person: str = ""
    status: str = ""
    establish_date: str = ""
    registered_capital: str = ""
    phone: str = ""


class EnterpriseCompanySearchOut(Schema):
    """企业搜索结果。"""

    keyword: str
    provider: str
    items: list[EnterpriseCompanyCandidateOut]
    total: int


class EnterpriseDuplicateClientOut(Schema):
    """已存在的当事人信息。"""

    id: int
    name: str


class EnterpriseClientPrefillDataOut(Schema):
    """企业信息映射后的当事人预填字段。"""

    client_type: str
    name: str
    id_number: str = ""
    legal_representative: str = ""
    address: str = ""
    phone: str = ""


class EnterpriseCompanyProfileOut(Schema):
    """企业基础档案。"""

    company_id: str
    company_name: str = ""
    unified_social_credit_code: str = ""
    legal_person: str = ""
    status: str = ""
    establish_date: str = ""
    registered_capital: str = ""
    address: str = ""
    business_scope: str = ""
    phone: str = ""


class EnterpriseClientPrefillOut(Schema):
    """企业信息预填结果。"""

    provider: str
    prefill: EnterpriseClientPrefillDataOut
    profile: EnterpriseCompanyProfileOut
    existing_client: EnterpriseDuplicateClientOut | None = None
