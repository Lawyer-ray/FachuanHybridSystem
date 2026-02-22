"""
FolderTemplateService 单元测试

测试文件夹模板服务的核心功能：
- 结构验证（循环引用检测、无效字符检测）
- 模板 CRUD 操作
- 模板查询逻辑

Requirements: 1.2, 1.4, 1.7, 1.8
"""

import pytest
from django.test import TestCase

from apps.core.dependencies.documents_query import build_folder_template_service
from apps.core.exceptions import NotFoundError, ValidationException
from apps.documents.models import DocumentCaseStage, DocumentCaseType, FolderTemplate
from apps.documents.services import FolderTemplateService


class TestFolderTemplateServiceValidation(TestCase):
    """测试文件夹结构验证功能"""

    def setUp(self) -> None:
        self.service = build_folder_template_service()  # type: ignore[func-returns-value]

    def test_validate_valid_structure(self):
        """测试有效结构验证通过"""
        structure = {
            "children": [
                {"id": "1", "name": "诉讼材料", "children": [{"id": "1-1", "name": "起诉状", "children": []}]},
                {"id": "2", "name": "证据材料", "children": []},
            ]
        }
        is_valid, msg = self.service.validate_structure(structure)
        self.assertTrue(is_valid)
        self.assertEqual(msg, "")

    def test_validate_empty_structure(self):
        """测试空结构验证通过"""
        structure: dict[str, list[str]] = {"children": []}
        is_valid, msg = self.service.validate_structure(structure)
        self.assertTrue(is_valid)

    def test_validate_invalid_chars_slash(self):
        """测试检测斜杠无效字符 - Requirements 1.8"""
        structure = {"children": [{"id": "1", "name": "诉讼/材料", "children": []}]}
        is_valid, msg = self.service.validate_structure(structure)
        self.assertFalse(is_valid)
        self.assertIn("无效字符", msg)

    def test_validate_invalid_chars_backslash(self):
        """测试检测反斜杠无效字符"""
        structure = {"children": [{"id": "1", "name": "诉讼\\材料", "children": []}]}
        is_valid, msg = self.service.validate_structure(structure)
        self.assertFalse(is_valid)
        self.assertIn("无效字符", msg)

    def test_validate_invalid_chars_colon(self):
        """测试检测冒号无效字符"""
        structure = {"children": [{"id": "1", "name": "诉讼:材料", "children": []}]}
        is_valid, msg = self.service.validate_structure(structure)
        self.assertFalse(is_valid)
        self.assertIn("无效字符", msg)

    def test_validate_invalid_chars_asterisk(self):
        """测试检测星号无效字符"""
        structure = {"children": [{"id": "1", "name": "诉讼*材料", "children": []}]}
        is_valid, msg = self.service.validate_structure(structure)
        self.assertFalse(is_valid)
        self.assertIn("无效字符", msg)

    def test_validate_circular_reference(self):
        """测试检测循环引用 - Requirements 1.2"""
        structure = {
            "children": [
                {"id": "1", "name": "文件夹A", "children": [{"id": "1", "name": "文件夹A重复", "children": []}]}
            ]
        }
        is_valid, msg = self.service.validate_structure(structure)
        self.assertFalse(is_valid)
        self.assertIn("循环引用", msg)

    def test_validate_nested_circular_reference(self):
        """测试检测嵌套循环引用"""
        structure = {
            "children": [
                {
                    "id": "1",
                    "name": "A",
                    "children": [{"id": "2", "name": "B", "children": [{"id": "1", "name": "A循环", "children": []}]}],
                }
            ]
        }
        is_valid, msg = self.service.validate_structure(structure)
        self.assertFalse(is_valid)
        self.assertIn("循环引用", msg)

    def test_validate_non_dict_structure(self):
        """测试非字典结构验证失败"""
        is_valid, msg = self.service.validate_structure("invalid")
        self.assertFalse(is_valid)
        self.assertIn("字典类型", msg)


