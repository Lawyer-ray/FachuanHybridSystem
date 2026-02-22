import subprocess

import pytest

from apps.core.exceptions import ExternalServiceError
from apps.core.subprocess_runner import SubprocessRunner


def test_subprocess_runner_timeout_maps_to_external_service_error(monkeypatch):
    def boom(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=kwargs.get("args") or [], timeout=1)

    monkeypatch.setattr("apps.core.subprocess_runner.subprocess.run", boom)
    with pytest.raises(ExternalServiceError) as e:
        SubprocessRunner().run(args=["echo", "hi"], timeout_seconds=1)
    assert e.value.code == "SUBPROCESS_TIMEOUT"


def test_subprocess_runner_popen_rejects_shell_true(monkeypatch):
    monkeypatch.setattr(
        "apps.core.subprocess_runner.subprocess.Popen",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("should not popen")),
    )
    with pytest.raises(ExternalServiceError) as e:
        SubprocessRunner().popen(args=["echo", "hi"], shell=True)  # noqa: S604
    assert e.value.code == "SUBPROCESS_UNSAFE_OPTIONS"


def test_subprocess_runner_allowlist_blocks_unapproved_program():
    with pytest.raises(ExternalServiceError) as e:
        SubprocessRunner(allowed_programs={"echo"}).run(args=["rm", "-rf", "/"], timeout_seconds=1)
    assert e.value.code == "SUBPROCESS_NOT_ALLOWED"


def test_subprocess_runner_called_process_error_maps_to_external_service_error(monkeypatch):
    def boom(*args, **kwargs):
        raise subprocess.CalledProcessError(returncode=2, cmd=["echo", "x"], output="ok", stderr="bad")

    monkeypatch.setattr("apps.core.subprocess_runner.subprocess.run", boom)
    with pytest.raises(ExternalServiceError) as e:
        SubprocessRunner().run(args=["echo", "x"], timeout_seconds=1, check=True)
    assert e.value.code == "SUBPROCESS_NONZERO_EXIT"
