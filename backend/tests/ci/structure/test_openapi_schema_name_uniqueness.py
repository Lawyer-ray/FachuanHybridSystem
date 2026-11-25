"""OpenAPI 组件名（`components.schemas`）必须全局唯一。

## 为什么需要这条结构测试

Django-ninja 把每个 `Schema` 子类的**类名**直接当作 `components.schemas` 的键。
两个 app 各写一个 `class FindingOut(Schema)` 时，**不会有任何报错**：后注册的
静默覆盖前一个，`backend/openapi.json` 里只剩一份定义，`openapi-typescript` 生成
的 TS 类型随之改变语义——前端某个 feature 的类型突然对不上，而错误信息只会说
「属性 X 不存在」，完全指不到「另一个 app 撞名了」。

真实事故（2026-11-26）：`apps/doc_workspace` 新增的 `FindingOut` 覆盖了
`apps/doc_verify` 的同名组件，`CaseVerifyCard.tsx` 当场编译不过，
而两边代码本身都没问题。

## 判据

扫全部 `apps/**` 里 `class X(Schema)` / `class X(父类Schema)` 的定义，类名不得重复。
`Schema` 只用于 API 出入参，同名即冲突。
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[3]

#: ninja Schema 的基类写法：`Schema` 或 `SomeBase(Schema)` 派生的自定义基类。
_BASE_NAME_RE = re.compile(r"(^|_)Schema$|Schema$")


def _iter_schema_classes() -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    for path in sorted((BACKEND_DIR / "apps").rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        if "class " not in text or "Schema" not in text:
            continue
        try:
            tree = ast.parse(text)
        except SyntaxError:  # 语法错误由 ruff/pytest 别处负责
            continue
        schema_class_names: set[str] = set()
        # 先收集本文件里所有继承 Schema 的类名，才能识别 `class X(SomeBase)` 这种间接派生
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                for base in node.bases:
                    base_name = getattr(base, "id", None) or getattr(base, "attr", None)
                    if base_name and _BASE_NAME_RE.search(base_name):
                        schema_class_names.add(node.name)
        # 二轮：继承「本文件里已知的 Schema 子类」也算
        changed = True
        while changed:
            changed = False
            for node in tree.body:
                if not isinstance(node, ast.ClassDef) or node.name in schema_class_names:
                    continue
                for base in node.bases:
                    base_name = getattr(base, "id", None) or getattr(base, "attr", None)
                    if base_name in schema_class_names:
                        schema_class_names.add(node.name)
                        changed = True
                        break

        for name in sorted(schema_class_names):
            found.append((name, str(path.relative_to(BACKEND_DIR))))
    return found


BASELINE_PATH = Path(__file__).with_name("_openapi_schema_collisions_baseline.json")


def _load_baseline() -> dict[str, list[str]]:
    import json

    data = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    return {k: v for k, v in data.items() if not k.startswith("_")}


def test_no_new_schema_name_collisions() -> None:
    """只拦**新增**撞名；存量冲突冻结在基线里（棘轮：只许减少）。"""
    baseline = _load_baseline()
    by_name: dict[str, list[str]] = {}
    for name, path in _iter_schema_classes():
        by_name.setdefault(name, []).append(path)

    duplicates = {name: paths for name, paths in by_name.items() if len(paths) > 1}
    new_ones = {name: paths for name, paths in duplicates.items() if name not in baseline}

    assert not new_ones, (
        "新增了 OpenAPI 组件名冲突（后注册的会静默覆盖前一个，前端类型随之变义）：\n"
        + "\n".join(f"  {name}: {paths}" for name, paths in sorted(new_ones.items()))
        + "\n修法：给其中一个加前缀（如 DocXxxOut / OoXxxOut），不要靠改生成物解决。"
    )


def test_baseline_entries_are_still_real() -> None:
    """基线里的条目失效（已修好 / 文件改名）就必须删掉，否则基线会变成摆设。"""
    baseline = _load_baseline()
    by_name: dict[str, list[str]] = {}
    for name, path in _iter_schema_classes():
        by_name.setdefault(name, []).append(path)

    stale: list[str] = []
    for name, paths in baseline.items():
        current = sorted(by_name.get(name, []))
        if len(current) < 2:
            stale.append(f"{name}：已不再冲突（当前 {current}），请从基线里删掉")
            continue
        missing = [p for p in paths if p not in current]
        if missing:
            stale.append(f"{name}：基线里的文件已不存在或不再声明该类（{missing}），请更新基线")

    assert not stale, "OpenAPI 撞名基线已过期：\n" + "\n".join(f"  {line}" for line in stale)
