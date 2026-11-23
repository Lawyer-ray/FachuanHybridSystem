"""生成文书的「同名文件已存在到第几版」探测（合同 / 补充协议共用）。

S48-48（2026-11-23 二轮审计）：原实现把「取绑定 → 解析子目录 → 列文件名 → 取最大版本号」
逐字复制在 `contract_generation_service._get_next_version` 与
`supplementary_agreement_generation_service._get_next_version`，而且两份已经分叉：合同份会把
模板名里的 `.docx` 剥掉再拼匹配模式，补充协议份不剥。于是 `agreement_name` 带扩展名时
`find_max_doc_version` 的正则永远匹配不上 → `max_version` 恒 0 → 永远返回 V1 →
同日重生成**覆盖旧文件**（`pipeline/naming.py` 注释里描述的那类事故）。
现在只有这一份实现，扩展名在 `pipeline.naming.strip_doc_extension` 里统一剥掉。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def probe_next_version(
    *,
    folder_binding_service: Any,
    binding: Any,
    doc_type: str,
    case_name: str,
    subdir_key: str,
) -> str:
    """探测绑定文件夹里「doc_type（case_name）Vn_今日.docx」的下一版本号。

    Args:
        folder_binding_service: 合同文件夹绑定服务（提供 `_resolve_subdir_path`）
        binding: 合同文件夹绑定行（`folder_path` / `storage_type` / 可选 `contract`）
        doc_type: 文书类型名（模板名 / 补充协议名，可带 `.docx` 扩展名）
        case_name: 案件（合同）名
        subdir_key: 子目录键名

    Returns:
        "V1"（首个版本）或 "V{n+1}"
    """
    # 函数内 import：测试按模块 patch `pipeline.naming._today_compact`，模块级绑定会绕过 patch
    from .pipeline.naming import _today_compact, find_max_doc_version, strip_doc_extension

    if not binding or not binding.folder_path:
        return "V1"

    # 构建子目录路径
    owner_type = binding.contract.case_type if hasattr(binding, "contract") else ""
    subdir_path = folder_binding_service._resolve_subdir_path(owner_type=owner_type, subdir_key=subdir_key)
    if not subdir_path:
        return "V1"

    # 获取文件名列表（云存储 vs 本地）
    storage_type = getattr(binding, "storage_type", "local")
    if storage_type != "local":
        from apps.cloud_storage.factory import create_provider_for_binding

        provider = create_provider_for_binding(binding)
        names: list[str] = []
        for _d, _s, files in provider.walk(subdir_path):
            names.extend(c.name for c in files if not c.is_dir)
    else:
        folder_path = Path(binding.folder_path) / subdir_path
        if not folder_path.exists():
            return "V1"
        names = [f.name for f in folder_path.iterdir() if f.is_file()]

    max_version = find_max_doc_version(
        names=names,
        doc_type=strip_doc_extension(doc_type),
        case_name=case_name,
        date_str=_today_compact(),
    )
    return f"V{max_version + 1}"
