"""检索类工具结果 → 引用（``CitationRef``）投影 + 本轮编号分配。

## 为什么需要它

前端早就把「入站引用」的渲染层做完了（``frontend/src/features/copilot/domain/
knowledge.ts`` 的 ``parseCiteMarkers``、``CitationMark.tsx`` 的角标与引用卡），
但后端**从不发引用**：``tool_result`` 只是把工具输出原样转给前端，模型在正文里
写「根据《民法典》第 X 条」时，那句话与任何一份材料都没有机器可读的对应关系。
结果就是律师最需要的那句话——「这句结论出自哪一条」——只能靠人工全文搜关键词。

本模块把「检索类工具返回的结构化命中」投影成 :class:`~apps.agent.sse_types.CitationRef`，
由编排层（``services/chat/stream.py``）随流推 ``citations`` 事件、并把本轮全部
引用落进 ``AgentMessage.metadata["citations"]``（历史回放没有 SSE，只有 metadata）。

## ``cite_no`` 的分配规则（**与模型的计数口径必须一致**）

模型要在正文里写 ``[K<编号>]``，而它看不到后端分配的编号。所以编号规则必须是
**模型能从自己看到的工具结果里推出来的**：

1. 只有 :data:`CITABLE_TOOLS` 里的工具参与编号——这份清单同时写进了系统提示词
   （``apps/agent/pi/AGENTS.md``），由 ``test_agent_citations`` 扫文本做同源比对；
2. 每轮从 ``1`` 开始（跨轮重新从 1 开始，与前端角标的「本轮」语义一致）；
3. 按**工具调用的发生顺序**累计，单次调用内部按**结果数组的顺序**；
4. **不合并、不重排、不跳过**：同一条案件被两次检索命中就占两个号。

第 4 条看起来「不优雅」，但它是安全的唯一前提：编号一旦去重，后面所有号都会
前移，模型算出的 ``[K5]`` 会指向另一份材料——**错的引用比没有引用更糟**（律师
拿它去写文书）。宁可有两条角标指向同一份材料，也不能让任何一条指错。

同理，``MAX_CITES_PER_TURN`` 只会**截掉尾部**（前缀不变）、单个命中缺 ``name``
才会被跳过（退化数据），两者都不会移动已分配的号。

## 什么不产引用（宁缺勿错）

- **纯文本 / Markdown 结果**：解析不出结构就没有定位信息，硬造一个 ``name``
  只会得到一条点开是空的卡片；
- **无结构化定位的命中**：必须有 ``name``，且至少有一个定位（``ref_id`` /
  ``page`` / ``clause`` / ``chunk_id``）。案件/合同没有页码，它们的定位就是
  ``ref_id``（点开跳详情页）——这正是前端 ``CitationKind`` 里同时有 ``case`` /
  ``contract`` 的原因；
- ``read_agent_attachment`` / ``read_folder_file``：返回的是 content blocks
  （正文或页图），只有「第 N 页」这种自由文本，没有结构化页码字段 → 当前不产引用
  （这是 ``kind="file"`` 暂时不可达的原因，见文末「未覆盖」）。

## 截断：只能拿到结果的前 2000 字

``tool_result.result`` 在 ``pi/bridge.py`` 被截到 2000 字（前端 Guide 与
``domain/reference.ts`` 都依赖这个事实：长正文靠 ``tool_call.arguments`` 那一路
才完整）。所以这里先 ``json.loads``，失败再按容器键**逐个解码完整对象**，
只取「确实完整的那些前缀项」——被截断的半个对象绝不解码成一条缺字段的引用。
后果是长列表只有前几条能编号：模型写到的尾部 ``[Kn]`` 会因「已知编号里没有它」
被前端丢弃（降级成普通文本），而不会指错。

## 未覆盖（下一步）

- ``kind="file"``：需要解析器回传结构化的 ``{file, page, chunk_id}``（当前
  ``/document-parsing/extract-text`` 只回一整段 ``text``）；
- ``chunk_id``：本仓库还没有向量/切片检索，字段先占位；
- **在带内编号**（最彻底的解法）：由 MCP 工具自己在返回体里写 ``[Kn]``，
  模型直接抄，不必数命中——那需要改 ``mcp_server`` 并重启共享 MCP，本轮不做。
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from ...backends.toolface import tool_prefix
from ...sse_types import CitationRef

logger = logging.getLogger(__name__)

#: 一轮最多记多少条引用。截断只发生在**尾部**（见模块 docstring 第 4 条），
#: 所以对已分配的编号没有影响。60 的来源：默认 ``list_cases`` 40 条 + 一次
#: 类案检索 5 条 + 法条核查若干，够覆盖「一轮把材料翻一遍」的真实用法，
#: 而 metadata 体积仍留在 ~20KB 以内。
MAX_CITES_PER_TURN = 60

#: 单条引用的 ``text``（原文片段）上限：它要进 metadata、也进每次 SSE 帧。
#: 角标卡片只显示两三行，再长就是白占带宽。
CITE_TEXT_LIMIT = 300

#: MCP 工具全名前缀（``mcp__fachuan__``）——模型侧的工具名带前缀，事件里也是。
_TOOL_PREFIX = tool_prefix()

#: 结果里装命中的容器键（按顺序取，全部命中都算）。
#: 这些名字**逐个核对过真实后端响应**，不是猜的：
#: - ``items``：``tool_shaping.list_result`` 的信封（``search_cases`` /
#:   ``list_cases`` / ``list_contracts`` / ``list_research_results``）；
#: - ``references``：``verify_citations`` / ``check_law_references``；
#: - ``results``：``capability_search``（``AgentSearchResponseV1.results``）；
#: - ``cases`` / ``contracts``：``global_search``（``GlobalSearchResult``）。
_CONTAINER_KEYS = ("items", "references", "results", "cases", "contracts")


def normalize_tool_name(name: str) -> str:
    """``mcp__fachuan__search_cases`` → ``search_cases``（其它 server 也剥前缀）。

    与 ``services/approval/risk.short_tool_name`` 同义，但那边 import Django
    模型（一整套审批表），本模块要在纯函数测试里单独 import，所以只依赖
    stdlib-only 的 ``backends.toolface``。
    """
    if not name:
        return ""
    if name.startswith(_TOOL_PREFIX):
        return name[len(_TOOL_PREFIX) :]
    return name.rsplit("__", 1)[-1]


# ── 小工具 ──────────────────────────────────────────────────────────────


def _as_int(value: Any) -> int | None:
    """转成 ``int``；转不了返回 ``None``（**不猜、不补 0**）。"""
    if isinstance(value, bool) or value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_text(value: Any, limit: int = CITE_TEXT_LIMIT) -> str:
    """把任意字段压成一段可展示的短文本（截断到 ``limit``）。"""
    if value in (None, ""):
        return ""
    if isinstance(value, Mapping):
        value = " ".join(str(item) for item in value.values())
    elif isinstance(value, (list, tuple)):
        value = " ".join(str(item) for item in value)
    return str(value).strip()[:limit]


def _hit(
    kind: str,
    name: str,
    *,
    ref_id: int | None = None,
    page: int | None = None,
    clause: str | None = None,
    chunk_id: int | None = None,
    text: str = "",
) -> dict[str, Any] | None:
    """一条命中的引用参数；``name`` 为空 → ``None``（没有可展示的标题就不产引用）。"""
    if not name:
        return None
    return {
        "kind": kind,
        "name": name,
        "ref_id": ref_id,
        "page": page,
        "clause": clause or None,
        "chunk_id": chunk_id,
        "text": text,
    }


# ── 各工具的命中投影（字段名逐个核对过真实响应结构）─────────────────────


def _case_hit(item: Mapping[str, Any]) -> dict[str, Any] | None:
    """案件命中。

    字段来源：``mcp_server/tools/cases/cases.py:73`` 的 ``search_cases``（信封
    ``items``，经 ``projection.CASE_LIST_FIELDS`` 投影）与 ``apps/core/api/
    search_api.py`` 的 ``global_search.cases``（``SearchResultItem``：
    ``id`` / ``title`` / ``subtitle``=案号）。两者都用 ``name``/``title`` 兜一遍：
    同一份投影在前端两个入口里叫法不同，取到哪个算哪个。

    ``clause`` 装**案号**（``filing_number`` / 全局搜索的 ``subtitle``）：案件
    没有页码，案号是它最接近「定位」的东西，也是律师核对时的第一眼标识。
    """
    return _hit(
        "case",
        _as_text(item.get("name") or item.get("title")),
        ref_id=_as_int(item.get("id")),
        clause=_as_text(item.get("filing_number") or item.get("subtitle"), 64),
        text=_as_text(item.get("cause_of_action") or item.get("current_stage"), 120),
    )


def _contract_hit(item: Mapping[str, Any]) -> dict[str, Any] | None:
    """合同命中（``list_contracts`` 的 ``items`` / ``global_search.contracts``）。"""
    return _hit(
        "contract",
        _as_text(item.get("name") or item.get("title")),
        ref_id=_as_int(item.get("id")),
        clause=_as_text(item.get("filing_number") or item.get("subtitle"), 64),
        text=_as_text(item.get("case_type_label") or item.get("status_label"), 120),
    )


def _statute_hit(item: Mapping[str, Any]) -> dict[str, Any] | None:
    """法条命中（``verify_citations`` / ``check_law_references`` 的 ``references``）。

    字段来源：``mcp_server/tools/legal_research/citation_check.py:99`` 的
    ``_extract_statutes`` 产物（``law_name`` / ``article_num`` /
    ``article_num_raw`` / ``paragraph`` / ``raw``）与
    ``apps/legal_research/services/law_verification_service.py:119`` 的回填
    （``article_text`` / ``reference_text``）。

    ``clause`` 用 ``article_num_raw``（中文原样，「第一千零七十九条」）优先：
    律师认的是中文条号，阿拉伯数字只在缺失时兜底。
    """
    law_name = _as_text(item.get("law_name"))
    if not law_name:
        return None
    # ``article_num_raw`` 来自 ``_STATUTE_RE`` 的 ``article`` 组（**不含**「条」），
    # 但上游若自己带了「条/款」后缀也不能拼成「第一千零七十九条条」——
    # 这类重复在界面上看不出是 bug，只会让律师觉得系统不严谨。
    article = _as_text(item.get("article_num_raw") or item.get("article_num"), 24).rstrip("条款")
    clause = f"第{article}条" if article else ""
    paragraph = _as_text(item.get("paragraph"), 12).rstrip("款")
    if paragraph:
        clause = f"{clause}第{paragraph}款" if clause else f"第{paragraph}款"
    return _hit(
        "statute",
        law_name,
        clause=clause,
        text=_as_text(item.get("article_text") or item.get("reference_text") or item.get("raw")),
    )


def _judgment_hit(item: Mapping[str, Any]) -> dict[str, Any] | None:
    """类案命中（``list_research_results`` 的 ``items``）。

    字段来源：``apps/legal_research/schemas/legal_research_schemas.py`` 的
    ``LegalResearchResultOut``（``id`` / ``title`` / ``document_number`` /
    ``case_digest`` / ``similarity_score``）。
    """
    return _hit(
        "judgment",
        _as_text(item.get("title")),
        ref_id=_as_int(item.get("id")),
        clause=_as_text(item.get("document_number"), 64),
        text=_as_text(item.get("case_digest")),
    )


def _capability_hit(item: Mapping[str, Any]) -> dict[str, Any] | None:
    """类案检索（``capability_search`` 的 ``results``，``RetrievalHitV1``）。

    ``doc_id`` 是**字符串**（威科先行侧的文档号），而契约里 ``ref_id`` 是
    ``int | None``——塞不进去，所以这里 ``ref_id`` 留空（角标能看不能跳）。
    这是刻意的次优选择：为它把契约改成 ``int | str`` 会让前端为每个 kind
    各写一次类型判断，代价大于收益。
    """
    snippets = item.get("snippets")
    snippet = ""
    if isinstance(snippets, Mapping):
        snippet = _as_text(snippets.get("reasoning") or snippets.get("holdings") or snippets.get("findings"))
    return _hit(
        "judgment",
        _as_text(item.get("title")),
        clause=_as_text(item.get("court"), 64),
        text=snippet or _as_text(item.get("why_selected")),
    )


#: 单条命中 → 引用参数（``None`` = 这条命中不产引用）。
_HitFn = Callable[[Mapping[str, Any]], "dict[str, Any] | None"]


@dataclass(frozen=True)
class _ToolSpec:
    """一个检索类工具的投影规则：``(容器键, 单条投影)`` 按顺序排列。

    **容器键必须与投影配对**，不能只给一串容器键再共用一个投影函数：
    ``global_search`` 的 ``cases`` / ``contracts`` 两条数组里各是``SearchResultItem``
    （``id`` + ``title``），字段名一模一样，只有容器名能区分种类。
    共用一个投影时合同会被追加成「案件」——引用卡片就会跳到错误的详情页。
    """

    rules: tuple[tuple[str, _HitFn], ...]


#: **可引用工具清单**——同时是「模型的计数口径」和「后端取数的白名单」。
#:
#: 这份清单必须与 ``apps/agent/pi/AGENTS.md`` 里写给模型的那段逐名一致
#: （``test_agent_citations.test_prompt_lists_every_citable_tool`` 会扫文本比对）。
#: 少写一个工具，模型就会为一个后端不认的号写 ``[Kn]``（角标消失）；
#: 多写一个工具，编号会整体前移（角标指错）——两个方向都必须在改清单时同步提示词。
TOOL_SPECS: dict[str, _ToolSpec] = {
    # 案件检索 / 浏览
    "search_cases": _ToolSpec((("items", _case_hit),)),
    "list_cases": _ToolSpec((("items", _case_hit),)),
    # 合同检索 / 浏览
    "list_contracts": _ToolSpec((("items", _contract_hit),)),
    # 跨模块关键词搜索：案件、合同两类命中都算（靠容器键区分种类）
    "global_search": _ToolSpec((("cases", _case_hit), ("contracts", _contract_hit))),
    # 法条核查（两个工具同一份 references 结构）
    "verify_citations": _ToolSpec((("references", _statute_hit),)),
    "check_law_references": _ToolSpec((("references", _statute_hit),)),
    # 类案检索
    "list_research_results": _ToolSpec((("items", _judgment_hit),)),
    "capability_search": _ToolSpec((("results", _capability_hit),)),
}

#: 参与编号的工具短名（提示词侧的同源清单）。
CITABLE_TOOLS: frozenset[str] = frozenset(TOOL_SPECS)


# ── 结果解析（截断也要拿到完整前缀）─────────────────────────────────────


def _parse(text: str) -> Any:
    """尽力把工具结果文本解析成 JSON；失败返回 ``None``（调用方走救急前缀解码）。"""
    stripped = (text or "").strip()
    if not stripped or stripped[0] not in "{[":
        return None
    try:
        return json.loads(stripped)
    except (TypeError, ValueError):
        return None


def _salvage_prefix_objects(text: str, containers: Iterable[str]) -> list[dict[str, Any]]:
    """从**被截断**的 JSON 里按容器键解出完整的对象前缀。

    为什么不能只 ``json.loads``：``tool_result.result`` 被截到 2000 字
    （见模块 docstring「截断」一节），``search_cases(limit=10)`` 的投影结果就有
    3~4KB——整段解析必然失败，而失败就等于「这条工具调用一条引用都不产」，
    正好丢掉最常用的检索路径。

    这里用 ``json.JSONDecoder.raw_decode`` 从容器数组的 ``[`` 之后**逐个对象**
    解码：只接受语法完整的对象，遇到第一个解不动的位置（被截断的那个）立即停止。
    半个对象绝不被接受——否则会产出一条 ``name`` 对、``ref_id`` 错（或相反）
    的引用，那正是最坏的结果。
    """
    decoder = json.JSONDecoder()
    found: list[dict[str, Any]] = []
    for container in containers:
        match = re.search(rf'"{container}"\s*:\s*\[', text)
        if match is None:
            continue
        index = match.end()
        while len(found) < MAX_CITES_PER_TURN:
            brace = text.find("{", index)
            if brace < 0:
                break
            try:
                obj, end = decoder.raw_decode(text, brace)
            except ValueError:
                break
            if isinstance(obj, dict):
                found.append(obj)
            index = end
        if found:
            break
    return found


def project_result(tool_name: str, result: str | None) -> list[dict[str, Any]]:
    """一次工具结果 → 若干条引用参数（``cite_no`` 尚未分配）。

    Args:
        tool_name: 事件里的工具名（可带 ``mcp__fachuan__`` 前缀）。
        result: ``ToolResultEvent.result``（**可能被截断**的 JSON 文本）。

    Returns:
        按命中顺序排列的参数 dict 列表；该工具不产引用时是空列表。
    """
    spec = TOOL_SPECS.get(normalize_tool_name(tool_name))
    if spec is None or not result:
        return []

    payload = _parse(result)
    hits: list[dict[str, Any]] = []
    first_rule = spec.rules[0]
    for container, project in spec.rules:
        if isinstance(payload, Mapping):
            raw = payload.get(container)
            items: list[Any] = list(raw) if isinstance(raw, list) else []
        elif isinstance(payload, list):
            # 裸数组结果（工具直接 return 列表、未经 list_result 信封化）：只能
            # 按第一条规则解释——多容器工具（global_search）不会是裸数组。
            items = list(payload) if container == first_rule[0] else []
        else:
            items = list(_salvage_prefix_objects(result, (container,)))
        for item in items:
            if not isinstance(item, Mapping):
                continue
            projected = project(item)
            if projected is not None:
                hits.append(projected)
    return hits


# ── 本轮编号分配 ────────────────────────────────────────────────────────


@dataclass
class CitationCollector:
    """一轮对话的引用分配器：``cite_no`` 单调递增，跨轮从 1 重新开始。

    为什么是「轮级对象」而不是函数式：编号要跨工具调用累计，且本轮全部引用
    最后要一次性写进 ``AgentMessage.metadata["citations"]``（历史回放靠它重建
    角标）。把状态放在一个显式对象里，多答时每栏各持一个——三栏的正文各自
    编号，互不干扰（前端也是按栏渲染角标的）。
    """

    _all: list[CitationRef] = field(default_factory=list)
    _next_no: int = 1
    #: 已经打满 ``MAX_CITES_PER_TURN`` 后只记一次日志，不刷屏。
    _capped: bool = False

    def ingest(self, *, tool_name: str, result: str | None) -> list[CitationRef]:
        """吃进一次工具结果，返回**本次新增**的引用（已带 ``cite_no``）。"""
        try:
            hits = project_result(tool_name, result)
        except Exception:
            # 引用是附加价值：任何解析意外都不能影响对话本身（这条路径在 SSE
            # 循环里，抛出去会中断整轮回答）。
            logger.warning("引用投影失败（不影响对话）tool=%s", tool_name, exc_info=True)
            return []

        new_refs: list[CitationRef] = []
        for params in hits:
            if self._next_no > MAX_CITES_PER_TURN:
                if not self._capped:
                    self._capped = True
                    logger.info(
                        "本轮引用已达上限 %s 条，后续命中不再编号 tool=%s",
                        MAX_CITES_PER_TURN,
                        normalize_tool_name(tool_name),
                    )
                break
            ref = CitationRef(cite_no=self._next_no, **params)
            self._next_no += 1
            self._all.append(ref)
            new_refs.append(ref)
        return new_refs

    @property
    def all(self) -> list[CitationRef]:
        """本轮已分配的全部引用（按 ``cite_no`` 升序）。"""
        return list(self._all)

    def wire(self, refs: Iterable[CitationRef] | None = None) -> list[dict[str, Any]]:
        """序列化成线路/落库用的 dict（``None`` 字段不出现，帧更小）。

        键名保持 **snake_case**（``cite_no`` 而不是 ``citeNo``）：TS 生成物由
        ``sse_types`` 反射而来，同样是 ``cite_no``，前端负责映射成 ``citeNo``。
        落库也用它——metadata 里的历史数据必须是同一套键名，否则刷新后重建
        角标的代码要写两套。
        """
        source = self._all if refs is None else list(refs)
        return [ref.model_dump(exclude_none=True) for ref in source]


__all__ = [
    "CITABLE_TOOLS",
    "CITE_TEXT_LIMIT",
    "MAX_CITES_PER_TURN",
    "TOOL_SPECS",
    "CitationCollector",
    "normalize_tool_name",
    "project_result",
]
