"""棘轮：Service 层不许留「空类壳」。

## 为什么需要这条（2026-11-23 真实事故）

`docs/harness/backend/four-layer.md` 禁止 Service 层用 `@staticmethod`，
历史上有一轮大规模「静态方法下沉为模块级函数」的清理（见
`tests/ci/structure/test_four_layer_architecture.py` 里
`SERVICE_STATIC_METHOD_RATCHET` 的注释：264 → 197 → 12）。

清理时把方法搬走了，**类体却留下来**：

```python
class ImageRotationJobService:      # ← 只剩注释，一个方法都没有
    '''图片旋转历史任务服务'''
```

而 API 层仍然写 `ImageRotationJobService().list_jobs(...)` →
`AttributeError` → 8 个 `/api/v1/image-rotation/jobs*` 端点全部 500。
它们全都带 `# pragma: no cover`，所以单测、覆盖率、结构测试**三处都看不见**。
同源死代码还有 `apps/oa_filing/services/stamp_lookup_service.py::StampLookupService`。

`test_four_layer_architecture.py` 现有两条检查都抓不到它：
- `_scan_service_staticmethod` 只看还有没有 `@staticmethod`；
- `test_no_sunk_function_called_as_instance_method` 只看包内 `self._foo(...)`，
  跨层（API → Service 实例）的调用不在它的视野里。

## 判定规则

扫 `apps/*/services/**/*.py`，凡类名以 `Service` 结尾、**没有任何基类**、
类体里没有函数定义也没有类属性赋值/注解 → 判为空壳。

**为什么豁免有基类的类**：仓库里有一批「子类只写 docstring、方法全继承」
的门面类（`CaseLogFacadeService(CaseLogService)`、
`CaseService(_CaseService)`、`FolderFilesystemService(_ImplFolderFilesystemService)` 等），
它们的成员来自父类，静态扫描看不见，属合法写法。
有基类还想判断方法是否存在，需要解析整个 MRO——超出这条棘轮的判据范围。

## 维护

清理一处就把基线减一（只减不增）。新增空壳服务类立即失败。
"""

from __future__ import annotations

import ast
from pathlib import Path

_APPS_ROOT = Path(__file__).resolve().parents[3] / "apps"

# 棘轮基线：2026-11-23 实测 0（`ImageRotationJobService` 与 `StampLookupService` 两个空壳
# 已在本轮删除）。只许保持 0；确有合法「空壳待填」的中间态才允许抬，并在此写清原因与期限。
EMPTY_SERVICE_CLASS_RATCHET = 0

_MEMBER_NODES = (
    ast.FunctionDef,
    ast.AsyncFunctionDef,
    ast.AnnAssign,
    ast.Assign,
)


def _iter_service_files() -> list[Path]:
    files: list[Path] = []
    for app_dir in sorted(_APPS_ROOT.iterdir()):
        services_dir = app_dir / "services"
        if not services_dir.is_dir():
            continue
        for py_file in services_dir.rglob("*.py"):
            if "__pycache__" in str(py_file):
                continue
            files.append(py_file)
    return files


def _scan_empty_service_classes() -> list[tuple[str, int, str]]:
    violations: list[tuple[str, int, str]] = []
    for py_file in _iter_service_files():
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8", errors="ignore"))
        except SyntaxError:  # pragma: no cover - 语法错误由 compileall 那一步负责
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            if not node.name.endswith("Service"):
                continue
            if node.bases:  # 有基类：成员可能全在父类，见模块 docstring「为什么豁免」
                continue
            if any(isinstance(member, _MEMBER_NODES) for member in node.body):
                continue
            violations.append((str(py_file.relative_to(_APPS_ROOT.parent)), node.lineno, node.name))
    return violations


def test_no_empty_service_class() -> None:
    """Service 层不许留无基类、无成员的空类壳（API 一调就是 AttributeError 500）。"""
    violations = _scan_empty_service_classes()
    assert len(violations) <= EMPTY_SERVICE_CLASS_RATCHET, (
        f"发现 {len(violations)} 个空壳 Service 类（无基类且无任何成员），"
        f"超过棘轮基线 {EMPTY_SERVICE_CLASS_RATCHET}。\n"
        "API 层一旦 `SomeService().method()` 就会 AttributeError 500；"
        "要么把方法放回类里，要么删掉类让调用方直接用模块级函数。\n"
        + "\n".join(f"  {path}:{lineno}: class {name}" for path, lineno, name in violations)
    )
