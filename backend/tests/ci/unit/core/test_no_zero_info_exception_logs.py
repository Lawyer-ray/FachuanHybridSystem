"""门禁：全仓不得再出现 `logger.exception("操作失败")` 这类零信息量 + 带完整堆栈的日志。

为什么这条能当门禁（不是风格洁癖）：

1. 它是**纯字面量**，没有任何合法用途。`logger.exception` 的 `msg` 参数是给线上排障用的，
   「操作失败」既不含模块/函数名，也不含失败动作，看到它无法定位是哪一处 except 触发的；
   而同一份堆栈在 150 条/接口的量级下占 p50 响应时间的 40%+（见 commit 说明），
   等于用最贵的方式写最没用的信息，还把真故障淹没。
2. 它可被**逐字判定**：不需要 AST、不需要启发式，数量为 0 就是真为 0，不会误伤。
3. 它是**回归高发点**：`except Exception:` + 编辑器片段会自然产出这句话；
   一旦放过一处，下一个人就会照着抄（本次清理前全仓已有 78 处，全部是复制传播）。
4. 修复成本极低且无风险：只改文案，不动 `except` 类型、日志级别与控制流。

因此本用例断言命中数为 0；若将来有人新增，正确写法是
`logger.exception("<模块/函数名>: <失败的动作>")`（例：`upload_mixin.upload_attachment: 上传附件失败`），
同一条链路上的多个点要能互相区分。
"""

from __future__ import annotations

import re
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[4]

# 扫描范围：后端全部业务代码（apps + 独立部署的 mcp_server）。
SCAN_ROOTS = [BACKEND_DIR / "apps", BACKEND_DIR / "mcp_server"]

# 只认「第一条参数就是这个零信息量字面量」的写法，允许 f\"\" 前缀与引号风格差异。
_ZERO_INFO_EXCEPTION_LOG = re.compile(r"""logger\.exception\(\s*[fr]?["']操作失败["']""")


def _zero_info_exception_count(text: str) -> int:
    """返回一段源码里 `logger.exception("操作失败")` 的出现次数。"""
    return len(_ZERO_INFO_EXCEPTION_LOG.findall(text))


def _iter_python_files() -> list[Path]:
    files: list[Path] = []
    for root in SCAN_ROOTS:
        for py_file in root.rglob("*.py"):
            if "__pycache__" in py_file.parts:
                continue
            files.append(py_file)
    return files


def test_zero_info_exception_logs_are_gone() -> None:
    """`apps` + `mcp_server` 里零信息量的 `logger.exception("操作失败")` 必须为 0 处。"""
    offenders: list[str] = []
    for py_file in _iter_python_files():
        text = py_file.read_text(encoding="utf-8", errors="ignore")
        if _ZERO_INFO_EXCEPTION_LOG.search(text):
            for lineno, line in enumerate(text.splitlines(), 1):
                if _ZERO_INFO_EXCEPTION_LOG.search(line):
                    offenders.append(f"{py_file.relative_to(BACKEND_DIR)}:{lineno}: {line.strip()}")

    assert not offenders, (
        "发现零信息量的 logger.exception(\"操作失败\")，请改成 "
        "'<模块/函数名>: <失败的动作>'（一行看不出是哪个函数就说明改得不对）：\n" + "\n".join(offenders)
    )


def test_scanner_detects_zero_info_message() -> None:
    """守护检测器本身：一旦 regex 或 logger 命名约定失效（扫不到东西），本门禁会变成假绿。

    本节故意写出违规字面量，因此 SCAN_ROOTS 不含 tests/——门禁只管业务代码。
    """
    assert _zero_info_exception_count('            logger.exception("操作失败")') == 1
    assert _zero_info_exception_count("logger.exception('操作失败', extra={'x': 1})") == 1
    assert _zero_info_exception_count('logger.exception("upload_mixin.upload_attachment: 上传附件失败")') == 0
