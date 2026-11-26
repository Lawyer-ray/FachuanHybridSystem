"""结构守卫：pdf_splitting ``summary`` 的每个键都必须在 ``summary_contract.py`` 里登记。

背景（v27.25.x → v27.26.1 两次实证）
------------------------------------
``PdfSplitJob.summary_payload`` 是后端与前端之间**没有 schema 的**自由字典：它不进
openapi 生成物，前端按字符串键去取。于是「后端算了、写了 summary、前端一个键都没读」
既不报错也不告警，只表现为页面上什么都没有：

- ``engine_disagreements_judge`` v27.25.4 就算出来落进 summary，直到 v27.26.0 才接上界面；
- ``degenerate_pages`` 取字阶段一直在算，直到 v27.26.1 才接上界面。

两次都靠人盯 changelog 才发现。登记表 ``services/split/summary_contract.py`` 把「这个键
是给律师看的，还是只给排障看的」变成可判定的声明；本文件负责让声明与代码不许漂移。

守 5 件事
----------
1. **扫描器不许静默空**：扫出的键数必须 >= 15，且包含四个 canary 键。扫描实现被重构
   弄坏（函数改名 / dict 改成别处拼）时这条先红——否则下面几条会「零键通过」假绿。
2. 扫出的每个键都必须登记在 ``ALL_SUMMARY_KEYS``。
3. 登记为 UI 的键必须在 ``frontend/src`` 里出现过。
4. 登记为 DIAG 的键必须写清「为什么律师不用看」。
5. ``KNOWN_DYNAMIC``（AST 拿不到的落点）只许是已知那几项，不许冒充静态键；
   并且它的**源头**（两条分段路径返回的 dict）会被反向校对——漏登一个新键会红。

扫描位置
--------
不按正则扫文本：``summary`` 的键散落在「关键字参数的 dict 字面量」与「辅助函数返回的
dict」里，正则会把同一份代码里的其他 dict（缓存、统计）一起扫进来。所以按函数名定位，
只取这几类落点：

- ``summary_payload=`` 关键字参数的 ``Dict``（``split/service.py`` 两处：``_persist_analysis``
  与 ``_persist_page_split``；``services/job_service.py`` 一处：建任务时的初始 payload）；
- ``PdfAnalysisOutcome(..., summary=...)`` 的 ``Dict``（``split/service.py::segment_stage``）；
- ``split/pipeline.py::_build_summary`` **返回**的那个 dict（取字阶段的 summary）；
- ``split/service.py::_dual_engine_summary`` **返回**的那个 dict（双引擎区块）。

后两个是「返回的 dict」：``_build_summary`` 先赋值给局部名再 ``.update({...})`` 追加，
所以两处字面量的键都算（它们都进了返回值）。

为什么这四类落点里包含 ``_persist_page_split`` 与 ``_dual_engine_summary``
----------------------------------------------------------------------------
这两处的键（``page_split`` 与 ``engine_disagreements_judge``）**只能**在这里静态看到：
它们分别来自按页切分路径、以及经 ``**_dual_engine_summary(...)`` 展开进 ``segment_stage``。
按住 ``summary_payload=`` / ``PdfAnalysisOutcome(summary=...)`` 两类一网打尽（不点名函数），
再补上两个「返回整个 summary 区块」的辅助函数，``engine_disagreements_judge`` 才拿得到——
而它恰恰是本测试的 canary，漏掉等于把这个守卫最该拦的那种回归放过去。

``split/pipeline.py::analyze_pdf`` 的 ``PdfAnalysisOutcome(summary=...)`` 刻意不扫：它一列
静态键都没新增（只 ``"table_geometry"``），三个 splat 的来源（``_build_summary`` /
``_inconsistency_summary`` / 分段字节）都已被上面的落点覆盖，再扫一遍只会把 splat 计数
翻倍而多不到一个键。

``**segment_summary`` 的两个源头（``_detect_segments_batched`` / ``_detect_segments_wholebook``）
另外单独扫一遍，但**只用来校对 ``KNOWN_DYNAMIC`` 漏没漏**，不进 ``scanned``：
实测整本分段路径已经在往 summary 里塞 4 个键（``segment_wholebook_budget`` /
``segment_batch_backend`` / ``segment_boundary_disagreement_pages`` /
``segment_boundary_disagreement_total``）而没有任何人登记过——只靠人记着改 ``KNOWN_DYNAMIC``
是拦不住的。
"""

from __future__ import annotations

import ast
import importlib.util
from functools import lru_cache
from pathlib import Path
from types import ModuleType

