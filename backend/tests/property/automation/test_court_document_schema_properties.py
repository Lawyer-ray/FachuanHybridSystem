"""
法院文书 Schema 属性测试

使用 Hypothesis 进行属性测试，验证 Schema 的正确性属性。
"""

from datetime import datetime
from typing import Any, Dict

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pydantic import ValidationError

from apps.automation.schemas import APIInterceptResponseSchema, CourtDocumentSchema


class TestAPIInterceptResponseSchemaProperties:
    """API拦截响应 Schema 属性测试"""

    # ========================================================================
    # Property 2: API响应解析完整性
    # ========================================================================

    @given(
        st.lists(
            st.fixed_dictionaries(
                {
                    "c_sdbh": st.text(min_size=1, max_size=128),
                    "c_stbh": st.text(min_size=1, max_size=512),
                    "wjlj": st.from_regex(r"https?://[a-z0-9\-\.]+\.[a-z]{2,}(/[^\s]*)?", fullmatch=True),
                    "c_wsbh": st.text(min_size=1, max_size=128),
                    "c_wsmc": st.text(min_size=1, max_size=512),
                    "c_fybh": st.text(min_size=1, max_size=64),
                    "c_fymc": st.text(min_size=1, max_size=256),
                    "c_wjgs": st.sampled_from(["pdf", "doc", "docx", "txt"]),
                    "dt_cjsj": st.datetimes(min_value=datetime(2020, 1, 1), max_value=datetime(2030, 12, 31)).map(
                        lambda dt: dt.isoformat()
                    ),
                }
            ),
            min_size=0,
            max_size=10,
        )
    )
    @settings(max_examples=100, deadline=None)
    def test_property_2_complete_api_response_parsing(self, document_list):
        """
        **Feature: court-document-api-optimization, Property 2: API响应解析完整性**

        属性测试：对于任何有效的API响应，解析后的数据应该包含所有必需字段
        （c_sdbh, c_stbh, wjlj, c_wsbh, c_wsmc, c_fybh, c_fymc, c_wjgs, dt_cjsj）

        **Validates: Requirements 1.2, 1.3**
        """
        # 构造完整的 API 响应
        api_response = {
            "code": 200,
            "msg": "成功",
            "data": document_list,
            "success": True,
            "totalRows": len(document_list),
        }

        try:
            # 解析响应
            schema = APIInterceptResponseSchema(**api_response)

            # 验证基本字段
            assert schema.code == 200
            assert schema.msg == "成功"
            assert schema.success is True
            assert schema.totalRows == len(document_list)
            assert len(schema.data) == len(document_list)

            # 验证每个文书记录包含所有必需字段
            required_fields = ["c_sdbh", "c_stbh", "wjlj", "c_wsbh", "c_wsmc", "c_fybh", "c_fymc", "c_wjgs", "dt_cjsj"]

            for idx, item in enumerate(schema.data):
                for field in required_fields:
                    assert field in item, f"数据项 {idx} 缺少必需字段: {field}"
                    assert item[field] is not None, f"数据项 {idx} 的字段 {field} 不应该为 None"

        except ValidationError as e:
            pytest.fail(f"有效的 API 响应不应该抛出验证错误: {e}")

    @given(
        st.lists(
            st.fixed_dictionaries(
                {
                    "c_sdbh": st.text(min_size=1, max_size=128),
                    "c_stbh": st.text(min_size=1, max_size=512),
                    # 故意缺少一些必需字段
                }
            ),
            min_size=1,
            max_size=5,
        )
    )
    @settings(max_examples=100, deadline=None)
    def test_property_2_incomplete_data_rejected(self, incomplete_list):
        """
        **Feature: court-document-api-optimization, Property 2: API响应解析完整性**

        属性测试：对于缺少必需字段的数据，Schema 应该抛出验证错误

        **Validates: Requirements 1.2, 1.3**
        """
        # 构造不完整的 API 响应
        api_response = {
            "code": 200,
            "msg": "成功",
            "data": incomplete_list,
            "success": True,
            "totalRows": len(incomplete_list),
        }

        # 应该抛出验证错误
        with pytest.raises(ValidationError) as exc_info:
            APIInterceptResponseSchema(**api_response)

        # 验证错误消息包含缺少字段的信息
        error_msg = str(exc_info.value)
        assert "缺少必需字段" in error_msg or "missing" in error_msg.lower()

    def test_property_2_empty_data_array_accepted(self):
        """
        **Feature: court-document-api-optimization, Property 2: API响应解析完整性**

        测试空数据数组被正确接受

        **Validates: Requirements 1.2, 1.3**
        """
        api_response = {"code": 200, "msg": "成功", "data": [], "success": True, "totalRows": 0}

        # 空数组应该被接受
        schema = APIInterceptResponseSchema(**api_response)
        assert schema.data == []
        assert schema.totalRows == 0

    @given(st.sampled_from(["c_sdbh", "c_stbh", "wjlj", "c_wsbh", "c_wsmc", "c_fybh", "c_fymc", "c_wjgs", "dt_cjsj"]))
    @settings(max_examples=100, deadline=None)
    def test_property_2_missing_single_field_rejected(self, missing_field):
        """
        **Feature: court-document-api-optimization, Property 2: API响应解析完整性**

        属性测试：对于缺少任何一个必需字段的数据，Schema 应该抛出验证错误

        **Validates: Requirements 1.2, 1.3**
        """
        # 创建完整的文书数据
        complete_doc = {
            "c_sdbh": "123456",
            "c_stbh": "ST123456",
            "wjlj": "https://example.com/doc.pdf",
            "c_wsbh": "WS123456",
            "c_wsmc": "测试文书",
            "c_fybh": "FY001",
            "c_fymc": "测试法院",
            "c_wjgs": "pdf",
            "dt_cjsj": "2024-01-01T00:00:00",
        }

        # 移除指定字段
        incomplete_doc = {k: v for k, v in complete_doc.items() if k != missing_field}

        api_response = {"code": 200, "msg": "成功", "data": [incomplete_doc], "success": True, "totalRows": 1}

        # 应该抛出验证错误
        with pytest.raises(ValidationError) as exc_info:
            APIInterceptResponseSchema(**api_response)

        # 验证错误消息提到缺少的字段
        error_msg = str(exc_info.value)
        assert missing_field in error_msg or "缺少必需字段" in error_msg


