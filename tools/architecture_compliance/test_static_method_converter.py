"""
StaticMethodConverter 单元测试

测试静态方法转换器的核心功能：
- 移除 @staticmethod 装饰器
- 添加 self 参数
- 替换 ClassName.method() → self.method()
- 识别依赖并生成/更新 __init__
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from .static_method_analyzer import ConversionReason, StaticMethodClassification, StaticMethodInfo
from .static_method_converter import DependencyInfo, FileConversionPlan, MethodConversionPlan, StaticMethodConverter


@pytest.fixture
def converter() -> StaticMethodConverter:
    """创建 StaticMethodConverter 实例"""
    return StaticMethodConverter()


@pytest.fixture
def tmp_service_file(tmp_path: Path) -> Path:
    """创建临时 Service 文件"""
    return tmp_path / "test_service.py"


class TestAddSelfParameter:
    """测试 _add_self_parameter 方法"""

    def test_no_params(self, converter: StaticMethodConverter) -> None:
        """无参数方法添加 self"""
        line = "    def calculate():\n"
        result = converter._add_self_parameter(line)
        assert result == "    def calculate(self):\n"

    def test_with_params(self, converter: StaticMethodConverter) -> None:
        """有参数方法添加 self"""
        line = "    def calculate(amount, rate):\n"
        result = converter._add_self_parameter(line)
        assert result == "    def calculate(self, amount, rate):\n"

    def test_async_method(self, converter: StaticMethodConverter) -> None:
        """异步方法添加 self"""
        line = "    async def fetch_data(url):\n"
        result = converter._add_self_parameter(line)
        assert result == "    async def fetch_data(self, url):\n"

    def test_no_params_with_return_type(self, converter: StaticMethodConverter) -> None:
        """带返回类型注解的无参数方法"""
        line = "    def get_name() -> str:\n"
        result = converter._add_self_parameter(line)
        assert result == "    def get_name(self) -> str:\n"

    def test_non_def_line(self, converter: StaticMethodConverter) -> None:
        """非 def 行不做修改"""
        line = "    x = 1\n"
        result = converter._add_self_parameter(line)
        assert result == "    x = 1\n"


class TestConvertFile:
    """测试 convert_file 完整流程"""

    def test_simple_static_method_conversion(
        self,
        converter: StaticMethodConverter,
        tmp_service_file: Path,
    ) -> None:
        """测试简单静态方法转换：移除装饰器 + 添加 self"""
        source = textwrap.dedent(
            """\
            class ContractService:
                @staticmethod
                def calculate_fee(amount, rate):
                    return amount * rate
        """
        )
        tmp_service_file.write_text(source, encoding="utf-8")

        method_info = StaticMethodInfo(
            class_name="ContractService",
            method_name="calculate_fee",
            file_path=str(tmp_service_file),
            line_number=3,
            classification=StaticMethodClassification.CONVERT,
            reasons=[
                ConversionReason(
                    rule="calls_class_method",
                    detail="调用同类方法: ContractService.helper()",
                ),
            ],
        )

        result = converter.convert_file(tmp_service_file, [method_info])
        assert result.success is True

        new_source = tmp_service_file.read_text(encoding="utf-8")
        assert "@staticmethod" not in new_source
        assert "def calculate_fee(self, amount, rate):" in new_source

    def test_class_method_call_replacement(
        self,
        converter: StaticMethodConverter,
        tmp_service_file: Path,
    ) -> None:
        """测试 ClassName.method() → self.method() 替换"""
        source = textwrap.dedent(
            """\
            class ContractService:
                @staticmethod
                def process(data):
                    result = ContractService.validate(data)
                    ContractService.save(result)
                    return result
        """
        )
        tmp_service_file.write_text(source, encoding="utf-8")

        method_info = StaticMethodInfo(
            class_name="ContractService",
            method_name="process",
            file_path=str(tmp_service_file),
            line_number=3,
            classification=StaticMethodClassification.CONVERT,
            reasons=[
                ConversionReason(
                    rule="calls_class_method",
                    detail="调用同类方法: ContractService.validate()",
                ),
            ],
        )

        result = converter.convert_file(tmp_service_file, [method_info])
        assert result.success is True

        new_source = tmp_service_file.read_text(encoding="utf-8")
        assert "self.validate(data)" in new_source
        assert "self.save(result)" in new_source
        assert "ContractService.validate" not in new_source
        assert "ContractService.save" not in new_source

    def test_multiple_methods_in_same_class(
        self,
        converter: StaticMethodConverter,
        tmp_service_file: Path,
    ) -> None:
        """测试同一个类中多个静态方法的转换"""
        source = textwrap.dedent(
            """\
            class MyService:
                @staticmethod
                def method_a(x):
                    return x + 1

                @staticmethod
                def method_b(y):
                    return MyService.method_a(y)
        """
        )
        tmp_service_file.write_text(source, encoding="utf-8")

        methods = [
            StaticMethodInfo(
                class_name="MyService",
                method_name="method_a",
                file_path=str(tmp_service_file),
                line_number=3,
                classification=StaticMethodClassification.CONVERT,
                reasons=[
                    ConversionReason(
                        rule="calls_class_method",
                        detail="调用同类方法: MyService.helper()",
                    ),
                ],
            ),
            StaticMethodInfo(
                class_name="MyService",
                method_name="method_b",
                file_path=str(tmp_service_file),
                line_number=7,
                classification=StaticMethodClassification.CONVERT,
                reasons=[
                    ConversionReason(
                        rule="calls_class_method",
                        detail="调用同类方法: MyService.method_a()",
                    ),
                ],
            ),
        ]

        result = converter.convert_file(tmp_service_file, [methods[0], methods[1]])
        assert result.success is True

        new_source = tmp_service_file.read_text(encoding="utf-8")
        assert "@staticmethod" not in new_source
        assert "def method_a(self, x):" in new_source
        assert "def method_b(self, y):" in new_source
        assert "self.method_a(y)" in new_source

    def test_skip_keep_methods(
        self,
        converter: StaticMethodConverter,
        tmp_service_file: Path,
    ) -> None:
        """测试跳过 classification == KEEP 的方法"""
        source = textwrap.dedent(
            """\
            class MyService:
                @staticmethod
                def pure_util(x):
                    return x * 2
        """
        )
        tmp_service_file.write_text(source, encoding="utf-8")

        method_info = StaticMethodInfo(
            class_name="MyService",
            method_name="pure_util",
            file_path=str(tmp_service_file),
            line_number=3,
            classification=StaticMethodClassification.KEEP,
            reasons=[
                ConversionReason(
                    rule="pure_string_math",
                    detail="纯工具函数",
                ),
            ],
        )

        result = converter.convert_file(tmp_service_file, [method_info])
        assert result.success is True
        assert "跳过" in result.changes_made[0]

        # 源代码不应被修改
        new_source = tmp_service_file.read_text(encoding="utf-8")
        assert "@staticmethod" in new_source

    def test_file_not_found(
        self,
        converter: StaticMethodConverter,
        tmp_path: Path,
    ) -> None:
        """测试文件不存在的情况"""
        fake_path = tmp_path / "nonexistent.py"
        result = converter.convert_file(fake_path, [])
        assert result.success is False
        assert "不存在" in (result.error_message or "")

    def test_dry_run_does_not_write(
        self,
        converter: StaticMethodConverter,
        tmp_service_file: Path,
    ) -> None:
        """测试 dry_run 模式不写入文件"""
        source = textwrap.dedent(
            """\
            class MyService:
                @staticmethod
                def do_work(data):
                    return data
        """
        )
        tmp_service_file.write_text(source, encoding="utf-8")

        method_info = StaticMethodInfo(
            class_name="MyService",
            method_name="do_work",
            file_path=str(tmp_service_file),
            line_number=3,
            classification=StaticMethodClassification.CONVERT,
            reasons=[
                ConversionReason(
                    rule="calls_class_method",
                    detail="调用同类方法",
                ),
            ],
        )

        result = converter.convert_file(
            tmp_service_file,
            [method_info],
            dry_run=True,
        )
        assert result.success is True

        # 文件内容不应改变
        assert tmp_service_file.read_text(encoding="utf-8") == source


class TestDependencyIdentification:
    """测试依赖识别逻辑"""

    def test_model_objects_dependency(
        self,
        converter: StaticMethodConverter,
        tmp_service_file: Path,
    ) -> None:
        """测试识别 Model.objects 依赖"""
        source = textwrap.dedent(
            """\
            class ContractService:
                @staticmethod
                def get_active(status):
                    return Contract.objects.filter(status=status)
        """
        )
        tmp_service_file.write_text(source, encoding="utf-8")

        method_info = StaticMethodInfo(
            class_name="ContractService",
            method_name="get_active",
            file_path=str(tmp_service_file),
            line_number=3,
            classification=StaticMethodClassification.CONVERT,
            reasons=[
                ConversionReason(
                    rule="model_objects_access",
                    detail="访问 Contract.objects，需要服务注入",
                ),
            ],
        )

        result = converter.convert_file(tmp_service_file, [method_info])
        assert result.success is True

        new_source = tmp_service_file.read_text(encoding="utf-8")
        # 应该生成 __init__ 包含 contract_service 依赖
        assert "__init__" in new_source
        assert "self.contract_service" in new_source

    def test_external_service_dependency(
        self,
        converter: StaticMethodConverter,
        tmp_service_file: Path,
    ) -> None:
        """测试识别外部 Service 依赖"""
        source = textwrap.dedent(
            """\
            class ContractService:
                @staticmethod
                def notify(contract_id):
                    svc = NotificationService()
                    svc.send(contract_id)
        """
        )
        tmp_service_file.write_text(source, encoding="utf-8")

        method_info = StaticMethodInfo(
            class_name="ContractService",
            method_name="notify",
            file_path=str(tmp_service_file),
            line_number=3,
            classification=StaticMethodClassification.CONVERT,
            reasons=[
                ConversionReason(
                    rule="calls_external_service",
                    detail="调用外部服务: NotificationService()",
                ),
            ],
        )

        result = converter.convert_file(tmp_service_file, [method_info])
        assert result.success is True

        new_source = tmp_service_file.read_text(encoding="utf-8")
        assert "__init__" in new_source
        assert "self.notification_service" in new_source


class TestInitHandling:
    """测试 __init__ 构造函数处理"""

    def test_update_existing_init(
        self,
        converter: StaticMethodConverter,
        tmp_service_file: Path,
    ) -> None:
        """测试更新已有的 __init__"""
        source = textwrap.dedent(
            """\
            class ContractService:
                def __init__(self):
                    self.repo = ContractRepo()

                @staticmethod
                def get_active(status):
                    return Contract.objects.filter(status=status)
        """
        )
        tmp_service_file.write_text(source, encoding="utf-8")

        method_info = StaticMethodInfo(
            class_name="ContractService",
            method_name="get_active",
            file_path=str(tmp_service_file),
            line_number=6,
            classification=StaticMethodClassification.CONVERT,
            reasons=[
                ConversionReason(
                    rule="model_objects_access",
                    detail="访问 Contract.objects，需要服务注入",
                ),
            ],
        )

        result = converter.convert_file(tmp_service_file, [method_info])
        assert result.success is True

        new_source = tmp_service_file.read_text(encoding="utf-8")
        # 原有的 repo 赋值应保留
        assert "self.repo = ContractRepo()" in new_source
        # 新依赖应追加
        assert "self.contract_service" in new_source

    def test_no_duplicate_init_attrs(
        self,
        converter: StaticMethodConverter,
        tmp_service_file: Path,
    ) -> None:
        """测试不重复添加已有的依赖属性"""
        source = textwrap.dedent(
            """\
            class ContractService:
                def __init__(self):
                    self.contract_service = None

                @staticmethod
                def get_active(status):
                    return Contract.objects.filter(status=status)
        """
        )
        tmp_service_file.write_text(source, encoding="utf-8")

        method_info = StaticMethodInfo(
            class_name="ContractService",
            method_name="get_active",
            file_path=str(tmp_service_file),
            line_number=6,
            classification=StaticMethodClassification.CONVERT,
            reasons=[
                ConversionReason(
                    rule="model_objects_access",
                    detail="访问 Contract.objects，需要服务注入",
                ),
            ],
        )

        result = converter.convert_file(tmp_service_file, [method_info])
        assert result.success is True

        new_source = tmp_service_file.read_text(encoding="utf-8")
        # 不应重复添加
        count = new_source.count("self.contract_service")
        assert count == 1


class TestHelperMethods:
    """测试辅助方法"""

    def test_extract_model_name(self) -> None:
        """测试从 reason detail 提取 Model 名称"""
        assert StaticMethodConverter._extract_model_name_from_reason("访问 Case.objects，需要服务注入") == "Case"
        assert StaticMethodConverter._extract_model_name_from_reason("无关文本") == ""

    def test_extract_service_name(self) -> None:
        """测试从 reason detail 提取 Service 名称"""
        assert StaticMethodConverter._extract_service_name_from_reason("调用外部服务: CaseService()") == "CaseService"
        assert StaticMethodConverter._extract_service_name_from_reason("无关文本") == ""

    def test_to_snake_case(self) -> None:
        """测试 CamelCase → snake_case"""
        assert StaticMethodConverter._to_snake_case("CaseService") == "case_service"
        assert StaticMethodConverter._to_snake_case("Contract") == "contract"
        assert StaticMethodConverter._to_snake_case("HTTPClient") == "h_t_t_p_client"

    def test_deduplicate_dependencies(self) -> None:
        """测试依赖去重"""
        deps = [
            DependencyInfo(name="case_service", source="Case.objects", rule="r1"),
            DependencyInfo(name="case_service", source="Case.objects", rule="r2"),
            DependencyInfo(name="other", source="Other", rule="r3"),
        ]
        result = StaticMethodConverter._deduplicate_dependencies(deps)
        assert len(result) == 2
        assert result[0].name == "case_service"
        assert result[1].name == "other"
