"""
GenerationService 单元测试

测试生成配置管理和任务创建功能。
"""

from unittest.mock import MagicMock, patch

import pytest
from django.utils import timezone

from apps.core.exceptions import NotFoundError, ValidationException
from apps.documents.models import (
    DocumentCaseStage,
    DocumentCaseType,
    DocumentTemplate,
    DocumentTemplateType,
    FolderTemplate,
    GenerationConfig,
    GenerationTask,
    GenerationTaskStatus,
)
from apps.documents.services.generation_service import GenerationService


@pytest.fixture
def generation_service():
    """创建 GenerationService 实例"""
    return GenerationService()


@pytest.fixture
def document_template(db):
    """创建测试用文书模板"""
    return DocumentTemplate.objects.create(
        name="测试起诉状模板",
        template_type=DocumentTemplateType.CASE,
        file_path="templates/complaint.docx",
        case_types=[DocumentCaseType.CIVIL],
        is_active=True,
    )


@pytest.fixture
def inactive_template(db):
    """创建禁用的文书模板"""
    return DocumentTemplate.objects.create(
        name="禁用模板",
        template_type=DocumentTemplateType.CONTRACT,
        file_path="templates/disabled.docx",
        is_active=False,
    )


@pytest.fixture
def folder_template(db):
    """创建测试用文件夹模板"""
    return FolderTemplate.objects.create(
        name="民事诉讼文件夹",
        template_type="case",
        case_types=[DocumentCaseType.CIVIL],
        case_stages=[DocumentCaseStage.FIRST_TRIAL],
        structure={"children": [{"id": "1", "name": "诉讼材料", "children": []}]},
        is_active=True,
    )


