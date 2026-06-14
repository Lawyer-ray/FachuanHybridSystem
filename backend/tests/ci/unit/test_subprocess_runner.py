"""Tests for apps.core.infrastructure.subprocess_runner."""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from apps.core.exceptions import ExternalServiceError
from apps.core.infrastructure.subprocess_runner import SubprocessOutput, SubprocessRunner


class TestSubprocessOutput:
    def test_dataclass(self):
        out = SubprocessOutput(stdout="ok", stderr="", returncode=0)
        assert out.stdout == "ok"
        assert out.returncode == 0


class TestSubprocessRunnerValidateArgs:
    def test_not_list(self):
        runner = SubprocessRunner()
        with pytest.raises(ExternalServiceError, match="参数无效"):
            runner.run(args="not a list")  # type: ignore[arg-type]

    def test_empty_list(self):
        runner = SubprocessRunner()
        with pytest.raises(ExternalServiceError, match="参数无效"):
            runner.run(args=[])

    def test_non_string_elements(self):
        runner = SubprocessRunner()
        with pytest.raises(ExternalServiceError, match="参数无效"):
            runner.run(args=["echo", 123])  # type: ignore[list-item]

    def test_empty_program(self):
        runner = SubprocessRunner()
        with pytest.raises(ExternalServiceError, match="参数无效"):
            runner.run(args=["  ", "arg"])

    def test_program_not_in_whitelist(self):
        runner = SubprocessRunner(allowed_programs={"allowed_cmd"})
        with pytest.raises(ExternalServiceError, match="不允许"):
            runner.run(args=["forbidden_cmd"])


class TestSubprocessRunnerTruncate:
    def test_within_limit(self):
        runner = SubprocessRunner(max_output_chars=100)
        assert runner._truncate("hello") == "hello"

    def test_exceeds_limit(self):
        runner = SubprocessRunner(max_output_chars=5)
        result = runner._truncate("hello world")
        assert result == "hello...(truncated)"

    def test_empty_string(self):
        runner = SubprocessRunner()
        assert runner._truncate("") == ""

    def test_none_string(self):
        runner = SubprocessRunner()
        assert runner._truncate(None) == ""  # type: ignore[arg-type]

    def test_zero_max_chars(self):
        runner = SubprocessRunner(max_output_chars=0)
        assert runner._truncate("anything") == ""


class TestSubprocessRunnerRun:
    @patch("apps.core.infrastructure.subprocess_runner.subprocess.run")
    def test_success(self, mock_run):
        mock_run.return_value = MagicMock(stdout="output", stderr="", returncode=0)
        runner = SubprocessRunner()
        result = runner.run(args=["echo", "hello"])
        assert result.stdout == "output"
        assert result.returncode == 0

    @patch("apps.core.infrastructure.subprocess_runner.subprocess.run")
    def test_nonzero_exit(self, mock_run):
        exc = subprocess.CalledProcessError(1, "cmd")
        exc.stdout = "out"
        exc.stderr = "err"
        mock_run.side_effect = exc
        runner = SubprocessRunner()
        with pytest.raises(ExternalServiceError, match="执行失败"):
            runner.run(args=["cmd"], check=True)

    @patch("apps.core.infrastructure.subprocess_runner.subprocess.run")
    def test_timeout(self, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired("cmd", 5)
        runner = SubprocessRunner()
        with pytest.raises(ExternalServiceError, match="执行超时"):
            runner.run(args=["cmd"], timeout_seconds=5)

    @patch("apps.core.infrastructure.subprocess_runner.subprocess.run")
    def test_file_not_found(self, mock_run):
        mock_run.side_effect = FileNotFoundError("not found")
        runner = SubprocessRunner()
        with pytest.raises(ExternalServiceError, match="不存在"):
            runner.run(args=["nonexistent"])

    @patch("apps.core.infrastructure.subprocess_runner.subprocess.run")
    def test_generic_exception(self, mock_run):
        mock_run.side_effect = RuntimeError("unexpected")
        runner = SubprocessRunner()
        with pytest.raises(ExternalServiceError, match="执行失败"):
            runner.run(args=["cmd"])


class TestSubprocessRunnerPopen:
    @patch("apps.core.infrastructure.subprocess_runner.subprocess.Popen")
    def test_success(self, mock_popen):
        mock_popen.return_value = MagicMock()
        runner = SubprocessRunner()
        result = runner.popen(args=["echo"])
        assert result is not None

    def test_shell_raises(self):
        runner = SubprocessRunner()
        with pytest.raises(ExternalServiceError, match="不安全"):
            runner.popen(args=["echo"], shell=True)

    @patch("apps.core.infrastructure.subprocess_runner.subprocess.Popen")
    def test_file_not_found(self, mock_popen):
        mock_popen.side_effect = FileNotFoundError("nope")
        runner = SubprocessRunner()
        with pytest.raises(ExternalServiceError, match="不存在"):
            runner.popen(args=["nonexistent"])

    @patch("apps.core.infrastructure.subprocess_runner.subprocess.Popen")
    def test_generic_error(self, mock_popen):
        mock_popen.side_effect = OSError("generic")
        runner = SubprocessRunner()
        with pytest.raises(ExternalServiceError, match="执行失败"):
            runner.popen(args=["cmd"])
