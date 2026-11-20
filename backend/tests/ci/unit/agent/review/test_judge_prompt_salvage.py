"""judge 输出被截断时，判定要能救回来；但**不许**救活协议偏离。

## 来历（真机实测）

第一次真实三栏评审：21 条判定里 **7 条 ``parse_failed``（33%）**，全部集中在长回答上。
原因是 judge 把解释写长、输出被 ``max_tokens`` 截断，JSON 缺右括号 → ``json.loads`` 失败
→ 整条判定丢掉。可判定本身往往写在最前面：

    {"criteria_met": true, "explanation": "……（被截断）

为一句解释丢掉整条判定，等于让"输出太长"变成"判不了"——在门禁里这会直接压掉有效票。

修法：整段解析失败时只捞 ``criteria_met`` 的**裸值**（true/false/null），
解释与证据留空；带引号的 ``"true"`` 属于协议偏离，**不救**；出现两个不同值算歧义，**不判**。
"""

from __future__ import annotations

import pytest

from apps.agent.services.review.judge_prompt import parse_verdict


class TestSalvageTruncatedVerdict:
    def test_truncated_true_is_recovered_without_guessy_explanation(self) -> None:
        parsed = parse_verdict('{"criteria_met": true, "explanation": "这条判定被截断在解释里')

        assert parsed.criteria_met is True
        assert parsed.explanation == "", "截断的解释不完整，留着会误导'为什么不过'"
        assert parsed.evidence_quote == ""

    def test_truncated_false_is_recovered(self) -> None:
        parsed = parse_verdict('{"criteria_met": false, "explanation": "没给出条款号')

        assert parsed.criteria_met is False

    def test_truncated_null_is_unjudgeable_not_false(self) -> None:
        parsed = parse_verdict('{"criteria_met": null, "explanation": "看不清')

        assert parsed.criteria_met is None
        assert parsed.scored is False, "null 是'判不了'，不能当作不通过进分母"

    def test_prose_around_json_is_tolerated(self) -> None:
        parsed = parse_verdict('我的判断如下：\n{"criteria_met": true, "explanation": "ok"}\n以上。')

        assert parsed.criteria_met is True


class TestSalvageMustNotRescueProtocolDeviation:
    @pytest.mark.parametrize(
        "text",
        [
            '{"criteria_met": "true", "explanation": "回答用了字符串',  # 带引号：协议偏离
            '{"criteria_met": 1, "explanation": "数字',
            'I think it meets the criterion.',  # 完全没有字段
            '{"explanation": "忘了给判定',
        ],
    )
    def test_not_scored_when_value_is_not_a_bare_boolean(self, text: str) -> None:
        parsed = parse_verdict(text)

        assert parsed.criteria_met is None
        assert parsed.unscored_reason == "parse_failed"

    def test_ambiguous_values_are_not_scored(self) -> None:
        """整段解析不了、又出现 true 与 false：宁可不判，不能猜它是哪一个。"""
        parsed = parse_verdict('criteria_met: true ... 结尾又写 criteria_met: false（JSON 已截断')

        assert parsed.criteria_met is None
        assert parsed.unscored_reason == "parse_failed"


class TestCompleteJsonStillWins:
    def test_full_json_keeps_explanation_and_evidence(self) -> None:
        parsed = parse_verdict(
            '{"criteria_met": true, "explanation": "给了条款号 7.2", "evidence_quote": "第 7.2 条"}'
        )

        assert parsed.criteria_met is True
        assert parsed.explanation == "给了条款号 7.2"
        assert parsed.evidence_quote == "第 7.2 条"
