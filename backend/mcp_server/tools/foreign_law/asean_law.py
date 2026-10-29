"""东盟域外法查明 MCP tools —— 让 AI 能检索、读取、核验境外法律。

## 数据源

“一带一路”沿线国家或地区法律查明服务中心数据库与服务平台
（https://barlc.swupl.edu.cn/）的“东盟域外法律查明”服务。
代码内简称 BARLC；对外文档写平台全称与服务全称，见
`plugins/barlc_asean_law/README.md` 的命名口径表。

## 为什么需要

跨境合同审查里，AI 最危险的错误不是「写得不好」，而是**编造外国法引用**。
模型对泰国、越南、印尼法的训练数据稀薄，`《泰国商业租赁法》第 42 条` 这种
写法看起来极真，实则可能整部法都不存在。

本组工具把西南政法大学中国—东盟法律查明数据库（BARLC）接进工具面，让 AI 的
每一条域外法引用都能落到可验证的条文原文上。

## 四个工具的分工

```
asean_law_countries   → 有哪些国家可查（配置期用，也用来提示模型别瞎猜国家）
asean_law_search      → 按关键词找法律，拿 sys_id
asean_law_read        → 按 sys_id 取正文（条款级或全文）
asean_law_verify      → 一步到位核验一条引用是否成立
```

`asean_law_verify` 是给 JEV 判断层用的：它内部先做纯规则判定（法律是否存在、
条款是否存在），只有「条文存在且可读」时才把主张与条文交给判定层。**大部分
编造引用在调用模型之前就被判死了。**

## 失败一律如实上报

与 `fetch_fetch_url` 同一原则：拿不到就是拿不到，返回
``{"ok": false, "reason": "..."}``，绝不返回空结果冒充「查无此法」。

尤其注意 ``credential_missing``：本插件不提供匿名降级。没有 BARLC 账号时
`FileCount == -2`，正文不可读，此时任何「核验通过」都是假的——宁可整条链路
失败，也不让 JEV 在无据可依的情况下给出结论。

## 为什么这里吞异常（而非抛 ToolError）

同文件的每个 ``except Exception`` 都把上游失败转成 ``ok=false`` + ``reason``，
**不是**静默吞掉伪装成正常结果：``ok`` 字段、``reason`` 枚举、``detail`` 原文
都在，模型能明确知道失败及其原因。之所以不抛 ``FachuanApiError``：

1. ``fetch_url`` 者把它确立为工具面对「外部上游不可达」的失败口径（MCP 规范
   推荐：可预期的业务/依赖失败用结构化错误结果，异常留给真异常）；
2. ``credential_missing`` /``login_failed`` 需要模型「停止重试、提示用户去 Admin
   配置」——抛成异常后模型只能看到一段错误文本，读不到 reason 枚举，会换关键词
   反复试（模型重试一个没配账号的检索，毫无意义）；
3. ``asean_law_verify`` 的调用方是 JEV 判断层，它需要区分「规则层没拿到数据」
   （待重试/待修配置）与「引用不存在」（规则层已判死），结构化 reason 是这个
   区分的载体。

豁免登记在 ``tests/ci/unit/mcp_server/test_error_semantics.py`` 的
``_SWALLOW_ALLOWLIST``，新加 ``except`` 同样要在那里写理由。
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def _tool_result(**fields: Any) -> dict[str, Any]:
    """统一的工具返回结构（私有 helper，不是工具，故 ``_`` 前缀）。

    与 ``fetch_url`` 同构：``ok`` 必须有，失败时带 ``reason`` 与 ``detail``。
    失败绝不返回空结果冒充「查无此法」——那会让模型以为「确实没有这个法律」，
    而真相可能是「没配凭据」或「网络挂了」。
    """
    return fields


def _adapter_and_credential() -> tuple[Any, Any]:
    """取适配器与凭据。

    BARLC 凭据由律师在 Django Admin「账号密码」登记（site_name: barlc /
    swupl_barlc），不读环境变量、不读配置文件。
    """
    from plugins.barlc_asean_law.adapter import get_adapter
    from plugins.barlc_asean_law.credential import resolve_credential

    return get_adapter(), resolve_credential()


def asean_law_countries() -> dict[str, Any]:
    """列出 BARLC 数据库可查明的国家/地区。

    返回每个国家的 `code`（检索时作为 country_code 传入）与中文/英文名。
    该接口无需登录，配置期或调试期可直接调用。

    Returns:
        {"ok": true, "count": N, "countries": [{"code","name_cn","name_en"}, ...]}
    """
    try:
        from plugins.barlc_asean_law.adapter import get_adapter

        countries = get_adapter().list_countries()
    except Exception as exc:  # 降级返回结构化失败，见 test_error_semantics 豁免表
        logger.warning("获取 BARLC 国别列表失败: %s", exc)
        return _tool_result(ok=False, reason="upstream_error", detail=str(exc))

    return _tool_result(
        ok=True,
        count=len(countries),
        countries=[
            {"code": item.code, "name_cn": item.name_cn, "name_en": item.name_en, "sys_id": item.sys_id}
            for item in countries
        ],
    )


def asean_law_search(
    keyword: str,
    country_code: str = "",
    field: str = "Title",
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    """在东盟域外法数据库中检索法律。

    Args:
        keyword: 检索关键词。支持中文、英文、当地语言（泰文/越南文等）。
            **不能为空**——空查询会拉取全库 16 万条数据。
        country_code: 国别代码，如 `LAWCOUNTRYTG`（泰国）、`LAWCOUNTRYYN`（越南）。
            留空则跨东盟全部国家检索。可用 asean_law_countries 查代码。
        field: 检索字段。
            - `Title`（默认）：只搜法律名称，最精确，用于定位某部具体的法
            - `QUANWEN`：全库全文检索，覆盖条文正文，用于「哪些法提到过某说法」
            - `KEYWORD`：搜数据库标注的关键词
            - `Theme`：搜主题
            - `EffectiveDate`：按生效日期检索
        page: 页码，从 1 开始。
        page_size: 每页条数，1–60。

    Returns:
        {"ok": true, "total": N, "hits": [{"sys_id","title_cn","title_en",
         "title_local","publish_date","effective_date"}, ...]}

    Note:
        `QUANWEN` 命中只说明全库某处词频出现，**不等于**某个法条支持该主张。
        要判断条文内容必须用 asean_law_read 取原文，或直接用 asean_law_verify。
    """
    try:
        adapter, credential = _adapter_and_credential()
    except Exception as exc:  # 降级返回结构化失败，见 test_error_semantics 豁免表
        return _credential_failure(exc)

    if not str(keyword or "").strip():
        return _tool_result(
            ok=False,
            reason="empty_keyword",
            detail="检索关键词不能为空。空查询会返回全库数据，请给出具体的法律名称或术语。",
        )

    try:
        total, hits = adapter.search(
            credential,
            keyword=keyword,
            country_code=country_code or None,
            field=field,
            page=page,
            page_size=page_size,
        )
    except Exception as exc:  # 降级返回结构化失败，见 test_error_semantics 豁免表
        logger.warning("BARLC 检索失败 keyword=%s: %s", keyword, exc)
        return _tool_result(ok=False, reason="search_failed", detail=str(exc))

    return _tool_result(
        ok=True,
        total=total,
        page=page,
        hits=[
            {
                "sys_id": hit.sys_id,
                "title_cn": hit.title_cn,
                "title_en": hit.title_en,
                "title_local": hit.title_local,
                "publish_date": hit.publish_date,
                "effective_date": hit.effective_date,
            }
            for hit in hits
        ],
    )


def asean_law_read(
    sys_id: str,
    section_number: str = "",
    lang: str = "en",
) -> dict[str, Any]:
    """读取一部东盟法律的正文。

    Args:
        sys_id: 法律 ID，来自 asean_law_search 的返回。
        section_number: 条款号。给出时只返回该条；留空则返回全部条款列表
            （仅编号与前 200 字，避免一次塞爆上下文）。
        lang: 正文语言。
            - `en`（默认）：英文版。条款结构规整（`Section N.`），推荐
            - `local`：当地官方语言版（泰文 มาตรา / 越南文 Điều）
            - `cn`：中译版
            - `en_local`：英文本地语对照版

    Returns:
        {"ok": true, "law": {...元数据...}, "section": {"number","text"} }
        或 {"ok": true, "law": {...}, "sections": [{"number","preview"}, ...]}

    Note:
        英文版并非每部法都有。可用返回里的 `has_english_pdf` 判断；没有英文版时
        会自动回退本地语版，此时条款号可能是泰文数字（会自动转成阿拉伯数字）。
    """
    try:
        adapter, credential = _adapter_and_credential()
    except Exception as exc:  # 降级返回结构化失败，见 test_error_semantics 豁免表
        return _credential_failure(exc)

    try:
        detail = adapter.get_detail(credential, sys_id=str(sys_id))
    except Exception as exc:  # 降级返回结构化失败，见 test_error_semantics 豁免表
        return _tool_result(ok=False, reason="detail_failed", detail=str(exc))

    law_meta = {
        "sys_id": detail.sys_id,
        "title_cn": detail.title_cn,
        "title_en": detail.title_en,
        "title_local": detail.title_local,
        "effective_date": detail.effective_date,
        "publish_date": detail.publish_date,
        "country_code": detail.country_code,
        "law_category": detail.law_category,
        "has_english_pdf": detail.has_english_pdf,
        "has_fulltext": detail.has_fulltext,
    }

    if not detail.has_fulltext:
        return _tool_result(
            ok=False,
            reason="no_fulltext",
            detail="该法律在数据库中无可用正文文件，无法读取条文。",
            law=law_meta,
        )

    effective_lang = lang
    if lang == "en" and not detail.has_english_pdf:
        effective_lang = "local"
        logger.info("《%s》无英文版，改用本地语正文", detail.title_cn)

    try:
        sections = adapter.fetch_sections(credential, detail=detail, lang=effective_lang)
    except Exception as exc:  # 降级返回结构化失败，见 test_error_semantics 豁免表
        return _tool_result(ok=False, reason="fulltext_failed", detail=str(exc), law=law_meta)

    if not sections:
        return _tool_result(
            ok=False,
            reason="no_sections_parsed",
            detail="正文已取到但未能切分出条款（可能该 PDF 不是条款体例，或语言不在支持范围）。",
            law=law_meta,
        )

    if str(section_number or "").strip():
        target = adapter.find_section(sections, section_number)
        if target is None:
            return _tool_result(
                ok=False,
                reason="section_not_found",
                detail=f"该法律正文中不存在第 {section_number} 条（共 {len(sections)} 条）",
                law=law_meta,
                available_sections=[item.number for item in sections],
            )
        return _tool_result(
            ok=True,
            law=law_meta,
            lang=effective_lang,
            section={"number": target.number, "text": target.text},
        )

    return _tool_result(
        ok=True,
        law=law_meta,
        lang=effective_lang,
        section_count=len(sections),
        sections=[
            {
                "number": item.number,
                "preview": item.text[:200].replace("\n", " "),
            }
            for item in sections
        ],
    )


def asean_law_verify(
    law_name: str,
    section_number: str = "",
    claim: str = "",
    country_code: str = "",
) -> dict[str, Any]:
    """核验一条域外法引用是否成立（JEV 判断层的入口）。

    这是跨境合同审查里最该用 AI 的场景：律师或上一轮 AI 写下
    「依据《某某法》第 X 条……」，本工具负责查明这句话到底站不站得住。

    Args:
        law_name: 被引用的法律名称，中英文均可。越完整越准
            （如 `Rental of Immovable Property for Commerce and Industry Act`）。
        section_number: 条款号，如 `4`。留空则只核验法律是否存在。
        claim: 该引用所要支持的主张，如「租赁合同必须书面并登记」。
            留空则只核验条款是否存在，不做内容比对。
        country_code: 国别代码，用于缩小检索范围。留空则全东盟检索。

    Returns:
        {"ok": true,
         "verdict": "支持" | "矛盾" | "原文未提及" | "不存在该引用" | "待判定",
         "law_title": "...", "section_number": "...", "section_text": "...",
         "reason": "..."}

    Note:
        `verdict == "待判定"` 表示条文已取到，需要调用方（JEV 判定层）拿
        `section_text` 与 `claim` 交给模型在固定选项里选一个。**规则层不做语义
        判断**，避免与模型层职责混淆。

        `verdict == "不存在该引用"` 是规则层直接判定，不消耗模型调用：
        法律检索不到、正文不可读、条款号超出范围，都归入此类。
    """
    try:
        adapter, credential = _adapter_and_credential()
    except Exception as exc:  # 降级返回结构化失败，见 test_error_semantics 豁免表
        return _credential_failure(exc)

    from plugins.barlc_asean_law.verify import CitationRequest, JudicialVerifier

    try:
        verifier = JudicialVerifier(adapter)
        check = verifier.check(
            credential,
            CitationRequest(
                law_name=str(law_name or ""),
                section_number=str(section_number or ""),
                claim=str(claim or ""),
                country_code=country_code or None,
            ),
        )
    except Exception as exc:  # 降级返回结构化失败，见 test_error_semantics 豁免表
        logger.warning("引用核验失败 law=%s: %s", law_name, exc)
        return _tool_result(ok=False, reason="verify_failed", detail=str(exc))

    return _tool_result(
        ok=True,
        verdict=check.result or "待判定",
        law_title=check.law_title,
        section_number=check.section_number,
        section_text=check.section_text,
        reason=check.reason,
        needs_model_judgement=not check.result,
        claim=str(claim or ""),
    )


def _credential_failure(exc: Exception) -> dict[str, Any]:
    """把凭据异常转成结构化失败。

    `credential_missing` 单独成一种 reason：它不是「调用出错」，而是「这台机器
    没配 BARLC 账号」。模型看到这个 reason 应当停止重试并提示用户去配置，
    而不是换关键词反复试。
    """
    from plugins.barlc_asean_law.models import BarlcCredentialMissing, BarlcLoginError

    if isinstance(exc, BarlcCredentialMissing):
        return _tool_result(ok=False, reason="credential_missing", detail=str(exc))
    if isinstance(exc, BarlcLoginError):
        return _tool_result(ok=False, reason="login_failed", detail=str(exc))
    logger.warning("BARLC 初始化失败: %s", exc)
    return _tool_result(ok=False, reason="init_failed", detail=str(exc))


__all__ = [
    "asean_law_countries",
    "asean_law_search",
    "asean_law_read",
    "asean_law_verify",
]
