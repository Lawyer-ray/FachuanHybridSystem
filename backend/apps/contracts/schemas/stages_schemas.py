"""非诉专项阶段树 Schemas（GET/PUT /contracts/contracts/{id}/stages）。

节点结构与前端已实现的形态**逐键一致**：
`frontend/prototype/2026.10.03-办案详情原型/54-assets/phase-tree.js` 的 `normPhase`：

    {"key": "ph_x", "name": "尽职调查", "acceptance": "《尽调报告》定稿",
     "templates": ["模板名"], "date": "2026-10-26",
     "deliverables": [{"date": "", "doc": "《报告》", "ver": "v1",
                       "state": "ok|doing|todo", "planned": true}],
     "children": [...]}

为什么 `stages` 用 `list[dict]` 而不是逐字段 Schema：阶段内容是律师在前端
编辑的产物（改名、调序、加交付物），后端只负责存盘；把每个键钉成 schema
会让前端每加一个展示字段就得同步改后端（原型里 note / _depth 都出现过）。
结构不变量（深度 ≤ 3、key 唯一、name 非空）由
`apps.contracts.validators.validate_stages` 校验，那里报错信息也更准。
"""

from __future__ import annotations

from typing import Any

from ninja import Schema


class ContractStagesIn(Schema):
    """PUT 请求体：整棵树覆盖写（阶段改名/调序后由前端提交全量）。"""

    stages: list[dict[str, Any]] = []


class ContractStagesOut(Schema):
    """GET/PUT 响应体。

    stages 里每个节点带 `state`（ok / doing / todo），由
    `apps.contracts.services.contract.stage_tree.derive_phase_states` 推导后
    合入节点：前端渲染直接读 `node.state`，不必自己再推一遍，也不会出现
    「页面推一套、接口存一套」。存盘时 `state` 会被剥离（见 stages_service），
    它是推导值不是律师编辑的数据。
    """

    stages: list[dict[str, Any]] = []
