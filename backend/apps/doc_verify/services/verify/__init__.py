"""入站核对的编排层：策略、幂等运行、状态推导、裁决留痕、待裁决查询。

模块分工（也是唯一的调用方向）：

- `policy`   哪些文书默认要求核对（纯函数，无 IO）
- `run`      一次核对的编排：提取 → 比对 → 推导状态 → 落 `VerificationRun`
- `decision` 律师裁决（append-only）
- `query`    详情与待裁决清单（读模型）
- `deps`     跨 lane 依赖（比对引擎 / 入站件提取），函数体内惰性 import

本文件只做公开面的 re-export，不放逻辑：其他 app（收件箱、归案、后台任务）
从这里取入口，不 import 内部模块名。
"""

from __future__ import annotations

from .decision import DECISION_ACTIONS, record_decision
from .policy import HIGH_RISK_DOC_TYPES, should_verify
from .query import DECIDED_ACTIONS, NEEDS_DECISION_STATES, get_artifact, get_run, list_unverified, run_detail
from .run import (
    FILE_NAME_MAX_LENGTH,
    TIERS,
    decode_inbound_payload,
    derive_state,
    verify_existing_bytes,
    verify_inbound,
)

__all__ = [
    "DECIDED_ACTIONS",
    "DECISION_ACTIONS",
    "FILE_NAME_MAX_LENGTH",
    "HIGH_RISK_DOC_TYPES",
    "NEEDS_DECISION_STATES",
    "TIERS",
    "decode_inbound_payload",
    "derive_state",
    "get_artifact",
    "get_run",
    "list_unverified",
    "record_decision",
    "run_detail",
    "should_verify",
    "verify_existing_bytes",
    "verify_inbound",
]
