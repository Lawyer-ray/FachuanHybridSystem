"""从 LLMProvider 生成 pi 的 models.json。

## 为什么要生成

pi 的模型来自 ``models.json``（文件），而本系统的 LLM 配置在数据库
（``core.LLMProvider``：base_url + 多 Key 池 + 模型白名单）。两边不打通，
用户在 Admin 改配置后 agent 不生效，是运维陷阱。

这里在建立 pi 会话前，把当前 LLMProvider 渲染成 ``models.json`` 写进该会话
的独立配置目录，使 **Admin 里的配置就是 agent 用的配置**。

## 与多 Key 池的关系

pi 只接受一个 ``apiKey``。系统的多 Key 轮询（``core.llm.key_pool``）在
**服务路径**上生效；agent 路径这里取「第一个可用 Key」，并在多个会话间
轮转（``_round_robin``），使并发时 Key 的使用分散开。

真正做到「每个请求都走 Key 池」需要一层网关（把 ``baseUrl`` 指向自家
网关，由网关做 Key 轮换）。本模块预留了 ``FACHUAN_PI_GATEWAY_URL``：
设置后 ``baseUrl`` 直接指向网关，Key 由网关管理，pi 侧不再持有真实 Key。
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

from apps.core.llm.gateway_profile import (
    DEFAULT_THINKING_LEVEL,
    fallback_chain,
    gateway_effort,
    model_supports_thinking,
    resolve_thinking,
)

logger = logging.getLogger(__name__)

GATEWAY_URL_ENV = "FACHUAN_PI_GATEWAY_URL"
GATEWAY_KEY_ENV = "FACHUAN_PI_GATEWAY_KEY"
#: 上下文窗口声明（写进 ``models.json`` 的 ``contextWindow``）。
#:
#: ## 为什么现在是 1,000,000 且可被环境变量覆盖
#:
#: 它决定**harness 什么时候开始自动压缩**：pi 到达这个值就摘要历史。声明得比真实
#: 窗口小，模型明明装得下也会被提前摘要（综合结论这种"一次喂五栏全文"的场景直接
#: 被吃掉一半）；声明得比真实窗口大，则会在真实上限处被网关 400，而那是**跑到一半
#: 才炸**，整轮回答丢失。
#:
#: 所以两个数都不是拍脑袋能定的：真值以模型卡/实测为准，这里只给默认与覆盖口。
#: 2026-11-22 按业务方决定取 1M；若某部署的模型实际是 256K，设
#: ``FACHUAN_CONTEXT_WINDOW=262144`` 即可，不用改代码。
DEFAULT_CONTEXT_WINDOW = int(os.environ.get("FACHUAN_CONTEXT_WINDOW", "1000000") or 1000000)

#: 单次输出的 token 上限（``models.json`` 的 ``maxTokens``）。
#:
#: 同样可覆盖：合成结论要一次写上千字，8192 在"思考 + 正文"并存的推理模型上会被
#: 顶满（实测 kimi-2.6 曾吃到 5958/6144），顶满即被视为"没写完"。
DEFAULT_MAX_TOKENS = int(os.environ.get("FACHUAN_MAX_TOKENS", "32768") or 32768)
# 上面的 ``DEFAULT_THINKING_LEVEL`` / ``gateway_effort`` 是**从
# ``apps.core.llm.gateway_profile`` 再导出**的（思考档位与能力特征表的唯一来源）：
# ``antigravity_backend`` / ``openai_agents_backend`` 都写着
# ``from ..pi.model_config import DEFAULT_THINKING_LEVEL, gateway_effort``，
# 删掉这两个名字会把它们打断。


def _next_key(keys: list[str], provider: str = "") -> str:
    """会话间轮转 Key，并**跳过别的进程判定冷却中**的 Key（审计 P0-1）。

    真正持有槽位的路径（core LLMClient / 检索）用 ``KeyPool.acquire``，冷却精确
    记账；而 pi/dsh/openai-agents 在外部进程里直接跟网关说话，拿不到请求边界，
    不能占槽位（会泄漏）。这里做读侧最小修复：健康优先轮转，绝不主动去撞一把
    已知 401/429 的 Key。全冷却时仍返回一把（fail-open，见 ``key_selector``）。
    """
    from apps.core.llm.key_selector import select_key

    return select_key(list(keys or []), provider=provider)


def _load_provider(model_hint: str = "") -> Any:
    """读取启用的 LLMProvider；失败时返回 None（调用方降级）。"""
    try:
        from apps.core.models.llm_provider import LLMProvider
    except Exception:
        logger.debug("无法导入 LLMProvider", exc_info=True)
        return None

    try:
        queryset = LLMProvider.objects.filter(enabled=True).order_by("priority", "name")
        for provider in queryset:
            models = _provider_models(provider)
            if not model_hint or model_hint in models or not models:
                return provider
        return queryset.first()
    except Exception:
        # warning 而非 debug：这里最典型的失败是在 async 上下文读库
        # （SynchronousOnlyOperation）。吞成 debug 会让「思考模式莫名不生效」
        # 「models.json 没生成」这类问题彻底无迹可查——排查时极难定位。
        logger.warning("查询 LLMProvider 失败（若在 async 上下文需用 sync_to_async 包裹）", exc_info=True)
        return None


def _provider_keys_and_models(provider: Any) -> tuple[list[str], dict[str, list[str]]]:
    """解析 provider 的 Key 及其模型白名单。

    ``api_keys`` 是原始文本，格式为 ``key`` 或 ``key|model1,model2``（每行一条），
    必须走 ``LLMProvider.parse_key_entries``，不能当字符串逐字符处理。
    """
    raw = getattr(provider, "api_keys", "") or ""
    try:
        from apps.core.models.llm_provider import parse_key_entries

        entries = parse_key_entries(str(raw))
    except Exception:
        logger.debug("解析 api_keys 失败", exc_info=True)
        entries = [(line.strip(), []) for line in str(raw).splitlines() if line.strip()]

    keys: list[str] = []
    scopes: dict[str, list[str]] = {}
    for key, models in entries:
        if not key or key in keys:
            continue
        keys.append(key)
        if models:
            scopes[key] = list(models)
    return keys, scopes


def _provider_models(provider: Any) -> list[str]:
    """provider 支持的模型列表（默认模型 + extra_models + Key 白名单）。"""
    models: list[str] = []
    default = str(getattr(provider, "default_model", "") or "").strip()
    if default:
        models.append(default)
    extra = str(getattr(provider, "extra_models", "") or "")
    for part in extra.replace(";", ",").split(","):
        name = part.strip()
        if name and name not in models:
            models.append(name)
    return models


def _is_vision_model(name: str, provider: Any) -> bool:
    """该模型是否是 provider 声明的视觉模型（精确名匹配）。

    要求 ``vision_model`` 与模型名 **精确相等**（仅忽略首尾空白与大小写）：
    前缀/子串匹配会把 ``kimi-2.6`` 的视觉能力误传给 ``kimi-2.6-text``，
    而网关对纯文本模型收到 ``image_url`` 的响应是 400 报错，比静默退回文本更糟。
    """
    vision = str(getattr(provider, "vision_model", "") or "").strip().lower()
    return bool(vision) and name.strip().lower() == vision


def supports_image_input(model_hint: str = "") -> bool:
    """当前模型是否接受图像输入（下游据此决定走视觉路径还是 OCR 文本路径）。

    与 ``_model_entry`` 的 ``input`` 声明同一口径：两者不一致会造成
    「models.json 说能读图，但工具层早年就转成了 OCR 文本」。

    调用方在返回 ``False`` 时应明确告知用户「当前模型无法读图，已返回 OCR 文本」，
    而不是静默退化（用户只看到回答未提图片，无法判断是模型没看图还是看了没看懂）。

    Args:
        model_hint: 模型名；空则回落到 provider 的 ``default_model``。

    Returns:
        模型声明为视觉模型时 ``True``；没有任何可用 provider 时 ``False``
        （fail-closed：宁可不发图，也不发网关不认的 ``image_url``）。
    """
    provider = _load_provider(model_hint)
    if provider is None:
        return False
    name = model_hint or str(getattr(provider, "default_model", "") or "")
    if not name:
        return False
    return _is_vision_model(name, provider)


def _model_entry(name: str, *, enable_thinking: bool, provider: Any) -> dict[str, Any]:
    """渲染 models.json 里的单个模型条目。

    ``reasoning`` 是 pi 的「模型支持思考」声明：为真时 pi 会启用 thinking，
    并把思考过程以 ``thinking_delta`` 事件推给客户端（前端据此展示「思考中」）。
    早期这里没声明该字段，于是即便后端开了思考模式，pi 也不会展示思考过程。

    仅对推理模型且平台开启 ``enable_thinking`` 时声明 ``reasoning: true``，
    避免给普通模型（glm53 等）错报能力导致 pi 发它不认的 thinking 参数。
    两个条件由 :func:`apps.core.llm.gateway_profile.resolve_thinking` 统一算：
    ``supported`` 是模型能力（特征表唯一来源），``enabled`` 还叠加了平台开关。

    ``input`` 是 pi 的 **vision gate**：pi 的 openai-completions 适配器只在
    ``model.input`` 含 ``"image"`` 时才把 image block 转成 ``image_url`` 下发。
    不写该字段时 pi 默认 ``["text"]``，用户上传的图片被**静默降级**成一句
    ``"(see attached image)"`` 文本——模型既看不到图，也不报错，表现为
    「附件显示已发送，但回答完全没提图片内容」。所以这里必须显式声明。

    匹配用**精确相等**（不做前缀/子串匹配）：给纯文本模型错报 vision 会让网关
    收到它不认的 ``image_url`` 而直接 400。相比「多报能力」，漏报只会退回文本
    路径，fail-closed 更安全。唯一真值来源是 ``provider.vision_model``
    （语义：该平台的多模态模型名，留空禁用视觉）。
    """
    directives = resolve_thinking(name, enable_thinking=enable_thinking)
    entry: dict[str, Any] = {
        "id": name,
        "contextWindow": DEFAULT_CONTEXT_WINDOW,
        "maxTokens": DEFAULT_MAX_TOKENS,
        "reasoning": directives.supported and directives.enabled,
        "input": ["text", "image"] if _is_vision_model(name, provider) else ["text"],
        # 网关适配（实测必需）：本仓库的 LiteLLM 网关把思考开关放在
        # ``chat_template_kwargs.thinking``（布尔），而 pi 的 openai-completions
        # 适配器默认探测会误判 → 不发思考参数，网关不返回 reasoning_content，
        # 表现为「思考模式开了但永远不思考」。
        #
        # 三个字段缺一不可：
        # - thinkingFormat=chat-template：走 chat_template_kwargs 通道
        # - chatTemplateKwargs：告诉 pi 往该通道写什么。
        #   ``$var: thinking.enabled`` 是 pi 的变量语法，由思考等级推导布尔值
        # - supportsReasoningEffort=false：避免发网关不认的 reasoning_effort
        # 为什么现在是 ``True``（与早先的 ``False`` 相反）：
        # 早先写 False 是因为当时的判断是「网关不认 reasoning_effort，发了会
        # 400」。实测（2026-11-19）证明那个判断错了——网关（LiteLLM → vLLM）
        # 接受且**需要** ``reasoning_effort`` 才能真正分级：
        #
        #   reasoning_effort=max  + chat_template_kwargs.thinking=true
        #   → HTTP 200，reasoning_tokens 26–48，reasoning_content 有内容
        #
        # 两个参数是**互补**而非互斥：thinking 开关管「要不要想」，
        # reasoning_effort 管「想多深」。只发前者等于永远停在默认深度，
        # 拖到 Max 也不生效。
        #
        # 若将来网关换成真的不认 effort 的实现，改回 False 即可（单点开关）。
        "compat": {
            "thinkingFormat": "chat-template",
            "supportsReasoningEffort": True,
            "maxTokensField": "max_tokens",
            "chatTemplateKwargs": {"thinking": {"$var": "thinking.enabled"}},
        },
    }
    if entry["reasoning"]:
        # 档位映射：pi 的七个档位 → 网关真正接受的 reasoning_effort。
        #
        # 为什么必须显式给：pi 文档原话是「模型没映射的档位走 provider 默认值
        # 到 high；**xhigh 和 max 不支持**」。不写这张表，使用者把档位拖到
        # Max 时会被默默降成 high——正是「看起来调了但没生效」。
        #
        # 为什么值不是原样七档：服务端（DeepSeek V4.1 / vLLM）只认
        # ``low`` / ``high`` / ``xhigh`` / ``max``，发 ``medium`` 直接 400。
        # 映射口径的唯一来源是 ``apps.core.llm.gateway_profile.gateway_effort``
        # （本表的值必须与它一致；``off`` 一栏是 pi 自己的语义，不在网关白名单里）。
        entry["thinkingLevelMap"] = {
            "off": "off",
            "minimal": "low",
            "low": "low",
            "medium": "high",
            "high": "high",
            "xhigh": "xhigh",
            "max": "max",
        }
    return entry


def resolve_thinking_level(model_hint: str = "", provider: Any | None = None) -> str | None:
    """解析该模型应使用的 pi 思考等级（``--thinking`` 参数值）。

    重要：``models.json`` 里的 ``reasoning: true`` 只是冓「这个模型能思考」，
    真正的推理开关是会话的 ``thinkingLevel``，默认 ``off``。只声明能力而不传
    ``--thinking``，模型依旧不思考、也不会产生 ``thinking_delta`` 事件。

    ``provider`` 缺省时自行查询；调用方已查过则传入，避免重复读库。

    Returns:
        ``max``（平台开启思考且模型是推理模型）；否则 ``None``（不传参数，
        pi 保持默认 off）。
    """
    if provider is None:
        provider = _load_provider(model_hint)
    if provider is None or not getattr(provider, "enable_thinking", False):
        return None
    models = _provider_models(provider)
    target = model_hint or str(getattr(provider, "default_model", "") or "")
    if target and models and target not in models:
        return None
    # 能力判定只问 ``gateway_profile``（特征表唯一来源）。原先问的是
    # ``provider.supports_thinking``，那只是同一张表的一层转发。
    if not model_supports_thinking(target):
        return None
    return DEFAULT_THINKING_LEVEL


def build_models_json(
    model_hint: str = "", provider: Any | None = None, *, api_key: str | None = None
) -> dict[str, Any] | None:
    """把当前 LLMProvider 渲染成 pi 的 models.json 内容。

    ``provider`` 缺省时自行查询；调用方已查过则传入，避免重复读库。

    Args:
        api_key: 本轮编排层指定的网关 key（``RunContext.api_key``）。有值时写进
            ``providers.fachuan.apiKey``，**不再调** ``_next_key``：网关限每把
            key 的并发（实测 3），同轮多个 agent 各拿一把互不相同的 key 只能由
            编排层按轮次分配（见 ``backends/key_scheduler``）。``None`` / 空串
            保持原轮转口径，行为与引入本参数前逐字一致。

    Returns:
        ``models.json`` 的 dict；无可用 provider 时返回 ``None``
        （此时 pi 用自己的用户级配置，不做任何覆盖）。
    """
    gateway = os.environ.get(GATEWAY_URL_ENV, "").strip()
    if provider is None:
        provider = _load_provider(model_hint)

    if gateway:
        # 网关模式：baseUrl 指向自家网关，pi 不持有真实 Key
        models = _provider_models(provider) if provider is not None else []
        if model_hint and model_hint not in models:
            models.insert(0, model_hint)
        if not models:
            models = [model_hint] if model_hint else []
        if not models:
            return None
        enable_thinking = bool(getattr(provider, "enable_thinking", False))
        return {
            "providers": {
                "fachuan": {
                    "baseUrl": gateway,
                    "api": "openai-completions",
                    "apiKey": os.environ.get(GATEWAY_KEY_ENV, "gateway"),
                    "models": [
                        _model_entry(name, enable_thinking=enable_thinking, provider=provider) for name in models
                    ],
                }
            }
        }

    if provider is None:
        return None

    base_url = str(getattr(provider, "base_url", "") or "").strip()
    keys, _scopes = _provider_keys_and_models(provider)
    if not base_url or not keys:
        logger.warning("LLMProvider 缺少 base_url 或 api_key，pi 将使用自身配置")
        return None

    models = _provider_models(provider)
    if model_hint and model_hint not in models:
        models.insert(0, model_hint)
    if not models:
        return None

    return {
        "providers": {
            "fachuan": {
                "baseUrl": base_url,
                "api": "openai-completions",
                "apiKey": (api_key or "").strip() or _next_key(keys, provider=getattr(provider, "name", "")),
                "models": [
                    _model_entry(
                        name, enable_thinking=bool(getattr(provider, "enable_thinking", False)), provider=provider
                    )
                    for name in models
                ],
            }
        }
    }


def write_models_json(
    target_dir: str | Path, model_hint: str = "", provider: Any | None = None, *, api_key: str | None = None
) -> Path | None:
    """把 models.json 写进目标目录；无可用配置时返回 ``None``。

    **文件含明文 API Key，必须以 0600 创建。** ``Path.write_text`` 会先按
    默认 umask（通常 0644）建文件再 chmod，中间存在其他用户可读的窗口期，
    且 chmod 失败时容易被静默吞掉。这里用 ``mkstemp``（创建即 0600）写同目录
    临时文件再 ``os.replace`` 原子替换：pi 任何时刻读到的都是完整 JSON，
    不会撞上 O_TRUNC 直写留下的截断/半截窗口。``provider`` 缺省时自行查询。
    ``api_key`` 原样转交 :func:`build_models_json`（编排层轮次级分配的 key）。
    """
    payload = build_models_json(model_hint, provider=provider, api_key=api_key)
    if payload is None:
        return None

    path = Path(target_dir) / "models.json"
    data = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")

    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=".models-", suffix=".tmp")
    try:
        # 缓冲写完整落盘（处理部分写）；mkstemp 创建即 0600，replace 后权限随新文件
        with os.fdopen(fd, "wb") as tmp_file:
            tmp_file.write(data)
        os.replace(tmp_name, path)
    finally:
        # replace 成功后 tmp 已不存在，suppress 兜底；失败时清掉残留临时文件
        with contextlib.suppress(OSError):
            os.unlink(tmp_name)
    return path


def resolve_fallback_models(model_hint: str = "") -> list[str]:
    """解析降级模型链（P2-7）：[主模型, fallback1, fallback2, ...]。

    主模型失败（PiError）时按序尝试备选；无备选返回单元素列表。

    ``fallback_models`` 原样交给 :func:`gateway_profile.fallback_chain`，
    **不能先 ``str()``**：该字段在服务通道是 ``list[str]``，字符串化会得到
    ``"['glm53', 'qwen3']"`` 这种形态，清洗后产出一个名为 ``['glm53`` 的模型。
    """
    provider = _load_provider(model_hint)
    if provider is None:
        return [model_hint] if model_hint else []
    primary = model_hint or str(getattr(provider, "default_model", "") or "")
    return fallback_chain(primary, getattr(provider, "fallback_models", "") or "")
