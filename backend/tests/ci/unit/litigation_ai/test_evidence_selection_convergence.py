"""安全审计（2026-10-19）：select_evidence 证据 ID 收敛到会话案件.

历史实现把客户端任意整数 evidence_item_ids / evidence_list_ids 未做归属校验
即写入会话元数据并透传 build_evidence_text 与 RAG aretrieve，可跨案件读取
他人证据.收敛入口在 ConversationFlowService.handle_evidence_selection
（converge_evidence_selection_to_case），下游只用收敛后的集合.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from apps.evidence.models import EvidenceItem, EvidenceList
from apps.litigation_ai.agent.tools import get_litigation_tools, search_evidence
from apps.litigation_ai.services.session.conversation_flow_service import converge_evidence_selection_to_case
from apps.testing.factories import CaseFactory


@pytest.mark.django_db
def test_cross_case_evidence_ids_dropped() -> None:
    """他人案件的 evidence/list id 被丢弃，只保留本会话案件的合法子集."""
    own_case = CaseFactory()
    other_case = CaseFactory()
    own_list = EvidenceList.objects.create(case=own_case)
    other_list = EvidenceList.objects.create(case=other_case)
    own_ids = [
        EvidenceItem.objects.create(evidence_list=own_list, name="我方证据A", purpose="证明目的A").id,
        EvidenceItem.objects.create(evidence_list=own_list, name="我方证据B", purpose="证明目的B").id,
    ]
    other_ids = [
        EvidenceItem.objects.create(evidence_list=other_list, name="他人证据A", purpose="他人证明A").id,
    ]

    with patch("apps.litigation_ai.services.session.conversation_flow_service.logger.warning") as mock_warn:
        list_ids, item_ids, our_ids, opponent_ids = converge_evidence_selection_to_case(
            own_case.id,
            [other_list.id, own_list.id],
            own_ids + other_ids,
            [own_ids[0], other_ids[0]],
            [other_ids[0], "not-an-int"],
        )

    # 他人案件的 id 全部被丢弃（含非整数垃圾值）
    assert item_ids == own_ids
    assert our_ids == [own_ids[0]]
    assert opponent_ids == []
    assert list_ids == [own_list.id]
    # 被丢弃的跨案件 id 记录 warning
    assert mock_warn.call_count == 2


def test_agent_tool_case_id_bound_to_session_case() -> None:
    """安全审计（2026-10-19）：工具 case_id 闭包绑定会话案件，忽略 LLM 填充值."""
    with patch("apps.litigation_ai.services.session.context_service.LitigationContextService") as mock_cls:
        mock_cls.return_value.get_case_info_for_agent.return_value = {"case_id": 42, "case_name": "会话案件"}
        tools = get_litigation_tools(42)
        tool = next(t for t in tools if t.name == "get_case_info")
        # LLM 在工具参数里填了他人案件 999，实际执行必须用闭包绑定的 42
        result = tool.invoke({"case_id": 999})

    assert result["case_id"] == 42
    mock_cls.return_value.get_case_info_for_agent.assert_called_once_with(42)
    # 无 case_id 参数的工具（search_evidence）原样返回
    assert any(t is search_evidence for t in tools)
