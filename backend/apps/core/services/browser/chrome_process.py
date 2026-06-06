"""Chrome 进程管理。

提供 CDP 模式下 Chrome 进程的启动、终止、端口检测能力。
统一 express_query 和 gsxt 各自的 Chrome 进程管理逻辑。
"""

from __future__ import annotations

import logging
import os
import signal
import subprocess
import time
from pathlib import Path
from typing import Final

import httpx

logger = logging.getLogger("apps.core")

_DEFAULT_CDP_PORT: Final[int] = 9222


def _detect_chrome_path() -> str:
    """自动检测 Chrome 可执行文件路径。"""
    import platform

    system = platform.system().lower()
    if system == "darwin":
        return "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    if system == "linux":
        import shutil

        for name in ("google-chrome", "google-chrome-stable", "chromium-browser", "chromium"):
            found = shutil.which(name)
            if found:
                return found
        return "google-chrome"
    return r"C:\Program Files\Google\Chrome\Application\chrome.exe"


def is_cdp_ready(port: int = _DEFAULT_CDP_PORT) -> bool:
    """检查 CDP 端点是否可用。"""
    try:
        with httpx.Client(transport=httpx.HTTPTransport(http2=False)) as client:
            resp = client.get(f"http://127.0.0.1:{port}/json/version", timeout=2)
            return resp.status_code == 200
    except Exception:
        return False


def launch_chrome(
    *,
    port: int = _DEFAULT_CDP_PORT,
    user_data_dir: str | Path | None = None,
    chrome_path: str | None = None,
    extra_args: list[str] | None = None,
) -> subprocess.Popen:
    """启动带调试端口的 Chrome 进程。

    Args:
        port: CDP 调试端口
        user_data_dir: Chrome 用户数据目录，None 则使用临时目录
        chrome_path: Chrome 可执行文件路径，None 则自动检测
        extra_args: 额外的 Chrome 启动参数

    Returns:
        Chrome 进程对象

    Raises:
        RuntimeError: Chrome 启动失败
    """
    if chrome_path is None:
        chrome_path = _detect_chrome_path()

    _is_temp_user_dir = user_data_dir is None
    if user_data_dir is None:
        import tempfile

        user_data_dir = Path(tempfile.mkdtemp(prefix="chrome_pw_"))
    else:
        user_data_dir = Path(user_data_dir)
        user_data_dir.mkdir(parents=True, exist_ok=True)

    cmd: list[str] = [
        chrome_path,
        f"--remote-debugging-port={port}",
        f"--user-data-dir={user_data_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-blink-features=AutomationControlled",
        *(extra_args or []),
    ]

    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        # 记录临时用户数据目录，供 kill_chrome 清理
        if _is_temp_user_dir:
            process._temp_user_data_dir = str(user_data_dir)  # type: ignore[attr-defined]
        logger.info("Chrome 启动成功 (PID=%d, port=%d)", process.pid, port)
    except FileNotFoundError:
        raise RuntimeError(f"Chrome 未找到: {chrome_path}") from None
    except OSError as exc:
        raise RuntimeError(f"Chrome 启动失败: {exc}") from exc

    # 等待 CDP 端点就绪
    for _ in range(15):
        time.sleep(1)
        if is_cdp_ready(port):
            logger.info("CDP 端点已就绪 (port=%d)", port)
            return process
        if process.poll() is not None:
            raise RuntimeError("Chrome 进程意外退出")

    raise RuntimeError(f"Chrome CDP 端点未就绪 (port={port})，请检查 Chrome 是否正常运行")


def _cleanup_temp_user_data_dir(process: subprocess.Popen) -> None:
    """清理 launch_chrome 自动创建的临时用户数据目录。"""
    import shutil

    temp_dir = getattr(process, "_temp_user_data_dir", None)
    if temp_dir:
        shutil.rmtree(temp_dir, ignore_errors=True)
        logger.debug("已清理 Chrome 临时用户数据目录: %s", temp_dir)


def kill_chrome(
    process: subprocess.Popen | None = None,
    *,
    port: int = _DEFAULT_CDP_PORT,
) -> None:
    """终止 Chrome 进程。

    如果传入 process，终止该进程。
    如果不传 process，清理占用指定端口的孤儿进程。
    """
    # 终止指定进程
    if process is not None:
        try:
            process.terminate()
            process.wait(timeout=5)
            logger.info("Chrome 进程已终止 (PID=%d)", process.pid)
        except subprocess.TimeoutExpired:
            process.kill()
            logger.warning("Chrome 进程强制终止 (PID=%d)", process.pid)
        except Exception as exc:
            logger.warning("终止 Chrome 进程失败: %s", exc)
        _cleanup_temp_user_data_dir(process)
        return

    # 清理占用端口的孤儿进程
    try:
        result = subprocess.run(
            ["/usr/sbin/lsof", "-ti", f":{port}"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.stdout.strip():
            for pid_str in result.stdout.strip().split("\n"):
                try:
                    pid = int(pid_str.strip())
                    os.kill(pid, signal.SIGTERM)
                    logger.info("已终止占用端口 %d 的进程 (PID=%d)", port, pid)
                except (ValueError, ProcessLookupError, PermissionError):
                    pass
                time.sleep(1)
    except Exception as exc:
        logger.debug("检查端口 %d 失败: %s", port, exc)
