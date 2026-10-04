"""legal_solution.tasks 真 async 化后的任务体测试。

覆盖：
- 入口 run_solution_task 经统一桥接（run_coro_sync）消费协程；
- async 任务体在真实事件循环中用 aget/asave/acount 走通全流程（阶段2/3 由
  既有 research_task + COMPLETED 状态短路，阶段4/5 的重 sync 服务打桩）；
- 异常路径回写 FAILED。
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from apps.legal_solution.models import SolutionTask, SolutionTaskStatus


@pytest.fixture
def solution_fixtures(db):
    from apps.legal_research.models import LegalResearchTask, LegalResearchTaskStatus
    from apps.legal_solution.models import SolutionTask as SolutionTaskModel
    from apps.organization.models import AccountCredential, Lawyer

    lawyer = Lawyer.objects.create_user(username="solution-task-lawyer", email="stl@example.com")
    credential = AccountCredential.objects.create(
        lawyer=lawyer,
        site_name="wkxx",
        account="acct",
        password="pwd",
    )
    research = LegalResearchTask.objects.create(
        credential=credential,
        keyword="工伤认定",
        case_summary="案情简述",
        status=LegalResearchTaskStatus.COMPLETED,
    )
    task = SolutionTaskModel.objects.create(
        case_summary="超龄劳动者工伤认定争议",
        keyword="工伤认定",
        credential=credential,
        research_task=research,
        llm_model="test-model",
    )
    return task


class TestRunSolutionTaskEntry:
    def test_entry_delegates_to_bridge(self):
        """Django-Q 入口是 sync 函数，经 run_coro_sync 消费 async 任务体。"""
        from apps.legal_solution import tasks as tasks_module

        def _swallow(coro, **kwargs):
            coro.close()
            return {"task_id": 1, "status": "completed"}

        with patch.object(tasks_module, "run_coro_sync", side_effect=_swallow) as mock_bridge:
            result = tasks_module.run_solution_task(1)

        assert result == {"task_id": 1, "status": "completed"}
        mock_bridge.assert_called_once()
        assert mock_bridge.call_args.kwargs["thread_name_prefix"] == "legal-solution"


# async ORM 经 asgiref 线程敏感执行器跑在与测试线程不同的连接上，
# 需要 transaction=True 让 fixture 数据真实提交可见（同 test_cloud_storage_account_service 模式）。
@pytest.mark.django_db(transaction=True)
class TestRunSolutionTaskAsync:
    @pytest.mark.asyncio
    @pytest.mark.django_db(transaction=True)
    async def test_full_flow_uses_async_orm(self, solution_fixtures: SolutionTask):
        """真 async 断言：任务体直接 await，ORM 全程 async（aget/asave/acount）。"""
        from apps.legal_solution import tasks as tasks_module
        from apps.legal_solution.services.html_renderer import HtmlRenderer
        from apps.legal_solution.services.solution_generator import SolutionGenerator

        with (
            patch("apps.legal_solution.services.solution_generator.SolutionGenerator") as MockGen,
            patch("apps.legal_solution.services.html_renderer.HtmlRenderer") as MockRenderer,
        ):
            mock_gen = MockGen.return_value
            mock_gen.generate.return_value = None
            MockRenderer.return_value.render.return_value = "<p>方案</p>"

            result = await tasks_module._run_solution_task_async(solution_fixtures.id)

        assert result == {"task_id": solution_fixtures.id, "status": SolutionTaskStatus.COMPLETED}
        mock_gen.generate.assert_called_once()
        # generate 在 to_thread 中被调用，参数即同一个 SolutionTask
        assert mock_gen.generate.call_args.args[0].id == solution_fixtures.id

        await solution_fixtures.arefresh_from_db()
        assert solution_fixtures.status == SolutionTaskStatus.COMPLETED
        assert solution_fixtures.progress == 100
        assert solution_fixtures.html_content == "<p>方案</p>"
        assert solution_fixtures.started_at is not None
        assert solution_fixtures.finished_at is not None

    @pytest.mark.asyncio
    @pytest.mark.django_db(transaction=True)
    async def test_failure_marks_task_failed(self, solution_fixtures: SolutionTask):
        from apps.legal_solution import tasks as tasks_module
        from apps.legal_solution.services.html_renderer import HtmlRenderer
        from apps.legal_solution.services.solution_generator import SolutionGenerator

        with (
            patch("apps.legal_solution.services.solution_generator.SolutionGenerator") as MockGen,
            patch("apps.legal_solution.services.html_renderer.HtmlRenderer") as MockRenderer,
        ):
            MockGen.return_value.generate.return_value = None
            MockRenderer.return_value.render.side_effect = RuntimeError("渲染崩溃")

            result = await tasks_module._run_solution_task_async(solution_fixtures.id)

        assert result["status"] == "failed"
        assert "渲染崩溃" in result["error"]
        await solution_fixtures.arefresh_from_db()
        assert solution_fixtures.status == SolutionTaskStatus.FAILED
        assert solution_fixtures.error == "渲染崩溃"

    @pytest.mark.asyncio
    @pytest.mark.django_db(transaction=True)
    async def test_partial_when_section_failed(self, solution_fixtures: SolutionTask):
        """存在失败段落时最终状态应为 PARTIAL（acount 真实查询）。"""
        from apps.legal_solution.models import SectionStatus, SolutionSection

        await SolutionSection.objects.acreate(
            task=solution_fixtures,
            section_type="case_analysis",
            title="案情分析",
            status=SectionStatus.FAILED,
        )

        from apps.legal_solution import tasks as tasks_module
        from apps.legal_solution.services.html_renderer import HtmlRenderer
        from apps.legal_solution.services.solution_generator import SolutionGenerator

        with (
            patch("apps.legal_solution.services.solution_generator.SolutionGenerator") as MockGen,
            patch("apps.legal_solution.services.html_renderer.HtmlRenderer") as MockRenderer,
        ):
            MockGen.return_value.generate.return_value = None
            MockRenderer.return_value.render.return_value = "<p>方案</p>"
            result = await tasks_module._run_solution_task_async(solution_fixtures.id)

        assert result["status"] == SolutionTaskStatus.PARTIAL
        await solution_fixtures.arefresh_from_db()
        assert solution_fixtures.status == SolutionTaskStatus.PARTIAL
        assert "1 段失败" in solution_fixtures.message

    def test_sync_entry_runs_async_body_end_to_end(self, solution_fixtures: SolutionTask):
        """sync 入口（Django-Q 调用形态）端到端：桥接真实消费 async 任务体。"""
        from apps.legal_solution import tasks as tasks_module
        from apps.legal_solution.services.html_renderer import HtmlRenderer
        from apps.legal_solution.services.solution_generator import SolutionGenerator

        with (
            patch("apps.legal_solution.services.solution_generator.SolutionGenerator") as MockGen,
            patch("apps.legal_solution.services.html_renderer.HtmlRenderer") as MockRenderer,
        ):
            MockGen.return_value.generate.return_value = None
            MockRenderer.return_value.render.return_value = "<p>方案</p>"
            result = tasks_module.run_solution_task(solution_fixtures.id)

        assert result["status"] == SolutionTaskStatus.COMPLETED
        solution_fixtures.refresh_from_db()
        assert solution_fixtures.status == SolutionTaskStatus.COMPLETED


class TestModuleContract:
    def test_no_allow_async_unsafe_import_left(self):
        """async 化后任务模块不应再引用 allow_async_unsafe。"""
        from apps.legal_solution import tasks as tasks_module

        assert not hasattr(tasks_module, "allow_async_unsafe")
