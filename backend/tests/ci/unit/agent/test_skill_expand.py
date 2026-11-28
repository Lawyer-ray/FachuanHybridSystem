"""编排层 ``/skill:`` 展开：锚点感知、白名单命中、超限透传、metadata 不留痕路径。

这条链路上最贵的事故是「静默不展开」：锚点行把 ``/skill:`` 顶离行首，pi 原生分支
直接失效，律师看到的只是「模型没按我的规范回答」，没有任何报错。所以锚点与命令的
每种组合（单锚点 / 三个锚点连排 / 跨行选段）都必须有用例，且「未命中就原样返回」
必须能保住锚点——否则一次误判就把案件归属信息丢了。
"""

from __future__ import annotations

import json
import logging
from typing import Any

import pytest

from apps.agent.models import AgentSkill
from apps.agent.services.skills import constants, expand, library, render
from apps.organization.models import LawFirm, Lawyer

TEST_PASSWORD = "x-test-12345678"  # pragma: allowlist secret

#: 随代码发布的内置技能（正文非空，展开用例不需要造数据）
BUILTIN = "web-research"
BUILTIN_COMMAND = f"/skill:{BUILTIN}"

BIZ_ANCHOR = "[当前业务：本委托“某银行” contract_id=8]"
PAGE_ANCHOR = "[当前页面：委托详情 · 某银行（contract_id=8）]"
FILE_ANCHOR = '[已引用文件：起诉状.pdf (attachment_id=31, contract_id=8, subpath="1-一审")]'
DIR_ANCHOR = '[已引用目录：立案材料 (case_id=7, subpath="1-一审/立案材料")]'
QUOTE_ANCHOR_FIRST = '[已引用选段："第一条 本金及利息\n第二条 违约责任" (contract_id=8, subpath="1-一审/合同.pdf")]'

EXPAND_LOGGER = "apps.agent.services.skills.expand"


@pytest.fixture(autouse=True)
def _user_skills_on(monkeypatch: pytest.MonkeyPatch) -> None:
    """默认把总开关摆成「on」：开发机 ``.env`` 里若配成 off 会让整组用例假红。"""
    monkeypatch.delenv(expand._USER_SKILLS_ENV, raising=False)


@pytest.fixture
def lawyer(db: Any) -> Lawyer:
    firm = LawFirm.objects.create(name="技能展开所")
    return Lawyer.objects.create_user(username="expand-user", password=TEST_PASSWORD, law_firm=firm)


def _personal(lawyer: Lawyer, name: str, **overrides: Any) -> AgentSkill:
    defaults: dict[str, Any] = {
        "scope": AgentSkill.Scope.LAWYER,
        "lawyer": lawyer,
        "name": name,
        "title": name,
        "description": f"{name} 的描述",
        "body": "# 做法\n先核主体资格。",
        "status": AgentSkill.Status.ACTIVE,
        "enabled": True,
        "created_by": lawyer,
    }
    defaults.update(overrides)
    return AgentSkill.objects.create(**defaults)


def _entry(name: str, *, scope: str = "lawyer", body: str = "# 做法", version: int = 1) -> dict[str, Any]:
    """``resolve_for_user`` 形状的条目（含正文），供「不碰 DB 也要测分支」的用例。"""
    return {
        "key": f"skill:{name}",
        "name": name,
        "title": name,
        "description": f"{name} 的描述",
        "scope": scope,
        "source": "user",
        "enabled": True,
        "editable": True,
        "version": version,
        "body": body,
    }


def _stub_candidates(monkeypatch: pytest.MonkeyPatch, *entries: dict[str, Any]) -> None:
    """把候选集钉死成给定条目：超限、作用域标签这类分支不该依赖造数据。"""
    monkeypatch.setattr(expand, "_candidates", lambda user_id: list(entries))


