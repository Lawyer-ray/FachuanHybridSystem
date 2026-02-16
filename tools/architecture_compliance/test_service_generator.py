"""
ServiceGenerator 单元测试
"""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from .business_logic_extractor import (
    ExtractedServiceMethod,
    SaveMethodRefactoring,
)
from .service_generator import (
    ServiceGenerationResult,
    ServiceGenerator,
    _to_snake_case,
)


@pytest.fixture
def generator() -> ServiceGenerator:
    return ServiceGenerator()


# ── _to_snake_case ──────────────────────────────────────────


class TestToSnakeCase:
    def test_simple(self) -> None:
        assert _to_snake_case("Contract") == "contract"

    def test_multi_word(self) -> None:
        assert _to_snake_case("ContractFinanceLog") == "contract_finance_log"

    def test_abbreviation(self) -> None:
        assert _to_snake_case("HTMLParser") == "html_parser"


# ── 路径推导 ────────────────────────────────────────────────


class TestResolveServicePath:
    def test_from_model_path(self, generator: ServiceGenerator) -> None:
        refactoring = _make_refactoring(
            model_name="Contract",
            file_path="backend/apps/contracts/models/contract.py",
        )
        path = generator._resolve_service_path(refactoring, None, None)
        assert path == Path("apps/contracts/services/contract_service.py")

    def test_explicit_target_overrides(self, generator: ServiceGenerator) -> None:
        refactoring = _make_refactoring(
            model_name="Contract",
            file_path="backend/apps/contracts/models/contract.py",
        )
        target = Path("/custom/path/my_service.py")
        path = generator._resolve_service_path(refactoring, None, target)
        assert path == target

    def test_with_project_root(self, generator: ServiceGenerator) -> None:
        refactoring = _make_refactoring(
            model_name="Case",
            file_path="backend/apps/cases/models/case.py",
        )
        root = Path("/home/user/project")
        path = generator._resolve_service_path(refactoring, root, None)
        assert path == root / "apps" / "cases" / "services" / "case_service.py"

    def test_fallback_no_apps_pattern(self, generator: ServiceGenerator) -> None:
        refactoring = _make_refactoring(
            model_name="Widget",
            file_path="src/models/widget.py",
        )
        path = generator._resolve_service_path(refactoring, None, None)
        assert path == Path("src/services/widget_service.py")


# ── 新文件生成 ──────────────────────────────────────────────


class TestCreateNewFile:
    def test_generates_valid_python(
        self, generator: ServiceGenerator, tmp_path: Path,
    ) -> None:
        service_path = tmp_path / "contract_service.py"
        refactoring = _make_refactoring(
            model_name="Contract",
            file_path="backend/apps/contracts/models/contract.py",
            methods=[
                _make_method(
                    "create_finance_log",
                    ["contract: Contract"],
                    'ContractFinanceLog.objects.create(contract=contract, amount=contract.fixed_amount)',
                    "创建财务记录",
                ),
            ],
        )

        result = generator.generate(
            refactoring, target_service_path=service_path,
        )

        assert result.file_created is True
        assert result.methods_added == ["create_finance_log"]
        assert result.methods_skipped == []
        assert "class ContractService:" in result.file_content
        assert "def create_finance_log(self, contract: Contract)" in result.file_content
        assert "from apps.contracts.models import Contract" in result.file_content
        # 验证语法正确
        compile(result.file_content, "<test>", "exec")

    def test_multiple_methods(
        self, generator: ServiceGenerator, tmp_path: Path,
    ) -> None:
        service_path = tmp_path / "order_service.py"
        refactoring = _make_refactoring(
            model_name="Order",
            file_path="backend/apps/orders/models/order.py",
            methods=[
                _make_method("create_log", ["order: Order"], "pass", "创建日志"),
                _make_method("notify_user", ["order: Order"], "pass", "通知用户"),
            ],
        )

        result = generator.generate(
            refactoring, target_service_path=service_path,
        )

        assert result.file_created is True
        assert result.methods_added == ["create_log", "notify_user"]
        assert "def create_log(self, order: Order)" in result.file_content
        assert "def notify_user(self, order: Order)" in result.file_content

    def test_empty_methods_returns_early(
        self, generator: ServiceGenerator, tmp_path: Path,
    ) -> None:
        service_path = tmp_path / "empty_service.py"
        refactoring = _make_refactoring(
            model_name="Empty",
            file_path="backend/apps/test/models/empty.py",
            methods=[],
        )

        result = generator.generate(
            refactoring, target_service_path=service_path,
        )

        assert result.methods_added == []
        assert result.file_content == ""
        assert result.file_created is False

    def test_includes_future_annotations(
        self, generator: ServiceGenerator, tmp_path: Path,
    ) -> None:
        service_path = tmp_path / "contract_service.py"
        refactoring = _make_refactoring(
            model_name="Contract",
            file_path="backend/apps/contracts/models/contract.py",
            methods=[_make_method("do_stuff", ["contract: Contract"], "pass", "desc")],
        )

        result = generator.generate(
            refactoring, target_service_path=service_path,
        )

        assert "from __future__ import annotations" in result.file_content