BACKEND_DIR = Path(__file__).resolve().parents[3]
REPO_ROOT = BACKEND_DIR.parent
SPLIT_DIR = BACKEND_DIR / "apps/pdf_splitting/services/split"
SERVICE_PY = SPLIT_DIR / "service.py"
REGISTRY_PY = SPLIT_DIR / "summary_contract.py"
PIPELINE_PY = SPLIT_DIR / "pipeline.py"
JOB_SERVICE_PY = BACKEND_DIR / "apps/pdf_splitting/services/job_service.py"
FRONTEND_SRC = REPO_ROOT / "frontend/src"

#: ``summary_payload=`` 关键字参数所在文件（``summary`` 落库的三个写点）。
SUMMARY_PAYLOAD_PY: tuple[Path, ...] = (SERVICE_PY, JOB_SERVICE_PY)

#: ``PdfAnalysisOutcome(..., summary=...)`` 所在文件（只收两阶段分段阶段的那个入口）。
ANALYSIS_OUTCOME_PY: tuple[Path, ...] = (SERVICE_PY,)

#: 「返回整个 summary 区块」的辅助函数：(文件, 函数名)。
RETURNED_SUMMARY_DICTS: tuple[tuple[Path, str], ...] = (
    (PIPELINE_PY, "_build_summary"),
    (SERVICE_PY, "_dual_engine_summary"),
)

#: 经 `**segment_summary` 铺平进 summary 的源头：(文件, 函数名)。
#: 这两条路径的键扫描器看不见（它们在另一个文件的返回值里），所以只用来**校对**
#: KNOWN_DYNAMIC 有没有漏——新键漏登时第 5 条断言会红。
SPLATTED_SUMMARY_DICTS: tuple[tuple[Path, str], ...] = (
    (PIPELINE_PY, "_detect_segments_batched"),
    (PIPELINE_PY, "_detect_segments_wholebook"),
)

#: AST 看不见的落点：这些键经 ``**`` 展开或辅助函数间接进入 summary，扫描器无从静态发现。
#:
#: 全部来自 ``detect_segments_with_fallback``：分批路径（``_detect_segments_batched``）与
#: 整本路径（``_detect_segments_wholebook``）各返回一个 dict，调用方用
#: ``**segment_summary`` 铺平进 ``segment_stage`` 的 summary。两条路径还都会带一个
#: ``segment_strategy``，但它静态可见（``job_service`` 建任务时也写同名键），所以
#: **不**放这里——放进来会被第 5 条断言当成「冒充动态」。
#:
#: **只许**放这八个：往这里塞静态可见的键，等于给自己开一条「测试看不见我」的后门。
KNOWN_DYNAMIC: frozenset[str] = frozenset(
    {
        # 两条路径共有 / 分批路径
        "segment_backend",
        "segment_llm_fallback_reason",
        "segment_total_batches",
        "segment_rule_batches",
        # 整本路径独有
        "segment_wholebook_budget",
        "segment_batch_backend",
        "segment_boundary_disagreement_pages",
        "segment_boundary_disagreement_total",
    }
)

#: ``**`` splat 的上限：``segment_stage`` 两处（``segment_summary`` / ``_dual_engine_summary``）
#: + ``_persist_analysis`` 两处（``previous_summary`` / ``outcome.summary``）。
#: 涨上去说明又有人用 splat 往 summary 里塞键，那种键扫描器看不见，必须显式登记进 KNOWN_DYNAMIC。
MAX_SPLATS = 4

#: 扫描器的哨兵键：这几个键拿不到 = 定位逻辑已经与被扫代码脱钩，后面几条断言全部无意义。
CANARY_KEYS: frozenset[str] = frozenset(
    {"page_quality", "degenerate_pages", "engine_disagreements_judge", "table_geometry"}
)

#: 扫不出这么多键就说明扫描器坏了（当前真实键数远高于此值）。
MIN_SCANNED_KEYS = 15

_FRONTEND_SUFFIXES = frozenset({".ts", ".tsx"})