class TestCommandMatching:
    def test_bare_command_expands(self) -> None:
        result = expand.expand_skill_prompt(user_id=None, text=f"{BUILTIN_COMMAND} 你好")
        assert result.skill is not None
        assert result.prompt.startswith(f'<skill name="{BUILTIN}" scope="builtin">')
        assert result.prompt.endswith("</skill>\n你好")
        assert "联网检索" in result.prompt  # 内置 SKILL.md 的正文确实进来了

    def test_command_without_args_keeps_block_only(self) -> None:
        result = expand.expand_skill_prompt(user_id=None, text=BUILTIN_COMMAND)
        assert result.prompt.endswith("</skill>\n")

    def test_plain_message_passthrough(self) -> None:
        result = expand.expand_skill_prompt(user_id=None, text="帮我看看这份合同的违约责任")
        assert result == expand.ExpandedPrompt(prompt="帮我看看这份合同的违约责任", skill=None)

    def test_command_mid_text_passthrough(self) -> None:
        text = f"请用 {BUILTIN_COMMAND} 看看"
        assert expand.expand_skill_prompt(user_id=None, text=text).prompt == text

    def test_name_must_end_at_whitespace(self) -> None:
        """``/skill:a，你好`` 不是点名：名字里混标点必须原样透传，不许猜近似名。"""
        text = f"{BUILTIN_COMMAND}，你好"
        assert expand.expand_skill_prompt(user_id=None, text=text).skill is None

    def test_invalid_slug_passthrough(self) -> None:
        text = "/skill:合同审查 你好"
        assert expand.expand_skill_prompt(user_id=None, text=text).skill is None

    def test_unknown_name_passthrough(self) -> None:
        text = "/skill:no-such-skill 你好"
        assert expand.expand_skill_prompt(user_id=None, text=text) == expand.ExpandedPrompt(prompt=text, skill=None)

    def test_missing_colon_passthrough(self) -> None:
        text = f"/skill {BUILTIN} 你好"
        assert expand.expand_skill_prompt(user_id=None, text=text).skill is None


class TestAnchors:
    def test_biz_anchor_kept_verbatim(self) -> None:
        result = expand.expand_skill_prompt(user_id=None, text=f"{BIZ_ANCHOR}\n{BUILTIN_COMMAND} 梳理材料")
        lines = result.prompt.split("\n")
        assert lines[0] == BIZ_ANCHOR
        assert lines[1].startswith(f'<skill name="{BUILTIN}"')
        assert result.prompt.endswith("梳理材料")

    def test_page_anchor_kept_verbatim(self) -> None:
        result = expand.expand_skill_prompt(user_id=None, text=f"{PAGE_ANCHOR}\n{BUILTIN_COMMAND} 这个页面怎么用")
        assert result.prompt.split("\n")[0] == PAGE_ANCHOR
        assert "<skill " in result.prompt

    def test_multiline_quote_anchor_kept_verbatim(self) -> None:
        """选段原文可能含换行：块尾只认「以 ``]`` 结尾」那一行。"""
        result = expand.expand_skill_prompt(user_id=None, text=f"{QUOTE_ANCHOR_FIRST}\n{BUILTIN_COMMAND} 分析这段")
        first, second = QUOTE_ANCHOR_FIRST.split("\n")
        lines = result.prompt.split("\n")
        assert lines[0] == first
        assert lines[1] == second
        assert lines[2].startswith("<skill ")

    def test_file_anchor_kept_verbatim(self) -> None:
        """``[已引用文件：…]`` 也必须能感知：拖文件进对话后 ``/skill:`` 不能失效。"""
        result = expand.expand_skill_prompt(user_id=None, text=f"{FILE_ANCHOR}\n{BUILTIN_COMMAND} 看这份")
        assert result.prompt.split("\n")[0] == FILE_ANCHOR
        assert "<skill " in result.prompt
        assert result.skill is not None

    def test_dir_anchor_kept_verbatim(self) -> None:
        result = expand.expand_skill_prompt(user_id=None, text=f"{DIR_ANCHOR}\n{BUILTIN_COMMAND} 遍历一下")
        assert result.prompt.split("\n")[0] == DIR_ANCHOR
        assert "<skill " in result.prompt

    def test_all_five_anchor_kinds_recognised(self) -> None:
        """五种锚点必须全部在 ``ANCHOR_PREFIXES`` 里——漏一个就是「某页面下静默失效」。"""
        expected = {
            "[已引用选段：x]",
            "[已引用文件：x]",
            "[已引用目录：x]",
            "[当前业务：x]",
            "[当前页面：x]",
        }
        for sample in expected:
            assert sample.startswith(expand.ANCHOR_PREFIXES), sample
            result = expand.expand_skill_prompt(user_id=None, text=f"{sample}\n{BUILTIN_COMMAND} 好")
            assert "<skill " in result.prompt, sample

    def test_three_anchors_in_a_row(self) -> None:
        text = f"{PAGE_ANCHOR}\n{BIZ_ANCHOR}\n{QUOTE_ANCHOR_FIRST}\n{BUILTIN_COMMAND} 综合看看"
        result = expand.expand_skill_prompt(user_id=None, text=text)
        expected_prefix = [PAGE_ANCHOR, BIZ_ANCHOR, *QUOTE_ANCHOR_FIRST.split("\n")]
        assert result.prompt.split("\n")[: len(expected_prefix)] == expected_prefix
        assert "<skill " in result.prompt

    def test_anchor_without_command_is_untouched(self) -> None:
        """未命中必须原样返回——锚点丢了，模型就不知道这是哪个案件。"""
        text = f"{BIZ_ANCHOR}\n帮我梳理一下材料"
        assert expand.expand_skill_prompt(user_id=None, text=text).prompt == text

    def test_command_args_after_newline_preserved(self) -> None:
        text = f"{BIZ_ANCHOR}\n{BUILTIN_COMMAND}\n第一段\n第二段"
        result = expand.expand_skill_prompt(user_id=None, text=text)
        assert result.prompt.endswith("</skill>\n第一段\n第二段")