class TestFolderTemplateServiceCRUD(TestCase):
    """测试文件夹模板 CRUD 操作"""

    def setUp(self) -> None:
        self.service = build_folder_template_service()  # type: ignore[func-returns-value]
        self.valid_structure = {"children": [{"id": "1", "name": "诉讼材料", "children": []}]}

    def test_create_template_success(self):
        """测试成功创建模板"""
        template = self.service.create_template(
            name="测试模板",
            case_type=DocumentCaseType.CIVIL,
            case_stage=DocumentCaseStage.FIRST_TRIAL,
            structure=self.valid_structure,
        )

        self.assertIsNotNone(template.id)
        self.assertEqual(template.name, "测试模板")
        self.assertEqual(template.case_type, DocumentCaseType.CIVIL)
        self.assertEqual(template.structure, self.valid_structure)

    def test_create_template_with_invalid_structure(self):
        """测试创建模板时验证失败"""
        invalid_structure = {"children": [{"id": "1", "name": "无效/名称", "children": []}]}

        with self.assertRaises(ValidationException):
            self.service.create_template(
                name="测试模板",
                case_type=DocumentCaseType.CIVIL,
                case_stage=DocumentCaseStage.FIRST_TRIAL,
                structure=invalid_structure,
            )

    def test_update_structure_success(self):
        """测试成功更新结构"""
        template = self.service.create_template(
            name="测试模板",
            case_type=DocumentCaseType.CIVIL,
            case_stage=DocumentCaseStage.FIRST_TRIAL,
            structure=self.valid_structure,
        )

        new_structure = {"children": [{"id": "1", "name": "新文件夹", "children": []}]}

        updated = self.service.update_structure(template.id, new_structure)
        self.assertEqual(updated.structure, new_structure)

    def test_update_structure_not_found(self):
        """测试更新不存在的模板"""
        with self.assertRaises(NotFoundError):
            self.service.update_structure(99999, self.valid_structure)

    def test_get_template_by_id(self):
        """测试根据 ID 获取模板"""
        template = self.service.create_template(
            name="测试模板",
            case_type=DocumentCaseType.CIVIL,
            case_stage=DocumentCaseStage.FIRST_TRIAL,
            structure=self.valid_structure,
        )

        found = self.service.get_template_by_id(template.id)
        self.assertEqual(found.id, template.id)

    def test_get_template_by_id_not_found(self):
        """测试获取不存在的模板"""
        with self.assertRaises(NotFoundError):
            self.service.get_template_by_id(99999)

    def test_delete_template_soft_delete(self):
        """测试软删除模板"""
        template = self.service.create_template(
            name="测试模板",
            case_type=DocumentCaseType.CIVIL,
            case_stage=DocumentCaseStage.FIRST_TRIAL,
            structure=self.valid_structure,
        )

        result = self.service.delete_template(template.id)
        self.assertTrue(result)

        # 验证软删除
        template.refresh_from_db()
        self.assertFalse(template.is_active)


class TestFolderTemplateServiceQuery(TestCase):
    """测试文件夹模板查询功能"""

    def setUp(self) -> None:
        self.service = build_folder_template_service()  # type: ignore[func-returns-value]
        self.valid_structure: dict[str, list[str]] = {"children": []}

    def test_get_template_for_case_returns_latest(self):
        """测试获取最新更新的模板 - Requirements 1.4"""
        # 创建两个相同类型的模板
        template1 = self.service.create_template(  # noqa: F841
            name="模板1",
            case_type=DocumentCaseType.CIVIL,
            case_stage=DocumentCaseStage.FIRST_TRIAL,
            structure=self.valid_structure,
        )

        template2 = self.service.create_template(
            name="模板2",
            case_type=DocumentCaseType.CIVIL,
            case_stage=DocumentCaseStage.FIRST_TRIAL,
            structure=self.valid_structure,
        )

        # 应该返回最新创建的模板2
        found = self.service.get_template_for_case(DocumentCaseType.CIVIL, DocumentCaseStage.FIRST_TRIAL)

        self.assertEqual(found.id, template2.id)

    def test_get_template_for_case_excludes_inactive(self):
        """测试查询排除非活跃模板"""
        template = self.service.create_template(  # noqa: F841
            name="模板",
            case_type=DocumentCaseType.CIVIL,
            case_stage=DocumentCaseStage.FIRST_TRIAL,
            structure=self.valid_structure,
            is_active=False,
        )

        found = self.service.get_template_for_case(DocumentCaseType.CIVIL, DocumentCaseStage.FIRST_TRIAL)

        self.assertIsNone(found)

    def test_get_template_for_case_no_match(self):
        """测试无匹配模板返回 None"""
        found = self.service.get_template_for_case(DocumentCaseType.CRIMINAL, DocumentCaseStage.SECOND_TRIAL)

        self.assertIsNone(found)

    def test_list_templates_filter_by_case_type(self):
        """测试按案件类型过滤"""
        self.service.create_template(
            name="民事模板",
            case_type=DocumentCaseType.CIVIL,
            case_stage=DocumentCaseStage.FIRST_TRIAL,
            structure=self.valid_structure,
        )

        self.service.create_template(
            name="刑事模板",
            case_type=DocumentCaseType.CRIMINAL,
            case_stage=DocumentCaseStage.FIRST_TRIAL,
            structure=self.valid_structure,
        )

        civil_templates = self.service.list_templates(case_type=DocumentCaseType.CIVIL)
        self.assertEqual(len(civil_templates), 1)
        self.assertEqual(civil_templates[0].case_type, DocumentCaseType.CIVIL)

    def test_list_templates_filter_by_active(self):
        """测试按活跃状态过滤"""
        self.service.create_template(
            name="活跃模板",
            case_type=DocumentCaseType.CIVIL,
            case_stage=DocumentCaseStage.FIRST_TRIAL,
            structure=self.valid_structure,
            is_active=True,
        )

        self.service.create_template(
            name="非活跃模板",
            case_type=DocumentCaseType.CIVIL,
            case_stage=DocumentCaseStage.FIRST_TRIAL,
            structure=self.valid_structure,
            is_active=False,
        )

        active_templates = self.service.list_templates(is_active=True)
        self.assertEqual(len(active_templates), 1)
        self.assertTrue(active_templates[0].is_active)
