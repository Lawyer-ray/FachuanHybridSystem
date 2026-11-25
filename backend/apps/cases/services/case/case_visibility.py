"""案件可见性：**谁算得上看过这个案子**。

## 只有两个真源

1. **案件指派**（`CaseAssignment`）——承办/协办律师，合同同步与手动添加都落这张表；
2. **显式授权**（`CaseAccessGrant`）——单独给某人开的权限。

不要再发明第三个（按律所、按创建人、按最近访问猜）。仓库里 `CaseAccessPolicy` 已经在
用这两个真源判可见性，这里只把它补成**能被人直接调用的纯查询**（不需要 AccessContext）。

## 为什么「无主案件」对所有人放开

一个案件既没有任何指派、也没有任何授权时，它没有任何「本来该看得见的人」——
这时若按白名单收窄，只有 superuser 能碰，等于把刚建出来、还没分派的案子锁死
（律师建完案立刻归档材料就会 403）。`CaseAccessPolicy._admin_firm_case_access`
已经是这个口径（「无任何指派的无主案件」视为可见），这里保持一致，不给第二套说法。

## 为什么 superuser / staff 不受限

它们是运维与律所管理员，`CaseAccessPolicy` 同样对管理员放开；把限制加在这里只会
让「管理员看不见自己刚处理过的案子」，属于把安全做成了麻烦。
"""

from __future__ import annotations

from typing import Any

from apps.cases.models import CaseAccessGrant, CaseAssignment


def _is_unrestricted(user: Any) -> bool:
    """平台管理员 / 律所管理员：不加案件级限制。"""
    if user is None:
        return False
    return bool(getattr(user, "is_superuser", False) or getattr(user, "is_staff", False))


def accessible_case_ids(user: Any) -> set[int] | None:
    """该用户能看见的案件 id 集合；`None` 表示不受限（管理员）。"""
    if _is_unrestricted(user):
        return None
    user_id = getattr(user, "pk", None)
    if not user_id:
        # 匿名 / 无主键：一个案件都看不见（调用方在此之前就该 403，这里只是兜底）
        return set()
    assigned = set(CaseAssignment.objects.filter(lawyer_id=user_id).values_list("case_id", flat=True))
    granted = set(CaseAccessGrant.objects.filter(grantee_id=user_id).values_list("case_id", flat=True))
    return assigned | granted


def can_access_case(user: Any, case_id: int) -> bool:
    """能不能碰这个案件：指派 / 授权 / 无主案件 / 管理员，四者之一成立即可。"""
    if _is_unrestricted(user):
        return True
    if not case_id:
        return False
    user_id = getattr(user, "pk", None)
    if user_id and (
        CaseAssignment.objects.filter(case_id=case_id, lawyer_id=user_id).exists()
        or CaseAccessGrant.objects.filter(case_id=case_id, grantee_id=user_id).exists()
    ):
        return True
    return _is_unowned(case_id)


def _is_unowned(case_id: int) -> bool:
    """无主案件：没有任何指派、也没有任何授权。"""
    if CaseAssignment.objects.filter(case_id=case_id).exists():
        return False
    return not CaseAccessGrant.objects.filter(case_id=case_id).exists()
