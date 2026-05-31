"""导入会话查询服务。"""

from __future__ import annotations

from typing import Any

from django.db.models import Q

from apps.oa_filing.models import CaseImportSession, ClientImportSession

def get_case_session_or_none(session_id: int) -> CaseImportSession | None:
    """获取案件导入会话，不存在返回 None。"""
    return CaseImportSession.objects.filter(pk=session_id).first()

def create_case_session(
    lawyer: Any,
    credential: Any,
    uploaded_filename: str = "",
) -> CaseImportSession:
    """创建案件导入会话。"""
    return CaseImportSession.objects.create(
        lawyer=lawyer,
        credential=credential,
        status="pending",
        uploaded_filename=uploaded_filename,
    )

def get_client_session_or_none(session_id: int) -> ClientImportSession | None:
    """获取客户导入会话，不存在返回 None。"""
    return ClientImportSession.objects.filter(pk=session_id).first()

def create_client_session(
    lawyer: Any,
    credential: Any,
) -> ClientImportSession:
    """创建客户导入会话。"""
    return ClientImportSession.objects.create(
        lawyer=lawyer,
        credential=credential,
        status="pending",
    )

def get_jtn_credential(lawyer_id: int) -> Any:
    """获取金诚同达 OA 凭证，不存在返回 None。"""
    from apps.organization.models import AccountCredential

    return AccountCredential.objects.filter(
        Q(account__icontains="jtn.com") | Q(url__icontains="jtn.com"),
        lawyer_id=lawyer_id,
    ).first()

def get_lawyer(lawyer_id: int) -> Any:
    """获取律师实例。"""
    from apps.organization.models import Lawyer

    return Lawyer.objects.get(pk=lawyer_id)

def client_exists_by_name(name: str) -> bool:
    """按名称检查客户是否存在。"""
    from apps.client.models import Client

    return Client.objects.filter(name=name).exists()

def client_exists_by_id_number(id_number: str) -> bool:
    """按身份证号检查客户是否存在。"""
    from apps.client.models import Client

    return Client.objects.filter(id_number=id_number).exists()

def create_client_for_import(
    *,
    name: str,
    client_type: str = "natural",
    phone: str = "",
    address: str = "",
    id_number: str | None = None,
    legal_representative: str = "",
) -> Any:
    """为导入创建客户。"""
    from apps.client.models import Client

    return Client.objects.create(
        name=name,
        client_type=client_type,
        phone=phone,
        address=address,
        id_number=id_number,
        legal_representative=legal_representative,
        is_our_client=True,
    )
