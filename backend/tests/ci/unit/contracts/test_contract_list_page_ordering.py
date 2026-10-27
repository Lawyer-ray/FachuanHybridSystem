"""合同分页列表排序的单元测试（list_contracts_page）。

场景来源：办案主页 `/projects` 是**纯平铺**渲染后端返回顺序（前端无任何客户端排序），
所以列表顺序完全由这里决定。历史实现按「离今天最近」排
（`ABS(end_date - CURRENT_DATE)` 升序、NULLS LAST、id 倒序），实际效果是：

- 绝对值把「已过期」与「快到期」混排，过期最久的能排到未过期合同前面；
- 大批在办合同 `end_date` 为空，被 NULLS LAST 整体沉到有日期那批之后，
  列表实际劈成「前 N 行按可疑规则 + 其后退化成 id 倒序」两段。

用户侧观感就是「排序不对」。现在固定 `-id`（最新建的在前），与 list_contracts
同口径，到期紧迫度由前端按 daysLeft 自行呈现，不再由列表顺序承载。

回归重点：无论 end_date 是未来/过去/为空，顺序都只由 id 决定。
"""

from __future__ import annotations

import datetime

import pytest

from apps.testing.factories import ContractFactory


@pytest.mark.django_db
class TestListContractsPageOrdering:
    """list_contracts_page 的排序口径：id 倒序"""

    def _service(self):
        from apps.contracts.services.contract.query.service import ContractQueryService

        return ContractQueryService()

    def _page_ids(self, svc, *, page: int = 1, page_size: int = 50):
        """跑一次分页查询，返回该页的 id 序列。

        perm_open_access=True：本用例只验证**排序**，不引入权限维度。
        不传则 access_policy.filter_queryset 因 user=None 直接返回 qs.none()，
        什么都拿不到（那是权限用例该盖的事）。
        """
        data = svc.list_contracts_page(page=page, page_size=page_size, include_facets=False, perm_open_access=True)
        return [c.id for c in data["items"]]

    def test_orders_by_id_desc_ignoring_end_date(self) -> None:
        """end_date 无论未来/过去/为空，顺序都只由 id 倒序决定（不看倒计时）。"""
        today = datetime.date.today()
        past = ContractFactory(name="已过期合同", end_date=today - datetime.timedelta(days=300))
        future_far = ContractFactory(name="很远到期合同", end_date=today + datetime.timedelta(days=300))
        no_end = ContractFactory(name="无到期日合同", end_date=None)
        future_near = ContractFactory(name="快到期合同", end_date=today + datetime.timedelta(days=2))
        # 手工把 id 顺序和「到期紧迫度」排成完全相反，以证明排序不跟着到期走
        expected = sorted([past.id, future_far.id, no_end.id, future_near.id], reverse=True)

        ids = self._page_ids(self._service())

        assert ids == expected

    def test_expired_contract_not_floated_to_top(self) -> None:
        """已过期合同不会因为 |days| 小而插到未过期合同前面。

        历史缺陷的直击用例：旧实现按 ABS(end_date - today) 升序，
        「过期 1 天」的距离是 1，会排到「剩 30 天」前面。
        """
        today = datetime.date.today()
        expired_yesterday = ContractFactory(name="昨天过期", end_date=today - datetime.timedelta(days=1))
        live_later = ContractFactory(name="还剩 30 天", end_date=today + datetime.timedelta(days=30))

        ids = self._page_ids(self._service())

        # live_later 建得更晚 → id 更大 → 应排在前面，无视它到期日更远
        assert ids.index(live_later.id) < ids.index(expired_yesterday.id)

    def test_null_end_date_not_sunk_to_bottom(self) -> None:
        """无 end_date 的合同按 id 正常参与排序，不被整体沉到有日期的那批之后。"""
        today = datetime.date.today()
        dated = ContractFactory(name="有到期日", end_date=today + datetime.timedelta(days=10))
        no_end = ContractFactory(name="无到期日", end_date=None)

        ids = self._page_ids(self._service())

        # no_end 建得更晚（id 更大）→ 排第一，不做 NULLS LAST 沉底
        assert ids[0] == no_end.id
        assert ids.index(no_end.id) < ids.index(dated.id)

    def test_pagination_is_stable_across_pages(self) -> None:
        """分页不重不漏：第 1 页 + 第 2 页拼起来仍是完整的 id 倒序序列。"""
        ids = [ContractFactory(name=f"合同{i}", end_date=None).id for i in range(5)]
        expected = sorted(ids, reverse=True)
        svc = self._service()

        page1 = self._page_ids(svc, page=1, page_size=3)
        page2 = self._page_ids(svc, page=2, page_size=3)

        assert page1 == expected[:3]
        assert page2 == expected[3:]

    def test_filters_do_not_disturb_order(self) -> None:
        """筛选（status）只裁行、不改顺序：命中项之间仍是 id 倒序。"""
        today = datetime.date.today()
        keep_a = ContractFactory(name="在办 A", status="active", end_date=today + datetime.timedelta(days=5))
        ContractFactory(name="已归档", status="archived", end_date=today + datetime.timedelta(days=1))
        keep_b = ContractFactory(name="在办 B", status="active", end_date=today - datetime.timedelta(days=90))

        svc = self._service()
        data = svc.list_contracts_page(
            page=1, page_size=50, status="active", include_facets=False, perm_open_access=True
        )
        ids = [c.id for c in data["items"]]

        assert ids == sorted([keep_a.id, keep_b.id], reverse=True)
