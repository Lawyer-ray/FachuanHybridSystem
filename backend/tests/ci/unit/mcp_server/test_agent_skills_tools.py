"""技能工具面（读半边 + 写半边）的契约测试。

四件事必须钉死（对应 ``CONTRACT.md`` §11 与 ``HANDOFF-P1`` §6）：

1. ``get_agent_skill`` **有用户上下文必须走 REST**（``resolve_for_user`` 是唯一
   知道「这位律师停用了哪个技能」「所内线上生效的是哪一版」的地方）；只有
   REST 不可用且名字是内置技能时才能回落到静态文件——否则读静态盘就绕过了
   停用偏好与共享审批版。
2. ``list_my_skills`` 返回 ``dict`` 信封（裸 ``list`` 会被 SDK 逐项拆块、空列表
   变零内容块，见 ``test_tool_shaping``）。
3. 参数名不得命中 ``SENSITIVE_ARG_MARKERS``：命中会把参数级判定送进「带敏感
   字段 → 高危」分支，审批语义就脏了（写工具本身就是 HIGH，不需要这层）。
4. 风险档与只读白名单：读 LOW / 写 HIGH；三个写工具不得进子 agent 的只读面
   （``readonly_tool_selection`` 只放 ``get_/list_/search_/read_/preview_``）。

用假 client 驱动 REST 路径，不打网络、不碰数据库。
"""

from __future__ import annotations

import fnmatch
import inspect
from pathlib import Path
from typing import Any
from unittest import mock

import pytest

from mcp_server.client import FachuanApiError
from mcp_server.identity import request_authorization
from mcp_server.tools.core import agent_skills

#: 个人技能的 key 形态（REST 只认 ``skill:<uuid>``）
_PERSONAL_KEY = "skill:3f2b1c4d-1111-4222-8333-444455556666"

#: 本轮新增 / 扩展的五个技能工具
_SKILL_TOOLS = (
    "get_agent_skill",
    "list_my_skills",
    "save_user_skill",
    "delete_user_skill",
    "submit_skill_for_review",
)

_BUILTIN = "deadline-queries"


@pytest.fixture()
def rest_client() -> Any:
    """替换模块级 ``client``：所有 REST 调用都落在假对象上。"""
    shared = mock.MagicMock()
    with mock.patch.object(agent_skills, "client", shared):
        yield shared


@pytest.fixture(autouse=True)
def _stdio_context() -> Any:
    """默认「无用户上下文」（本地 stdio / 单测）；需要 REST 的用例自己 set。"""
    token = request_authorization.set("")
    yield
    request_authorization.reset(token)


def _act_as_lawyer() -> None:
    """模拟 HTTP 模式透传的律师身份（``RequestAuthMiddleware`` 的效果）。"""
    request_authorization.set("Bearer test-token")


class TestGetAgentSkillRest:
    """有用户上下文时，正文只从 REST 取。"""

    def test_uses_resolve_endpoint_with_start(self, rest_client: Any) -> None:
        _act_as_lawyer()
        payload = {
            "key": "builtin:web-research",
            "name": "web-research",
            "scope": "builtin",
            "version": 0,
            "content": "# 续读窗口",
            "start": 16000,
            "total_bytes": 40000,
            "truncated": True,
            "next_start": 32000,
        }
        rest_client.get.return_value = payload

        result = agent_skills.get_agent_skill("web-research", start=16000)

        assert result is payload
        rest_client.get.assert_called_once_with("/agent/skills/resolve/web-research/content", params={"start": 16000})

    def test_normalizes_name_and_accepts_personal_key(self, rest_client: Any) -> None:
        _act_as_lawyer()
        rest_client.get.return_value = {"content": "正文"}

        agent_skills.get_agent_skill(" Builtin:Web-Research ")
        rest_client.get.assert_called_once_with(
            "/agent/skills/resolve/builtin:web-research/content", params={"start": 0}
        )

        rest_client.get.reset_mock()
        agent_skills.get_agent_skill(_PERSONAL_KEY)
        rest_client.get.assert_called_once_with(f"/agent/skills/resolve/{_PERSONAL_KEY}/content", params={"start": 0})

    @pytest.mark.parametrize("bad", ["../secrets", "a/b", "/etc/passwd", "..", "", "技能名"])
    def test_rejects_path_injection_before_building_url(self, rest_client: Any, bad: str) -> None:
        """``{ref}`` 会被拼进 URL 路径——白名单先于任何请求生效。"""
        _act_as_lawyer()
        with pytest.raises(ValueError, match="非法技能名"):
            agent_skills.get_agent_skill(bad)
        rest_client.get.assert_not_called()

    def test_rejects_malformed_personal_key(self, rest_client: Any) -> None:
        _act_as_lawyer()
        with pytest.raises(ValueError, match="非法技能 key"):
            agent_skills.get_agent_skill("skill:../../etc/passwd")
        rest_client.get.assert_not_called()

    def test_falls_back_to_static_for_builtin(self, rest_client: Any) -> None:
        """REST 不可用 + 内置名 → 读盘兜底（内置技能随代码发布，盘上有）。"""
        _act_as_lawyer()
        rest_client.get.side_effect = FachuanApiError("HTTP 404: {'detail': '端点不存在'}")

        result = agent_skills.get_agent_skill(_BUILTIN)

        assert result["name"] == _BUILTIN
        assert result["scope"] == "builtin"
        assert result["content"] == (Path(agent_skills._DEFAULT_SKILLS_ROOT) / _BUILTIN / "SKILL.md").read_text(
            encoding="utf-8"
        )
        assert result["truncated"] is False
        assert result["next_start"] is None

    def test_fails_loudly_for_user_skill(self, rest_client: Any) -> None:
        """非内置名没有本地副本：报错并带上 REST 的真实原因，不许静默空手。"""
        _act_as_lawyer()
        rest_client.get.side_effect = FachuanApiError("HTTP 503: {'detail': '数据库不可用'}")

        with pytest.raises(ValueError, match="非内置技能没有本地副本") as excinfo:
            agent_skills.get_agent_skill("my-style")
        assert "HTTP 503" in str(excinfo.value)


