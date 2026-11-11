"""Structure guard: Admin / Model 两层的四层架构棘轮。

背景
----
`tests/ci/structure/test_four_layer_architecture.py` 原先只守 **API 层**
（`Model.objects` 不得出现）与 **Service 层**（禁用 `@staticmethod`）。
`docs/harness/backend/four-layer.md` 明确规定的另外两条禁令一直没有守卫：

- **Admin 层**：禁止直接实例化 Service（应走工厂函数 / wiring）
- **Model 层**：禁止业务方法、禁止自定义 `save()`

于是这两层的历史违规只增不减，且清理后极易回流——2026-11 代码质量审查实测：
Admin 层直接实例化 Service **91 处**、Model 层自定义 `save()` **10 处**。

本文件为这两层建立**只减不增**的棘轮基线。

棘轮纪律
--------
- 基线是**上限**，不是目标值。清理一处就把对应 baseline 减一。
- **任何新增违规立即失败**，不允许「先抬基线把 PR 过掉」。
- 确实需要豁免时，在 `ALLOWLIST` 里按 `path:symbol` 精确列出并写清原因。

为什么按「计数」而不是按「文件清单」
------------------------------------
Admin 层 91 处分散在几十个文件里，逐条列路径会让基线文件本身变成维护负担。
计数上限配合 `--tb` 输出的前若干条明细，已足够定位是哪次改动把数字抬上去。
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

_APPS_ROOT = Path(__file__).resolve().parents[3] / "apps"

# ── 棘轮基线（2026-11-11 实测，清理一处减一，只减不增）──────────────
#: Admin 层 `XxxService()` / `XxxService(...)` 直接实例化的出现次数。
ADMIN_SERVICE_INSTANTIATION_RATCHET = 91

#: Model 层自定义 `save()` 的数量。
MODEL_CUSTOM_SAVE_RATCHET = 10

#: Model 层**写操作**方法（方法体内出现 self.save / self.delete / .objects. / transaction.atomic）。
#: 这是四层架构真正的红线：写逻辑必须下沉 Service，Model 只留字段与只读派生。
#: 2026-11-11 实测 9 处，均在 contract_review / document_parsing / labor_arbitration。
MODEL_WRITE_METHOD_RATCHET = 9

#: Model 层**只读派生**却写成普通方法（未用 @property）的数量。
#: 不是架构违规，是风格债（改了会影响调用方 s.foo() -> s.foo 语法）。
#: 2026-11-11 实测 16 处，主要在 LLMProvider.parsed_* 与 GenerationTask.*。
MODEL_READONLY_METHOD_RATCHET = 16

#: Model 层允许存在的方法名（Django 约定 + 只读派生）。
_MODEL_ALLOWED_METHODS: frozenset[str] = frozenset(
    {
        "save",
        "delete",
        "clean",
        "full_clean",
        "get_absolute_url",
        "__str__",
        "__repr__",
        "__eq__",
        "__hash__",
        "__lt__",
        "__le__",
        "__gt__",
        "__ge__",
    }
)

#: Model 方法名前缀白名单（Django 的 `get_<field>_display`、只读 property 等）。
_MODEL_ALLOWED_PREFIXES: tuple[str, ...] = ("get_", "is_", "has_", "can_")

#: 明确的豁免项：`path:symbol` → 原因。只增「有充分理由」的条目。
ALLOWLIST: dict[str, str] = {
    # 校验下沉到 Model 是被 Django formset 调用时机逼出来的：
    # full_clean() 对每一行（含标了删除的行）都调 clean()，而 DELETE 标记要等
    # save_existing_objects() 才生效，校验放进 clean() 会让一行脏数据导致整个
    # 表单集既存不下也删不掉（2026-11-06 实爆）。Model 只提供方法、由 Admin 层发起。
    "apps/client/models/identity_doc.py:ClientIdentityDoc.validate_doc_type_for_client": "formset 调用时机约束",
    # 字段级幂等加密变换，无跨模型编排、无外部 IO，属「字段自身的表示变换」，
    # 放 Model 反而比 Service 更难出错（避免有人忘了加密就写库）。
    "apps/cloud_storage/models.py:CloudStorageAccount.encrypt_sensitive_fields": "字段级幂等加密变换",
}


def _iter_admin_files() -> list[Path]:
    """所有 `apps/<app>/admin/**/*.py`。"""
    files: list[Path] = []
    if not _APPS_ROOT.is_dir():
        return files
    for app_dir in sorted(_APPS_ROOT.iterdir()):
        if not app_dir.is_dir() or app_dir.name.startswith("_"):
            continue
        admin_dir = app_dir / "admin"
        if not admin_dir.is_dir():
            continue
        for py_file in admin_dir.rglob("*.py"):
            if "__pycache__" in str(py_file):
                continue
            files.append(py_file)
    return files


def _iter_model_files() -> list[Path]:
    """所有 `apps/<app>/models.py` 与 `apps/<app>/models/**/*.py`。"""
    files: list[Path] = []
    if not _APPS_ROOT.is_dir():
        return files
    for app_dir in sorted(_APPS_ROOT.iterdir()):
        if not app_dir.is_dir() or app_dir.name.startswith("_"):
            continue
        models_py = app_dir / "models.py"
        if models_py.is_file():
            files.append(models_py)
        models_dir = app_dir / "models"
        if models_dir.is_dir():
            for py_file in models_dir.rglob("*.py"):
                if "__pycache__" in str(py_file):
                    continue
                files.append(py_file)
    return files


# ── Admin 层：直接实例化 Service ──────────────────────────────
_SERVICE_INSTANTIATION = re.compile(r"(?<![.\w])(?P<name>\w+Service)\s*\(")


def _scan_admin_service_instantiation() -> list[tuple[str, int, str]]:
    """检出 Admin 层 `XxxService(...)` 直接实例化。

    只认「调用」形态：`Name(...)`。以下不算违规：
    - 类型注解 `svc: FooService | None`
    - `isinstance(x, FooService)`
    - 模块级 import 语句
    - `super().__init__` 之类的既有调用
    """
    violations: list[tuple[str, int, str]] = []
    for py_file in _iter_admin_files():
        rel = py_file.relative_to(_APPS_ROOT.parent).as_posix()
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8", errors="ignore"))
        except SyntaxError:  # pragma: no cover - 语法错误由 ruff/编译期拦
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not isinstance(func, ast.Name):
                continue
            name = func.id
            if not name.endswith("Service"):
                continue
            # 排除 isinstance 的第二参数等非调用场景（isinstance 不是 Call 的 func 同名）
            key = f"{rel}:{name}"
            if key in ALLOWLIST:
                continue
            violations.append((rel, node.lineno, f"{name}(...)"))
    return violations


# ── Model 层：自定义 save() 与业务方法 ────────────────────────
#: 方法体中出现这些即判定为「写操作 / 跨层 IO」的 Model 方法。
_WRITE_SIGNALS: tuple[str, ...] = (
    "self.save(",
    "self.delete(",
    ".objects.",
    "super().save(",
    "transaction.atomic",
)


def _scan_model_methods() -> tuple[list[tuple[str, int, str]], list[tuple[str, int, str]], list[tuple[str, int, str]]]:
    """返回 (自定义 save() 列表, 写操作方法列表, 只读派生方法列表)。"""
    saves: list[tuple[str, int, str]] = []
    writes: list[tuple[str, int, str]] = []
    readonly: list[tuple[str, int, str]] = []

    for py_file in _iter_model_files():
        rel = py_file.relative_to(_APPS_ROOT.parent).as_posix()
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8", errors="ignore"))
        except SyntaxError:  # pragma: no cover
            continue

        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            # 只检查真正的 Django Model 子类
            is_model = any(
                (isinstance(base, ast.Attribute) and base.attr == "Model")
                or (isinstance(base, ast.Name) and base.id == "Model")
                for base in node.bases
            )
            if not is_model:
                continue

            for member in node.body:
                if not isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                method_name = member.name
                # 装饰器：@property / @cached_property / @classmethod 等不算「业务方法」
                decorators = {
                    d.id if isinstance(d, ast.Name) else (d.attr if isinstance(d, ast.Attribute) else "")
                    for d in member.decorator_list
                }
                if decorators & {"property", "cached_property", "classmethod", "staticmethod"}:
                    continue

                symbol = f"{node.name}.{method_name}"
                key = f"{rel}:{symbol}"
                if key in ALLOWLIST:
                    continue

                if method_name == "save":
                    saves.append((rel, member.lineno, symbol))
                    continue

                if method_name in _MODEL_ALLOWED_METHODS:
                    continue
                if method_name.startswith(_MODEL_ALLOWED_PREFIXES):
                    continue

                # 按方法体里的信号区分「写操作」（真违规）与「只读派生」（风格债）
                body_src = ast.get_source_segment(py_file.read_text(encoding="utf-8", errors="ignore"), member) or ""
                if any(sig in body_src for sig in _WRITE_SIGNALS):
                    writes.append((rel, member.lineno, symbol))
                else:
                    readonly.append((rel, member.lineno, symbol))

    return saves, writes, readonly


# ── 测试 ────────────────────────────────────────────────────
def test_admin_layer_service_instantiation_within_ratchet() -> None:
    """Admin 层直接实例化 Service 的数量不得超过棘轮基线。"""
    violations = _scan_admin_service_instantiation()
    assert len(violations) <= ADMIN_SERVICE_INSTANTIATION_RATCHET, (
        f"Admin 层直接实例化 Service 共 {len(violations)} 处，"
        f"超过棘轮基线 {ADMIN_SERVICE_INSTANTIATION_RATCHET}。\n"
        "按 docs/harness/backend/four-layer.md，Admin 层应通过工厂函数 / wiring 取服务实例，"
        "不要 new Service。清理一处后请把 ADMIN_SERVICE_INSTANTIATION_RATCHET 减一。\n"
        + "\n".join(f"  {path}:{lineno}: {content}" for path, lineno, content in violations[:15])
    )


def test_model_layer_no_additional_custom_save() -> None:
    """Model 层自定义 save() 数量不得超过棘轮基线。"""
    saves, _, _ = _scan_model_methods()
    assert len(saves) <= MODEL_CUSTOM_SAVE_RATCHET, (
        f"Model 层自定义 save() 共 {len(saves)} 处，超过棘轮基线 {MODEL_CUSTOM_SAVE_RATCHET}。\n"
        "按 four-layer.md，Model 只放字段定义与只读 @property，写逻辑属于 Service 层。\n"
        + "\n".join(f"  {path}:{lineno}: {content}" for path, lineno, content in saves[:10])
    )


def test_model_layer_no_additional_write_methods() -> None:
    """Model 层不得新增写操作方法（save 本身由上一个棘轮单独管）。

    判定依据：方法体里出现 ``self.save(`` / ``self.delete(`` / ``.objects.`` /
    ``transaction.atomic``——这些都是「写逻辑/跨层 IO」，按 four-layer.md 属于 Service。
    """
    _, writes, _ = _scan_model_methods()
    assert len(writes) <= MODEL_WRITE_METHOD_RATCHET, (
        f"Model 层出现 {len(writes)} 个写操作方法，超过棘轮基线 {MODEL_WRITE_METHOD_RATCHET}。\n"
        "Model 只应包含字段定义与只读派生（@property）。"
        "写操作、跨模型编排、事务、外部 IO 一律下沉 Service 层。\n"
        + "\n".join(f"  {path}:{lineno}: {content}" for path, lineno, content in writes[:15])
    )


def test_model_layer_readonly_methods_within_ratchet() -> None:
    """Model 层把只读派生写成普通方法的数量不得超过棘轮基线（风格债）。"""
    _, _, readonly = _scan_model_methods()
    assert len(readonly) <= MODEL_READONLY_METHOD_RATCHET, (
        f"Model 层有 {len(readonly)} 个只读派生写成普通方法，超过棘轮基线 "
        f"{MODEL_READONLY_METHOD_RATCHET}。\n"
        "这类方法应改为 @property（调用方从 s.foo() 变 s.foo）。\n"
        + "\n".join(f"  {path}:{lineno}: {content}" for path, lineno, content in readonly[:15])
    )
