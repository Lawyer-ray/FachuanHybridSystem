"""judge 模型的四步解析（契约 §C2）：请求 → 平台配置 → 本轮模型 → 422。

## 为什么这件事必须服务端做

前端**不许猜模型名**：写死一个平台上不存在的名字，评审会以 ``judge_error`` 全线失败，
而律师看到的是「三栏全都没评上」——没人知道病因是名字错了。所以顺序是：

1. 请求里给了就用（律师显式选的）；
2. 没给用平台配置 ``FACHUAN_REVIEW_JUDGE_MODELS``；
3. 再没给用**本轮真的跑过的模型**（``AgentMessage.metadata["model"]``，一定在平台白名单
   里——那是平台自己派下去的）；
4. 都没有 = 平台上确实一个可用模型都没有 → HTTP 层 422「未配置评审模型」。

## 为什么本轮模型最多取 2 个

judge 的意义是"另一个模型看同一份回答"；全同源就失去互检，而三个以上只会把延迟拉长
（重试是串行换模型）。取前两个是契约 §C2 定的口径。

## 为什么读 ``os.environ`` 而不是 Django settings

与 ``adoption.SHADOW_ENV`` 同一个理由：``FACHUAN_REVIEW_*`` 这一族评审开关都不在 settings
里注册，免得"改 .env 还要同步改 settings"两处漂移。缺省/空值一律当"未配置"。
"""

from __future__ import annotations

import os
import re
from collections.abc import Sequence

#: 平台级 judge 模型配置（逗号分隔；与 ``adoption.SHADOW_ENV`` 同族）。
JUDGE_MODELS_ENV = "FACHUAN_REVIEW_JUDGE_MODELS"
#: 从本轮各栏模型里最多取几个（§C2 第 3 条）。
MAX_TURN_JUDGE_MODELS = 2

#: 逗号/空白都可作分隔符：``kimi-2.6, glm53`` 与换行写法的 .env 都要能读。
_SPLIT_RE = re.compile(r"[,\s]+")


def _clean(models: Sequence[str]) -> list[str]:
    """去空白、丢空串、去重保序（重复模型名只会让重试落在同一个模型上）。"""
    return list(dict.fromkeys(stripped for stripped in (model.strip() for model in models) if stripped))


def split_models(raw: str) -> list[str]:
    """把一段平台的模型配置拆成清单（空串 → ``[]``）。"""
    return _clean(_SPLIT_RE.split(raw))


def configured_judge_models() -> list[str]:
    """``FACHUAN_REVIEW_JUDGE_MODELS`` 的模型清单（未配置/空 → 空列表）。"""
    return split_models(os.environ.get(JUDGE_MODELS_ENV, ""))


def resolve_judge_models(
    *,
    requested: Sequence[str],
    configured: Sequence[str],
    turn_models: Sequence[str],
) -> list[str]:
    """按契约 §C2 的 1→2→3 顺序取 judge 模型。

    Args:
        requested: 请求体里的 ``judge_models``（可为空）。
        configured: ``configured_judge_models()`` 的结果（可为空）。
        turn_models: 本轮各栏实际用过的模型（去重保序，可为空）。

    Returns:
        非空模型清单；三处都空时返回 ``[]``——HTTP 层据此 422「未配置评审模型」，
        **不在这里编一个默认模型名**（平台上没有的名字只会让评审全线失败）。
    """
    for candidate in (requested, configured):
        models = _clean(candidate)
        if models:
            return models
    return _clean(turn_models)[:MAX_TURN_JUDGE_MODELS]


__all__ = [
    "JUDGE_MODELS_ENV",
    "MAX_TURN_JUDGE_MODELS",
    "configured_judge_models",
    "resolve_judge_models",
    "split_models",
]
