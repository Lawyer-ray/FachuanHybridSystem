"""案件 Admin 视图能力的聚合入口。

实现按职责拆在同目录的兄弟模块里：
- ``views_list_display``：列表页列展示
- ``views_detail``：详情页、材料页、changeform 扩展、自定义 URL 注册
- ``views_document_parse``：裁判文书解析、执行事项预览、临时上传
- ``views_folder_import``：打开本地文件夹、邮件文件夹导入
- ``views_coercion``：请求参数类型转换纯函数
"""

from __future__ import annotations

from .views_detail import (
    CaseAdminDetailViewsMixin,
    _get_case_stage_choices,
    _get_case_sync_integration,
    _get_contact_role_choices,
    _get_media_url,
    _has_court_filing_plugin,
    _log_inline_formset,
)
from .views_document_parse import CaseAdminDocumentParseMixin, _resolve_confined_temp_path
from .views_folder_import import CaseAdminFolderImportMixin
from .views_list_display import CaseAdminListDisplayMixin


class CaseAdminViewsMixin(  # pragma: no cover
    CaseAdminListDisplayMixin,
    CaseAdminDetailViewsMixin,
    CaseAdminDocumentParseMixin,
    CaseAdminFolderImportMixin,
):
    """案件管理后台视图Mixin，提供自定义URL和视图方法。

    只做聚合：MRO 顺序与方法来源见 ``CaseAdminListDisplayMixin`` /
    ``CaseAdminDetailViewsMixin`` / ``CaseAdminDocumentParseMixin`` /
    ``CaseAdminFolderImportMixin``，各组之间无同名方法，不存在互相覆盖。
    """


__all__: list[str] = ["CaseAdminViewsMixin"]