class TestGenerationConfigManagement:
    """生成配置管理测试"""

    def test_create_generation_config_success(self, generation_service, document_template, db):
        """测试成功创建生成配置"""
        config = generation_service.create_generation_config(
            name="起诉状配置",
            case_type=DocumentCaseType.CIVIL,
            case_stage=DocumentCaseStage.FIRST_TRIAL,
            document_template_id=document_template.id,
            folder_path="诉讼材料/起诉状",
            priority=10,
        )

        assert config.id is not None
        assert config.name == "起诉状配置"
        assert config.case_type == DocumentCaseType.CIVIL
        assert config.case_stage == DocumentCaseStage.FIRST_TRIAL
        assert config.document_template_id == document_template.id
        assert config.folder_path == "诉讼材料/起诉状"
        assert config.priority == 10
        assert config.is_active is True

    def test_create_generation_config_with_condition(self, generation_service, document_template, db):
        """测试创建带条件的生成配置"""
        condition = {"case_amount": {"$gt": 100000}}
        config = generation_service.create_generation_config(
            name="大额案件配置",
            case_type=DocumentCaseType.CIVIL,
            case_stage=DocumentCaseStage.FIRST_TRIAL,
            document_template_id=document_template.id,
            folder_path="诉讼材料",
            condition=condition,
        )

        assert config.condition == condition

    def test_create_generation_config_template_not_found(self, generation_service, db):
        """测试创建配置时模板不存在"""
        with pytest.raises(NotFoundError) as exc_info:
            generation_service.create_generation_config(
                name="测试配置",
                case_type=DocumentCaseType.CIVIL,
                case_stage=DocumentCaseStage.FIRST_TRIAL,
                document_template_id=99999,
                folder_path="诉讼材料",
            )

        assert "文书模板不存在" in str(exc_info.value)

    def test_create_generation_config_template_inactive(self, generation_service, inactive_template, db):
        """测试创建配置时模板已禁用"""
        with pytest.raises(ValidationException) as exc_info:
            generation_service.create_generation_config(
                name="测试配置",
                case_type=DocumentCaseType.CIVIL,
                case_stage=DocumentCaseStage.FIRST_TRIAL,
                document_template_id=inactive_template.id,
                folder_path="诉讼材料",
            )

        assert "已禁用" in str(exc_info.value)

    def test_create_generation_config_empty_folder_path(self, generation_service, document_template, db):
        """测试创建配置时文件夹路径为空"""
        with pytest.raises(ValidationException) as exc_info:
            generation_service.create_generation_config(
                name="测试配置",
                case_type=DocumentCaseType.CIVIL,
                case_stage=DocumentCaseStage.FIRST_TRIAL,
                document_template_id=document_template.id,
                folder_path="   ",
            )

        assert "不能为空" in str(exc_info.value)

    def test_update_generation_config(self, generation_service, document_template, db):
        """测试更新生成配置"""
        config = generation_service.create_generation_config(
            name="原始配置",
            case_type=DocumentCaseType.CIVIL,
            case_stage=DocumentCaseStage.FIRST_TRIAL,
            document_template_id=document_template.id,
            folder_path="诉讼材料",
            priority=5,
        )

        updated = generation_service.update_generation_config(
            config_id=config.id,
            name="更新后配置",
            priority=20,
        )

        assert updated.name == "更新后配置"
        assert updated.priority == 20
        assert updated.folder_path == "诉讼材料"  # 未更新的字段保持不变

    def test_get_configs_for_case_priority_order(self, generation_service, document_template, db):
        """测试获取配置按优先级排序"""
        # 创建多个配置，优先级不同
        generation_service.create_generation_config(
            name="低优先级",
            case_type=DocumentCaseType.CIVIL,
            case_stage=DocumentCaseStage.FIRST_TRIAL,
            document_template_id=document_template.id,
            folder_path="path1",
            priority=1,
        )
        generation_service.create_generation_config(
            name="高优先级",
            case_type=DocumentCaseType.CIVIL,
            case_stage=DocumentCaseStage.FIRST_TRIAL,
            document_template_id=document_template.id,
            folder_path="path2",
            priority=100,
        )
        generation_service.create_generation_config(
            name="中优先级",
            case_type=DocumentCaseType.CIVIL,
            case_stage=DocumentCaseStage.FIRST_TRIAL,
            document_template_id=document_template.id,
            folder_path="path3",
            priority=50,
        )

        configs = generation_service.get_configs_for_case(
            case_type=DocumentCaseType.CIVIL,
            case_stage=DocumentCaseStage.FIRST_TRIAL,
        )

        assert len(configs) == 3
        assert configs[0].name == "高优先级"
        assert configs[1].name == "中优先级"
        assert configs[2].name == "低优先级"

    def test_get_configs_for_case_excludes_inactive(self, generation_service, document_template, db):
        """测试获取配置默认排除禁用的"""
        generation_service.create_generation_config(
            name="启用配置",
            case_type=DocumentCaseType.CIVIL,
            case_stage=DocumentCaseStage.FIRST_TRIAL,
            document_template_id=document_template.id,
            folder_path="path1",
            is_active=True,
        )
        generation_service.create_generation_config(
            name="禁用配置",
            case_type=DocumentCaseType.CIVIL,
            case_stage=DocumentCaseStage.FIRST_TRIAL,
            document_template_id=document_template.id,
            folder_path="path2",
            is_active=False,
        )

        configs = generation_service.get_configs_for_case(
            case_type=DocumentCaseType.CIVIL,
            case_stage=DocumentCaseStage.FIRST_TRIAL,
        )

        assert len(configs) == 1
        assert configs[0].name == "启用配置"

    def test_validate_config_references_valid(self, generation_service, document_template, db):
        """测试验证有效的配置引用"""
        config = generation_service.create_generation_config(
            name="测试配置",
            case_type=DocumentCaseType.CIVIL,
            case_stage=DocumentCaseStage.FIRST_TRIAL,
            document_template_id=document_template.id,
            folder_path="诉讼材料",
        )

        is_valid, error = generation_service.validate_config_references(config)

        assert is_valid is True
        assert error == ""

    def test_validate_config_references_template_deleted(self, generation_service, document_template, db):
        """测试验证引用已删除模板的配置"""
        config = generation_service.create_generation_config(
            name="测试配置",
            case_type=DocumentCaseType.CIVIL,
            case_stage=DocumentCaseStage.FIRST_TRIAL,
            document_template_id=document_template.id,
            folder_path="诉讼材料",
        )

        # 删除模板
        document_template.delete()

        is_valid, error = generation_service.validate_config_references(config)

        assert is_valid is False
        assert "不存在" in error

    def test_delete_generation_config_soft_delete(self, generation_service, document_template, db):
        """测试软删除生成配置"""
        config = generation_service.create_generation_config(
            name="待删除配置",
            case_type=DocumentCaseType.CIVIL,
            case_stage=DocumentCaseStage.FIRST_TRIAL,
            document_template_id=document_template.id,
            folder_path="诉讼材料",
        )

        result = generation_service.delete_generation_config(config.id)

        assert result is True

        # 验证是软删除
        config.refresh_from_db()
        assert config.is_active is False


