"""连接池默认关闭守卫 + `thread_sensitive=False` 与池不兼容的回归测试。

背景（2026-11-03 事故）：`GET /api/v1/oa-filing/session/105` 每 2s 轮询一次，
单请求只做一条 `SELECT`，却报
`psycopg_pool.PoolTimeout: couldn't get a connection after 10.00 sec`。
现场 `pg_stat_activity` 有 44 条 `idle`（非 `idle in transaction`）连接，
按 08:27→09:56→11:26→12:56→13:56 数小时单调增长。

根因：`OPTIONS["pool"]` 与 `sync_to_async(..., thread_sensitive=False)` 叠加。
    - Django 的 `connections` 是 `thread_critical=True` 的**线程局部**对象；
    - 开池后连接归还只发生在**持有它的那条线程**的 `close()` 里
      （`postgresql/base.py::_close → pool.putconn`），而 close 由
      `request_finished` 在**请求收尾线程**触发；
    - `thread_sensitive=False` 让 ORM 落到 anyio 默认线程池，于是连接
      **借出在 worker 线程、归还在别处**，worker 线程那份 wrapper 永不归还，
      池被逐步借空；anyio worker 长期存活 ⇒ 每条新 worker ≈ 永久少一条连接。

修复：`DB_POOL` 默认改回**关**（原先默认 `_pool_env == "" and DEBUG`，
即 dev 默认开）。只要池默认关着，`thread_sensitive=False` 不会耗尽池
（无池时每线程自持有连接）。彻底根治需收敛全站调用点后再评估开池。

复现脚本：`backend/devtools/repro_pool_leak.py`（同 8 并发 `SELECT 1`：
`thread_sensitive=False` + 池 = 立刻 PoolTimeout；`thread_sensitive=True` 正常）。
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from django.conf import settings

_SETTINGS_PY = Path(__file__).resolve().parents[4] / "apiSystem" / "apiSystem" / "settings.py"

# 允许保留 thread_sensitive=False 的域：纯长任务 / 与 DB 无关，改回 True 会串行化。
# OA 的 4 个轮询读端点已改回默认 True（纯短 DB 查询 + 前端高频轮询 = 泄漏点）。
# 注：这是**基线数据**，当前用例尚未逐文件比对（故 CodeQL 报「未使用」）；
# 保留的理由是它是「哪些域允许例外」的唯一记录，删掉会丢失判断依据。
_KNOWN_LONG_TASK_FILES = {
    "apps/agent/pi/pool.py",
    "apps/agent/services/chat_service.py",
}


class TestPoolDefaultOff:
    """连接池默认必须是关闭的——这是 thread_sensitive=False 未收敛前的前置条件。"""

    def test_pool_disabled_by_default(self) -> None:
        """不显式设 DB_POOL 时不应启用池。

        若这里挂了，说明有人把默认值改回「DEBUG 开池」。请先阅读本文件文件头，
        确认全站 thread_sensitive=False 调用点已收敛，再连同本用例一起改。
        """
        pool = settings.DATABASES["default"]["OPTIONS"].get("pool")
        assert pool is None, (
            "连接池默认被启用了（OPTIONS['pool']="
            f"{pool!r}）。thread_sensitive=False 的调用点会把连接永久借走，"
            "导致 PoolTimeout。详见本文件文件头 / devtools/repro_pool_leak.py"
        )

    def test_conn_max_age_restored_when_no_pool(self) -> None:
        """不开池时必须回落到 CONN_MAX_AGE 持久连接 + 健康检查。

        开池时代码会强制 `CONN_MAX_AGE=0` 且 `CONN_HEALTH_CHECKS=False`；
        若默认关池但没恢复这两项，等于退化成「每请求建连」，属性能倒退。
        """
        db = settings.DATABASES["default"]
        assert "pool" not in db["OPTIONS"] or db["OPTIONS"]["pool"] is None
        assert db["CONN_MAX_AGE"] != 0, "不开池时 CONN_MAX_AGE 不应为 0（会每请求建连）"
        assert db["CONN_HEALTH_CHECKS"] is True, "不开池时应开启连接健康检查"


class TestPoolToggleRespected:
    """显式开关仍须生效（给将来收敛完毕后开池留出口）。"""

    def test_settings_source_references_db_pool_env(self) -> None:
        """settings.py 里必须仍由 DB_POOL 环境变量驱动，而不是写死。"""
        assert _SETTINGS_PY.exists(), f"找不到 settings.py: {_SETTINGS_PY}"
        source = _SETTINGS_PY.read_text(encoding="utf-8")
        assert 'os.environ.get("DB_POOL"' in source
        assert "_use_pool" in source


class TestThreadSensitiveAudit:
    """把 thread_sensitive=False 的分布钉住，避免新增无人知情的泄漏点。"""

    @staticmethod
    def _count_thread_insensitive(root: Path) -> dict[str, int]:
        """统计 root 下各文件出现的 thread_sensitive=False 次数（AST 口径）。"""
        found: dict[str, int] = {}
        for path in root.rglob("*.py"):
            if "__pycache__" in path.parts or ".venv" in path.parts:
                continue
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            except (SyntaxError, UnicodeDecodeError, OSError):
                continue
            hits = 0
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                for kw in node.keywords:
                    if kw.arg == "thread_sensitive" and isinstance(kw.value, ast.Constant):
                        if kw.value.value is False:
                            hits += 1
            if hits:
                found[str(path)] = hits
        return found

    def test_oa_polling_read_endpoints_are_thread_sensitive(self) -> None:
        """OA 的 4 个轮询读端点必须是 thread_sensitive=True（默认）。

        这四个是 2026-11-03 事故的直接现场：纯短 DB 查询 + 前端每 2s 轮询，
        用 False 会在 anyio 线程池里借走连接不还。
        """
        apps_dir = Path(__file__).resolve().parents[4] / "apps" / "oa_filing" / "api"
        assert apps_dir.exists(), f"找不到 {apps_dir}"

        # 这些函数名出现在 sync_to_async 里且带 thread_sensitive=False 即为回归
        guarded = {
            "get_session",
            "get_stamp_session",
            "get_archive_session",
            "list_sites_for_lawyer",
        }
        offenders: list[str] = []
        for path in apps_dir.rglob("*.py"):
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            except (SyntaxError, UnicodeDecodeError, OSError):
                continue
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                if not isinstance(func, (ast.Attribute, ast.Name)):
                    continue
                if getattr(func, "id", None) != "sync_to_async":
                    continue
                if not node.args:
                    continue
                first = node.args[0]
                target = first.attr if isinstance(first, ast.Attribute) else getattr(first, "id", "")
                if target in guarded:
                    for kw in node.keywords:
                        if (
                            kw.arg == "thread_sensitive"
                            and isinstance(kw.value, ast.Constant)
                            and kw.value.value is False
                        ):
                            offenders.append(f"{path.name}:{node.lineno} sync_to_async({target}, ...)")

        assert not offenders, (
            "OA 轮询读端点又出现了 thread_sensitive=False —— 会重新引发 PoolTimeout：\n  " + "\n  ".join(offenders)
        )

    def test_thread_insensitive_call_sites_do_not_grow_unnoticed(self) -> None:
        """thread_sensitive=False 的总量不得无声膨胀。

        本用例不是「不许新增」，而是「新增必须被看见」：改动时把新数字填进
        _BASELINE 并说明为何该处必须并行。基线取修复后 AST 口径实测值。
        """
        _BASELINE = 58  # 2026-11-03 修复后 AST 实测（原 rg 口径 66 含注释行，非真实调用）
        root = Path(__file__).resolve().parents[4] / "apps"
        found = self._count_thread_insensitive(root)
        total = sum(found.values())
        assert total == _BASELINE, (
            f"thread_sensitive=False 调用点变更：基线 {_BASELINE} → 当前 {total}。\n"
            "新增点若触发的是短 DB 查询/被轮询，请改用默认 True；\n"
            "长任务请改用显式 executor=ThreadPoolExecutor(...)。\n"
            "减少是好消息，同样请同步更新 _BASELINE，让下一个改动者有正确锚点。\n"
            "当前分布：\n  " + "\n  ".join(f"{k}: {v}" for k, v in sorted(found.items()))
        )


@pytest.mark.django_db
def test_db_actually_usable() -> None:
    """冒烟：改完 settings 后数据库仍可正常查询（防止开关改动打断连接路径）。"""
    from django.db import connection

    with connection.cursor() as cur:
        cur.execute("SELECT 1")
        assert cur.fetchone()[0] == 1
