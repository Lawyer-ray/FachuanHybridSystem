"""Structure guard: 询价「删旧 + 写新」必须在同一事务内。

背景
----
``PreservationQuoteService.execute_quote`` 曾按下面顺序写库::

    await sync_to_async(InsuranceQuote.objects.filter(...).delete)()
    success_count, failed_count = await self._save_premium_results(...)   # -> bulk_create

两个 await 之间没有任何事务：``transaction.atomic`` 不能用于 async 上下文，
``ATOMIC_REQUESTS=False``，且所有调用方（async 视图 / Django-Q 任务经
``run_coro_sync`` / admin 批量执行）都不在外面包事务。于是 ``bulk_create``
一旦抛异常，旧报价记录已被永久删除、新记录没有落库——任务停在 RUNNING，
历史询价数据静默丢失。

修法是把「删 + 批量写」收进同步函数 ``_replace_quotes_sync``，事务边界写在
该函数内（一次 ``sync_to_async`` 调用跨过它）。状态迁移（RUNNING →
SUCCESS/PARTIAL_SUCCESS/FAILED）刻意留在事务外，由 ``execute_quote`` 原有的
``except`` 分支负责，避免「失败置 FAILED」被回滚掉。

本测试守三件事：
- A. ``_replace_quotes_sync`` 内存在 ``with transaction.atomic():`` 块
- B. ``delete()`` 与写新（``_save_premium_results_sync``，内部走 ``bulk_create``）
  都落在这个 atomic 块内
- C. ``execute_quote`` 不再有裸的 delete→save 序列，且状态迁移写在块外
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[3]

SERVICE_MODULE = "plugins/court_automation/preservation_quote/service.py"
MIXIN_MODULE = "plugins/court_automation/preservation_quote/execution_mixin.py"


def _parse_module(relative_path: str) -> ast.Module:
    path = BACKEND_DIR / relative_path
    assert path.exists(), f"找不到 {relative_path}"
    return ast.parse(path.read_text(encoding="utf-8"))


def _parse_service() -> ast.Module:
    return _parse_module(SERVICE_MODULE)


def _class_node(tree: ast.Module, name: str) -> ast.ClassDef:
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == name:
            return node
    raise AssertionError(f"未找到类 {name}")


def _method(class_node: ast.ClassDef, name: str) -> ast.FunctionDef | ast.AsyncFunctionDef:
    for node in class_node.body:
        # execute_quote 是 async def（AsyncFunctionDef），同步私有方法（FunctionDef）一并匹配
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise AssertionError(f"未找到方法 {name}")


def _atomic_blocks(func: ast.FunctionDef | ast.AsyncFunctionDef) -> list[ast.With]:
    """取出函数体内 ``with transaction.atomic():`` 的块。"""
    blocks: list[ast.With] = []
    for node in ast.walk(func):
        if not isinstance(node, ast.With):
            continue
        for item in node.items:
            ctx = item.context_expr
            if isinstance(ctx, ast.Call):
                callee = ctx.func
                if isinstance(callee, ast.Attribute) and callee.attr == "atomic":
                    blocks.append(node)
    return blocks


def _calls(func: ast.AST, attr: str) -> list[ast.AST]:
    """取出 ``<expr>.attr(...)`` 形式的调用节点。"""
    found: list[ast.AST] = []
    for node in ast.walk(func):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == attr:
            found.append(node)
    return found


def _within(node: ast.AST, container: ast.AST) -> bool:
    return any(child is node for child in ast.walk(container))


@pytest.mark.unit
class TestQuoteReplaceAtomic:
    """询价结果替换的事务边界守卫。"""

    def test_replace_quotes_sync_has_atomic_block(self) -> None:
        """A. 替换函数内必须存在 transaction.atomic() 块。"""
        service = _class_node(_parse_service(), "PreservationQuoteService")
        method = _method(service, "_replace_quotes_sync")

        assert _atomic_blocks(method), (
            f"{SERVICE_MODULE}::_replace_quotes_sync 缺少 `with transaction.atomic():`；"
            "删旧与写新必须在同一事务内，否则 bulk_create 失败会丢数据"
        )

    def test_delete_and_bulk_create_inside_atomic(self) -> None:
        """B. delete() 与写新（bulk_create）必须都落在 atomic 块内。"""
        service = _class_node(_parse_service(), "PreservationQuoteService")
        method = _method(service, "_replace_quotes_sync")
        # 写新实现在 mixin 的同步方法里（service 通过继承获得）
        mixin = _class_node(_parse_module(MIXIN_MODULE), "QuoteExecutionMixin")
        sync_writer = _method(mixin, "_save_premium_results_sync")

        blocks = _atomic_blocks(method)
        assert blocks, "缺少 atomic 块，无法校验包裹关系"
        atomic_block = blocks[0]

        deletes = _calls(method, "delete")
        assert deletes, "_replace_quotes_sync 内未找到 delete() 调用"
        for call in deletes:
            assert _within(call, atomic_block), (
                f"{SERVICE_MODULE}:{call.lineno} 的 delete() 在 atomic 块外，异常时旧数据会先被删掉且无法回滚"
            )

        # bulk_create 实际写在 _save_premium_results_sync 里，必须由 atomic 块内的调用引入
        writer_calls = _calls(method, "_save_premium_results_sync")
        assert writer_calls, "_replace_quotes_sync 内未调用 _save_premium_results_sync"
        for call in writer_calls:
            assert _within(call, atomic_block), (
                f"{SERVICE_MODULE}:{call.lineno} 的 _save_premium_results_sync 调用在 atomic 块外，"
                "写新失败时旧数据已删除"
            )

        assert _calls(sync_writer, "bulk_create"), (
            f"{MIXIN_MODULE}::_save_premium_results_sync 内未找到 bulk_create() 调用"
        )

    def test_execute_quote_has_no_bare_delete(self) -> None:
        """C. execute_quote 不再直接 delete，状态迁移仍在事务外。"""
        service = _class_node(_parse_service(), "PreservationQuoteService")
        execute = _method(service, "execute_quote")

        assert not _calls(execute, "delete"), (
            f"{SERVICE_MODULE}:execute_quote 仍直接调用 delete()；删除必须与写新一起收进 _replace_quotes_sync 的事务"
        )

        # 状态迁移（quote.status = ...）必须留在事务外，靠原 except 分支兜底
        assert not _atomic_blocks(execute), "execute_quote 不应包 atomic：状态迁移若在事务内，失败置 FAILED 会被回滚"
