"""非诉专项阶段树：模型校验 / 状态推导 / API 读写。

三块断言分别对应三处实现，故意放在一个文件里，改动其一能顺手看到另外两块：

1. `validate_stages`（apps/contracts/domain/validators.py）——结构不变量；
2. `derive_phase_states`（apps/contracts/services/contract/stage_tree.py）——
   与原型 `54-assets/phase-tree.js::deriveStates` 同一套状态规则；
3. `/contracts/{id}/stages` 的 GET/PUT——整树覆盖写 + 推导状态回吐。
"""

from __future__ import annotations

import copy
from typing import Any

import pytest

from apps.testing.factories import ContractFactory

STAGES: list[dict[str, Any]] = [
    {
        "key": "ph_dd",
        "name": "尽职调查",
        "acceptance": "《尽职调查报告》定稿（资产/债务/职工底数核清）",
        "templates": ["尽职调查清单模板", "尽调报告模板"],
        "date": "2026-10-26",
        "deliverables": [
            {"date": "2026-10-27", "doc": "《关厂清盘尽职调查清单》", "ver": "v1", "state": "ok", "planned": False},
            {"date": "2026-10-29", "doc": "《尽职调查报告》", "ver": "v2", "state": "ok", "planned": False},
        ],
        "children": [],
    },
    {
        "key": "ph_draft",
        "name": "文件起草",
        "acceptance": "三件核心文书定稿",
        "templates": ["职工安置方案模板"],
        "date": "",
        "deliverables": [],
        "children": [
            {
                "key": "ph_draft_1",
                "name": "职工安置文书",
                "acceptance": "《职工安置方案》定稿",
                "templates": ["职工安置方案模板"],
                "date": "",
                "deliverables": [
                    {"date": "", "doc": "《职工安置方案》", "ver": "v2", "state": "doing", "planned": True}
                ],
                "children": [],
            },
            {
                "key": "ph_draft_2",
                "name": "债权债务与决议",
                "acceptance": "《债权债务清理方案》与《股东会决议》定稿",
                "templates": ["债权债务清理方案模板"],
                "date": "",
                "deliverables": [
                    {"date": "", "doc": "《股东会决议（解散清算）》", "ver": "v1", "state": "ok", "planned": False},
                ],
                "children": [],
            },
        ],
    },
    {
        "key": "ph_register",
        "name": "登记与注销",
        "acceptance": "市场监管注销登记完成",
        "templates": ["注销登记材料清单"],
        "date": "",
        "deliverables": [],
        "children": [],
    },
]


