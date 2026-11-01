"""东盟域外法查明的 HTTP 契约。

数据源同 ``mcp_server.tools.foreign_law.asean_law``（BARLC 数据库）。HTTP 层
**不做**任何判定或改写：出参就是 MCP 工具的返回结构，前端/上层拿到的字段与
AI 工具面看到的一致，避免两套口径在「核验是否成立」上打架。

失败一律是 ``ok=false`` + ``reason``，不是 HTTP 5xx：
前端要能区分「查不到这条引用」与「这台机器没配 BARLC 账号」
（``credential_missing``），5xx 会把两者压成同一个红叉。
"""

from __future__ import annotations

from pydantic import BaseModel, Field

# BARLC 国别代码（如 LAWCOUNTRYTG）是 8–20 位大写字母，历史上有带数字后缀的。
# 只做长度/字符集约束，不枚举——国家列表随数据库变化，写死会在新增国别时假拒。
_COUNTRY_CODE_PATTERN = r"^[A-Z0-9]{2,32}$"


class ForeignLawVerifyIn(BaseModel):
    """核验一条域外法引用。"""

    law_name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="被引用的法律名称（中文或英文），如「民商法典」；不要带「泰国」前缀",
    )
    section_number: str = Field(default="", max_length=32, description="条款号，如 538；留空则只核验法律是否存在")
    claim: str = Field(default="", max_length=2000, description="该引用所要支持的主张；留空则只核验条款是否存在")
    country_code: str = Field(
        default="",
        max_length=32,
        pattern=f"^$|{_COUNTRY_CODE_PATTERN}",
        description="BARLC 国别代码，如 LAWCOUNTRYTG（泰国）；留空则全东盟检索",
    )


class ForeignLawVerifyOut(BaseModel):
    """``asean_law_verify`` 的返回结构（原样透出）。

    成功时 ``verdict == "待判定"`` 表示条文已取到，需判定层比对 ``section_text``
    与 ``claim``；``"不存在该引用"`` 是规则层直接判死，不消耗模型调用。
    """

    ok: bool
    verdict: str = ""
    law_title: str = ""
    section_number: str = ""
    section_text: str = ""
    reason: str = ""
    needs_model_judgement: bool = False
    claim: str = ""
    # 失败时 asean_law_* 回带的结构化原因（reason 枚举 + detail 原文）
    detail: str = ""


class ForeignLawSearchHitOut(BaseModel):
    sys_id: str
    title_cn: str = ""
    title_en: str = ""
    title_local: str = ""
    publish_date: str | None = None
    effective_date: str | None = None


class ForeignLawSearchOut(BaseModel):
    """``asean_law_search`` 的返回结构（原样透出）。"""

    ok: bool
    total: int = 0
    page: int = 1
    hits: list[ForeignLawSearchHitOut] = Field(default_factory=list)
    reason: str = ""
    detail: str = ""


class ForeignLawCountryOut(BaseModel):
    code: str
    name_cn: str = ""
    name_en: str = ""
    sys_id: int = 0


class ForeignLawCountriesOut(BaseModel):
    """``asean_law_countries`` 的返回结构（原样透出）。"""

    ok: bool
    count: int = 0
    countries: list[ForeignLawCountryOut] = Field(default_factory=list)
    reason: str = ""
    detail: str = ""
