"""东盟域外法查明的 HTTP 契约。

数据源同 ``mcp_server.tools.foreign_law.asean_law``（BARLC 数据库）。HTTP 层
**不做**任何判定或改写：出参就是 MCP 工具的返回结构，前端/上层拿到的字段与
AI 工具面看到的一致，避免两套口径在「核验是否成立」上打架。

失败一律是 ``ok=false`` + ``reason``，不是 HTTP 5xx：
前端要能区分「查不到这条引用」与「这台机器没配 BARLC 账号」
（``credential_missing``），5xx 会把两者压成同一个红叉。
"""

from __future__ import annotations

from typing import Any

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
    as_of_date: str = Field(
        default="",
        max_length=10,
        description="引用时点（YYYY-MM-DD），如合同签署日或争议发生时点；给了才做时效比对",
    )
    contract_id: int | None = Field(default=None, description="关联合同 id（仅用于留痕归类，可空）")
    citation_anchor: str = Field(default="", max_length=128, description="合同内的锚点，如「第三条 租金」（可空）")


class ForeignLawVerifyOut(BaseModel):
    """``asean_law_verify`` 的返回结构（原样透出）。

    判定已在插件里完成（多判定器合议），这里**不再有**「等外部判定层比对」那一步：

    - ``verdict`` 可能是四个结论之一，也可能是 ``待判定``（没有结论）；
    - ``待判定`` 有两种成因，靠 ``adjudicated`` 区分：
      合议跑过但弃权（``true``，**不要再找模型判**）vs. 合议未开启（``false``）；
    - ``不存在该引用`` 是规则层直接判死，不消耗模型调用；
    - ``needs_human`` 为真时，前端**必须**把 ``review_reasons`` 展示出来，
      不能只给一个绿色 pill。
    """

    ok: bool
    verdict: str = ""
    law_title: str = ""
    section_number: str = ""
    section_text: str = ""
    reason: str = ""
    needs_model_judgement: bool = False
    claim: str = ""
    # ---- 多判定器合议结论面 ------------------------------------------------
    # 合议跑过 = 判定已经做完（包括「弃权」也是结论）；
    # 合议没跑（开关关闭）时才是 `needs_model_judgement=True`。
    adjudicated: bool = False
    #: 没有结论（区分它与「不存在该引用」）。
    unconfirmed: bool = False
    #: 结论可用但必须把复核提示带给律师。
    needs_human: bool = False
    review_reasons: list[str] = []
    #: 最高票 / 有效票；无有效票时为 null（**不是 0 分**）。
    agreement: float | None = None
    #: 怎么定位到这部法的：exact / containment / ambiguous。
    matched_by: str = ""
    #: 逐要件判定（律师问「哪一项没依据」的答案）。
    elements: list[dict[str, Any]] = []
    #: 判定器摘要（不含自由文本，避免白吃上下文）。
    votes: list[dict[str, Any]] = []
    #: 合议消耗的 token（与生成本分开记）。`cached=True` 时是上次的成本，不可重复求和。
    jury_tokens: int = 0
    #: 合议结果是否来自缓存。
    cached: bool = False
    # ---- 溯源与生效版本（申报书要求「注明国别、名称及生效版本」）--------------
    #: 该法在 BARLC（公开学术平台的代码内简称）的详情页地址，给律师点回原页。
    source_url: str = ""  # privacy-allow BARLC 是公开学术平台缩写，非客户机构
    effective_date: str = ""
    revise_date: str = ""
    #: 时效告警。非空时前端**必须**原样展示（如「生效日晚于引用时点」）。
    version_warnings: list[str] = []
    # 失败时 asean_law_* 回带的结构化原因（reason 枚举 + detail 原文）
    detail: str = ""
    # 调用轨迹：接入 → 登录 → 检索 → 取正文 → 切条款 → 取原文
    #
    # ⚠️ 这两个字段必须在这里声明：Ninja 按 response schema **过滤**返回字典，
    # 未声明的键会被静默丢掉（不报错、不告警），表现为"后端明明赋了值，
    # 前端拿不到"。踩过一次。
    total_ms: int = 0
    trace: list[dict[str, Any]] = []


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
