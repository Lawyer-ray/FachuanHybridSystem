"""客户关联案件/合同查询端口。

封装对 cases / contracts 模块的依赖（含其各自的访问策略），
供 client 查询门面调用，避免 Service 层跨模块导入 Model。
"""

from __future__ import annotations

from typing import Any, Protocol


class RelatedItemsPort(Protocol):
    """关联案件/合同查询端口。"""

    def get_related_items(self, *, client_id: int, user: Any | None) -> dict[str, list[dict[str, Any]]]:
        """返回客户关联且查询用户有权访问的案件/合同。"""
        ...
