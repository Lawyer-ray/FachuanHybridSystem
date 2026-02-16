"""Module for subprocess runner."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from typing import Any

from apps.core.exceptions import ExternalServiceError
from apps.core.security.scrub import scrub_text


@dataclass(frozen=True)
class SubprocessOutput:
    stdout: str
    stderr: str
    returncode: int


class SubprocessRunner:
    def __init__(self, *, allowed_programs: set[str] | None = None, max_output_chars: int = 20_000) -> None:
        self._allowed_programs = allowed_programs
        self._max_output_chars = int(max_output_chars) if max_output_chars is not None else 20_000

    def _truncate(self, value: str) -> str:
        if not value:
            return ""
        if self._max_output_chars <= 0:
            return ""
        if len(value) <= self._max_output_chars:
            return value
        return value[: self._max_output_chars] + "...(truncated)"

    def _validate_args(self, args: list[str]) -> None:
        if not isinstance(args, list) or not args or not all(isinstance(a, str) for a in args):
            raise ExternalServiceError(message="外部命令参数无效", code="SUBPROCESS_INVALID_ARGS", errors={})
        program = str(args[0] or "").strip()
        if not program:
            raise ExternalServiceError(message="外部命令参数无效", code="SUBPROCESS_INVALID_ARGS", errors={})
        if self._allowed_programs is not None and program not in self._allowed_programs:
            raise ExternalServiceError(
                message="外部命令不允许",
                code="SUBPROCESS_NOT_ALLOWED",
                errors={"command": scrub_text(program)},
            )

    def run(
        self,
        *,
        args: list[str],
        timeout_seconds: float | None = None,
        check: bool = False,
        text: bool = True,
    ) -> SubprocessOutput:
        self._validate_args(args)
        try:
            cp = subprocess.run(
                args,
                check=check,
                capture_output=True,
                text=text,
                timeout=timeout_seconds,
            )
        except subprocess.CalledProcessError as e:
            stdout = e.stdout or ""
            stderr = e.stderr or ""
            if isinstance(stdout, bytes):
                stdout = stdout.decode("utf-8", errors="replace")
            if isinstance(stderr, bytes):
                stderr = stderr.decode("utf-8", errors="replace")
            raise ExternalServiceError(
                message="外部命令执行失败",
                code="SUBPROCESS_NONZERO_EXIT",
                errors={
                    "command": scrub_text(str(args[0] if args else "")),
                    "returncode": int(getattr(e, "returncode", 0) or 0),
                    "stdout": self._truncate(scrub_text(str(stdout))),
                    "stderr": self._truncate(scrub_text(str(stderr))),
                },
            ) from e
        except subprocess.TimeoutExpired as e:
            raise ExternalServiceError(
                message="外部命令执行超时",
                code="SUBPROCESS_TIMEOUT",
                errors={
                    "command": scrub_text(str(args[0] if args else "")),
                    "timeout_seconds": timeout_seconds,
                    "detail": self._truncate(scrub_text(str(e))),
                },
            ) from e
        except FileNotFoundError as e:
            raise ExternalServiceError(
                message="外部命令不存在",
                code="SUBPROCESS_NOT_FOUND",
                errors={
                    "command": scrub_text(str(args[0] if args else "")),
                    "detail": self._truncate(scrub_text(str(e))),
                },
            ) from e
        except Exception as e:
            raise ExternalServiceError(
                message="外部命令执行失败",
                code="SUBPROCESS_FAILED",
                errors={
                    "command": scrub_text(str(args[0] if args else "")),
                    "detail": self._truncate(scrub_text(str(e))),
                },
            ) from e

        stdout = cp.stdout or ""
        stderr = cp.stderr or ""
        if isinstance(stdout, bytes):
            stdout = stdout.decode("utf-8", errors="replace")
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", errors="replace")
        return SubprocessOutput(
            stdout=self._truncate(scrub_text(str(stdout))),
            stderr=self._truncate(scrub_text(str(stderr))),
            returncode=int(cp.returncode or 0),
        )

    def popen(self, *, args: list[str], **kwargs: Any) -> subprocess.Popen[Any]:
        self._validate_args(args)
        if "shell" in kwargs and kwargs.get("shell"):
            raise ExternalServiceError(
                message="外部命令执行参数不安全",
                code="SUBPROCESS_UNSAFE_OPTIONS",
                errors={"command": scrub_text(str(args[0] if args else "")), "option": "shell"},
            )
        try:
            return subprocess.Popen(args, **kwargs)
        except FileNotFoundError as e:
            raise ExternalServiceError(
                message="外部命令不存在",
                code="SUBPROCESS_NOT_FOUND",
                errors={
                    "command": scrub_text(str(args[0] if args else "")),
                    "detail": self._truncate(scrub_text(str(e))),
                },
            ) from e
        except Exception as e:
            raise ExternalServiceError(
                message="外部命令执行失败",
                code="SUBPROCESS_FAILED",
                errors={
                    "command": scrub_text(str(args[0] if args else "")),
                    "detail": self._truncate(scrub_text(str(e))),
                },
            ) from e
