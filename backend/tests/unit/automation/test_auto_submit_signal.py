"""
测试询价任务自动提交信号

验证当创建新的询价任务时，系统会自动提交到 Django Q 队列。
"""

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from apps.automation.models import PreservationQuote, QuoteStatus


@pytest.mark.django_db(transaction=True)
class TestAutoSubmitSignal:
    """测试询价任务自动提交信号"""

    def test_new_quote_auto_submits_to_django_q(self):
        """
        测试：创建新的询价任务时，自动提交到 Django Q 队列

        验证：
        - 创建新任务时，async_task 被调用
        - 传递正确的参数
        - 任务名称正确
        """
        with patch("apps.automation.signals.async_task") as mock_async_task:
            # 设置 mock 返回值
            mock_async_task.return_value = "test_task_id_123"

            # 创建询价任务
            quote = PreservationQuote.objects.create(
                preserve_amount=Decimal("100000.00"),
                corp_id="test_corp",
                category_id="test_category",
                status=QuoteStatus.PENDING,
            )

            # 验证 async_task 被调用
            mock_async_task.assert_called_once()

            # 验证调用参数
            call_args = mock_async_task.call_args
            assert call_args[0][0] == "apps.automation.tasks.execute_preservation_quote_task"
            assert call_args[0][1] == quote.id
            assert call_args[1]["task_name"] == f"询价任务 #{quote.id}"
            assert call_args[1]["timeout"] == 600

    def test_updated_quote_does_not_auto_submit(self):
        """
        测试：更新现有任务时，不会重新提交到队列

        验证：
        - 更新任务时，async_task 不被调用
        """
        with patch("apps.automation.signals.async_task") as mock_async_task:
            # 创建询价任务
            quote = PreservationQuote.objects.create(
                preserve_amount=Decimal("100000.00"),
                corp_id="test_corp",
                category_id="test_category",
                status=QuoteStatus.PENDING,
            )

            # 重置 mock
            mock_async_task.reset_mock()

            # 更新任务
            quote.preserve_amount = Decimal("200000.00")
            quote.save()

            # 验证 async_task 没有被调用
            mock_async_task.assert_not_called()

    def test_non_pending_quote_does_not_auto_submit(self):
        """
        测试：创建非 PENDING 状态的任务时，不会自动提交

        验证：
        - 状态为 RUNNING、SUCCESS、FAILED 等的任务不会自动提交
        """
        with patch("apps.automation.signals.async_task") as mock_async_task:
            # 创建状态为 RUNNING 的任务
            quote = PreservationQuote.objects.create(
                preserve_amount=Decimal("100000.00"),
                corp_id="test_corp",
                category_id="test_category",
                status=QuoteStatus.RUNNING,  # 非 PENDING 状态
            )

            # 验证 async_task 没有被调用
            mock_async_task.assert_not_called()

    def test_signal_handles_async_task_error_gracefully(self):
        """
        测试：当 async_task 失败时，信号处理器不会崩溃

        验证：
        - async_task 抛出异常时，任务仍然被创建
        - 错误被记录但不影响任务创建
        """
        with patch("apps.automation.signals.async_task") as mock_async_task:
            # 设置 mock 抛出异常
            mock_async_task.side_effect = Exception("Django Q 连接失败")

            # 创建询价任务（不应该抛出异常）
            quote = PreservationQuote.objects.create(
                preserve_amount=Decimal("100000.00"),
                corp_id="test_corp",
                category_id="test_category",
                status=QuoteStatus.PENDING,
            )

            # 验证任务被创建
            assert quote.id is not None
            assert quote.status == QuoteStatus.PENDING

            # 验证 async_task 被调用（尽管失败了）
            mock_async_task.assert_called_once()

    def test_multiple_quotes_auto_submit_independently(self):
        """
        测试：创建多个询价任务时，每个任务独立提交

        验证：
        - 每个任务都会触发一次 async_task 调用
        - 任务 ID 正确传递
        """
        with patch("apps.automation.signals.async_task") as mock_async_task:
            # 设置 mock 返回不同的 task_id
            mock_async_task.side_effect = ["task_1", "task_2", "task_3"]

            # 创建多个询价任务
            quote1 = PreservationQuote.objects.create(
                preserve_amount=Decimal("100000.00"),
                corp_id="test_corp",
                category_id="test_category",
                status=QuoteStatus.PENDING,
            )

            quote2 = PreservationQuote.objects.create(
                preserve_amount=Decimal("200000.00"),
                corp_id="test_corp",
                category_id="test_category",
                status=QuoteStatus.PENDING,
            )

            quote3 = PreservationQuote.objects.create(
                preserve_amount=Decimal("300000.00"),
                corp_id="test_corp",
                category_id="test_category",
                status=QuoteStatus.PENDING,
            )

            # 验证 async_task 被调用 3 次
            assert mock_async_task.call_count == 3

            # 验证每次调用的参数
            calls = mock_async_task.call_args_list
            assert calls[0][0][1] == quote1.id
            assert calls[1][0][1] == quote2.id
            assert calls[2][0][1] == quote3.id