class TestCourtDocumentSchemaProperties:
    """法院文书 Schema 属性测试"""

    @given(
        st.fixed_dictionaries(
            {
                "id": st.integers(min_value=1, max_value=1000000),
                "scraper_task_id": st.integers(min_value=1, max_value=1000000),
                "case_id": st.one_of(st.none(), st.integers(min_value=1, max_value=1000000)),
                "c_sdbh": st.text(min_size=1, max_size=128),
                "c_stbh": st.text(min_size=1, max_size=512),
                "wjlj": st.from_regex(r"https?://[a-z0-9\-\.]+\.[a-z]{2,}(/[^\s]*)?", fullmatch=True),
                "c_wsbh": st.text(min_size=1, max_size=128),
                "c_wsmc": st.text(min_size=1, max_size=512),
                "c_fybh": st.text(min_size=1, max_size=64),
                "c_fymc": st.text(min_size=1, max_size=256),
                "c_wjgs": st.sampled_from(["pdf", "doc", "docx", "txt"]),
                "dt_cjsj": st.datetimes(min_value=datetime(2020, 1, 1), max_value=datetime(2030, 12, 31)),
                "download_status": st.sampled_from(["pending", "downloading", "success", "failed"]),
                "local_file_path": st.one_of(st.none(), st.text(min_size=1, max_size=1024)),
                "file_size": st.one_of(st.none(), st.integers(min_value=0, max_value=100000000)),
                "error_message": st.one_of(st.none(), st.text(min_size=0, max_size=1000)),
                "created_at": st.datetimes(min_value=datetime(2020, 1, 1), max_value=datetime(2030, 12, 31)),
                "updated_at": st.datetimes(min_value=datetime(2020, 1, 1), max_value=datetime(2030, 12, 31)),
                "downloaded_at": st.one_of(
                    st.none(), st.datetimes(min_value=datetime(2020, 1, 1), max_value=datetime(2030, 12, 31))
                ),
            }
        )
    )
    @settings(max_examples=100, deadline=None)
    def test_property_2_document_schema_accepts_valid_data(self, document_data):
        """
        **Feature: court-document-api-optimization, Property 2: API响应解析完整性**

        属性测试：对于任何包含所有必需字段的文书数据，
        CourtDocumentSchema 应该成功解析

        **Validates: Requirements 1.2, 1.3**
        """
        try:
            schema = CourtDocumentSchema(**document_data)

            # 验证所有字段都被正确设置
            assert schema.id == document_data["id"]
            assert schema.scraper_task_id == document_data["scraper_task_id"]
            assert schema.case_id == document_data["case_id"]
            assert schema.c_sdbh == document_data["c_sdbh"]
            assert schema.c_stbh == document_data["c_stbh"]
            assert schema.wjlj == document_data["wjlj"]
            assert schema.c_wsbh == document_data["c_wsbh"]
            assert schema.c_wsmc == document_data["c_wsmc"]
            assert schema.c_fybh == document_data["c_fybh"]
            assert schema.c_fymc == document_data["c_fymc"]
            assert schema.c_wjgs == document_data["c_wjgs"]
            assert schema.download_status == document_data["download_status"]

            # 验证可选字段
            assert schema.local_file_path == document_data["local_file_path"]
            assert schema.file_size == document_data["file_size"]
            assert schema.error_message == document_data["error_message"]
            assert schema.downloaded_at == document_data["downloaded_at"]

        except ValidationError as e:
            pytest.fail(f"有效的文书数据不应该抛出验证错误: {e}")

    def test_property_2_document_schema_requires_mandatory_fields(self):
        """
        **Feature: court-document-api-optimization, Property 2: API响应解析完整性**

        测试缺少必需字段时抛出验证错误

        **Validates: Requirements 1.2, 1.3**
        """
        # 缺少 id 字段
        incomplete_data = {
            "scraper_task_id": 1,
            "c_sdbh": "123456",
            "c_stbh": "ST123456",
            "wjlj": "https://example.com/doc.pdf",
            "c_wsbh": "WS123456",
            "c_wsmc": "测试文书",
            "c_fybh": "FY001",
            "c_fymc": "测试法院",
            "c_wjgs": "pdf",
            "dt_cjsj": datetime.now(),
            "download_status": "pending",
            "created_at": datetime.now(),
            "updated_at": datetime.now(),
        }

        with pytest.raises(ValidationError):
            CourtDocumentSchema(**incomplete_data)


