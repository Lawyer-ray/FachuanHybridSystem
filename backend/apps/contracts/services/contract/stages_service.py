"""非诉专项阶段树读写服务（Contract.stages）。

纯函数 `derive_phase_states` 在同目录 `stage_tree.py`；本模块只负责「读一棵
带状态的树 / 校验并整树覆盖写」这两件事，不碰权限（行级 ACL 由 API 层的
`ContractAccessPolicy` 在调用前后收口，与其它 contract_api 端点一致）。

为什么把推导值 `state` 剥掉再存：`state` 是文件事实推出来的，改一个交付物
的 planned 就会全部重算。存进 JSONField 只会让下一次读到的树带着过期状态，
而前端又得再推一遍——两套结果迟早对不上。
"""

from __future__ import annotations

import copy
from typing import Any

from django.db import transaction

from apps.contracts.models import Contract
from apps.contracts.validators import validate_stages

from .stage_tree import derive_phase_states

StageNode = dict[str, Any]


def _strip_states(nodes: list[StageNode]) -> list[StageNode]:
    """去掉推导值 `state`（递归），返回新树。"""
    out: list[StageNode] = []
    for node in nodes:
        cleaned = {k: v for k, v in node.items() if k != "state"}
        if cleaned.get("children"):
            cleaned["children"] = _strip_states(cleaned["children"])
        out.append(cleaned)
    return out


class ContractStagesService:
    """阶段树读取 / 覆盖写。Contract 的取用只按 id，不做业务判断。"""

    def get_stages(self, contract_id: int) -> list[StageNode]:
        """返回带推导 `state` 的阶段树；合同不存在时由 `get` 抛 DoesNotExist。"""
        contract = Contract.objects.get(id=contract_id)
        return derive_phase_states(contract.stages or [])

    @transaction.atomic
    def replace_stages(self, contract_id: int, stages: list[StageNode] | None) -> list[StageNode]:
        """整树覆盖写，返回写入后（带 state）的树。

        阶段改名/调序/增删都是整树提交：局部 patch 无法表达「顺序变了」，
        而树的规模只有几十个节点，全量覆盖最简单也最不容易漂移。
        """
        cleaned = _strip_states(validate_stages(copy.deepcopy(stages or [])))
        contract = Contract.objects.select_for_update().get(id=contract_id)
        contract.stages = cleaned
        contract.save(update_fields=["stages", "updated_at"])
        return derive_phase_states(cleaned)


__all__ = ["ContractStagesService"]
