"""全局检索端点的降级隔离回归（/api/v1/search）。

事故背景（2026-10）：message_hub 的 InboxMessage 加了 upload_link 字段，但迁移
没上库，``search_inbox`` 报 ``column ... upload_link_id does not exist``。
当时 ``asyncio.gather`` 没有 ``return_exceptions=True``，一个类别的异常直接把整个
端点抛成 500 —— 用户侧看到的是「全局检索啥都搜不出来」，另外五类完全正常的检索
结果一并丢失，排查时也看不出是哪一类坏了。

本测试锁两件事：
1. 任一类查询抛异常时，端点仍返回 200，且其余类别结果照常下发；
2. 坏掉的那一类退化为空列表（不是整个响应为空），并记 ERROR 日志留痕。
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest
from django.test import RequestFactory

# 不打 django_db：六个 search_* 全部被 mock，端点里唯一的 DB 依赖
# （resolve_request_org_access）也被下面的 patch 掉，不碰库即无迁移依赖。


def _call_search(q: str = "测试") -> dict[str, Any]:
    """直接调用端点函数：绕开鉴权中间件与 org_access 解析，只验证 gather 的降级行为。"""
    import asyncio

    from apps.core.api.search_api import global_search

    request = RequestFactory().get("/api/v1/search", {"q": q, "limit": 8})
    with (
        patch("apps.core.security.admin_access.get_request_user", return_value=None),
        patch(
            "apps.core.dependencies.business.resolve_request_org_access",
            return_value=None,
        ),
    ):
        return asyncio.run(global_search(request, q=q, limit=8))


class TestGlobalSearchDegradation:
    def test_one_category_failure_does_not_blank_whole_response(self) -> None:
        """inbox 查询炸掉（模拟缺列）时，其余类别照常返回，inbox 退化为空。"""
        from apps.core.services.search_service import SearchResultItem

        ok_item = SearchResultItem(id=1, title="张三", subtitle="")

        with (
            patch("apps.core.services.search_service.search_inbox") as inbox_mock,
            patch("apps.core.services.search_service.search_contracts") as contracts_mock,
            patch("apps.core.services.search_service.search_cases") as cases_mock,
            patch("apps.core.services.search_service.search_clients") as clients_mock,
            patch("apps.core.services.search_service.search_court_sms") as sms_mock,
            patch("apps.core.services.search_service.search_contacts") as contacts_mock,
        ):
            # 典型事故形态：模型有字段、库里没列
            inbox_mock.side_effect = Exception("column upload_link_id does not exist")
            contracts_mock.return_value = [ok_item]
            cases_mock.return_value = []
            clients_mock.return_value = [ok_item]
            sms_mock.return_value = []
            contacts_mock.return_value = []

            result = _call_search()

        # 不抛异常 = 端点不会退化成 500
        assert set(result) == {"clients", "cases", "contracts", "inbox", "court_sms", "contacts"}
        # 坏掉的类别只影响自己
        assert result["inbox"] == []
        # 其余类别结果完整保留（此前整包丢失）
        assert [i.title for i in result["contracts"]] == ["张三"]
        assert [i.title for i in result["clients"]] == ["张三"]

    def test_all_categories_succeed_normal_path(self) -> None:
        """正常路径不受 return_exceptions 影响：各类别结果原样合并。"""
        from apps.core.services.search_service import SearchResultItem

        with (
            patch("apps.core.services.search_service.search_inbox") as inbox_mock,
            patch("apps.core.services.search_service.search_contracts") as contracts_mock,
            patch("apps.core.services.search_service.search_cases") as cases_mock,
            patch("apps.core.services.search_service.search_clients") as clients_mock,
            patch("apps.core.services.search_service.search_court_sms") as sms_mock,
            patch("apps.core.services.search_service.search_contacts") as contacts_mock,
        ):
            inbox_mock.return_value = [SearchResultItem(id=9, title="邮件", subtitle="a@b.c")]
            contracts_mock.return_value = [SearchResultItem(id=1, title="合同A", case_type="civil")]
            cases_mock.return_value = []
            clients_mock.return_value = []
            sms_mock.return_value = []
            contacts_mock.return_value = []

            result = _call_search()

        assert result["inbox"][0].title == "邮件"
        assert result["contracts"][0].case_type == "civil"

    def test_failed_category_logs_error(self, caplog: pytest.LogCaptureFixture) -> None:
        """坏掉的类别必须留 ERROR 日志——否则下次又只能靠翻 stacktrace 猜。"""
        import logging

        with patch("apps.core.services.search_service.search_inbox") as inbox_mock:
            inbox_mock.side_effect = RuntimeError("boom")
            with caplog.at_level(logging.ERROR):
                _call_search()

        records = [r for r in caplog.records if r.levelno >= logging.ERROR]
        assert records, "类别失败必须记 ERROR 日志"
        # 日志里要带类别名，才能定位是哪一类挂了
        assert "inbox" in records[0].getMessage()

    def test_empty_query_short_circuits(self) -> None:
        """空关键词直接返回空结构（六类全空），不触碰任何查询。"""
        with patch("apps.core.services.search_service.search_inbox") as inbox_mock:
            result = _call_search(q="   ")
        assert inbox_mock.call_count == 0
        assert set(result) == {"clients", "cases", "contracts", "inbox", "court_sms", "contacts"}
        assert all(v == [] for v in result.values())