class TestExceptionResponseHandlingProperties:
    """异常响应处理属性测试"""

    # ========================================================================
    # Property 3: 异常响应处理
    # ========================================================================

    @given(
        st.lists(
            st.dictionaries(
                keys=st.text(min_size=1, max_size=20),
                values=st.one_of(st.text(min_size=0, max_size=100), st.integers(), st.none()),
                min_size=0,
                max_size=5,
            ),
            min_size=1,
            max_size=5,
        )
    )
    @settings(max_examples=100, deadline=None)
    def test_property_3_malformed_response_raises_validation_error(self, malformed_data):
        """
        **Feature: court-document-api-optimization, Property 3: 异常响应处理**

        属性测试：对于任何格式异常的API响应（缺少必需字段或字段类型错误），
        系统应该抛出 ValidationError 并包含详细的错误信息

        **Validates: Requirements 1.5**
        """
        # 构造格式异常的 API 响应
        api_response = {
            "code": 200,
            "msg": "成功",
            "data": malformed_data,  # 使用格式异常的数据
            "success": True,
            "totalRows": len(malformed_data),
        }

        # 应该抛出 ValidationError
        with pytest.raises(ValidationError) as exc_info:
            APIInterceptResponseSchema(**api_response)

        # 验证错误信息包含详细描述
        error = exc_info.value
        assert error is not None, "应该抛出 ValidationError"

        # 验证错误信息是详细的
        error_str = str(error)
        assert len(error_str) > 0, "错误信息不应该为空"

        # 错误信息应该提到缺少的字段或验证失败
        assert any(
            keyword in error_str for keyword in ["缺少必需字段", "missing", "required", "field", "字段"]
        ), f"错误信息应该包含字段相关的描述: {error_str}"

    def test_property_3_missing_code_field_raises_error(self):
        """
        **Feature: court-document-api-optimization, Property 3: 异常响应处理**

        测试缺少 code 字段时抛出 ValidationError

        **Validates: Requirements 1.5**
        """
        # 缺少 code 字段
        api_response = {"msg": "成功", "data": [], "success": True, "totalRows": 0}

        with pytest.raises(ValidationError) as exc_info:
            APIInterceptResponseSchema(**api_response)

        error_str = str(exc_info.value)
        assert "code" in error_str.lower() or "字段" in error_str

    def test_property_3_missing_data_field_raises_error(self):
        """
        **Feature: court-document-api-optimization, Property 3: 异常响应处理**

        测试缺少 data 字段时抛出 ValidationError

        **Validates: Requirements 1.5**
        """
        # 缺少 data 字段
        api_response = {"code": 200, "msg": "成功", "success": True, "totalRows": 0}

        with pytest.raises(ValidationError) as exc_info:
            APIInterceptResponseSchema(**api_response)

        error_str = str(exc_info.value)
        assert "data" in error_str.lower() or "字段" in error_str

    @given(
        st.one_of(
            st.text(min_size=0, max_size=100),
            st.integers(),
            st.dictionaries(
                keys=st.text(min_size=1, max_size=10), values=st.text(min_size=0, max_size=50), min_size=0, max_size=3
            ),
            st.none(),
        )
    )
    @settings(max_examples=100, deadline=None)
    def test_property_3_wrong_data_type_raises_error(self, wrong_data):
        """
        **Feature: court-document-api-optimization, Property 3: 异常响应处理**

        属性测试：对于 data 字段类型错误（不是列表）的响应，
        应该抛出 ValidationError

        **Validates: Requirements 1.5**
        """
        # data 字段应该是列表，但提供其他类型
        if isinstance(wrong_data, list):
            # 跳过列表类型，因为这是正确的类型
            return

        api_response = {"code": 200, "msg": "成功", "data": wrong_data, "success": True, "totalRows": 0}

        with pytest.raises(ValidationError) as exc_info:
            APIInterceptResponseSchema(**api_response)

        error_str = str(exc_info.value)
        # 错误信息应该提到类型问题
        assert any(
            keyword in error_str.lower() for keyword in ["list", "array", "type", "类型", "data"]
        ), f"错误信息应该提到类型问题: {error_str}"

    def test_property_3_error_contains_field_information(self):
        """
        **Feature: court-document-api-optimization, Property 3: 异常响应处理**

        测试 ValidationError 包含具体的字段信息

        **Validates: Requirements 1.5**
        """
        # 提供多个错误的响应
        api_response = {
            "code": "invalid",  # 应该是整数
            "msg": 123,  # 应该是字符串
            "data": "not a list",  # 应该是列表
            "success": "yes",  # 应该是布尔值
            "totalRows": "many",  # 应该是整数
        }

        with pytest.raises(ValidationError) as exc_info:
            APIInterceptResponseSchema(**api_response)

        error = exc_info.value
        error_str = str(error)

        # 验证错误信息包含多个字段的信息
        # 至少应该提到一些字段名
        field_count = sum(1 for field in ["code", "msg", "data", "success", "totalRows"] if field in error_str.lower())
        assert field_count > 0, f"错误信息应该包含字段名: {error_str}"

    @given(st.integers(min_value=-1000, max_value=1000).filter(lambda x: x != 200))
    @settings(max_examples=100, deadline=None)
    def test_property_3_non_200_code_accepted_with_valid_structure(self, error_code):
        """
        **Feature: court-document-api-optimization, Property 3: 异常响应处理**

        属性测试：对于非 200 状态码但结构正确的响应，
        Schema 应该接受（因为我们只验证结构，不验证业务逻辑）

        **Validates: Requirements 1.5**
        """
        api_response = {"code": error_code, "msg": "错误", "data": [], "success": False, "totalRows": 0}

        # 结构正确的响应应该被接受，即使 code 不是 200
        try:
            schema = APIInterceptResponseSchema(**api_response)
            assert schema.code == error_code
            assert schema.success is False
        except ValidationError as e:
            pytest.fail(f"结构正确的响应不应该抛出验证错误: {e}")