class TestGetAgentSkillStatic:
    """无用户上下文（本地 stdio / 单测）只读内置静态文件。"""

    def test_static_only_without_user_context(self, rest_client: Any) -> None:
        result = agent_skills.get_agent_skill(_BUILTIN)

        assert result["key"] == f"builtin:{_BUILTIN}"
        assert result["content"].startswith("---")
        rest_client.get.assert_not_called()

    def test_unknown_name_lists_available(self, rest_client: Any) -> None:
        with pytest.raises(ValueError, match=r"未知技能.*可用技能"):
            agent_skills.get_agent_skill("nonexistent-skill")
        rest_client.get.assert_not_called()

    def test_static_segmentation_round_trip(self, tmp_path: Path, monkeypatch: Any, rest_client: Any) -> None:
        """``truncated=true`` 时带 ``start=next_start`` 续读，拼回去等于原文。"""
        body = "法" * 8000  # 24000 字节 > 16000 预算，必然分段
        (tmp_path / "long-skill").mkdir()
        (tmp_path / "long-skill" / "SKILL.md").write_text(body, encoding="utf-8")
        monkeypatch.setenv(agent_skills._SKILLS_DIR_ENV, str(tmp_path))

        first = agent_skills.get_agent_skill("long-skill")
        assert first["truncated"] is True
        assert first["next_start"] == len(first["content"].encode("utf-8"))
        assert len(first["content"].encode("utf-8")) <= agent_skills._CONTENT_BYTE_BUDGET
        assert first["total_bytes"] == len(body.encode("utf-8"))

        second = agent_skills.get_agent_skill("long-skill", start=first["next_start"])
        assert second["truncated"] is False
        assert first["content"] + second["content"] == body
        rest_client.get.assert_not_called()

    def test_start_out_of_range_raises(self, rest_client: Any) -> None:
        with pytest.raises(ValueError, match="越界"):
            agent_skills.get_agent_skill(_BUILTIN, start=999_999)


class TestListMySkills:
    def test_returns_dict_envelope_with_effective_skills_only(self, rest_client: Any) -> None:
        rest_client.get.return_value = {
            "skills": [
                {
                    "key": "builtin:web-research",
                    "name": "web-research",
                    "title": "联网检索",
                    "description": "查法条 / 抓网页原文时使用",
                    "scope": "builtin",
                    "source": "builtin",
                    "enabled": True,
                    "editable": False,
                    "version": 0,
                },
                {
                    "key": _PERSONAL_KEY,
                    "name": "my-style",
                    "title": "我的写作风格",
                    "description": "起草文书时使用",
                    "scope": "lawyer",
                    "source": "user",
                    "enabled": False,
                    "editable": True,
                    "version": 2,
                },
                {
                    "key": "skill:99999999-1111-4222-8333-444455556666",
                    "name": "firm-style",
                    "title": "所内写法",
                    "description": "被个人同名技能遮蔽",
                    "scope": "law_firm",
                    "source": "law_firm",
                    "enabled": True,
                    "editable": False,
                    "effective": False,
                    "version": 3,
                },
            ]
        }

        result = agent_skills.list_my_skills()

        assert isinstance(result, dict)
        assert [item["name"] for item in result["skills"]] == ["web-research"]
        assert set(result["skills"][0]) == {"key", "name", "title", "description", "scope"}
        rest_client.get.assert_called_once_with("/agent/skills")

    def test_empty_list_is_explicit(self, rest_client: Any) -> None:
        rest_client.get.return_value = {"skills": []}
        assert agent_skills.list_my_skills() == {"skills": []}


