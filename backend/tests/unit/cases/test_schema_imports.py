"""单元测试：API 层 Schema 迁移后导入路径正确。

验证 template_binding_schemas.py 和 litigation_fee_schemas.py
中的 Schema 可通过直接路径和重导出路径正常导入。

验证: 需求 3.7
"""

from __future__ import annotations


class TestTemplateBindingSchemaImports:
    """验证 template_binding_schemas.py 中所有 Schema 可正常导入。"""

    def test_import_bind_template_request_schema(self) -> None:
        from apps.cases.schemas.template_binding_schemas import BindTemplateRequestSchema

        assert BindTemplateRequestSchema is not None

    def test_import_generate_template_request_schema(self) -> None:
        from apps.cases.schemas.template_binding_schemas import GenerateTemplateRequestSchema

        assert GenerateTemplateRequestSchema is not None

    def test_import_template_binding_schema(self) -> None:
        from apps.cases.schemas.template_binding_schemas import TemplateBindingSchema

        assert TemplateBindingSchema is not None

    def test_import_template_category_schema(self) -> None:
        from apps.cases.schemas.template_binding_schemas import TemplateCategorySchema

        assert TemplateCategorySchema is not None

    def test_import_bindings_response_schema(self) -> None:
        from apps.cases.schemas.template_binding_schemas import BindingsResponseSchema

        assert BindingsResponseSchema is not None

    def test_import_available_template_schema(self) -> None:
        from apps.cases.schemas.template_binding_schemas import AvailableTemplateSchema

        assert AvailableTemplateSchema is not None

    def test_import_success_response_schema(self) -> None:
        from apps.cases.schemas.template_binding_schemas import SuccessResponseSchema

        assert SuccessResponseSchema is not None

    def test_reexport_via_schemas_init(self) -> None:
        """验证通过 schemas/__init__.py 重导出路径导入。"""
        from apps.cases.schemas import (
            AvailableTemplateSchema,
            BindingsResponseSchema,
            BindTemplateRequestSchema,
            GenerateTemplateRequestSchema,
            SuccessResponseSchema,
            TemplateCategorySchema,
            TemplateBindingSchema,
        )

        for cls in (
            BindTemplateRequestSchema,
            GenerateTemplateRequestSchema,
            TemplateBindingSchema,
            TemplateCategorySchema,
            BindingsResponseSchema,
            AvailableTemplateSchema,
            SuccessResponseSchema,
        ):
            assert cls is not None


class TestLitigationFeeSchemaImports:
    """验证 litigation_fee_schemas.py 中所有 Schema 可正常导入。"""

    def test_import_fee_calculation_request(self) -> None:
        from apps.cases.schemas.litigation_fee_schemas import FeeCalculationRequest

        assert FeeCalculationRequest is not None

    def test_import_fee_calculation_response(self) -> None:
        from apps.cases.schemas.litigation_fee_schemas import FeeCalculationResponse

        assert FeeCalculationResponse is not None

    def test_reexport_via_schemas_init(self) -> None:
        """验证通过 schemas/__init__.py 重导出路径导入。"""
        from apps.cases.schemas import FeeCalculationRequest, FeeCalculationResponse

        assert FeeCalculationRequest is not None
        assert FeeCalculationResponse is not None


class TestSchemaIdentityAcrossImportPaths:
    """验证直接导入和重导出导入返回相同对象。"""

    def test_template_binding_schemas_identity(self) -> None:
        from apps.cases.schemas import BindTemplateRequestSchema as via_init
        from apps.cases.schemas.template_binding_schemas import BindTemplateRequestSchema as via_direct

        assert via_init is via_direct

    def test_litigation_fee_schemas_identity(self) -> None:
        from apps.cases.schemas import FeeCalculationRequest as via_init
        from apps.cases.schemas.litigation_fee_schemas import FeeCalculationRequest as via_direct

        assert via_init is via_direct
