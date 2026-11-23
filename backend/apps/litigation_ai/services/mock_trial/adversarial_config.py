"""多 Agent 对抗模式的用户配置文本解析.

S23-15（2026-11-23 二轮审计）：这类「把用户敲的几行中文文本解析成 AdversarialConfig」
原本是 `MockTrialFlowService._parse_adversarial_config`（50 行）长在状态机类里；
现独立成模块级纯函数，状态机只保留一行转发，便于单独阅读/修改解析规则。
"""

from __future__ import annotations

from .types import AdversarialConfig

ROLE_MAP: dict[str, str] = {"原告": "plaintiff", "被告": "defendant", "法官": "judge", "观看": "observer"}
LEVEL_MAP: dict[str, str] = {"一审": "first", "二审": "second"}


def parse_adversarial_config(text: str, models: list[str]) -> AdversarialConfig:
    """解析用户输入的配置文本（每行 `键: 值`，中英文冒号均可）。"""

    def resolve_model(val: str) -> str:
        val = val.strip()
        try:
            idx = int(val) - 1
            if 0 <= idx < len(models):
                return models[idx]
        except ValueError:
            pass
        # 直接用名称
        for m in models:
            if val.lower() in m.lower():
                return m
        return val

    config = AdversarialConfig()

    def _apply_rule(key: str, val: str) -> None:
        if "原告" in key and "模型" in key:
            config.plaintiff_model = resolve_model(val)
        elif "被告" in key and "模型" in key:
            config.defendant_model = resolve_model(val)
        elif "法官" in key and "模型" in key:
            config.judge_model = resolve_model(val)
        elif "轮数" in key:
            try:
                config.debate_rounds = max(3, int(val))
            except ValueError:
                pass
        elif "角色" in key:
            config.user_role = ROLE_MAP.get(val, "observer")
        elif "审级" in key:
            config.trial_level = LEVEL_MAP.get(val, "first")

    for line in text.split("\n"):
        line = line.strip()
        if ":" not in line and "：" not in line:
            continue
        key, _, val = line.replace("：", ":").partition(":")
        _apply_rule(key.strip(), val.strip())

    return config
