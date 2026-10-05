"""JTN 案件选择弹窗（layui）操作与确认循环单测。

mock frame/page 的 evaluate 返回值序列，断言：
- radio 勾选 / 弹窗开合判断 / 警告层关闭的 JS 桥接与类型收敛
- confirm_case_selection 的确认循环：正常关闭、警告后重选重试、
  重选失败立即抛错、重试耗尽抛「回填失败」
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from apps.oa_filing.services.oa_scripts.jtn import case_dialog as cd_mod
from apps.oa_filing.services.oa_scripts.jtn.case_dialog import (
    confirm_case_selection,
    dismiss_case_alert,
    is_case_dialog_open,
    select_case_radio_in_frame,
)


@pytest.fixture
def no_sleep(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    sleep = AsyncMock()
    monkeypatch.setattr(cd_mod, "asyncio", SimpleNamespace(sleep=sleep))
    return sleep


class TestPrimitives:
    @pytest.mark.asyncio
    async def test_select_case_radio_returns_bool(self):
        for returned, expected in ((True, True), (False, False), ("yes", True), ("", False)):
            frame = _mock_with_evaluate(returned)
            assert await select_case_radio_in_frame(frame, "OA-1") is expected
            frame.evaluate.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_is_case_dialog_open_coerces_to_bool(self):
        for returned, expected in ((True, True), (0, False), ("层", True), (None, False)):
            page = _mock_with_evaluate(returned)
            assert await is_case_dialog_open(page) is expected

    @pytest.mark.asyncio
    async def test_dismiss_case_alert_keeps_str_only(self):
        for returned, expected in (("请选择对应的案件信息", "请选择对应的案件信息"), (None, None), (123, None)):
            page = _mock_with_evaluate(returned)
            assert await dismiss_case_alert(page) is expected

    @pytest.mark.asyncio
    async def test_js_constants_contain_expected_markers(self):
        # 选择器契约：radio 勾选依赖 tr 第二列案件编号，弹窗判断依赖 layui-layer
        assert 'input[type="radio"]' in cd_mod._SELECT_RADIO_FN
        assert ".layui-layer" in cd_mod._IS_DIALOG_OPEN_FN
        assert "请选择对应的案件信息" in cd_mod._DISMISS_ALERT_FN
        assert "选择" in cd_mod._CLICK_CHOOSE_FN


class TestConfirmCaseSelection:
    """evaluate 调用序列：每次循环依次消耗 弹窗开合判断 / 点「选择」/ 警告检测。"""

    def _page(self, results: list[Any]) -> Any:
        return _mock_with_evaluate_sequence(results)

    @pytest.mark.asyncio
    async def test_dialog_open_click_then_closed_returns(self, no_sleep):
        # 序列：弹窗开 → 点选择 → 无警告 → 弹窗已关 → 返回
        page = self._page([True, "clicked", None, False])

        await confirm_case_selection(page, "OA-1", find_frame=AsyncMock(), wait_after_click=0.2)

        assert no_sleep.await_count == 1
        assert cd_mod._CLICK_CHOOSE_FN in [c.args[0] for c in page.evaluate.await_args_list]

    @pytest.mark.asyncio
    async def test_dialog_already_closed_returns_without_click(self, no_sleep):
        # 初始即关闭：跳过点击，最终开合复查仍为关 → 返回
        page = self._page([False, None, False])

        await confirm_case_selection(page, "OA-1", find_frame=AsyncMock(), wait_after_click=0.2)

        assert cd_mod._CLICK_CHOOSE_FN not in [c.args[0] for c in page.evaluate.await_args_list]

    @pytest.mark.asyncio
    async def test_alert_triggers_reselect_and_retry(self, no_sleep):
        # 第1轮：开→点选择→警告；重新勾选；第2轮：开→点选择→无警告→已关
        page = self._page([True, "clicked", "请选择对应的案件信息", True, "clicked", None, False])
        frame = _mock_with_evaluate(True)
        find_frame = AsyncMock(return_value=frame)

        await confirm_case_selection(page, "OA-2", find_frame=find_frame, wait_after_click=0.1)

        find_frame.assert_awaited_once_with(page)
        frame.evaluate.assert_awaited_once_with(cd_mod._SELECT_RADIO_FN, "OA-2")

    @pytest.mark.asyncio
    async def test_alert_with_missing_frame_raises(self, no_sleep):
        page = self._page([True, "clicked", "请选择对应的案件信息"])
        find_frame = AsyncMock(return_value=None)

        with pytest.raises(RuntimeError, match="重试勾选案件失败: OA-3"):
            await confirm_case_selection(page, "OA-3", find_frame=find_frame, wait_after_click=0.1)

    @pytest.mark.asyncio
    async def test_alert_with_failed_reselect_raises(self, no_sleep):
        page = self._page([True, "clicked", "请选择对应的案件信息"])
        frame = _mock_with_evaluate(False)
        find_frame = AsyncMock(return_value=frame)

        with pytest.raises(RuntimeError, match="重试勾选案件失败: OA-4"):
            await confirm_case_selection(page, "OA-4", find_frame=find_frame, wait_after_click=0.1)

    @pytest.mark.asyncio
    async def test_exhausted_attempts_raise(self, no_sleep):
        # 弹窗始终开、始终无警告 → 3 轮后抛「回填失败」
        page = self._page([True, "clicked", None, True] * 3)

        with pytest.raises(RuntimeError, match="案件选择弹窗回填失败"):
            await confirm_case_selection(page, "OA-5", find_frame=AsyncMock(), wait_after_click=0.1)

        assert no_sleep.await_count == 3


# ──────────── 小工具 ────────────


def _mock_with_evaluate(returned: Any) -> Any:
    obj = SimpleNamespace()
    obj.evaluate = AsyncMock(return_value=returned)
    return obj


def _mock_with_evaluate_sequence(results: list[Any]) -> Any:
    obj = SimpleNamespace()
    obj.evaluate = AsyncMock(side_effect=results)
    return obj