# ── 更新已有文件 ────────────────────────────────────────────


class TestUpdateExistingFile:
    def test_adds_method_to_existing_class(
        self, generator: ServiceGenerator, tmp_path: Path,
    ) -> None:
        service_path = tmp_path / "contract_service.py"
        existing_code = textwrap.dedent("""\
            from apps.contracts.models import Contract


            class ContractService:

                def __init__(self) -> None:
                    pass

                def existing_method(self) -> None:
                    pass
        """)
        service_path.write_text(existing_code, encoding="utf-8")

        refactoring = _make_refactoring(
            model_name="Contract",
            file_path="backend/apps/contracts/models/contract.py",
            methods=[
                _make_method(
                    "create_finance_log",
                    ["contract: Contract"],
                    "pass",
                    "创建财务记录",
                ),
            ],
        )

        result = generator.generate(
            refactoring, target_service_path=service_path,
        )

        assert result.file_created is False
        assert result.methods_added == ["create_finance_log"]
        assert "def create_finance_log(self, contract: Contract)" in result.file_content
        assert "def existing_method(self)" in result.file_content
        compile(result.file_content, "<test>", "exec")

    def test_skips_duplicate_methods(
        self, generator: ServiceGenerator, tmp_path: Path,
    ) -> None:
        service_path = tmp_path / "contract_service.py"
        existing_code = textwrap.dedent("""\
            from apps.contracts.models import Contract


            class ContractService:

                def __init__(self) -> None:
                    pass

                def create_finance_log(self, contract: Contract) -> None:
                    pass
        """)
        service_path.write_text(existing_code, encoding="utf-8")

        refactoring = _make_refactoring(
            model_name="Contract",
            file_path="backend/apps/contracts/models/contract.py",
            methods=[
                _make_method(
                    "create_finance_log",
                    ["contract: Contract"],
                    "pass",
                    "创建财务记录",
                ),
            ],
        )

        result = generator.generate(
            refactoring, target_service_path=service_path,
        )

        assert result.methods_added == []
        assert result.methods_skipped == ["create_finance_log"]

    def test_adds_model_import_if_missing(
        self, generator: ServiceGenerator, tmp_path: Path,
    ) -> None:
        service_path = tmp_path / "contract_service.py"
        existing_code = textwrap.dedent("""\
            class ContractService:

                def __init__(self) -> None:
                    pass
        """)
        service_path.write_text(existing_code, encoding="utf-8")

        refactoring = _make_refactoring(
            model_name="Contract",
            file_path="backend/apps/contracts/models/contract.py",
            methods=[
                _make_method("do_stuff", ["contract: Contract"], "pass", "desc"),
            ],
        )

        result = generator.generate(
            refactoring, target_service_path=service_path,
        )

        assert "from apps.contracts.models import Contract" in result.file_content

    def test_finds_service_class_by_suffix(
        self, generator: ServiceGenerator, tmp_path: Path,
    ) -> None:
        """当类名不完全匹配时，查找以 Service 结尾的类"""
        service_path = tmp_path / "contract_service.py"
        existing_code = textwrap.dedent("""\
            class MyContractService:

                def __init__(self) -> None:
                    pass
        """)
        service_path.write_text(existing_code, encoding="utf-8")

        refactoring = _make_refactoring(
            model_name="Contract",
            file_path="backend/apps/contracts/models/contract.py",
            methods=[
                _make_method("do_stuff", ["contract: Contract"], "pass", "desc"),
            ],
        )

        result = generator.generate(
            refactoring, target_service_path=service_path,
        )

        assert result.service_class_name == "MyContractService"
        assert result.methods_added == ["do_stuff"]

    def test_appends_class_when_no_service_class_found(
        self, generator: ServiceGenerator, tmp_path: Path,
    ) -> None:
        """文件存在但无 Service 类时，追加新类"""
        service_path = tmp_path / "contract_service.py"
        existing_code = textwrap.dedent("""\
            # Some utility code
            def helper():
                pass
        """)
        service_path.write_text(existing_code, encoding="utf-8")

        refactoring = _make_refactoring(
            model_name="Contract",
            file_path="backend/apps/contracts/models/contract.py",
            methods=[
                _make_method("do_stuff", ["contract: Contract"], "pass", "desc"),
            ],
        )

        result = generator.generate(
            refactoring, target_service_path=service_path,
        )

        assert "class ContractService:" in result.file_content
        assert "def helper():" in result.file_content
        assert result.methods_added == ["do_stuff"]