@lru_cache(maxsize=1)
def _registry() -> ModuleType:
    """按文件路径加载登记表，**不走包导入**。

    ``import apps.pdf_splitting.services.split.summary_contract`` 会顺藤摸进
    ``services/__init__.py`` → ``job_service`` → ``apps.core.services`` → ``models``，
    把整个 Django 应用链拖进来。本守卫只读源码，不该因为 Django 没配好而红/绿，
    也不该让「登记表写错了」与「应用起不来」共用同一条失败信息。
    """
    spec = importlib.util.spec_from_file_location("pdf_split_summary_contract", REGISTRY_PY)
    if spec is None or spec.loader is None:
        raise AssertionError(f"读不到 summary 登记表：{REGISTRY_PY}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _functions(tree: ast.Module) -> dict[str, ast.AST]:
    return {node.name: node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}


def _function(path: Path, tree: ast.Module, name: str) -> ast.AST:
    """按名字取函数；改名/删除时立刻红，而不是静默扫出 0 个键。"""
    func = _functions(tree).get(name)
    assert func is not None, (
        f"扫描目标不存在：{path.name}::{name}。函数被改名/搬走了，先修本测试的扫描目标——"
        f"否则 summary 键会静默扫不出来，后面的断言全部假绿。"
    )
    return func


def _dict_string_keys(node: ast.Dict, *, where: str) -> tuple[set[str], int]:
    """dict 字面量的**顶层**字符串键 + 被忽略的 ``**`` splat 个数。

    键不是字符串字面量（变量、f-string）时直接红：那是扫描器看不见的落点，
    静默跳过等于给它发通行证。
    """
    keys: set[str] = set()
    splats = 0
    for key in node.keys:
        if key is None:
            splats += 1
            continue
        assert isinstance(key, ast.Constant) and isinstance(key.value, str), (
            f"{where} 的 dict 里有非字面量键（{ast.dump(key)[:80]}）：扫描器看不见它。"
            f"请改成字符串字面量，或把该键登记进 KNOWN_DYNAMIC 并说明为什么拿不到。"
        )
        keys.add(key.value)
    return keys, splats


def _keyword_dicts(tree: ast.Module, keyword: str, *, where: str) -> list[ast.Dict]:
    out: list[ast.Dict] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        for kw in node.keywords:
            if kw.arg == keyword and isinstance(kw.value, ast.Dict):
                out.append(kw.value)
    assert out, f"{where} 里没找到任何 `{keyword}=` 的 dict 字面量：扫描目标已经失效，先修本测试。"
    return out


def _outcome_summary_dicts(tree: ast.Module, *, where: str) -> list[ast.Dict]:
    out: list[ast.Dict] = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)):
            continue
        if node.func.id != "PdfAnalysisOutcome":
            continue
        for kw in node.keywords:
            if kw.arg == "summary" and isinstance(kw.value, ast.Dict):
                out.append(kw.value)
    assert out, f"{where} 里没找到 `PdfAnalysisOutcome(summary={{...}})`：扫描目标已经失效，先修本测试。"
    return out


def _string_subscript_name(target: ast.expr, name: str) -> str | None:
    """``name["<键>"] = ...`` 形式的赋值目标 → 那个键；其他形状返回 ``None``。"""
    if not isinstance(target, ast.Subscript):
        return None
    if not (isinstance(target.value, ast.Name) and target.value.id == name):
        return None
    index = target.slice
    if isinstance(index, ast.Constant) and isinstance(index.value, str):
        return index.value
    return None


def _assignments(func: ast.AST) -> list[tuple[list[ast.expr], ast.expr]]:
    """函数体里的每条赋值 → (目标列表, 右值)。``Assign`` 与 ``AnnAssign`` 一起收。

    两个都得收：``summary = {...}`` 与 ``summary: dict[str, Any] = {...}`` 都是「把键放进返回的 dict」，
    只认前者的后果是带类型注解的那个 dict 整块看不见（整本分段的 ``segment_wholebook_budget``
    就是这么漏的）。
    """
    out: list[tuple[list[ast.expr], ast.expr]] = []
    for node in ast.walk(func):
        if isinstance(node, ast.Assign):
            out.append((node.targets, node.value))
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            out.append(([node.target], node.value))
    return out


def _returned_dicts_and_names(func: ast.AST) -> tuple[list[ast.Dict], set[str]]:
    """函数返回值里直接出现的 dict 字面量与局部名（认 ``return {...}`` / ``return x, {...}`` / ``return x``）。

    只看**返回表达式本身**，不 `ast.walk` 进去：否则 dict 里嵌套的零值形状
    （如 ``dict(...) or {"high": 0, ...}``）会被当成顶层键。
    """
    dicts: list[ast.Dict] = []
    names: set[str] = set()
    for node in ast.walk(func):
        if not (isinstance(node, ast.Return) and node.value is not None):
            continue
        parts = node.value.elts if isinstance(node.value, ast.Tuple) else [node.value]
        for part in parts:
            if isinstance(part, ast.Dict):
                dicts.append(part)
            elif isinstance(part, ast.Name):
                names.add(part.id)
    return dicts, names


