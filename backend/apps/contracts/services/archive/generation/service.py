"""归档文书批量生成服务 facade。

保持 ArchiveGenerationService 的公共 API 不变，内部实现委托给子模块。
新增 async 版本（_a 前缀），CPU 密集操作通过 asyncio.to_thread 卸载。
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from apps.contracts.models import Contract

from . import document_generator as doc_gen
from . import download_handler, folder_builder, pdf_utils, template_finder


class ArchiveGenerationService:
    """归档文书批量生成服务"""

    # ---- 模板路径查找 ----

    def get_template_path(self, template_subtype: str, contract: Contract | None = None) -> Path | None:
        return template_finder.get_template_path(template_subtype, contract)

    # ---- 预览 ----

    def preview_archive_template(self, contract_id: int, template_subtype: str) -> dict[str, Any]:
        return doc_gen.preview_archive_template(contract_id, template_subtype)

    # ---- 文书生成 ----

    def generate_archive_documents(
        self,
        contract: Contract,
        case: Any | None = None,
    ) -> list[dict[str, Any]]:
        return doc_gen.generate_archive_documents(contract, case)

    def generate_single_archive_document(
        self,
        contract: Contract,
        archive_item_code: str,
        case: Any | None = None,
    ) -> dict[str, Any]:
        return doc_gen.generate_single_archive_document(contract, archive_item_code, case)

    # ---- 下载 ----

    def download_archive_item(
        self,
        contract: Contract,
        archive_item_code: str,
    ) -> dict[str, Any]:
        return download_handler.download_archive_item(contract, archive_item_code)

    # ---- 归档文件夹 ----

    def generate_archive_folder(self, contract: Contract) -> dict[str, Any]:
        return folder_builder.generate_archive_folder(contract)

    async def agenerate_archive_folder(self, contract: Contract) -> dict[str, Any]:
        """异步版归档文件夹生成（CPU 密集，卸载到线程池）。"""
        return await asyncio.to_thread(folder_builder.generate_archive_folder, contract)

    # ---- PDF 工具 ----

    def scale_pages_to_a4(self, contract: Contract) -> dict[str, Any]:
        return pdf_utils.scale_pages_to_a4(contract)

    async def ascale_pages_to_a4(self, contract: Contract) -> dict[str, Any]:
        """异步版 A4 缩放（CPU 密集，卸载到线程池）。"""
        return await asyncio.to_thread(pdf_utils.scale_pages_to_a4, contract)
