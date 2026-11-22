"""威科先行账号凭证的**自动解析** —— 让调用方不用知道 `credential_id`。

## 为什么需要它

`AccountCredential` 是"外部系统登录账号"的通用表，一张表里同时装着法院送达平台、
OA、工商、邮箱、东盟法、威科先行……库里现在 10 条，其中威科只有 2 条（id 6 / 7）。

于是「请传入 credential_id」这种参数对使用者是**不可解的问题**：律师不知道 6 和 7
有什么区别，模型更不知道——它得先调 `list_credentials` 再猜哪个是威科，猜错了就是
"登录工商去查法条"。凭证 ID 是实现细节，不该出现在工具签名里。

## 解析口径

1. **优先复用调用方给的 ID**（显式指定就是显式指定，不覆盖）；
2. 否则在**当前用户可见范围**内挑威科凭证：非超管只看本所（安全审计 A-07 的
   归属口径，与 `LawVerificationService` 一致），超管不限；
3. 命中多条时取 `id` 最小的那条（稳定、可复现——按 `last_login_success_at` 排序
   会让同一个问题在不同时间用不同账号，出问题难复现）；
4. 一条都没有 → 返回 `None`，由调用方降级为"只做格式检查"。

## 调用方

- REST：`legal_research_api` 的建任务、能力检索（含 MCP 包装版）与法规核查接口，
  `credential_id` 均可省略，省略时经本模块解析；解析不出返回 422（不降级）。
- MCP 工具：`create_research_task` / `capability_search` / `check_law_references` /
  `verify_citations` 的 `credential_id` 均为可选，原样转发给上面的 REST 接口。
- 综合结论的引用核验（`agent/services/synthesis/verify.py`）：解析不出时降级为
  "只做格式检查"。
"""

from __future__ import annotations

from typing import Any

from django.db.models import Q

#: 判"这是威科先行凭证"的唯一口径。
#:
#: 同时看 `site_name` 与 `url`：现有数据两者都不完全可靠（有的站点名写 "wkxx"、
#: 有的写 "wk"、有的干脆不写而 url 是 wkinfo），只认一个会漏。
WEIKE_FILTER = (
    Q(site_name__icontains="wkxx")
    | Q(site_name__iexact="wk")
    | Q(site_name__icontains="weike")
    | Q(url__icontains="wkinfo.com.cn")
)


def resolve_weike_credential_id(*, user: Any, explicit: int | None = None) -> int | None:
    """解析本次该用哪条威科凭证；解析不出返回 ``None``。

    Args:
        user: 当前用户（Django ``User``）。``None`` 表示无身份（后台任务），
            此时不按律所过滤——调用方通常是系统自身，不存在越权读取他人凭证的问题；
            但**仍然只返回威科凭证**，不会解析到别的平台。
        explicit: 调用方显式指定的 ID；非空直接返回，不做任何校验/猜测。

    Returns:
        凭证 ID；没有可用威科凭证时 ``None``。
    """
    from apps.organization.models import AccountCredential

    if explicit:
        return int(explicit)

    queryset = AccountCredential.objects.filter(WEIKE_FILTER)
    if user is not None and not getattr(user, "is_superuser", False):
        law_firm_id = getattr(user, "law_firm_id", None)
        # 拿不到律所 → 不返回任何凭证（fail-closed）。宁可降级为"只做格式检查"，
        # 也不要跨律所借用别人的威科账号。
        if law_firm_id is None:
            return None
        queryset = queryset.filter(lawyer__law_firm_id=law_firm_id)

    row = queryset.order_by("id").values_list("id", flat=True).first()
    return int(row) if row else None


__all__ = ["WEIKE_FILTER", "resolve_weike_credential_id"]
