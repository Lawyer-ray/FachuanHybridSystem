"""任务失败日志降噪：run_task 与 django-q monitor 两处都不能再刷整段堆栈。"""

from __future__ import annotations

import logging

import pytest

from apps.core.infrastructure.task_result_logging import TaskResultLogFilter
from apps.core.tasking.context import TaskContext
from apps.core.tasking.entries import _is_expected_task_error, _log_task_failure, _shorten


class TestExpectedTaskError:
    def test_dns_failure_is_expected(self):
        import socket

        assert _is_expected_task_error(socket.gaierror(8, "nodename nor servname provided")) is True

    def test_timeout_is_expected(self):
        assert _is_expected_task_error(TimeoutError("timed out")) is True

    def test_connection_error_message_is_expected(self):
        # IMAP 侧抛的是内置 ConnectionError，链上下文的 gaierror 只体现在文案里
        exc = ConnectionError("IMAP 主机无法解析（已尝试: a.com, b.com）")
        assert _is_expected_task_error(exc) is True

    def test_playwright_closed_is_expected(self):
        assert _is_expected_task_error(Exception("Target closed")) is True

    def test_code_defect_is_not_expected(self):
        assert _is_expected_task_error(AttributeError("type object has no attribute 'X'")) is False

    def test_shorten_collapses_newlines(self):
        assert _shorten("a\n  b\nc") == "a b c"

    def test_shorten_truncates(self):
        out = _shorten("x" * 1000, limit=10)
        assert out.startswith("xxxxxxxxxx")
        assert "共 1000 字符" in out


class TestRunTaskFailureLog:
    """run_task 内部：环境类失败落一行 WARNING，代码缺陷才抛完整栈。"""

    def _run(self, exc: Exception, caplog):
        target_module = "apps.core.tasking.entries"
        logger = logging.getLogger(target_module)

        def _boom(*_a, **_k):
            raise exc

        from unittest.mock import patch

        with patch("apps.core.tasking.entries._import_callable", return_value=_boom):
            with caplog.at_level(logging.DEBUG, logger=target_module):
                with pytest.raises(type(exc)):
                    from apps.core.tasking.entries import run_task

                    run_task("fake.task", [], {}, TaskContext(task_name="message_hub:sync_source").to_dict())
        return logger

    def test_expected_error_logs_warning_without_traceback(self, caplog):
        self._run(ConnectionError("IMAP 连接失败: name or service not known"), caplog)

        record = next(r for r in caplog.records if "任务因外部环境失败" in r.getMessage())
        assert record.levelno == logging.WARNING
        assert record.exc_info is None
        assert "fake.task" in record.getMessage()

    def test_unexpected_error_keeps_traceback(self, caplog):
        self._run(AttributeError("boom"), caplog)

        record = next(r for r in caplog.records if "task_failed" in r.getMessage())
        assert record.levelno == logging.ERROR
        assert record.exc_info is not None
        assert record.error_type == "AttributeError"

    def test_log_helper_shortens_long_error(self, caplog):
        logger = logging.getLogger("apps.core.tasking")
        with caplog.at_level(logging.ERROR, logger="apps.core.tasking"):
            _log_task_failure("fake.task", TaskContext(), RuntimeError("y" * 5000))
        record = caplog.records[-1]
        assert len(record.getMessage()) < 800
        assert logger.name == "apps.core.tasking"


class TestTaskResultLogFilter:
    """django-q monitor 的失败日志（含整段 traceback）压成单行。"""

    FAILED_MSG = (
        "'apps.core.tasking.entries.run_task' (finch-asparagus-indigo-montana) 失败 - "
        "IMAP 连接失败（已尝试: mail.example.com）: [Errno 8] nodename nor servname provided"
        " : Traceback (most recent call last):\n"
        '  File "/x/imap_fetcher.py", line 128, in _connect\n'
        "    m = imaplib.IMAP4_SSL(host, IMAP_PORT)\n"
        "socket.gaierror: [Errno 8] nodename nor servname provided, or not known\n"
    )

    def _record(self, msg: str) -> logging.LogRecord:
        return logging.LogRecord(
            name="django-q monitor.monitor",
            level=logging.ERROR,
            pathname=__file__,
            lineno=10,
            msg=msg,
            args=None,
            exc_info=None,
        )

    def test_traceback_collapsed_to_single_line(self):
        record = self._record(self.FAILED_MSG)
        TaskResultLogFilter().filter(record)

        text = record.getMessage()
        assert "\n" not in text
        assert "Traceback (most recent call last)" not in text
        assert "imaplib.IMAP4_SSL" not in text
        assert "任务失败" in text
        # 保留了可定位的信息（异常末行）
        assert "nodename nor servname provided" in text

    def test_expected_failure_downgraded_to_warning(self):
        record = self._record(self.FAILED_MSG)
        TaskResultLogFilter().filter(record)
        assert record.levelno == logging.WARNING
        assert "外部环境不可用" in record.getMessage()

    def test_random_task_name_replaced_with_readable_label(self):
        record = self._record(self.FAILED_MSG)
        TaskResultLogFilter().filter(record)
        text = record.getMessage()
        assert "finch-asparagus-indigo-montana" not in text
        # 能拿到业务任务名时用业务名，否则回落到 func 路径
        assert "message_hub:sync_source" in text or "apps.core.tasking.entries.run_task" in text

    def test_unexpected_failure_keeps_error_level(self):
        msg = (
            "'apps.core.tasking.entries.run_task' (x-y) 失败 - AttributeError: boom"
            " : Traceback (most recent call last):\n"
            '  File "/x/a.py", line 1, in f\n'
            "AttributeError: boom\n"
        )
        record = self._record(msg)
        TaskResultLogFilter().filter(record)
        assert record.levelno == logging.ERROR
        assert "需要排查" in record.getMessage()
        assert record.exc_info is None  # 不再二次吐栈

    def test_non_task_messages_pass_through(self):
        record = self._record("上一轮消息同步调度仍在锁周期内，跳过本轮")
        assert TaskResultLogFilter().filter(record) is True
        assert record.getMessage() == "上一轮消息同步调度仍在锁周期内，跳过本轮"
        assert record.levelno == logging.ERROR


class TestTaskResultLogFilterWithPrefix:
    """日志被前端格式化器加上时间戳前缀时（如 '[2026-11-09 13:44:46] ERROR - '）仍要能切。"""

    WITH_PREFIX = (
        "[2026-11-09 13:44:46] ERROR - 'apps.core.tasking.entries.run_task' "
        "(finch-asparagus-indigo-montana) 失败 - "
        "IMAP 连接失败（已尝试: mail.example.com, imap.example.com）: [Errno 8] nodename nor servname provided"
        " : Traceback (most recent call last):\n"
        '  File "/x/imap_fetcher.py", line 128, in _connect\n'
        "socket.gaierror: [Errno 8] nodename nor servname provided, or not known\n"
    )

    def test_prefix_does_not_break_label(self):
        record = logging.LogRecord(
            name="django-q monitor.monitor",
            level=logging.ERROR,
            pathname=__file__,
            lineno=1,
            msg=self.WITH_PREFIX,
            args=None,
            exc_info=None,
        )
        TaskResultLogFilter().filter(record)
        text = record.getMessage()
        # 标签可能是业务任务名（请求上下文里残留）或 func 路径，但绝不能是随机名
        assert "message_hub:sync_source" in text or "apps.core.tasking.entries.run_task" in text
        assert "finch-asparagus-indigo-montana" not in text
        assert "Traceback" not in text
        assert record.levelno == logging.WARNING
