"""案件合同关联查询服务。"""

from __future__ import annotations

from typing import Any

from apps.cases.models import Case


def get_case_or_none(case_id: int) -> Any:  # pragma: no cover
    """获取案件实例，不存在返回 None。"""
    return Case.objects.filter(pk=case_id).first()


def get_case_contract_info(case_id: int) -> Any:  # pragma: no cover
    """获取案件绑定的合同 ID 和文件夹绑定 ID。

    Returns:
        dict with keys: contract_id, contract__folder_binding__id，无匹配返回 None。
    """
    return Case.objects.filter(pk=case_id).values("contract_id", "contract__folder_binding__id").first()


def get_active_template_or_none(template_id: int) -> Any:  # pragma: no cover
    """获取激活的文档模板，不存在或未激活返回 None。"""
    from apps.documents.models import DocumentTemplate

    return DocumentTemplate.objects.filter(pk=template_id, is_active=True).first()