@pytest.mark.django_db
class TestResolution:
    def test_enabled_personal_skill_expands(self, lawyer: Lawyer) -> None:
        _personal(lawyer, "my-style")
        result = expand.expand_skill_prompt(user_id=lawyer.pk, text="/skill:my-style 你好")
        assert result.skill is not None
        assert result.skill["scope"] == "lawyer"
        assert result.prompt.startswith('<skill name="my-style" scope="lawyer">')

    def test_disabled_personal_skill_passthrough(self, lawyer: Lawyer) -> None:
        _personal(lawyer, "my-style", enabled=False)
        text = "/skill:my-style 你好"
        assert expand.expand_skill_prompt(user_id=lawyer.pk, text=text).prompt == text

    def test_archived_personal_skill_passthrough(self, lawyer: Lawyer) -> None:
        _personal(lawyer, "my-style", status=AgentSkill.Status.ARCHIVED)
        text = "/skill:my-style 你好"
        assert expand.expand_skill_prompt(user_id=lawyer.pk, text=text).prompt == text

    def test_other_lawyers_skill_passthrough(self, lawyer: Lawyer) -> None:
        other = Lawyer.objects.create_user(username="expand-other", password=TEST_PASSWORD, law_firm=lawyer.law_firm)
        _personal(other, "my-style")
        text = "/skill:my-style 你好"
        assert expand.expand_skill_prompt(user_id=lawyer.pk, text=text).prompt == text

    def test_user_skills_off_only_builtin(self, lawyer: Lawyer, monkeypatch: pytest.MonkeyPatch) -> None:
        """``FACHUAN_AGENT_USER_SKILLS=off``：个人技能一律不展开，内置照旧。"""
        _personal(lawyer, "my-style")
        monkeypatch.setenv(expand._USER_SKILLS_ENV, "off")
        assert expand.expand_skill_prompt(user_id=lawyer.pk, text="/skill:my-style 你好").skill is None
        assert expand.expand_skill_prompt(user_id=lawyer.pk, text=f"{BUILTIN_COMMAND} 你好").skill is not None

    def test_builtin_disabled_by_preference_passthrough(self, lawyer: Lawyer) -> None:
        """内置技能的偏好停用也走同一条解析面：停用后点名同样不展开。"""
        from apps.agent.models import AgentSkillPreference

        AgentSkillPreference.objects.create(user=lawyer, skill_key=f"builtin:{BUILTIN}", enabled=False)
        text = f"{BUILTIN_COMMAND} 你好"
        assert expand.expand_skill_prompt(user_id=lawyer.pk, text=text).prompt == text


