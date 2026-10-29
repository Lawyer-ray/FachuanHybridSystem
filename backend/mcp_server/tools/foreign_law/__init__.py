"""东盟域外法查明 MCP tools（foreign_law 域）。

单开一个域而不是并进 `legal_research`，原因：`legal_research` 是境内案例检索
（威科），法源、数据结构、失败模式都不同；且申报书把「域外法查明」定位为可
独立接入的模块，域边界与产品边界保持一致。
"""

from .asean_law import asean_law_countries, asean_law_read, asean_law_search, asean_law_verify

__all__ = [
    "asean_law_countries",
    "asean_law_search",
    "asean_law_read",
    "asean_law_verify",
]
