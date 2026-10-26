"""划词直改（direct-edit）的请求 / 响应模型。

与 `review_schemas` 分开：那套是「任务」模型（上传 → 定立场 → 跑流水线 →
逐条决策），这套是「一次改写请求」的无状态调用，没有 task_id、没有等级、
没有报告。混在一起会让读者误以为两者同构。
"""

from __future__ import annotations

from ninja import Schema


class DirectEditSuggestIn(Schema):
    """请求改写候选。不写盘、不建任务。"""

    contract_id: int
    """合同 ID（绑定文件夹归属）"""
    subpath: str
    """绑定根下的相对路径，如 `3-办案/专项合同.docx`"""
    selection: str
    """律师在编辑器里框选的原文"""
    instruction: str
    """律师的要求，如「违约金降到合同总额的 10%」"""
    model_name: str = ""


class DirectEditCandidateOut(Schema):
    suggested: str
    reason: str = ""


class DirectEditSuggestOut(Schema):
    candidates: list[DirectEditCandidateOut]
    """2~3 条取向不同的改写候选；律师挑一条再调 apply"""
    context_before: str = ""
    """选区前文（前端展示「这段在什么语境里」，也便于排查定位失败）"""
    context_after: str = ""


class DirectEditApplyIn(Schema):
    """采纳某一条候选：写成 Word 修订痕迹并覆写原文件。"""

    contract_id: int
    subpath: str
    selection: str
    """必须是 suggest 时用的同一段原文——落笔定位靠它"""
    suggested: str
    """律师选中的那条改写文本"""


class DirectEditApplyOut(Schema):
    applied: bool
    subpath: str
    name: str = ""
    reason: str = ""
    """applied=False 时的人话原因（定位失败等），可直接展示给律师"""