def _node(key: str, *, planned: bool | None = None, children: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    deliverables = [] if planned is None else [{"doc": f"{key}.docx", "planned": planned}]
    return {"key": key, "name": key, "deliverables": deliverables, "children": children or []}


class TestValidateStages:
    """结构不变量：深度 ≤ 3、key 唯一且非空、name 非空。"""

    def test_accepts_three_level_tree(self) -> None:
        from apps.contracts.validators import validate_stages

        tree = [_node("l1", children=[_node("l2", children=[_node("l3")])])]
        assert validate_stages(tree) == tree

    def test_rejects_fourth_level(self) -> None:
        from apps.contracts.validators import validate_stages
        from apps.core.exceptions import ValidationException

        tree = [_node("l1", children=[_node("l2", children=[_node("l3", children=[_node("l4")])])])]
        with pytest.raises(ValidationException) as exc:
            validate_stages(tree)
        assert exc.value.code == "STAGES_TOO_DEEP"

    def test_rejects_duplicate_key(self) -> None:
        from apps.contracts.validators import validate_stages
        from apps.core.exceptions import ValidationException

        tree = [_node("ph_a"), _node("ph_b", children=[_node("ph_a")])]
        with pytest.raises(ValidationException) as exc:
            validate_stages(tree)
        assert exc.value.code == "DUPLICATE_STAGE_KEY"
        assert exc.value.errors["duplicate_keys"] == ["ph_a"]

    def test_rejects_blank_name(self) -> None:
        from apps.contracts.validators import validate_stages
        from apps.core.exceptions import ValidationException

        with pytest.raises(ValidationException) as exc:
            validate_stages([{"key": "ph_a", "name": "   "}])
        assert exc.value.code == "INVALID_STAGE_NAME"

    def test_rejects_missing_key(self) -> None:
        from apps.contracts.validators import validate_stages
        from apps.core.exceptions import ValidationException

        with pytest.raises(ValidationException) as exc:
            validate_stages([{"name": "尽职调查"}])
        assert exc.value.code == "INVALID_STAGE_KEY"

    def test_none_and_empty_are_valid(self) -> None:
        from apps.contracts.validators import validate_stages

        assert validate_stages(None) == []
        assert validate_stages([]) == []


@pytest.mark.django_db
class TestContractModelStages:
    """Contract.clean() 把 validate_stages 挂进模型校验。"""

    def test_clean_accepts_valid_tree(self) -> None:
        """合法树过 clean() 只做校验、不改写：与两个 rejects 用例互为对照。"""
        contract = ContractFactory(stages=copy.deepcopy(STAGES))
        contract.full_clean()

        # 结构原样保留：clean() 返回的是原树，不是重建/裁剪后的树
        assert contract.stages == STAGES
        assert [node["key"] for node in contract.stages] == ["ph_dd", "ph_draft", "ph_register"]
        # 父子关系与字段值不被顺手归一化（阶段名可改、顺序可调，服务端无更权威默认值）
        assert contract.stages[1]["children"][0]["deliverables"][0]["planned"] is True
        assert contract.stages[1]["date"] == ""
        assert contract.stages[1]["children"][1]["key"] == "ph_draft_2"

    def test_clean_rejects_too_deep(self) -> None:
        """contract.clean() 直接把 validate_stages 的 ValidationException 透出。"""
        from apps.core.exceptions import ValidationException

        tree = [_node("l1", children=[_node("l2", children=[_node("l3", children=[_node("l4")])])])]
        contract = ContractFactory()
        contract.stages = tree
        with pytest.raises(ValidationException) as exc:
            contract.full_clean()
        assert exc.value.code == "STAGES_TOO_DEEP"

    def test_clean_rejects_duplicate_key(self) -> None:
        from apps.core.exceptions import ValidationException

        contract = ContractFactory()
        contract.stages = [_node("ph_a"), _node("ph_a")]
        with pytest.raises(ValidationException) as exc:
            contract.full_clean()
        assert exc.value.code == "DUPLICATE_STAGE_KEY"

    def test_default_is_empty_list(self) -> None:
        assert ContractFactory().stages == []


class TestDerivePhaseStates:
    """状态推导：有实际文件的叶子 = 完成；第一个没文件的叶子 = 进行中；父由子聚合。"""

    def _states(self, tree: list[dict[str, Any]]) -> dict[str, str]:
        from apps.contracts.services.contract.stage_tree import derive_phase_states

        rows: dict[str, str] = {}
        level = list(derive_phase_states(tree))
        while level:
            rows.update({str(node["key"]): node["state"] for node in level})
            level = [child for node in level for child in node.get("children") or []]
        return rows

    def test_leaf_with_real_file_is_done(self) -> None:
        assert self._states([_node("a", planned=False)]) == {"a": "ok"}

    def test_first_leafless_leaf_is_doing_rest_todo(self) -> None:
        states = self._states([_node("a", planned=False), _node("b"), _node("c")])
        assert states == {"a": "ok", "b": "doing", "c": "todo"}

    def test_parent_aggregates_children(self) -> None:
        tree = [_node("p", children=[_node("c1", planned=False), _node("c2", planned=False)])]
        assert self._states(tree) == {"p": "ok", "c1": "ok", "c2": "ok"}

    def test_parent_with_unfinished_child_is_doing(self) -> None:
        tree = [_node("p", children=[_node("c1", planned=False), _node("c2")])]
        states = self._states(tree)
        assert states["p"] == "doing"
        assert states["c2"] == "doing"

    def test_parent_does_not_steal_current_leaf(self) -> None:
        """父节点 deliverables 为空时不能把「进行中」抢走（原型踩过的坑）。"""
        tree = [_node("p", children=[_node("c1", planned=False), _node("c2")]), _node("q")]
        states = self._states(tree)
        assert states == {"p": "doing", "c1": "ok", "c2": "doing", "q": "todo"}

    def test_does_not_mutate_input(self) -> None:
        from apps.contracts.services.contract.stage_tree import derive_phase_states

        tree = [_node("a", planned=False)]
        derive_phase_states(tree)
        assert "state" not in tree[0]

    def test_empty_tree(self) -> None:
        from apps.contracts.services.contract.stage_tree import derive_phase_states

        assert derive_phase_states([]) == []
        assert derive_phase_states(None) == []

    def test_prototype_tree_states(self) -> None:
        """原型 data.js 的树（交付物按 planned 标出「有没有实际文件」）。

        文件起草的职工安置文书只有一个 `planned` 交付物（方案还没落文件），
        所以它是当前叶子 = 进行中，父阶段随之进行中；登记与注销仍在它后面 = 未开始。
        """
        assert self._states(STAGES) == {
            "ph_dd": "ok",
            "ph_draft": "doing",
            "ph_draft_1": "doing",
            "ph_draft_2": "ok",
            "ph_register": "todo",
        }


@pytest.mark.django_db
class TestStagesApi:
    """service 层读写（API 端点是薄封装，权限在 contract_api 同一套 policy 上）。"""

    def test_get_returns_derived_states(self) -> None:
        from apps.contracts.services.contract.stages_service import ContractStagesService

        contract = ContractFactory(stages=STAGES, case_type="special")
        stages = ContractStagesService().get_stages(contract.id)
        assert [node["key"] for node in stages] == ["ph_dd", "ph_draft", "ph_register"]
        assert stages[1]["children"][0]["state"] == "doing"
        assert stages[-1]["state"] == "todo"

    def test_replace_persists_without_derived_state(self) -> None:
        from apps.contracts.services.contract.stages_service import ContractStagesService

        contract = ContractFactory(case_type="special")
        service = ContractStagesService()
        written = service.replace_stages(contract.id, STAGES)

        assert written[0]["state"] == "ok"
        contract.refresh_from_db()
        assert contract.stages[0]["key"] == "ph_dd"
        # 推导值不落库：改一个交付物状态就重算，存下来必然过期
        assert all("state" not in node for node in contract.stages)

    def test_replace_rejects_too_deep(self) -> None:
        from apps.contracts.services.contract.stages_service import ContractStagesService
        from apps.core.exceptions import ValidationException

        contract = ContractFactory(case_type="special")
        tree = [_node("l1", children=[_node("l2", children=[_node("l3", children=[_node("l4")])])])]
        with pytest.raises(ValidationException):
            ContractStagesService().replace_stages(contract.id, tree)
        contract.refresh_from_db()
        assert contract.stages == []


class TestStagesApiRoutes:
    """路由注册在合同前缀下 —— 真实 URL 是 /api/v1/contracts/contracts/{id}/stages。"""

    def test_endpoints_registered(self) -> None:
        from apiSystem.api import api_v1

        paths = {path for path in api_v1.get_openapi_schema()["paths"] if "stages" in path}
        assert paths == {"/api/v1/contracts/contracts/{contract_id}/stages"}
