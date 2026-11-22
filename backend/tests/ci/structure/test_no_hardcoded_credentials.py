"""棘轮：默认配置里 `is_secret: True` 的项，`value` 必须是空串。

## 为什么（2026-11-23 审计 P0）

`apps/core/admin/_system_config_data/*.py` 是「初始化默认配置」的数据源，
Admin 的「初始化默认配置」按钮与 `init_system_config` 都从它读，写入 `SystemConfig`。

审计发现该目录里硬编码了 **4 个真实可用的第三方凭据**（飞书 App Secret、天眼查 Key、
企查查 Key、PaddleOCR Token），它们随仓库进了 git 历史；更糟的是那几行带着
`# pragma: allowlist secret`，等于把密钥扫描器**静音**了，pre-commit 的
detect-secrets 与隐私复审都不会再报警。

代码里删掉不等于止血——已经被 clone / fork / 备份的副本里仍然有效，
真实止血必须在对应平台**吊销并轮换**。这条测试只负责「不许再写回来」。

## 判定规则

扫 `apps/core/admin/_system_config_data/*.py` 的 AST：

1. 任一 `dict` 字面量同时含 `"is_secret": True` 与 `"value": <非空且非占位符的字符串>` → 违规。
   `value: ""` 合法；尖括号/`YOUR_`/`xxx`/`changeme` 这类**占位符**也合法（它们是给人看的填写指引，
   不是凭据）。判定：去掉首尾空白后，空串、`<...>` 包裹、或命中占位符词表 → 放行。
2. 该目录里出现 `# pragma: allowlist secret` 注释 → 违规（它会把密钥扫描静音，
   默认配置里根本不该有需要 allowlist 的东西）。
"""
from __future__ import annotations

import ast
from pathlib import Path

_CONFIG_DIR = Path(__file__).resolve().parents[3] / "apps" / "core" / "admin" / "_system_config_data"


def _iter_config_files() -> list[Path]:
    if not _CONFIG_DIR.is_dir():  # pragma: no cover - 目录被移走时给出明确失败
        raise AssertionError(f"默认配置目录不存在：{_CONFIG_DIR}（若已迁址，请同步更新本测试）")
    return sorted(_CONFIG_DIR.glob("*.py"))


# 允许的占位符形态：这些是「填在这里」的指引，不是真凭据
_PLACEHOLDER_MARKERS = ("YOUR_", "your_", "changeme", "CHANGEME", "xxx", "XXX", "example", "placeholder")


def _is_placeholder(value: str) -> bool:
    text = value.strip()
    if not text:
        return True
    if text.startswith("<") and text.endswith(">"):
        return True
    return any(marker in text for marker in _PLACEHOLDER_MARKERS)


def _dict_value(node: ast.Dict) -> tuple[bool, str | None]:
    """返回 (是否 is_secret=True, value 常量字符串或 None)。"""
    is_secret = False
    value: str | None = None
    for key, val in zip(node.keys, node.values):
        if not isinstance(key, ast.Constant) or not isinstance(key.value, str):
            continue
        if key.value == "is_secret" and isinstance(val, ast.Constant) and val.value is True:
            is_secret = True
        elif key.value == "value" and isinstance(val, ast.Constant) and isinstance(val.value, str):
            value = val.value
    return is_secret, value


def _scan() -> tuple[list[str], list[str]]:
    hardcoded: list[str] = []
    silenced: list[str] = []
    for path in _iter_config_files():
        text = path.read_text(encoding="utf-8", errors="ignore")
        for lineno, line in enumerate(text.splitlines(), start=1):
            if "pragma: allowlist secret" in line:
                silenced.append(f"{path.name}:{lineno}")
        try:
            tree = ast.parse(text)
        except SyntaxError:  # pragma: no cover
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Dict):
                continue
            is_secret, value = _dict_value(node)
            if is_secret and value is not None and not _is_placeholder(value):
                hardcoded.append(f"{path.name}:{node.lineno}")
    return hardcoded, silenced


def test_secret_defaults_have_empty_value() -> None:
    """`is_secret: True` 的默认配置项必须是空串（真实凭据只允许存在于数据库与 .env）。"""
    hardcoded, _ = _scan()
    assert not hardcoded, (
        "默认配置里仍有非空的密钥值（会被「初始化默认配置」灌进数据库，并随 git 历史永久泄漏）：\n  "
        + "\n  ".join(hardcoded)
        + "\n修法：把 value 改成空串，并在对应平台吊销/轮换该凭据。"
    )


def test_no_allowlist_silencing_in_default_configs() -> None:
    """默认配置目录里不许出现 `# pragma: allowlist secret`（它会把密钥扫描静音）。"""
    _, silenced = _scan()
    assert not silenced, (
        "默认配置目录里出现 allowlist 静音注释，密钥扫描将不再报警：\n  " + "\n  ".join(silenced)
    )
