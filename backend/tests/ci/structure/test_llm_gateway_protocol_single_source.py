"""Structure guard: 网关协议知识（思考能力 / 档位 / 请求字段）必须有唯一来源。

背景
----
「网关认哪些字段、认哪些档位、认哪些模型能思考」这三件事此前被复制在 **5 处**，
且已经分叉到会改变用户可见的回答质量。2026-11 实测：``kimi-k2`` 命中 Agent 通道的
宽匹配表（下发 ``thinking=true`` + ``reasoning_effort=max``），却不命中服务通道的窄
匹配表（**一个字段都不发**）——同一平台、同一模型、同一个开关，copilot 里深度推理，
诉状生成里完全不推理，**且没有任何报错**。

``apps/core/llm/gateway_profile.py`` 把这些知识收成单一权威。本文件负责**防回流**：
谁再复制一份，这里立刻红。复制的代价不是「多写几行」，而是下一次改口径时只改一处，
两条通道重新静默分叉。

守 5 件事
----------
1. 思考能力特征串（``"deepseekreasoner"`` 等）只许出现在 ``gateway_profile.py``；
2. ``reasoning_effort`` 白名单字面量 tuple/list 只许出现在 ``gateway_profile.py``；
3. ``{"chat_template_kwargs": {"thinking": ...}}`` 的 dict 字面构造只许出现在
   ``gateway_profile.py``（adapter 应改用 :func:`gateway_profile.wire_fields`）；
4. 各 adapter 必须 import ``gateway_profile``（防「删掉 import、顺手内联一份」）；
5. Admin 表单里 ``rpm_limit`` / ``tpm_limit`` 的 help_text 必须写明「仅服务通道生效」——
   这两个字段只对能看到请求边界的服务通道有效，Agent 通道（copilot）不受此限，
   页面上必须说清楚，否则运维会以为改它能治 copilot 的 429；文案必须**引用**
   ``gateway_profile.RATE_LIMIT_CHANNEL_NOTE``，不许在 Admin 里再写一份字面量。

为什么断言 5 查的是 Admin 表单而不是 ``LLMProvider._meta``
--------------------------------------------------------
字段的 ``help_text`` 属**迁移状态**：改一个字就会生成一份 help_text-only 的
``AlterField`` 迁移（实测 ``makemigrations --check`` 会报 ``0042_alter_llmprovider_...``），
而迁移需要真人审批拍库。这段口径只是给人看的适用范围声明，不值得为它背一份永久迁移。
所以文案的真相放在无模型的 ``gateway_profile``（不触发 autodetector），
由 Admin 表单在渲染时引用。两条断言（表单能拿到文案 + Admin 源码里出现该常量名）
一起才能证明「运维看得见」且「只有一份」。

注意：本条**不**守 Agent 通道是否真的不做限流（那是行为，由 ``key_pool`` 的
单元测试与 TECH-DEBT ⑤ 的压测结论管），只守「页面不会误导人」。

为什么按「唯一来源」而不是按「计数棘轮」
----------------------------------------
这四项的正确值都是 **0**（除权威模块外一处都不该有），所以没有「基线」可言：
新增一条违规就直接失败，不存在「还没超过基线先放过」。确实需要豁免时，按
``path:symbol`` 精确登记在 :data:`ALLOWED_PROTOCOL_FILES` 并写清原因，不要按目录批量放行。

允许名单
--------
- ``gateway_profile.py`` 本体（字面量本来就写在这里）；
- ``migrations/``：历史快照，永不改写（``help_text`` 的旧文案不该被判违规）；
- harness 自有配置键（``thinkingFormat`` / ``chatTemplateKwargs`` /
  ``reasoningEfforts`` / ``thinkingLevelMap``）：那是 pi / dsh 的**配置格式**，
  不是「网关认什么」的知识，不在禁令内。
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[3]
APPS_DIR = BACKEND_DIR / "apps"

#: 网关协议知识的唯一权威模块。
AUTHORITY_MODULE = "apps/core/llm/gateway_profile.py"

#: rpm/tpm 适用范围文案的载体模块（即 ``LLMProvider`` 的 Admin 页）。
ADMIN_MODULE = "apps/core/admin/llm_provider_admin.py"

#: 适用范围文案的常量名（它必须被 Admin **引用**，不能在 Admin 里另写一份字面量）。
RATE_LIMIT_NOTE_SYMBOL = "RATE_LIMIT_CHANNEL_NOTE"

#: 允许出现网关协议字面量的文件（`path:symbol` 粒度，路径相对 ``backend/``）。
#: 只减不增：别的文件不该再有。
ALLOWED_PROTOCOL_FILES: dict[str, str] = {
    AUTHORITY_MODULE: "权威模块本体：思考能力表 / 档位白名单 / 请求字段构造的唯一实现",
}

#: 必须 import ``gateway_profile`` 的 adapter（新增 adapter 时加到这里）。
#: 这是「单点口径」的入口：只要 adapter 从 profile 取知识，改口径就只需改 profile。
GATEWAY_ADAPTERS: tuple[str, ...] = (
    "apps/core/llm/backends/openai_compatible.py",  # 服务通道
    "apps/agent/pi/model_config.py",  # pi
    "apps/agent/backends/dsh_config.py",  # DeepSeek Harness
    # openai-agents 后端已于 v27.23.10 移除（空缺由 codex 顶上）；codex 走
    # `codex app-server` + config.toml，思考字段由 codex 自己算，不经过本表。
    # antigravity：字段在``antigravity_backend.thinking_extra``里算好（它 import 权威模块），
    # loopback 代理``antigravity_gateway``只负责把它合并进请求体、不自己拼字段——
    # 对它来说「不复制知识」的守卫是断言 3（不得出现 wire 字段字面构造），而非要求它
    # 多一个只为满足检查的 import。
    "apps/agent/backends/antigravity_backend.py",
)

#: 思考能力特征串。只列**不会与自然语言撞车**的 4 条：
#: ``"kimi"`` / ``"mimo"`` / ``"reasoner"`` 太泛（``enable_thinking`` 的 help_text
#: 会写「如 kimi-2.6 / DeepSeek R1 / MiMo」），按子串扫会误报。
THINKING_MARKER_STRINGS: tuple[str, ...] = (
    "deepseekreasoner",
    "deepseekr1",
    "qwq",
    "glmz",
)

#: 网关 ``reasoning_effort`` 白名单的四个档位（``gateway_profile.GATEWAY_EFFORTS``）。
#: 判定口径：tuple/list 字面量里**同时出现这四个值** → 有人在自建白名单。
EFFORT_WHITELIST_LEVELS: tuple[str, ...] = ("low", "high", "xhigh", "max")

#: 网关**不接受**的档位。tuple/list 里出现其中任一个，说明它是 harness 自己的档位词汇
#: （如 ``pi/model_config._PI_THINKING_LEVELS`` 的七档），不是网关白名单的复印件——
#: 白名单按定义不可能含 ``medium``（发了直接 400）。
HARNESS_ONLY_LEVELS: frozenset[str] = frozenset({"minimal", "medium"})

#: 网关请求字段的字面构造：``{"chat_template_kwargs": {"thinking": ...}}``。
WIRE_FIELD_KEY = "chat_template_kwargs"
WIRE_FIELD_INNER_KEY = "thinking"


def _iter_app_py_files() -> list[Path]:
    """``apps/`` 下所有源文件（跳过 ``__pycache__`` 与历史迁移快照）。"""
    files: list[Path] = []
    if not APPS_DIR.is_dir():  # pragma: no cover - 路径错由其他结构测试兜住
        return files
    for py_file in sorted(APPS_DIR.rglob("*.py")):
        rel = py_file.relative_to(BACKEND_DIR).as_posix()
        if "__pycache__" in rel or "/migrations/" in rel:
            continue
        files.append(py_file)
    return files


def _rel(py_file: Path) -> str:
    return py_file.relative_to(BACKEND_DIR).as_posix()


def _parse(py_file: Path) -> ast.AST:
    return ast.parse(py_file.read_text(encoding="utf-8", errors="ignore"), filename=str(py_file))


def _iter_scannable_files() -> list[Path]:
    """待扫描文件：``apps/`` 全部源文件去掉权威模块本体（它本来就该有这些字面量）。"""
    return [py_file for py_file in _iter_app_py_files() if _rel(py_file) not in ALLOWED_PROTOCOL_FILES]


def _constant_str_values(node: ast.AST) -> set[str]:
    """``ast.Tuple`` / ``ast.List`` 里的字符串常量值。"""
    if not isinstance(node, (ast.Tuple, ast.List)):
        return set()
    return {elt.value for elt in node.elts if isinstance(elt, ast.Constant) and isinstance(elt.value, str)}


def _imports_gateway_profile(py_file: Path) -> bool:
    """该文件是否 import 了 ``gateway_profile``（含 ``from ... import gateway_profile`` 与函数内延迟 import）。"""
    for node in ast.walk(_parse(py_file)):
        if isinstance(node, ast.Import):
            if any(alias.name.split(".")[-1] == "gateway_profile" for alias in node.names):
                return True
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module.split(".")[-1] == "gateway_profile":
                return True
            if any(alias.name == "gateway_profile" for alias in node.names):
                return True
    return False


@pytest.mark.unit
class TestLLMGatewayProtocolSingleSource:
    """网关协议知识的唯一来源守卫（纯静态扫描，不连库）。"""

    def test_thinking_capability_markers_only_in_authority(self) -> None:
        """1. 思考能力特征串只许出现在 ``gateway_profile.py``。

        复制这张表的后果不是多几行代码，而是「同一个模型在两条通道上判出相反结论」。
        """
        offenders: list[str] = []
        for py_file in _iter_scannable_files():
            for node in ast.walk(_parse(py_file)):
                if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                    continue
                lowered = node.value.lower()
                hits = [marker for marker in THINKING_MARKER_STRINGS if marker in lowered]
                if hits:
                    offenders.append(f"{_rel(py_file)}:{node.lineno}: {sorted(hits)} in {node.value[:60]!r}")

        assert offenders == [], (
            f"思考能力特征串只允许出现在 {AUTHORITY_MODULE}，"
            "其他地方请改用 gateway_profile.model_supports_thinking / resolve_thinking：\n" + "\n".join(offenders)
        )

    def test_reasoning_effort_whitelist_only_in_authority(self) -> None:
        """2. ``reasoning_effort`` 白名单字面量 tuple/list 只许出现在 ``gateway_profile.py``。

        同时含 ``low`` / ``high`` / ``xhigh`` / ``max`` 的 tuple/list 就是白名单的复印件
        （dsh 曾自写一份 ``("off", "low", "high", "xhigh", "max")``，与 pi 的口径不一致）。
        正确写法：``gateway_profile.selectable_efforts()`` / ``GATEWAY_EFFORTS``。

        含 :data:`HARNESS_ONLY_LEVELS` 的不算：那是 harness 自己的档位全集（键），值仍须经
        ``gateway_effort`` 映射，不构成第二份白名单。
        """
        expected = set(EFFORT_WHITELIST_LEVELS)
        offenders: list[str] = []
        for py_file in _iter_scannable_files():
            for node in ast.walk(_parse(py_file)):
                values = _constant_str_values(node)
                if expected <= values and not (values & HARNESS_ONLY_LEVELS):
                    offenders.append(f"{_rel(py_file)}:{node.lineno}: {sorted(values)}")

        assert offenders == [], (
            f"reasoning_effort 白名单只允许出现在 {AUTHORITY_MODULE}，"
            "其他地方请改用 gateway_profile.GATEWAY_EFFORTS / selectable_efforts()：\n" + "\n".join(offenders)
        )

    def test_wire_fields_dict_literal_only_in_authority(self) -> None:
        """3. ``{"chat_template_kwargs": {"thinking": ...}}`` 的 dict 字面构造只许出现在权威模块。

        这是「网关真正吃哪两个字段」的知识，且**关闭时必须显式发 false**、开启时才带
        ``reasoning_effort``——三条分支任何一处抄错都会表现为「思考开关看着开了但不生效」。
        正确写法：``gateway_profile.wire_fields()``。
        """
        offenders: list[str] = []
        for py_file in _iter_scannable_files():
            for node in ast.walk(_parse(py_file)):
                if not isinstance(node, ast.Dict):
                    continue
                for key, value in zip(node.keys, node.values, strict=False):
                    if not (isinstance(key, ast.Constant) and key.value == WIRE_FIELD_KEY):
                        continue
                    if not isinstance(value, ast.Dict):
                        continue
                    inner_keys = {k.value for k in value.keys if isinstance(k, ast.Constant)}
                    if WIRE_FIELD_INNER_KEY in inner_keys:
                        offenders.append(f"{_rel(py_file)}:{node.lineno}")

        assert offenders == [], (
            "网关请求字段的字面构造只允许出现在 "
            f"{AUTHORITY_MODULE}，其他地方请改用 gateway_profile.wire_fields()：\n" + "\n".join(offenders)
        )

    def test_gateway_adapters_import_authority(self) -> None:
        """4. **计算**思考字段的 adapter 必须 import ``gateway_profile``。

        「不许复制知识」只能靠 import 来兑现：不 import 的 adapter 迟早自己再写一份表。
        覆盖范围见 :data:`GATEWAY_ADAPTERS`，新增 adapter 时一并登记。

        只登记**自己计算**字段的模块。纯传输层（如 ``antigravity_gateway``：只把上层
        算好的 dict 合并进请求体）不在其中——它不得构造 wire 字段，那件事由断言 3 守。
        把传输层也塞进本清单，只会逼它加一个无意义的 import 来满足检查。
        """
        missing: list[str] = []
        for adapter in GATEWAY_ADAPTERS:
            py_file = BACKEND_DIR / adapter
            if not py_file.exists():
                missing.append(f"{adapter}: 文件不存在（adapter 改名后请同步本测试的 GATEWAY_ADAPTERS）")
                continue
            if not _imports_gateway_profile(py_file):
                missing.append(f"{adapter}: 未 import apps.core.llm.gateway_profile")

        assert missing == [], (
            "下列 adapter 没有引用网关协议层，请改为从 gateway_profile 取思考能力/档位/请求字段：\n"
            + "\n".join(missing)
        )

    def test_rate_limit_help_text_states_service_channel_only(self) -> None:
        """5. Admin 表单里 ``rpm_limit`` / ``tpm_limit`` 的 help_text 必须写明「仅服务通道生效」。

        这两个字段的唯一消费点是服务通道的 ``key_pool.configure_limits``；Agent 通道
        （copilot 主对话）的 model 调用在外部进程里，Django 侧看不到请求边界，根本不受限。
        页面上不明示，运维就会把它当成 copilot 的限流开关，改完以为治了 429。
        """
        from django.contrib import admin
        from django.test import RequestFactory

        from apps.core.admin.llm_provider_admin import LLMProviderAdmin
        from apps.core.llm.gateway_profile import RATE_LIMIT_CHANNEL_NOTE
        from apps.core.models import LLMProvider

        # 只构造表单（不连库）：admin 的 get_form 不读 DB，RequestFactory 也不。
        form_class = LLMProviderAdmin(LLMProvider, admin.site).get_form(RequestFactory().get("/admin/"))
        for field_name in ("rpm_limit", "tpm_limit"):
            help_text = form_class.base_fields[field_name].help_text
            assert RATE_LIMIT_CHANNEL_NOTE in help_text, (
                f"Admin 表单 {field_name} 的 help_text 未引用 gateway_profile.RATE_LIMIT_CHANNEL_NOTE"
                f"（当前：{help_text!r}）"
            )
            # 常量本身也必须真的在说「服务通道」，防有人把常量清空/改写成空话后本测试假绿。
            assert "服务通道" in help_text, (
                f"Admin 表单 {field_name} 的 help_text 未写明「仅服务通道生效」（当前：{help_text!r}）"
            )

        # 只看表单还不够：把文案在 Admin 里另写一份也能过上面两条，于是下一次改口径又只剩
        # 一处被改到——正是本文件要防的病。所以再要求 Admin 源码里真的引用了那个常量名。
        admin_src = (BACKEND_DIR / ADMIN_MODULE).read_text(encoding="utf-8")
        assert RATE_LIMIT_NOTE_SYMBOL in admin_src, (
            f"{ADMIN_MODULE} 未引用 gateway_profile.{RATE_LIMIT_NOTE_SYMBOL}"
            "（rpm/tpm 的适用范围文案必须只有一份，不要在 Admin 里另写字面量）"
        )
