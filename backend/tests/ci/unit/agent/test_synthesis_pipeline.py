"""综合流水线：取消必须一路上抛；普通失败才降级（评审 / 写转录）。

评审 🔴4 的回归：前置评审与写转录两处用宽口径 except 做"失败不阻断"，旧实现只放行
``KeyboardInterrupt`` / ``SystemExit`` / ``GeneratorExit``，``asyncio.CancelledError``
被当普通失败吞掉——用户点了取消，评审 / 综合照样跑完、照样花钱。

全部依赖打桩：不联网、不起 agent、不读库。
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest

from apps.agent.services.chat.aggregate import Candidate
from apps.agent.services.synthesis import pipeline
from apps.agent.services.synthesis.pipeline import NoUsableCandidatesError, SynthesisRequest

_SESSION = SimpleNamespace(session_id="00000000-0000-0000-0000-0000000000aa")


def _install_happy_path(monkeypatch: pytest.MonkeyPatch, calls: dict[str, Any]) -> None:
    """流水线的每个外部依赖都换成桩，``calls`` 记录它们收到的参数。"""

    async def fake_load(session: Any, turn: int, lanes: Any) -> tuple[str, list[Candidate]]:
        return "问题", [Candidate(lane="pi", model="m1", text="甲方违约[来源：pi]"), Candidate(lane="dsh", model="m2", text="乙")]

    async def fake_resolve(session: Any, turn: int, requested: str) -> str:
        return "m1"

    async def fake_agent(**kwargs: Any) -> Any:
        calls["agent"] = kwargs
        return SimpleNamespace(text="结论[来源：pi]", model="m1")

    async def fake_verify(**kwargs: Any) -> tuple[list[str], str]:
        calls["verify"] = kwargs
        return [], ""

    async def fake_save(*, session: Any, user_id: Any, synthesis: Any) -> Any:
        calls["saved"] = synthesis
        return SimpleNamespace(synthesis_id=synthesis.synthesis_id)

    async def fake_message(*, session: Any, synthesis: Any) -> None:
        calls["message"] = synthesis

    monkeypatch.setattr(pipeline, "load_turn_candidates", fake_load)
    monkeypatch.setattr(pipeline, "resolve_model", fake_resolve)
    monkeypatch.setattr(pipeline, "run_synthesis_agent", fake_agent)
    monkeypatch.setattr(pipeline, "verify_synthesis_citations", fake_verify)
    monkeypatch.setattr(pipeline, "save_synthesis", fake_save)
    monkeypatch.setattr(pipeline, "save_synthesis_message", fake_message)


async def _run(request: SynthesisRequest, stages: list[str] | None = None) -> Any:
    async def on_stage(stage: str) -> None:
        if stages is not None:
            stages.append(stage)

    return await pipeline.run_synthesis_pipeline(
        session=_SESSION, user_id=7, user=SimpleNamespace(pk=7), request=request, run_id="run-xyz", on_stage=on_stage
    )


@pytest.mark.asyncio
async def test_pipeline_passes_run_id_user_and_reports_stages(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict[str, Any] = {}
    _install_happy_path(monkeypatch, calls)
    stages: list[str] = []

    record = await _run(SynthesisRequest(turn=2, lanes=["pi", "dsh"], kind="pi", review=False, credential_id=5), stages)

    assert record.synthesis_id == calls["saved"].synthesis_id
    # 关掉评审时不进 review 阶段；其余三段按顺序上报（前端据此显示进度）
    assert stages == ["synthesis", "verify", "saving"]
    # run_id 由任务层给（按任务唯一），流水线原样传给 agent
    assert calls["agent"]["run_id"] == "run-xyz"
    assert calls["agent"]["model"] == "m1"
    # 核验拿的是后台重新加载的用户，不是 HTTP 请求对象
    assert calls["verify"]["user"].pk == 7
    assert calls["verify"]["credential_id"] == 5
    assert calls["saved"].lanes_used == ["pi", "dsh"]
    assert calls["message"].synthesis_id == calls["saved"].synthesis_id


@pytest.mark.asyncio
async def test_pipeline_rejects_turn_without_usable_candidates(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict[str, Any] = {}
    _install_happy_path(monkeypatch, calls)

    async def all_failed(session: Any, turn: int, lanes: Any) -> tuple[str, list[Candidate]]:
        return "问题", [Candidate(lane="pi", model="", text=None), Candidate(lane="dsh", model="", text="  ")]

    monkeypatch.setattr(pipeline, "load_turn_candidates", all_failed)

    with pytest.raises(NoUsableCandidatesError):
        await _run(SynthesisRequest(turn=1, lanes=["pi", "dsh"], review=False))
    assert "agent" not in calls, "没有可综合的候选时不能调模型"


@pytest.mark.asyncio
async def test_transcript_write_failure_degrades_but_cancellation_propagates(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict[str, Any] = {}
    _install_happy_path(monkeypatch, calls)

    async def broken_message(**_kwargs: Any) -> None:
        raise RuntimeError("db down")

    monkeypatch.setattr(pipeline, "save_synthesis_message", broken_message)
    record = await _run(SynthesisRequest(turn=1, lanes=["pi"], review=False))
    assert record.synthesis_id == calls["saved"].synthesis_id, "写转录失败只降级，快照照常返回"

    async def cancelled_message(**_kwargs: Any) -> None:
        raise asyncio.CancelledError

    monkeypatch.setattr(pipeline, "save_synthesis_message", cancelled_message)
    with pytest.raises(asyncio.CancelledError):
        await _run(SynthesisRequest(turn=1, lanes=["pi"], review=False))


def _install_review_stubs(monkeypatch: pytest.MonkeyPatch, run_jury: Any) -> None:
    from apps.agent.services.review import judge_models, jury, rubric
    from apps.agent.services.review import store as review_store

    async def fake_answers(session: Any, turn: int, lanes: Any) -> tuple[str, dict[str, str]]:
        return "问题", {"pi": "甲"}

    async def fake_models(session: Any, turn: int, lanes: Any) -> list[str]:
        return ["judge-a"]

    monkeypatch.setattr(rubric, "load_rubric", lambda _rubric_id: [])
    monkeypatch.setattr(review_store, "load_turn_answers", fake_answers)
    monkeypatch.setattr(review_store, "load_turn_models", fake_models)
    monkeypatch.setattr(judge_models, "configured_judge_models", lambda: ["judge-a"])
    monkeypatch.setattr(judge_models, "resolve_judge_models", lambda **_kwargs: ["judge-a"])
    monkeypatch.setattr(jury, "run_jury", run_jury)


@pytest.mark.asyncio
async def test_review_failure_degrades_to_empty_summary(monkeypatch: pytest.MonkeyPatch) -> None:
    async def broken_jury(**_kwargs: Any) -> Any:
        raise RuntimeError("judge 超时")

    _install_review_stubs(monkeypatch, broken_jury)
    summary = await pipeline.run_review_summary(session=_SESSION, user_id=1, turn=1, lanes=["pi"])
    assert summary == ""


@pytest.mark.asyncio
async def test_review_cancellation_propagates(monkeypatch: pytest.MonkeyPatch) -> None:
    """旧实现把这里的 CancelledError 吞掉并返回空串，综合随后照跑。"""

    async def cancelled_jury(**_kwargs: Any) -> Any:
        raise asyncio.CancelledError

    _install_review_stubs(monkeypatch, cancelled_jury)
    with pytest.raises(asyncio.CancelledError):
        await pipeline.run_review_summary(session=_SESSION, user_id=1, turn=1, lanes=["pi"])


def test_request_params_round_trip() -> None:
    request = SynthesisRequest(turn=3, lanes=["pi", "dsh"], model="glm53", kind="claude-agent", review=False, credential_id=9)
    assert SynthesisRequest.from_params(3, request.to_params()) == request
    # 老任务 / 缺字段时按默认值回放
    assert SynthesisRequest.from_params(1, {}) == SynthesisRequest(turn=1, lanes=[])
