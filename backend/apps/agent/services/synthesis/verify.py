"""综合结论的引用核验 —— 把 `Synthesis.unverified` 真正填上。

## 为什么必须有这一步

综合 agent 的 prompt 要求"只使用候选里出现过的法条与案号"，但它**验不了候选本身
对不对**。此前 `aggregate.synthesize` 把 `unverified` 写死为 `[]`——契约里有字段、
前端 `SynthesisCard` 有专门的「未核验」区块，却永远不出现。等于对律师说"都核过了"。

## 核验走哪条路

复用既有威科链路（`LawVerificationService.check_references`）：凭证解密、E-13 域名
白名单、登录与插件探测都在那一层，**不重写**。它在 app 层，不需要经过 MCP。

## 失败一律降级为"未核验"，不阻断综合

综合稿本身有价值，核验不了不该把它一起丢掉。三种降级都在 `note` 里说清：

- 没传 `credential_id` → 「未提供威科凭证」；
- 插件没装 / 凭证无权限 / 威科登录失败 → 「核验未执行：<原因>」；
- 核验跑了但有条目没兜住 → 逐条进 `unverified`（这才是正常产出）。
"""

from __future__ import annotations

import logging
from typing import Any

from asgiref.sync import sync_to_async

logger = logging.getLogger(__name__)

#: 不该被"核验失败不阻断"吞掉的控制流异常。
_NOT_OURS: tuple[type[BaseException], ...] = (KeyboardInterrupt, SystemExit, GeneratorExit)

#: 后端返回的"这条法规没问题"取值（插件侧约定，见 law_verification_service）。
_VALID_STATUSES = frozenset({"valid", "ok"})
#: 失效类取值：命中即算未核验（哪怕 status 写着 valid）。
_INVALID_VALIDITY = frozenset({"invalid", "repealed", "abolished"})


def _describe(item: dict[str, Any]) -> str:
    """一条核验结果 → 给人看的一句话（进 `unverified`）。"""
    name = str(item.get("law_name") or "").strip() or "（未识别法规）"
    article = item.get("article_num")
    label = f"《{name}》" if name and not name.startswith("《") else name
    if article:
        label = f"{label}第 {article} 条"
    status = str(item.get("status") or "").strip() or "unknown"
    validity = str(item.get("validity") or "").strip()
    detail = f"状态 {status}" + (f" / 效力 {validity}" if validity else "")
    return f"{label}：{detail}"


def _is_verified(item: dict[str, Any]) -> bool:
    status = str(item.get("status") or "").lower()
    validity = str(item.get("validity") or "").lower()
    return status in _VALID_STATUSES and validity not in _INVALID_VALIDITY


async def verify_synthesis_citations(
    *,
    text: str,
    credential_id: int | None,
    user: Any,
) -> tuple[list[str], str]:
    """核验综合稿里的法规引用。

    Returns:
        ``(unverified, note)``：``unverified`` 是**未核验条目的中文描述**（直接进
        `Synthesis.unverified`）；``note`` 是本次覆盖口径（`""` = 全量核验且全通过）。
    """
    body = str(text or "").strip()
    if not body:
        return [], "空正文，未核验"
    if not credential_id:
        # 不是失败：没给凭证就是"没查"。写成"未提供凭证"而不是"未通过核验"，
        # 否则律师会以为查过了且有问题。
        return [], "未提供威科凭证，本次只做了格式检查，未做外部核验"

    from apps.legal_research.services.law_verification_service import LawVerificationService

    service = LawVerificationService()
    try:
        # check_references 是同步阻塞的（威科登录 + HTTP/Playwright IO），必须下线程。
        payload = await sync_to_async(service.check_references, thread_sensitive=True)(
            text=body, credential_id=int(credential_id), user=user
        )
    except _NOT_OURS:
        raise
    except BaseException as exc:
        # 核验失败**不阻断综合**：稿子本身有价值，只是这一批引用没核到。
        # 用宽口径接住是因为失败面太杂（插件缺失 / 凭证无权限 / 登录失败 / 网络），
        # 逐类接只会漏；而 ``BaseException`` 是为了把取消也覆盖到（再显式放行
        # 上面那三类控制流异常）。异常类型进日志，不进用户文案。
        logger.warning("综合稿引用核验失败（不阻断）", exc_info=True)
        return [], f"核验未执行：{type(exc).__name__}"

    references = payload.get("references") if isinstance(payload, dict) else None
    if not references:
        return [], "核验已执行，但文末未识别到法规引用"

    unverified = [_describe(item) for item in references if not _is_verified(item)]
    if not unverified:
        return [], ""
    return unverified, f"核验已执行：{len(unverified)} 条未通过"


__all__ = ["verify_synthesis_citations"]