class TestWriteToolsCallRest:
    """写工具必须真的打到对应端点（静默空转 = 模型以为存了，其实没存）。"""

    def test_save_user_skill_posts_personal_skill(self, rest_client: Any) -> None:
        rest_client.post.return_value = {"key": _PERSONAL_KEY, "name": "my-style", "title": "我的写作风格"}
        result = agent_skills.save_user_skill(
            name="my-style",
            title="我的写作风格",
            description="起草文书时按这个格式输出",
            body="先给结论，再列依据。",
        )

        rest_client.post.assert_called_once_with(
            "/agent/skills",
            json={
                "name": "my-style",
                "title": "我的写作风格",
                "description": "起草文书时按这个格式输出",
                "body": "先给结论，再列依据。",
            },
        )
        assert result["name"] == "my-style"
        # 正文不回显：正文可到 32KB，原样回显会撞上 pi 的 20KB 输出截断线
        assert "body" not in result

    def test_delete_user_skill_deletes_personal_key(self, rest_client: Any) -> None:
        rest_client.delete.return_value = None

        result = agent_skills.delete_user_skill(_PERSONAL_KEY)

        rest_client.delete.assert_called_once_with(f"/agent/skills/{_PERSONAL_KEY}")
        assert result == {"key": _PERSONAL_KEY, "deleted": True}

    def test_submit_skill_for_review_posts_target_scope(self, rest_client: Any) -> None:
        rest_client.post.return_value = {"key": _PERSONAL_KEY, "review_status": "pending"}

        result = agent_skills.submit_skill_for_review(_PERSONAL_KEY, "law_firm", note="全所都能用")

        rest_client.post.assert_called_once_with(
            f"/agent/skills/{_PERSONAL_KEY}/submit",
            json={"target_scope": "law_firm", "note": "全所都能用"},
        )
        assert result["review_status"] == "pending"


class TestParamNamesAvoidSensitiveMarkers:
    """参数名严禁含 ``SENSITIVE_ARG_MARKERS`` 词根（status / state / stage 等）。"""

    def test_no_param_hits_sensitive_markers(self) -> None:
        from apps.agent.services.approval import SENSITIVE_ARG_MARKERS

        offenders: list[str] = []
        for tool in _SKILL_TOOLS:
            for param in inspect.signature(getattr(agent_skills, tool)).parameters:
                hits = [marker for marker in SENSITIVE_ARG_MARKERS if marker in param.lower()]
                if hits:
                    offenders.append(f"{tool}.{param} 命中 {hits}")
        assert not offenders, f"技能工具的参数名命中了敏感词根（会被参数级判定升档）: {offenders}"

    def test_write_tool_signatures_are_contract_shaped(self) -> None:
        """参数名是契约的一部分（审批卡与 REST 字段一一对应），改名要同步契约。"""
        assert list(inspect.signature(agent_skills.save_user_skill).parameters) == [
            "name",
            "title",
            "description",
            "body",
        ]
        assert list(inspect.signature(agent_skills.delete_user_skill).parameters) == ["key"]
        assert list(inspect.signature(agent_skills.submit_skill_for_review).parameters) == [
            "key",
            "target_scope",
            "note",
        ]


class TestRiskTiers:
    def test_write_tools_are_high(self) -> None:
        from apps.agent.services.approval import RiskLevel, classify_risk

        assert classify_risk("save_user_skill") is RiskLevel.HIGH
        assert classify_risk("delete_user_skill") is RiskLevel.HIGH
        assert classify_risk("submit_skill_for_review") is RiskLevel.HIGH

    def test_read_tools_are_low(self) -> None:
        from apps.agent.services.approval import RiskLevel, classify_risk

        assert classify_risk("get_agent_skill") is RiskLevel.LOW
        assert classify_risk("list_my_skills") is RiskLevel.LOW


class TestReadonlyToolSelection:
    """子 agent 的只读面：读工具自动纳入，写工具结构性不可达。"""

    @staticmethod
    def _covered(tool: str, selection: str) -> bool:
        patterns = [pattern.strip() for pattern in selection.split(",") if pattern.strip()]
        return any(fnmatch.fnmatchcase(f"mcp__fachuan__{tool}", pattern) for pattern in patterns)

    def test_read_tools_included_write_tools_excluded(self) -> None:
        from apps.agent.services import subtask

        selection = subtask.readonly_tool_selection()

        assert self._covered("get_agent_skill", selection)
        assert self._covered("list_my_skills", selection)
        assert not self._covered("save_user_skill", selection)
        assert not self._covered("delete_user_skill", selection)
        assert not self._covered("submit_skill_for_review", selection)
