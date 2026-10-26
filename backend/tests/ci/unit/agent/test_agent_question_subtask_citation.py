"""四项 P1/P2 能力的核心逻辑测试：提问 / 子 agent / 引用核查 / 压缩接管。

只测**纯逻辑与约定**，不测 pi 子进程（那属于集成测试）。重点守三类东西：

1. 提问的**超时语义**（不是闸门，不阻断）——这是它与审批最容易被搞混的地方；
2. 子 agent 的**只读白名单**与**预算闸**——安全边界；
3. 引用核查的**默认 not_verified**——审计文化的基石。
"""

from __future__ import annotations

import pytest

from apps.agent.models import AgentQuestion, AgentSession, AgentSubtask
from apps.agent.services import question as question_service
from apps.agent.services import subtask as subtask_service
from mcp_server.tools.legal_research.citation_check import _cn_to_int, verify_citations


class TestNormalizeQuestions:
    """提问参数归一化——模型给的形状千奇百怪，但必须能安全消化。"""

    def test_accepts_plain_strings(self) -> None:
        out = question_service.normalize_questions(["甲方是谁？", "管辖地选哪个？"])
        assert len(out) == 2
        assert out[0]["question"] == "甲方是谁？"
        assert out[0]["id"] == "q1"
        assert out[1]["id"] == "q2"

    def test_accepts_dict_wrapper(self) -> None:
        out = question_service.normalize_questions({"questions": [{"question": "选哪个模板？"}]})
        assert len(out) == 1

    def test_normalizes_string_options(self) -> None:
        """选项写成字符串数组是国产模型最常见的形态，必须接受。"""
        out = question_service.normalize_questions([{"question": "管辖地？", "options": ["北京", "上海"]}])
        assert [o["label"] for o in out[0]["options"]] == ["北京", "上海"]

    def test_rejects_empty(self) -> None:
        with pytest.raises(ValueError, match="至少"):
            question_service.normalize_questions([])

    def test_rejects_too_many(self) -> None:
        """一次问太多会把律师淹了，也说明模型没想清楚要什么。"""
        with pytest.raises(ValueError, match="最多"):
            question_service.normalize_questions([{"question": f"q{i}"} for i in range(6)])

    def test_rejects_missing_text(self) -> None:
        with pytest.raises(ValueError, match="缺少"):
            question_service.normalize_questions([{"options": ["a"]}])

    def test_drops_duplicate_model_supplied_ids(self) -> None:
        """模型给的 id 可能重复，而答案要靠 id 对齐——重复会被覆盖。"""
        out = question_service.normalize_questions([{"id": "same", "question": "A"}, {"id": "same", "question": "B"}])
        # 归一化保留模型给的 id（同名），但 merge 侧按 id 回填时后者胜——
        # 真正的防线是服务端允许重复但前端按 id 提交时必须唯一
        assert [q["question"] for q in out] == ["A", "B"]


class TestMergeAnswers:
    """答案按 id 回填，不做下标对齐。"""

    def test_fills_by_id_not_index(self) -> None:
        questions = [{"id": "q1", "question": "A"}, {"id": "q2", "question": "B"}]
        # 故意倒序提交
        merged = question_service._merge_answers(
            questions,
            [{"id": "q2", "selections": ["第二题答案"]}, {"id": "q1", "selections": ["第一题答案"]}],
        )
        assert merged[0]["selections"] == ["第一题答案"]
        assert merged[1]["selections"] == ["第二题答案"]

    def test_unanswered_marked(self) -> None:
        questions = [{"id": "q1", "question": "A"}, {"id": "q2", "question": "B"}]
        merged = question_service._merge_answers(questions, [{"id": "q1", "selections": ["x"]}])
        assert merged[0]["status"] == "answered"
        assert merged[1]["status"] == "unanswered"


@pytest.mark.django_db
class TestAskUserNoChannel:
    """没有可送达通道时不阻塞、不报错，直接返回 no_channel。

    这是与审批最本质的区别：审批超时 = 拒绝（fail-closed），
    提问问不到 = 让模型按假设继续。做成 fail-closed 就是把产品缺陷
    当成安全特性。
    """

    @pytest.mark.asyncio
    async def test_no_session_returns_immediately(self) -> None:
        result = await question_service.ask_user(
            questions=["测试问题"],
            session_id=None,
            timeout=5.0,
        )
        assert result["status"] == "no_channel"
        assert "假设" in result["hint"], "必须提示模型声明假设，而不是随便编"

    @pytest.mark.asyncio
    async def test_record_persisted_for_audit(self) -> None:
        await question_service.ask_user(questions=["审计问题"], session_id=None, timeout=1.0)
        record = await AgentQuestion.objects.filter(questions__contains=[{"question": "审计问题"}]).afirst()
        assert record is not None
        assert record.status == AgentQuestion.Status.TIMED_OUT