def _returned_summary_keys(func: ast.AST, *, where: str) -> tuple[set[str], int]:
    """函数**返回**的那个 summary dict 的顶层键 + 其中被忽略的 ``**`` 个数。

    四种写法都认，都是「返回的 dict 的顶层键」：

    - ``return {...}`` / ``return drafts, {...}``（``_dual_engine_summary`` / 分段两条路径）；
    - ``return summary``，其中 ``summary = {...}``（``_build_summary``）；
    - 对该名的就地 ``summary.update({...})``（``_build_summary`` 的预算分支）；
    - 对该名逐条塞 ``summary["<键>"] = ...``（整本分段把两个分支的计数补进去）。
    """
    return_dicts, returned_names = _returned_dicts_and_names(func)
    keys: set[str] = set()
    splats = 0
    for node in return_dicts:
        found, skipped = _dict_string_keys(node, where=f"{where} 的 return")
        keys |= found
        splats += skipped
    for name in returned_names:
        for targets, value in _assignments(func):
            for target in targets:
                if isinstance(target, ast.Name) and target.id == name and isinstance(value, ast.Dict):
                    found, skipped = _dict_string_keys(value, where=f"{where} 的 {name} = {{...}}")
                    keys |= found
                    splats += skipped
                subscript_key = _string_subscript_name(target, name)
                if subscript_key is not None:
                    keys.add(subscript_key)
        for node in ast.walk(func):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "update":
                if isinstance(node.func.value, ast.Name) and node.func.value.id == name:
                    for arg in node.args:
                        if isinstance(arg, ast.Dict):
                            found, skipped = _dict_string_keys(arg, where=f"{where} 的 {name}.update({{...}})")
                            keys |= found
                            splats += skipped
    assert keys, (
        f"{where} 里没找到返回的 summary 键（``return {{...}}`` / ``summary = {{...}}`` / ``summary[...] = ...``）："
        f"先修本测试。"
    )
    return keys, splats


def _scanned_summary() -> tuple[frozenset[str], int]:
    """扫出 summary 顶层键的集合与忽略掉的 ``**`` splat 个数。"""
    keys: set[str] = set()
    splats = 0
    for path in SUMMARY_PAYLOAD_PY:
        tree = _parse(path)
        for node in _keyword_dicts(tree, "summary_payload", where=path.name):
            found, skipped = _dict_string_keys(node, where=f"{path.name} summary_payload=")
            keys |= found
            splats += skipped
    for path in ANALYSIS_OUTCOME_PY:
        tree = _parse(path)
        for node in _outcome_summary_dicts(tree, where=path.name):
            found, skipped = _dict_string_keys(node, where=f"{path.name} PdfAnalysisOutcome(summary=)")
            keys |= found
            splats += skipped
    for path, name in RETURNED_SUMMARY_DICTS:
        where = f"{path.name}::{name}"
        found, skipped = _returned_summary_keys(_function(path, _parse(path), name), where=where)
        keys |= found
        splats += skipped
    return frozenset(keys), splats


@lru_cache(maxsize=1)
def _frontend_corpus() -> tuple[str, ...]:
    """``frontend/src`` 全部 TS/TSX 的正文：只读一遍盘，供「这个键有没有落点」逐个查。"""
    return tuple(
        path.read_text(encoding="utf-8", errors="ignore")
        for path in sorted(FRONTEND_SRC.rglob("*"))
        if path.is_file() and path.suffix in _FRONTEND_SUFFIXES
    )


def test_scanner_is_not_silently_empty() -> None:
    """1. 扫描器不许静默空（防假绿，关键）：重构把扫描弄坏时这条先红。"""
    scanned, splats = _scanned_summary()
    assert len(scanned) >= MIN_SCANNED_KEYS, (
        f"只扫出 {len(scanned)} 个 summary 键（要求 >= {MIN_SCANNED_KEYS}）：扫描器已经扫不到东西了。"
        f"summary 的键被搬到了新的位置？把新位置加进 SUMMARY_PAYLOAD_PY / ANALYSIS_OUTCOME_PY / "
        f"RETURNED_SUMMARY_DICTS，不要调低这个门槛。"
    )
    missing = CANARY_KEYS - scanned
    assert not missing, (
        f"哨兵键扫不出来：{sorted(missing)}。这几个键的位置就是扫描器是否还活着的证据——"
        f"缺了说明定位逻辑（按函数名找 dict 字面量）已经与被扫代码脱钩。"
    )
    assert splats <= MAX_SPLATS, (
        f"summary 的 dict 字面量里有 {splats} 个 `**` splat（上限 {MAX_SPLATS}）："
        f"splat 展开进来的键扫描器看不见。新增的 splat 请把那几个键显式登记进 KNOWN_DYNAMIC，"
        f"并说明为什么只能动态进入 summary。"
    )