class TestTaskManagement:
    """任务管理测试"""

    def test_create_task_success(self, generation_service, folder_template, db):
        """测试成功创建任务"""
        task = generation_service.create_task(
            folder_template_id=folder_template.id,
            output_path="/output/test",
        )

        assert task.id is not None
        assert task.status == GenerationTaskStatus.PENDING
        assert task.folder_template_id == folder_template.id
        assert task.output_path == "/output/test"
        assert task.generated_files == []
        assert task.error_logs == []

    def test_create_task_without_references(self, generation_service, db):
        """测试创建不带引用的任务"""
        task = generation_service.create_task()

        assert task.id is not None
        assert task.case is None
        assert task.folder_template_id is None

    def test_create_task_folder_template_not_found(self, generation_service, db):
        """测试创建任务时文件夹模板不存在"""
        with pytest.raises(NotFoundError) as exc_info:
            generation_service.create_task(folder_template_id=99999)

        assert "文件夹模板不存在" in str(exc_info.value)

    def test_update_task_status_to_processing(self, generation_service, db):
        """测试更新任务状态为处理中"""
        task = generation_service.create_task()

        updated = generation_service.update_task_status(task.id, GenerationTaskStatus.PROCESSING)

        assert updated.status == GenerationTaskStatus.PROCESSING
        assert updated.completed_at is None

    def test_update_task_status_to_completed(self, generation_service, db):
        """测试更新任务状态为已完成"""
        task = generation_service.create_task()

        updated = generation_service.update_task_status(task.id, GenerationTaskStatus.COMPLETED)

        assert updated.status == GenerationTaskStatus.COMPLETED
        assert updated.completed_at is not None

    def test_update_task_status_to_failed_with_error(self, generation_service, db):
        """测试更新任务状态为失败并记录错误"""
        task = generation_service.create_task()

        updated = generation_service.update_task_status(
            task.id,
            GenerationTaskStatus.FAILED,
            error_message="模板文件不存在",
        )

        assert updated.status == GenerationTaskStatus.FAILED
        assert updated.completed_at is not None
        assert len(updated.error_logs) == 1
        assert "模板文件不存在" in updated.error_logs[0]["message"]

    def test_update_task_status_invalid_status(self, generation_service, db):
        """测试更新任务为无效状态"""
        task = generation_service.create_task()

        with pytest.raises(ValidationException) as exc_info:
            generation_service.update_task_status(task.id, "invalid_status")

        assert "无效的任务状态" in str(exc_info.value)

    def test_add_generated_file(self, generation_service, db):
        """测试添加生成的文件记录"""
        task = generation_service.create_task()

        updated = generation_service.add_generated_file(
            task.id,
            file_path="/output/complaint.docx",
            file_name="起诉状.docx",
        )

        assert len(updated.generated_files) == 1
        assert updated.generated_files[0]["path"] == "/output/complaint.docx"
        assert updated.generated_files[0]["name"] == "起诉状.docx"

    def test_add_error_log(self, generation_service, db):
        """测试添加错误日志"""
        task = generation_service.create_task()

        updated = generation_service.add_error_log(
            task.id,
            error_message="占位符 case_name 未定义",
            error_type="warning",
        )

        assert len(updated.error_logs) == 1
        assert updated.error_logs[0]["message"] == "占位符 case_name 未定义"
        assert updated.error_logs[0]["type"] == "warning"

    def test_list_tasks_by_status(self, generation_service, db):
        """测试按状态列出任务"""
        # 创建不同状态的任务
        task1 = generation_service.create_task()
        task2 = generation_service.create_task()
        generation_service.update_task_status(task2.id, GenerationTaskStatus.COMPLETED)

        pending_tasks = generation_service.list_tasks(status=GenerationTaskStatus.PENDING)
        completed_tasks = generation_service.list_tasks(status=GenerationTaskStatus.COMPLETED)

        assert len(pending_tasks) == 1
        assert pending_tasks[0].id == task1.id
        assert len(completed_tasks) == 1
        assert completed_tasks[0].id == task2.id

    def test_generate_requires_case(self, generation_service, db):
        """测试 generate 方法要求关联案件"""
        task = generation_service.create_task()

        with pytest.raises(ValidationException) as exc_info:
            generation_service.generate(task)

        assert "任务未关联案件" in str(exc_info.value)