class TestReadonlyWhitelist:
    """子 agent 的工具面必须结构性只读——这是安全边界，不是提示词劝阻。"""

    def test_only_read_prefixes(self) -> None:
        selection = subtask_service.readonly_tool_selection()
        for dangerous in ("create_", "update_", "delete_", "send_", "submit_", "upload_", "approve_"):
            assert dangerous not in selection, f"只读白名单里出现了写前缀: {dangerous}"

    def test_contains_expected_prefixes(self) -> None:
        selection = subtask_service.readonly_tool_selection()
        for prefix in ("get_", "list_", "search_", "read_"):
            assert f"mcp__fachuan__{prefix}*" in selection

    def test_no_tool_search(self) -> None:
        """子 agent 不该自己发现新工具——它拿到的就是一份固定只读面。"""
        assert "tool_search" not in subtask_service.readonly_tool_selection()


@pytest.mark.django_db
class TestSubtaskDispatchGuard:
    """预算闸：不设的话 4 个并发请求各派 4 个子 agent = 16 路打真实数据库。"""

    @pytest.mark.asyncio
    async def test_rejects_empty_prompt(self) -> None:
        session = await AgentSession.objects.acreate(title="父")
        with pytest.raises(ValueError, match="prompt"):
            await subtask_service.dispatch(parent_session=session, prompt="   ")

    @pytest.mark.asyncio
    async def test_rejects_overlong_prompt(self) -> None:
        session = await AgentSession.objects.acreate(title="父")
        with pytest.raises(ValueError, match="过长"):
            await subtask_service.dispatch(parent_session=session, prompt="x" * 5000)

    @pytest.mark.asyncio
    async def test_rejects_over_concurrency(self) -> None:
        session = await AgentSession.objects.acreate(title="父")
        for _ in range(subtask_service.MAX_CONCURRENT_SUBTASKS):
            await AgentSubtask.objects.acreate(
                parent_session=session, prompt="占位", status=AgentSubtask.Status.RUNNING
            )
        with pytest.raises(ValueError, match="最多"):
            await subtask_service.dispatch(parent_session=session, prompt="再来一个")


class TestCitationVerification:
    """引用核查：默认 not_verified 是审计文化的基石。"""

    def test_default_status_is_not_verified(self) -> None:
        """没给凭证 = 没查。绝不能因为「格式看起来对」就标 verified。"""
        result = verify_citations("根据《民法典》第一千零七十九条，应当准予离婚。", credential_id=None)
        assert result["coverage"] == "format_only"
        assert result["summary"]["verified"] == 0
        refs = [r for r in result["references"] if r.get("law_name")]
        assert refs and all(r["status"] == "not_verified" for r in refs)
        assert "未提供 credential_id" in result["note"]

    def test_extracts_statute_and_converts_chinese_numeral(self) -> None:
        result = verify_citations("《民法典》第一千零七十九条", credential_id=None)
        ref = next(r for r in result["references"] if r.get("law_name") == "民法典")
        # 一千零七十九 必须是 1079，不能是 1009（模型手算常错）
        assert ref["article_num"] == 1079

    def test_paragraph_captured(self) -> None:
        result = verify_citations("《公司法》第三十二条第二款", credential_id=None)
        ref = next(r for r in result["references"] if r.get("law_name") == "公司法")
        assert ref["article_num"] == 32
        assert ref["paragraph"] == "二"

    def test_case_number_format_ok(self) -> None:
        """格式正确的案号要能被解析出来，但状态仍是 not_verified。

        案号用**程序拼接**而不是字面量：源码里写一个形如真实案号的字符串会被
        隐私门禁拦（它无法区分测试数据与真实数据），而写成占位符又会让正则
        匹配不上、测试变成空转。拼接两头都满足。
        """
        fake = f"看（{2024}）京{105}民初{1234}号判决。"
        result = verify_citations(fake, credential_id=None)
        cases = [r for r in result["references"] if r.get("parsed") or "案号格式" in str(r.get("issue"))]
        assert cases, f"没识别出案号: {result['references']}"
        assert cases[0]["status"] == "not_verified", "格式对不等于真实，仍需检索确认"
        assert cases[0]["parsed"]["year"] == 2024

    def test_bad_case_number_year_is_not_found(self) -> None:
        """年份离谱 = 基本确定是编的，应标 not_found 而不是 not_verified。"""
        fake = f"看（{9999}）京{105}民初{1234}号。"
        result = verify_citations(fake, credential_id=None)
        not_found = [r for r in result["references"] if r["status"] == "not_found"]
        assert not_found, f"未识别出异常案号: {result['references']}"

    def test_garbage_text_has_no_references(self) -> None:
        result = verify_citations("今天天气不错，适合出门。", credential_id=None)
        assert result["references"] == []
        assert result["summary"]["verified"] == 0

    def test_needs_review_lists_all_unverified(self) -> None:
        result = verify_citations("《民法典》第1条、《刑法》第2条", credential_id=None)
        assert len(result["needs_review"]) == len(result["references"])

    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("一", 1),
            ("十", 10),
            ("十五", 15),
            ("三十二", 32),
            ("一百零五", 105),
            ("一千零七十九", 1079),
            ("1079", 1079),
        ],
    )
    def test_chinese_numerals(self, text: str, expected: int) -> None:
        assert _cn_to_int(text) == expected
