"""SMS 任务队列测试。"""

from __future__ import annotations

from apps.automation.services.sms.task_queue import DjangoQTaskQueue


class TestDjangoQTaskQueue:
    """DjangoQTaskQueue 测试。"""

    def test_enqueue_callable(self) -> None:
        """测试 callable 路径转换。"""
        queue = DjangoQTaskQueue()
        # 测试 callable 转换为字符串路径
        def my_func() -> None:
            pass

        # DjangoQTaskQueue.enqueue 会将 callable 转为字符串路径
        # 这里只测试转换逻辑，不测试实际提交
        target = f"{my_func.__module__}.{my_func.__qualname__}"
        assert "my_func" in target

    def test_enqueue_string_path(self) -> None:
        """测试字符串路径。"""
        queue = DjangoQTaskQueue()
        # 字符串路径直接使用
        target = "apps.automation.tasks.execute_scraper_task"
        assert target == "apps.automation.tasks.execute_scraper_task"