# ── 批量生成 ────────────────────────────────────────────────


class TestGenerateBatch:
    def test_batch_generates_multiple(
        self, generator: ServiceGenerator, tmp_path: Path,
    ) -> None:
        refactorings = [
            _make_refactoring(
                model_name="Contract",
                file_path="backend/apps/contracts/models/contract.py",
                methods=[_make_method("m1", ["c: Contract"], "pass", "d1")],
            ),
            _make_refactoring(
                model_name="Order",
                file_path="backend/apps/orders/models/order.py",
                methods=[_make_method("m2", ["o: Order"], "pass", "d2")],
            ),
        ]

        results = generator.generate_batch(refactorings)

        assert len(results) == 2
        assert results[0].service_class_name == "ContractService"
        assert results[1].service_class_name == "OrderService"


# ── 导入管理 ────────────────────────────────────────────────


class TestImportManagement:
    def test_has_import_detects_existing(self, generator: ServiceGenerator) -> None:
        source = "from apps.contracts.models import Contract\n"
        assert generator._has_import(source, "Contract") is True

    def test_has_import_returns_false(self, generator: ServiceGenerator) -> None:
        source = "from apps.contracts.models import Order\n"
        assert generator._has_import(source, "Contract") is False

    def test_add_import_line_after_last_import(
        self, generator: ServiceGenerator,
    ) -> None:
        source = "import os\nfrom pathlib import Path\n\nx = 1\n"
        result = generator._add_import_line(source, "from apps.x import Y")
        lines = result.splitlines()
        assert "from apps.x import Y" in lines
        # 应该在 from pathlib import Path 之后
        idx = lines.index("from apps.x import Y")
        assert idx == 2

    def test_build_model_import_with_app(
        self, generator: ServiceGenerator,
    ) -> None:
        result = generator._build_model_import(
            "Contract", "backend/apps/contracts/models/contract.py",
        )
        assert result == "from apps.contracts.models import Contract"

    def test_build_model_import_fallback(
        self, generator: ServiceGenerator,
    ) -> None:
        result = generator._build_model_import("Widget", "src/widget.py")
        assert result == "from ..models import Widget"


# ── 辅助函数 ───────────────────────────────────────────────


def _make_method(
    name: str,
    params: list[str],
    body: str,
    description: str,
) -> ExtractedServiceMethod:
    return ExtractedServiceMethod(
        method_name=name,
        parameters=params,
        body_code=body,
        description=description,
        source_lines=(1, 5),
    )


def _make_refactoring(
    model_name: str,
    file_path: str,
    methods: list[ExtractedServiceMethod] | None = None,
) -> SaveMethodRefactoring:
    return SaveMethodRefactoring(
        model_name=model_name,
        file_path=file_path,
        service_methods=methods or [],
        cleaned_save_code="",
        clean_method_code=None,
        original_save_code="",
    )
