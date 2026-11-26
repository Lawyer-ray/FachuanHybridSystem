"""一句话起草：文书类型 → 骨架 → 填槽 → 渲染 → 落位 → 落盘。

## 一句话省掉了哪三件事

`POST /draft`（`draft_service.draft_contract`）要求调用方自己挑 `template_id`、自己算目标
目录、自己给文件名——那是「模板库」的语气，不是律师的语气。律师说的是「出一份管辖权异议」，
整句话里只有**文书类型**一个信息，剩下三件都得由系统定：

| 要定的事 | 由谁定 |
|:--|:--|
| 用哪份骨架 | `DocumentSpec.skeleton_template`（一行数据，不是让模型现场发挥） |
| 每个槽填什么 | `spec_service.resolve_slot_values`（事实优先，缺的走 pending） |
| 放进哪个目录 | `DocumentSpec.folder_slot` + `SlotResolutionService.find_slot_paths` |

所以本模块**不生成格式**。「AI 不会异想天开出一种不存在的文书」这件事在这里是结构性的：
它连排版动作都没有，只有「填哪几个槽」的选择权。

## 为什么起草不拍快照

`snapshot_service.capture()` 的语义是「覆盖之前先存一份旧内容」，而这里是**新建文件**——
之前没有旧内容可留，与 `draft_service.draft_contract()` 同口径。AI 原稿的基线不用额外留：
律师第一次在画布上保存时，被覆盖掉的正是这份原稿，`domain_registry` 的保存回写会先拍快照。

## 全或无

槽位解析、渲染、落位判定全部在写盘**之前**完成；写盘只有一次（`write_service.create_file`，
内部 tmp + `os.replace`，同名自动加序号、绝不覆盖）。写盘之后只剩两件增强——未决项批注与
自动初审。它们失败不回滚文件：正文里仍有 `<待填写：x>` 可见占位，成稿本身完整可用；把刚写好
的文件再删掉，等于把律师眼前的东西凭空抽走，比「批注少了」更难解释。

## 落位只降级一级

`folder_slot` 零命中时**只**降级到 `other_filing`；它也没有就 `created=False` 并说清「这个案件
的文件夹里没有 X 的位置」。多试几个 kind 就是猜路径，而落错位置比不落更糟：律师会以为文书
已经生成好了。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import InvalidOperation
from pathlib import Path
from typing import Any, Callable

from apps.core.exceptions import ValidationException
from apps.documents.services.draft import spec_service

from . import draft_service, write_service

logger = logging.getLogger(__name__)

LLMCaller = Callable[[list[dict[str, str]]], str]

#: `folder_slot` 在某个案件的文件夹模板里不存在时的**唯一**降级目标。
#: 写死这一个（而不是「再找一个别的」）：`other_filing` 是《民事诉讼文书样式》里
#: 「其他立案材料」那个兜底格子，律师一眼知道该去那里翻。
DEGRADED_SLOT = "other_filing"

_NO_SKELETON_REASON = (
    "「{doc_type}」还没有骨架：文书规格（DocumentSpec）里没有这一项。"
    "先在文书规格里建一条（骨架模板 + 各槽来源 + 落位槽位），之后每次都能一句话出——"
    "现在**不会**替你猜一种格式。"
)

_OWNER_REASON = (
    "case_id 与 contract_id 必须二选一：文书要落进某个项目文件夹，两个都不给就没有落点，"
    "两个都给说明引用块读串了——猜一个就是写进别人的案卷。"
)


@dataclass
class _OwnerRef:
    """文书落在谁的文件夹里（`kind`/`owner_id` 与写通道同一套坐标）。"""

    kind: str
    owner_id: int
    target: Any


def draft_document(
    *,
    doc_type: str,
    case_id: int | None = None,
    contract_id: int | None = None,
    facts: dict[str, str] | None = None,
    instruction: str = "",
    auto_review: bool = True,
    user: Any = None,
    org_access: Any = None,
) -> dict[str, Any]:
    """按文书类型起草一份文书并落进项目文件夹的对应位置。

    返回体与 `DocDraftByTypeOut` 逐键对应；`created=False` 时只有 `reason` / `warnings` 有内容，
    **不留任何半成品文件**。

    Args:
        doc_type: 律师嘴里的文书类型（= `DocumentSpec.doc_type`）。
        case_id / contract_id: 二选一，决定落到哪个项目文件夹。
        facts: 律师显式给出的事实，优先级最高（金额/日期这类不交模型）。
        instruction: 律师那句话里除文书类型外的补充，会作为额外要求交给填槽的模型。
        auto_review: 起草完是否顺手排一轮初审（沿用 `review_pipeline` 的轮次）。
    """
    doc_type = (doc_type or "").strip()
    if not doc_type:
        return _rejected("", "doc_type 不能为空：律师说的「出一份 X」里那个 X 就是它")

    spec = spec_service.get_spec(doc_type)
    if spec is None:
        return _rejected(doc_type, _NO_SKELETON_REASON.format(doc_type=doc_type))

    owner, reason = _resolve_owner(case_id=case_id, contract_id=contract_id, user=user, org_access=org_access)
    if owner is None:
        return _rejected(doc_type, reason)

    template_bytes = _skeleton_bytes(spec)
    if template_bytes is None:
        return _rejected(
            doc_type,
            f"「{doc_type}」的骨架模板取不到文件：文书规格里没挂骨架模板，或模板文件已不在原路径。"
            "补上骨架模板再试——格式只能来自模板，这里不会现造。",
        )

    case = owner.target if owner.kind == write_service.KIND_CASE else None
    contract = owner.target if owner.kind == write_service.KIND_CONTRACT else None
    given = {str(key): str(value) for key, value in (facts or {}).items()}
    merged = _build_facts(case=case, contract=contract, given=given)
    raw_context, pending = spec_service.resolve_slot_values(
        spec, case=case, contract=contract, facts=merged, llm_caller=_llm_caller(instruction)
    )
    context = {str(key): _to_docx_text(str(value)) for key, value in raw_context.items()}

    rendered = draft_service.render(template_bytes, context, pending=pending)
    rendered = _apply_title_override(rendered, str(getattr(spec, "title_override", "") or ""))
    rendered = _apply_headings(rendered, _heading_overrides(spec=spec, context=context))

    folder_template = _folder_template_for(owner.kind, owner.target)
    warnings: list[str] = []
    if folder_template is None:
        return _rejected(
            doc_type,
            f"案件/合同 {owner.owner_id} 没有匹配的文件夹模板，无从判断「{spec.display_name or doc_type}」该放哪。"
            "先给这类项目配一个文件夹模板——这里不会自己挑一条路径。",
        )
    placement, placement_warnings = _placement_for(spec=spec, folder_template=folder_template)
    warnings.extend(placement_warnings)
    if placement is None:
        return _rejected(
            doc_type,
            f"这个案件的文件夹里没有「{spec.display_name or doc_type}」的位置："
            f"槽位「{spec.folder_slot or '（未声明）'}」与兜底槽「{DEGRADED_SLOT}」在文件夹模板里都没找到。"
            "先补文件夹模板的槽位，或告诉我该放哪个目录。",
            warnings,
        )

    created = write_service.create_file(
        kind=owner.kind,
        owner_id=owner.owner_id,
        subpath_dir="/".join(placement),
        name=spec.display_name or doc_type,
        raw_docx=rendered,
        user=user,
        org_access=org_access,
    )
    warnings.extend(
        _comment_pending(
            kind=owner.kind,
            owner_id=owner.owner_id,
            subpath=created["subpath"],
            pending=pending,
            user=user,
            org_access=org_access,
        )
    )
    review_run_id = _queue_review(
        enabled=auto_review,
        kind=owner.kind,
        owner_id=owner.owner_id,
        subpath=created["subpath"],
        user=user,
        org_access=org_access,
    )

    total = len(context) + len(pending)
    logger.info(
        "一句话起草落盘: doc_type=%s %s/%s -> %s（已填 %d，待填 %d）",
        doc_type,
        owner.kind,
        owner.owner_id,
        created["subpath"],
        len(context),
        len(pending),
    )
    return {
        "created": True,
        "doc_type": doc_type,
        "name": created["name"],
        "subpath": created["subpath"],
        "file_url": created["file_url"],
        "filled": context,
        "pending": list(pending),
        "slot_fill_rate": round(len(context) / total, 4) if total else 1.0,
        "review_run_id": review_run_id,
        "warnings": warnings,
        "reason": "",
    }


def _rejected(doc_type: str, reason: str, warnings: list[str] | None = None) -> dict[str, Any]:
    """「不生成」的统一回执：`reason` 必须能直接念给律师听。"""
    logger.info("一句话起草未生成: doc_type=%s reason=%s", doc_type, reason)
    return {
        "created": False,
        "doc_type": doc_type,
        "name": "",
        "subpath": "",
        "file_url": "",
        "filled": {},
        "pending": [],
        "slot_fill_rate": 0.0,
        "review_run_id": None,
        "warnings": list(warnings or []),
        "reason": reason,
    }


def _resolve_owner(
    *, case_id: int | None, contract_id: int | None, user: Any, org_access: Any
) -> tuple[_OwnerRef | None, str]:
    """`case_id` / `contract_id` 二选一 → 落位坐标 + 只读视图（DTO，不是 ORM 实例）。"""
    if (case_id is None) == (contract_id is None):
        return None, _OWNER_REASON
    if case_id is not None:
        return _OwnerRef(
            kind=write_service.KIND_CASE, owner_id=case_id, target=_load_case(case_id, user, org_access)
        ), ""
    assert contract_id is not None
    contract = _load_contract(contract_id)
    if contract is None:
        return None, f"合同 {contract_id} 不存在"
    return _OwnerRef(kind=write_service.KIND_CONTRACT, owner_id=contract_id, target=contract), ""


def _load_case(case_id: int, user: Any, org_access: Any) -> Any:
    """案件只读视图。走 `CaseQueryService` 是为了**带上行级 ACL**：不存在抛可选、无权抛禁止。"""
    from apps.cases.services.case.case_access_policy import CaseAccessPolicy
    from apps.cases.services.case.case_query_service import CaseQueryService
    from apps.core.dto.cases import CaseDTO

    case = CaseQueryService(access_policy=CaseAccessPolicy()).get_case(
        case_id=case_id, user=user, org_access=org_access
    )
    return CaseDTO.from_model(case)


def _load_contract(contract_id: int) -> Any:
    """合同只读视图（DTO；不存在返回 None）。"""
    from apps.core.dependencies.business_contract import build_contract_query_service

    return build_contract_query_service().get_contract(contract_id)


def _build_facts(*, case: Any, contract: Any, given: dict[str, str]) -> dict[str, str]:
    """律师显式给的事实 + 抽取器从案件/合同/材料里读到的事实（律师给的优先）。

    抽取器是 `apps.documents.services.draft.facts_builder`。**它只负责「能读到的事实」**，
    金额/日期这类字段取不到就空着——宁可让成稿留 `<待填写：x>`，也不能让模型编一个金额。

    这层兜底不是可选的：真机联调时 `CaseDTO.target_amount` 是字符串，金额格式化抛了
    `ValueError`，整个起草直接 **500**——律师看到的就是「服务器错误」，而不是「金额没取到，
    这里等你填」。**数据形状不对属于可预期情况**（DTO 跟实体类型不一致、历史脏数据），
    降级成「只用律师显式给的事实」比把整单打挂有用。

    只接「数据形状」那一类；程序性错误（NameError / ImportError 等）照常抛，
    否则真 bug 会被这条兜底永久掩盖。
    """
    from apps.documents.services.draft.facts_builder import build_facts

    try:
        return build_facts(case=case, contract=contract, explicit=given)
    except (ValidationException, AttributeError, KeyError, TypeError, LookupError, ValueError, InvalidOperation):
        logger.warning("事实组装失败，退回只用律师显式给的事实: %s", type(case).__name__, exc_info=True)
        return {str(key): str(value) for key, value in (given or {}).items() if str(value).strip()}


def _skeleton_bytes(spec: Any) -> bytes | None:
    """骨架模板的字节；模板没挂或文件不在盘上时返回 None（**绝不退化成自由生成**）。"""
    from . import queries

    template_id = getattr(spec, "skeleton_template_id", None)
    if not template_id:
        return None
    _template, location = queries.document_template_file(int(template_id))
    if not location:
        return None
    return Path(location).read_bytes()


def _folder_template_for(kind: str, target: Any) -> Any:
    """该案件/合同该用哪棵文件夹树（只读，不落库）。

    ## 为什么必须带「我方诉讼地位」这一维（真机联调改的）

    原来只用 `FolderTemplateQueryService.get_template_for_case(case_type, case_stage)`，而它
    **不看 `legal_statuses`**，并且按 `-updated_at` 取第一条。实测后果：`civil + first_trial`
    同时命中「民事一审起诉」（`legal_statuses=['plaintiff']`）与「民事一审答辩」
    （`['defendant']`）两棵树，取到的是**答辩**那棵 —— 于是起诉状/管辖权异议在这棵树上
    找不到槽位，整条起草直接失败。

    这不是「已知局限」，是**选错了树**：同一案件类型同一阶段本来就可能有多棵树，区分它们的
    唯一字段就是我方诉讼地位。所以改用仓里已有的 `CaseTemplateMatchPolicy`（案件类型 + 阶段 +
    我方诉讼地位三维），不另写一套匹配规则。
    """
    case_type = str(getattr(target, "case_type", "") or "")
    if kind != write_service.KIND_CASE:
        from apps.documents.services.generation.pipeline.template_matcher import TemplateMatcher

        return TemplateMatcher().match_folder_template(case_type)

    from apps.cases.services.template.repo import CaseTemplateBindingRepo
    from apps.cases.services.template.template_match_policy import CaseTemplateMatchInput, CaseTemplateMatchPolicy
    from apps.documents.models import FolderTemplate, FolderTemplateType

    # 手里是 CaseDTO（无 ORM 管理器），所以走按 id 取的那个重载。
    legal_statuses = set(CaseTemplateBindingRepo().get_our_legal_statuses_by_case_id(int(target.id)))
    match_input = CaseTemplateMatchInput(
        case_type=case_type,
        case_stage=str(getattr(target, "current_stage", "") or ""),
        legal_statuses=legal_statuses,
    )
    templates = list(
        FolderTemplate.objects.filter(is_active=True, template_type=FolderTemplateType.CASE).order_by("id")
    )
    matched = CaseTemplateMatchPolicy().filter(templates, match_input)
    return matched[0] if matched else None


def _placement_for(*, spec: Any, folder_template: Any) -> tuple[list[str] | None, list[str]]:
    """`DocumentSpec.folder_slot` → 文件夹模板里的实际路径段（命中多条取第一条）。"""
    from apps.documents.services.template.slot_resolution_service import SlotResolutionService

    resolver = SlotResolutionService()
    warnings: list[str] = []
    declared = str(getattr(spec, "folder_slot", "") or "")

    if declared:
        hits = resolver.find_slot_paths(folder_template, declared)
        if len(hits) > 1:
            warnings.append(f"槽位「{declared}」在这个文件夹模板里有 {len(hits)} 处，已取第一处：{'/'.join(hits[0])}")
        if hits:
            return hits[0], warnings
    else:
        warnings.append(
            f"「{getattr(spec, 'display_name', '') or '这份文书'}」的文书规格没有声明落位槽位，"
            f"已按兜底槽「{DEGRADED_SLOT}」处理"
        )

    fallback = resolver.find_slot_paths(folder_template, DEGRADED_SLOT)
    if fallback:
        warnings.append(
            f"这个案件的文件夹里没有「{declared or '（未声明槽位）'}」的位置，已降级到「{DEGRADED_SLOT}」："
            f"{'/'.join(fallback[0])}。要放到别处请先给文件夹模板补槽位——不猜路径。"
        )
        return fallback[0], warnings
    return None, warnings


def _apply_headings(docx_bytes: bytes, headings: dict[str, str]) -> bytes:
    """把「请求段 / 事实段」的小标题换成 `DocumentSpec.claim_heading` / `facts_heading`。

    **为什么必须接上这一步**：这两个字段在模型里、Admin 里、种子里都有，但此前**没有任何
    代码读它**——纯死配置。真机产出的管辖权异议申请书顶着「诉讼请求：」，而这份文书的
    规范小标题是「异议请求：」。声明了却不生效，比没有这个字段更坏：管理员改了以为生效了。

    定位方式（不猜 XML 结构）：`headings` 的键是**已经填进去的正文首行**，值是要换成的标题。
    找到文本等于该首行的段落，把**它前面最近的非空段落**的文字改掉。这样无需知道模板里
    标题原文是什么，也不用去动 `{{槽位}}` 的 run 结构。

    找不到锚点就原样返回（不抛）——标题只是观感，不该让整份起草失败。
    """
    if not headings:
        return docx_bytes
    import zipfile
    from io import BytesIO

    from lxml import etree

    ns = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    w_p, w_t = f"{{{ns}}}p", f"{{{ns}}}t"

    src = zipfile.ZipFile(BytesIO(docx_bytes))
    root = etree.fromstring(src.read("word/document.xml"))
    paragraphs = list(root.iter(w_p))

    def _text(node: Any) -> str:
        return "".join((t.text or "") for t in node.iter(w_t)).strip()

    changed = False
    for anchor_text, heading in headings.items():
        anchor_text = (anchor_text or "").strip()
        heading = (heading or "").strip()
        if not anchor_text or not heading:
            continue
        body_index = next((i for i, para in enumerate(paragraphs) if _text(para) == anchor_text), None)
        if body_index is None:
            logger.warning("小标题未生效：找不到正文锚点（首行 %r）", anchor_text[:30])
            continue
        prev_index = next((i for i in range(body_index - 1, -1, -1) if _text(paragraphs[i])), None)
        if prev_index is None:
            logger.warning("小标题未生效：正文前面没有非空段落")
            continue
        nodes = list(paragraphs[prev_index].iter(w_t))
        if not nodes:
            logger.warning("小标题未生效：标题段落没有 w:t")
            continue
        nodes[0].text = heading
        nodes[0].set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
        for node in nodes[1:]:
            node.text = ""
        changed = True

    if not changed:
        return docx_bytes
    patched = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
    out = BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as dst:
        for item in src.infolist():
            dst.writestr(item, patched if item.filename == "word/document.xml" else src.read(item.filename))
    return out.getvalue()


def _heading_overrides(*, spec: Any, context: dict[str, str]) -> dict[str, str]:
    """要换的小标题：{已填正文的首行: 目标标题}。取不到就不换。"""
    from apps.documents.services.draft import spec_service as _spec

    try:
        available = set(_spec._skeleton_placeholders(spec))
    except (AttributeError, KeyError, TypeError, ValueError, LookupError):
        # 骨架占位符取不到就不换标题——标题只是观感，不该让整份起草失败。
        return {}
    out: dict[str, str] = {}
    for section in ("claim", "facts"):
        heading = str(getattr(spec, f"{section}_heading", "") or "").strip()
        if not heading:
            continue
        key = _spec._section_target(spec, section, available)
        if not key:
            continue
        value = (context.get(key) or "").strip()
        if not value:
            continue
        _lines = value.splitlines()
        first_line = _lines[0].strip() if _lines else ""
        if first_line and first_line != heading:
            out[first_line] = heading
    return out


def _apply_title_override(docx_bytes: bytes, title: str) -> bytes:
    """把骨架首段的标题换成这份文书自己的标题（`DocumentSpec.title_override`）。

    **为什么必须有这一步**：管辖权异议申请书复用起诉状的骨架，而骨架的第一段是写死的
    「民事起诉状」——它不是占位符，槽位填不进去。真机联调时生成的管辖权异议申请书顶着
    「民事起诉状」的标题，这在实务上是**给法院的文书贴错名字**。

    只改第一段的文字，run 的格式（字号/加粗/居中）原样保留：把标题写进第一个 `w:t`，
    该段其余 `w:t` 清空。没有非空段落时原样返回。
    """
    if not title.strip():
        return docx_bytes
    import zipfile
    from io import BytesIO

    from lxml import etree

    ns = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    w_p, w_t = f"{{{ns}}}p", f"{{{ns}}}t"

    src = zipfile.ZipFile(BytesIO(docx_bytes))
    root = etree.fromstring(src.read("word/document.xml"))
    for para in root.iter(w_p):
        texts = list(para.iter(w_t))
        if not any((node.text or "").strip() for node in texts):
            continue
        first, *rest = texts
        first.text = title
        first.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
        for node in rest:
            node.text = ""
        break
    else:
        return docx_bytes

    patched = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
    out = BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as dst:
        for item in src.infolist():
            dst.writestr(item, patched if item.filename == "word/document.xml" else src.read(item.filename))
    return out.getvalue()


def _to_docx_text(value: str) -> str:
    """只做一件：把 `**加粗**` 换成私用区哨兵（渲染后处理换成真加粗）。

    **这里绝不能折段落。** `\\n -> \\a` 的归一化只在 `draft_service.render()` 里做一次，
    而 `to_body_text()` **不是幂等的**：它把输入自带的 `\\a` 当 C0 控制符剥掉（这是安全要求，
    否则模型能自己断段、能插分页）。原先本函数先折一次、`render()` 再折一次，第二次把刚插入的
    `\\a` 全吃掉 —— 实测 `to_body_text(to_body_text(x))` 把 5 段压成 1 行；而单元测试要么用
    单段值、要么直接测 `to_body_text`，所以一路绿灯。真机联调才看出来：生成的起诉状正文是一整段墙。

    职责边界：**归一化只有一处**（renderer），本函数只管样式。
    """
    from apps.documents.services.placeholders.long_text import markdown_bold_to_sentinel

    return markdown_bold_to_sentinel(value)


def _llm_caller(instruction: str) -> LLMCaller:
    """填槽用的模型调用口。律师那句补充要求挂成最后一条 user 消息。

    异常**不在这里吞**：`resolve_slot_values` 约定了「不得抛异常，缺东西就走 pending」，
    由它把「模型挂了」翻译成待填项，比在这里返回空串更诚实（空串会被当成「模型没有答案」）。
    """
    extra = (instruction or "").strip()

    def _call(messages: list[dict[str, str]]) -> str:
        payload = list(messages)
        if extra:
            payload.append({"role": "user", "content": f"## 律师的补充要求\n{extra}"})
        from apps.core.llm.service import LLMService

        response = LLMService().chat(payload, temperature=0.2, max_tokens=16384, fallback=True)
        content = getattr(response, "content", None)
        if content is None and isinstance(response, dict):
            content = response.get("content")
        return str(content or "")

    return _call


def _comment_pending(
    *, kind: str, owner_id: int, subpath: str, pending: list[str], user: Any, org_access: Any
) -> list[str]:
    """未决项挂成 Word 批注（**沿用 `draft_service` 的做法**：正文占位 + 批注解释为什么空着）。"""
    if not pending:
        return []
    outcome = write_service.apply_comments(
        kind=kind,
        owner_id=owner_id,
        subpath=subpath,
        comments=[
            {
                "selection": draft_service.PENDING_TEMPLATE.format(slot=slot),
                "text": f"待确认：{slot}。这一项没有从已知事实里推出来，请补充后再定稿。",
            }
            for slot in pending
        ],
        user=user,
        org_access=org_access,
    )
    if outcome.get("applied"):
        return []
    return [
        "未决项批注没挂上（"
        + str(outcome.get("reason") or "定位不到占位文字")
        + "）：正文里仍有「<待填写：…>」，请按占位逐项补。",
    ]


def _queue_review(*, enabled: bool, kind: str, owner_id: int, subpath: str, user: Any, org_access: Any) -> int | None:
    """起草即初审：建一轮审查（不在这里跑模型，与 `draft_contract` 同口径）。"""
    if not enabled:
        return None
    from . import review_pipeline

    run = review_pipeline.create_run(kind=kind, owner_id=owner_id, subpath=subpath, user=user, org_access=org_access)
    return int(run.pk)


__all__ = ["DEGRADED_SLOT", "draft_document"]


def list_doc_types() -> list[dict[str, str]]:
    """前端下拉用的文书类型清单（只含已登记的 spec）。

    形状与 `DocTypeOut` 逐键对应。**不猜、不补**：`doc_type` 是律师说出口的那个词，
    `display_name` 是写在文书首行的那个标题，两者都由 `DocumentSpec` 决定。
    """
    return [
        {
            "doc_type": spec.doc_type,
            "display_name": spec.display_name,
            "family": spec.family,
        }
        for spec in spec_service.list_specs(active_only=True)
    ]