def test_every_summary_key_is_registered() -> None:
    """2. 扫出的键必须 ⊆ ALL_SUMMARY_KEYS。"""
    scanned, _splats = _scanned_summary()
    unregistered = sorted(scanned - _registry().ALL_SUMMARY_KEYS)
    assert not unregistered, (
        "你新加了 summary 键 "
        + "、".join(unregistered)
        + "：请判它是 UI 还是 DIAG，登记到 apps/pdf_splitting/services/split/summary_contract.py"
        "（UI = 律师要在界面上看到它；DIAG = 只有排障用）。"
    )


def test_ui_keys_have_a_frontend_landing() -> None:
    """3. 每个 UI 键都必须在 ``frontend/src`` 里出现过。"""
    corpus = _frontend_corpus()
    assert corpus, f"{FRONTEND_SRC} 下没读到任何 .ts/.tsx：路径写错了，这条断言会恒真，先修本测试。"
    orphans = sorted(key for key in _registry().UI_SUMMARY_KEYS if not any(key in text for text in corpus))
    assert not orphans, (
        "登记为 UI 但前端没有任何读取："
        + "、".join(orphans)
        + "。要么补落点（在 frontend/src 里真的消费这个键），要么改登记为 DIAG。"
    )


def test_diag_keys_explain_themselves() -> None:
    """4. 每个 DIAG 键都写清了「为什么律师不用看」。"""
    unexplained = sorted(key for key, reason in _registry().DIAG_SUMMARY_KEYS.items() if len(reason.strip()) < 8)
    assert not unexplained, (
        "登记为 DIAG 但没写清为什么律师不用看：" + "、".join(unexplained) + "。一句话说明它只服务哪类排障；"
        "写不出来就说明它其实该是 UI。"
    )


def test_known_dynamic_only_lists_real_unscannable_keys() -> None:
    """5. ``KNOWN_DYNAMIC`` 只许是已知那几项，且不许冒充静态可见的键。"""
    scanned, _splats = _scanned_summary()
    masquerading = sorted(KNOWN_DYNAMIC & scanned)
    assert not masquerading, (
        f"{masquerading} 明明是静态可见的（扫描器已经扫到了），却登记在 KNOWN_DYNAMIC 里："
        f"那是给自己开一条「测试看不见我」的后门，删掉这条登记即可。"
    )
    unregistered = sorted(KNOWN_DYNAMIC - _registry().ALL_SUMMARY_KEYS)
    assert not unregistered, (
        f"KNOWN_DYNAMIC 里的 {unregistered} 没登记进 ALL_SUMMARY_KEYS：它在 summary 里是真的存在，"
        f"只是扫描器拿不到，同样要判 UI / DIAG。"
    )
    # 反向一档：声明为「静态拿不到」的键，必须真的在业务代码里存在，否则它只是为了让测试
    # 变绿而编的名字（删除键后忘了同步删这里，也会被这条抓住）。
    source = "\n".join(path.read_text(encoding="utf-8") for path in SPLIT_DIR.glob("*.py"))
    fabricated = sorted(key for key in KNOWN_DYNAMIC if f'"{key}"' not in source)
    assert not fabricated, (
        f"KNOWN_DYNAMIC 里的 {fabricated} 在 apps/pdf_splitting/services/split/ 里连字面量都找不到："
        f"这个名字是编的（或者键已被删除但登记没跟上）。"
    )
    # 最强的一道：两个「经 **splat 铺平进 summary」的源头函数，它们返回的每个键都必须有交代。
    # 少了这一条，KNOWN_DYNAMIC 就只是一份人工记忆——在整本分段路径里新增一个键不会有人红。
    splatted: set[str] = set()
    for path, name in SPLATTED_SUMMARY_DICTS:
        where = f"{path.name}::{name}"
        found, _skipped = _returned_summary_keys(_function(path, _parse(path), name), where=where)
        splatted |= found
    uncovered = sorted(splatted - KNOWN_DYNAMIC - scanned)
    assert not uncovered, (
        f"{uncovered} 会被 `**segment_summary` 铺平进 summary，但既不在 KNOWN_DYNAMIC 里也不静态可见："
        f"扫描器看不到它，等于它从登记里漏掉了。先登记进 summary_contract.py，再补进 KNOWN_DYNAMIC。"
    )