class TestMetadataAndPaths:
    def test_metadata_is_minimal_and_path_free(self) -> None:
        result = expand.expand_skill_prompt(user_id=None, text=BUILTIN_COMMAND)
        assert result.skill == {"key": f"builtin:{BUILTIN}", "name": BUILTIN, "scope": "builtin", "version": 0}
        assert set(result.skill) == {"key", "name", "scope", "version"}
        assert "/" not in json.dumps(result.skill, ensure_ascii=False)

    def test_prompt_never_contains_host_path(self) -> None:
        result = expand.expand_skill_prompt(user_id=None, text=BUILTIN_COMMAND)
        assert str(library.skills_root()) not in result.prompt
        assert "/Users/" not in result.prompt
        assert ".md" not in result.prompt

    def test_invocation_is_logged_without_body(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """命中日志只记 name/scope/key——正文进日志等于把律师私人规范写进日志文件。"""
        _stub_candidates(monkeypatch, _entry("marker", body="# 做法\n原样输出：芒果-7731"))
        with caplog.at_level(logging.INFO, logger=EXPAND_LOGGER):
            expand.expand_skill_prompt(user_id=7, text="/skill:marker 你好")
        assert "agent.skill_invoked name=marker scope=lawyer" in caplog.text
        assert "芒果-7731" not in caplog.text


class TestScopeLabels:
    @pytest.mark.parametrize("scope", ["lawyer", "team", "law_firm", "builtin"])
    def test_scope_lands_in_tag(self, monkeypatch: pytest.MonkeyPatch, scope: str) -> None:
        _stub_candidates(monkeypatch, _entry("shared", scope=scope))
        result = expand.expand_skill_prompt(user_id=7, text="/skill:shared 你好")
        assert result.prompt.startswith(f'<skill name="shared" scope="{scope}">')
        assert result.skill is not None
        assert result.skill["scope"] == scope

    def test_unknown_scope_falls_back_to_lawyer(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """来历不明的作用域按个人算：四档前言里个人那档最保守。"""
        entry = _entry("mystery")
        entry["scope"] = "galaxy"
        _stub_candidates(monkeypatch, entry)
        result = expand.expand_skill_prompt(user_id=7, text="/skill:mystery")
        assert result.skill is not None
        assert result.skill["scope"] == "lawyer"

    def test_body_is_carried_into_block(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _stub_candidates(monkeypatch, _entry("marker", body="# 做法\n原样输出：芒果-7731"))
        result = expand.expand_skill_prompt(user_id=7, text="/skill:marker 你好")
        assert "原样输出：芒果-7731" in result.prompt


class TestOversizedBody:
    def test_body_over_limit_passthrough(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        oversized = "x" * (constants.MAX_BODY_BYTES + 1)
        _stub_candidates(monkeypatch, _entry("huge", body=oversized))
        text = "/skill:huge 你好"
        with caplog.at_level(logging.WARNING, logger=EXPAND_LOGGER):
            result = expand.expand_skill_prompt(user_id=7, text=text)
        assert result.prompt == text
        assert result.skill is None
        assert "不展开" in caplog.text

    def test_body_at_limit_expands(self, monkeypatch: pytest.MonkeyPatch) -> None:
        at_limit = "x" * constants.MAX_BODY_BYTES
        _stub_candidates(monkeypatch, _entry("big", body=at_limit))
        result = expand.expand_skill_prompt(user_id=7, text="/skill:big 你好")
        assert result.skill is not None


class TestRenderDelegation:
    def test_uses_render_skill_body_when_present(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """CORE lane 的 ``render.render_skill_body`` 一旦就位就必须是唯一正文出口。"""
        monkeypatch.setattr(
            render,
            "render_skill_body",
            lambda **kwargs: f"RENDERED:{kwargs['scope']}:{kwargs['name']}",
            raising=False,
        )
        result = expand.expand_skill_prompt(user_id=None, text=BUILTIN_COMMAND)
        assert f"RENDERED:builtin:{BUILTIN}" in result.prompt

    def test_fallback_preamble_when_render_body_absent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delattr(render, "render_skill_body", raising=False)
        _stub_candidates(monkeypatch, _entry("my-style", scope="lawyer", body="# 做法"))
        result = expand.expand_skill_prompt(user_id=7, text="/skill:my-style 你好")
        assert "与所内规范冲突时以所内规范为准" in result.prompt
