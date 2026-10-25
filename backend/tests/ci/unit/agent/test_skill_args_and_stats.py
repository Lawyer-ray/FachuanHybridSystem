"""rpc_client 技能参数拼装与水位解析单测（不拉子进程）。"""

from __future__ import annotations

from typing import Any

from apps.agent.pi.rpc_client import PiRpcSession, parse_context_usage


def _session(**kwargs: Any) -> PiRpcSession:
    kwargs.setdefault("cwd", "/tmp/work")
    kwargs.setdefault("extension_path", "/tmp/ext.ts")
    return PiRpcSession(**kwargs)


def _args(**kwargs: Any) -> list[str]:
    return _session(**kwargs)._build_args("/usr/local/bin/pi")


class TestSkillArgs:
    def test_no_skills_always_present(self) -> None:
        """宿主机用户级技能（~/.agents/skills 等）绝不能混进生产会话。"""
        args = _args()
        assert "--no-skills" in args
        assert not any(a.startswith("--skill") for a in args)

    def test_explicit_skills_appended_in_order(self) -> None:
        args = _args(skill_paths=["/srv/skills/web-research", "/srv/skills/list-projection"])
        assert "--no-skills" in args
        i1 = args.index("--skill")
        assert args[i1 + 1] == "/srv/skills/web-research"
        i2 = args.index("--skill", i1 + 1)
        assert args[i2 + 1] == "/srv/skills/list-projection"

    def test_empty_list_means_zero_skills(self) -> None:
        """空清单 = 显式零技能（update_or_create 恒定语义，不回落自动发现）。"""
        args = _args(skill_paths=[])
        assert "--no-skills" in args
        assert "--skill" not in args


class TestParseContextUsage:
    def test_happy_path(self) -> None:
        stats: dict[str, Any] = {
            "contextUsage": {"tokens": 12345, "contextWindow": 131072, "percent": 9.4}
        }
        assert parse_context_usage(stats) == (12345, 131072)

    def test_unknown_tokens_is_none_not_zero(self) -> None:
        """压缩刚结束、模型还没回过话时 pi 给 tokens=null——「不知道」不得伪装成 0。"""
        stats: dict[str, Any] = {"contextUsage": {"tokens": None, "contextWindow": 131072}}
        assert parse_context_usage(stats) == (None, 131072)

    def test_missing_context_usage(self) -> None:
        assert parse_context_usage({}) == (None, None)
        assert parse_context_usage({"contextUsage": "garbage"}) == (None, None)

    def test_non_numeric_rejected(self) -> None:
        stats: dict[str, Any] = {"contextUsage": {"tokens": "12k", "contextWindow": True}}
        assert parse_context_usage(stats) == (None, None)
