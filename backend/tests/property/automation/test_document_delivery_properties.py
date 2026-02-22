"""
文书送达自动下载属性测试

使用 Hypothesis 进行属性测试，验证文书送达相关数据类的正确性属性。
"""

from datetime import datetime, timezone
from typing import Any, Dict

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from apps.automation.schemas import DocumentDeliveryRecord


class TestDocumentDeliveryRecordProperties:
    """DocumentDeliveryRecord 属性测试"""

    # ========================================================================
    # Property 10: DocumentDeliveryRecord round-trip
    # ========================================================================

    @given(
        case_number=st.text(min_size=1, max_size=128),
        send_time=st.datetimes(min_value=datetime(2020, 1, 1), max_value=datetime(2030, 12, 31)).map(
            lambda dt: dt.replace(tzinfo=timezone.utc)
        ),
        element_index=st.integers(min_value=0, max_value=1000),
        document_name=st.text(min_size=0, max_size=512),
        court_name=st.text(min_size=0, max_size=256),
    )
    @settings(max_examples=100, deadline=None)
    def test_property_10_document_delivery_record_round_trip(
        self, case_number, send_time, element_index, document_name, court_name
    ):
        """
        **Feature: court-document-auto-download, Property 10: DocumentDeliveryRecord round-trip**

        属性测试：对于任何有效的 DocumentDeliveryRecord，
        序列化为字典后再反序列化应该产生等价的记录

        **Validates: Requirements 9.1, 9.2, 9.3**
        """
        # 创建原始记录
        original = DocumentDeliveryRecord(
            case_number=case_number,
            send_time=send_time,
            element_index=element_index,
            document_name=document_name,
            court_name=court_name,
        )

        # 序列化为字典
        serialized = original.to_dict()

        # 验证序列化结果是字典
        assert isinstance(serialized, dict), "序列化结果应该是字典"

        # 验证包含所有必需字段
        required_fields = ["case_number", "send_time", "element_index", "document_name", "court_name"]
        for field in required_fields:
            assert field in serialized, f"序列化结果应该包含字段: {field}"

        # 反序列化
        deserialized = DocumentDeliveryRecord.from_dict(serialized)

        # 验证反序列化结果与原始记录等价
        assert deserialized.case_number == original.case_number, "案号应该相等"
        assert deserialized.element_index == original.element_index, "元素索引应该相等"
        assert deserialized.document_name == original.document_name, "文书名称应该相等"
        assert deserialized.court_name == original.court_name, "法院名称应该相等"

        # 时间字段需要特殊处理（可能有精度差异）
        if original.send_time is not None and deserialized.send_time is not None:
            # 允许毫秒级别的差异
            time_diff = abs((original.send_time - deserialized.send_time).total_seconds())
            assert time_diff < 1.0, f"时间差异应该小于1秒，实际差异: {time_diff}秒"
        else:
            assert original.send_time == deserialized.send_time, "时间字段应该相等"

    @given(case_number=st.text(min_size=1, max_size=128), element_index=st.integers(min_value=0, max_value=1000))
    @settings(max_examples=100, deadline=None)
    def test_property_10_minimal_record_round_trip(self, case_number, element_index):
        """
        **Feature: court-document-auto-download, Property 10: DocumentDeliveryRecord round-trip**

        属性测试：对于只包含必需字段的最小记录，
        round-trip 序列化应该保持一致性

        **Validates: Requirements 9.1, 9.2, 9.3**
        """
        # 创建最小记录（只有必需字段）
        original = DocumentDeliveryRecord(
            case_number=case_number, send_time=datetime.now(timezone.utc), element_index=element_index
        )

        # Round-trip 序列化
        serialized = original.to_dict()
        deserialized = DocumentDeliveryRecord.from_dict(serialized)

        # 验证核心字段
        assert deserialized.case_number == original.case_number
        assert deserialized.element_index == original.element_index
        assert deserialized.document_name == original.document_name  # 应该是默认值 ""
        assert deserialized.court_name == original.court_name  # 应该是默认值 ""

    def test_property_10_none_send_time_handling(self):
        """
        **Feature: court-document-auto-download, Property 10: DocumentDeliveryRecord round-trip**

        测试 send_time 为 None 时的处理

        **Validates: Requirements 9.1, 9.2, 9.3**
        """
        # 创建 send_time 为 None 的记录
        original = DocumentDeliveryRecord(case_number="(2024)粤01民初123号", send_time=None, element_index=0)  # type: ignore[arg-type]

        # Round-trip 序列化
        serialized = original.to_dict()
        deserialized = DocumentDeliveryRecord.from_dict(serialized)

        # 验证 None 值被正确处理
        assert deserialized.send_time is None
        assert deserialized.case_number == original.case_number
        assert deserialized.element_index == original.element_index

    @given(
        st.dictionaries(
            keys=st.sampled_from(["case_number", "send_time", "element_index", "document_name", "court_name"]),
            values=st.one_of(
                st.text(min_size=0, max_size=100),
                st.integers(min_value=0, max_value=1000),
                st.none(),
                st.datetimes().map(lambda dt: dt.isoformat()),
            ),
            min_size=3,  # 至少包含必需字段
            max_size=5,
        ).filter(lambda d: "case_number" in d and "element_index" in d)
    )
    @settings(max_examples=100, deadline=None)
    def test_property_10_from_dict_handles_various_inputs(self, dict_data):
        """
        **Feature: court-document-auto-download, Property 10: DocumentDeliveryRecord round-trip**

        属性测试：from_dict 方法应该能处理各种合理的输入格式

        **Validates: Requirements 9.1, 9.2, 9.3**
        """
        # 确保必需字段存在且类型正确
        if not isinstance(dict_data.get("case_number"), str) or not dict_data.get("case_number"):
            dict_data["case_number"] = "测试案号"

        if not isinstance(dict_data.get("element_index"), int):
            dict_data["element_index"] = 0

        try:
            # 尝试从字典创建记录
            record = DocumentDeliveryRecord.from_dict(dict_data)

            # 验证必需字段被正确设置
            assert isinstance(record.case_number, str)
            assert isinstance(record.element_index, int)
            assert isinstance(record.document_name, str)
            assert isinstance(record.court_name, str)

            # send_time 可以是 None 或 datetime
            assert record.send_time is None or isinstance(record.send_time, datetime)

        except (ValueError, TypeError, KeyError) as e:
            # 对于无效输入，应该抛出合理的异常
            assert len(str(e)) > 0, "异常信息不应该为空"

    def test_property_10_serialization_preserves_field_types(self):
        """
        **Feature: court-document-auto-download, Property 10: DocumentDeliveryRecord round-trip**

        测试序列化保持字段类型的正确性

        **Validates: Requirements 9.1, 9.2, 9.3**
        """
        original = DocumentDeliveryRecord(
            case_number="(2024)粤01民初123号",
            send_time=datetime(2024, 1, 15, 10, 30, 45, tzinfo=timezone.utc),
            element_index=5,
            document_name="判决书",
            court_name="广州市中级人民法院",
        )

        serialized = original.to_dict()

        # 验证序列化后的字段类型
        assert isinstance(serialized["case_number"], str)
        assert isinstance(serialized["send_time"], str)  # 应该被序列化为 ISO 格式字符串
        assert isinstance(serialized["element_index"], int)
        assert isinstance(serialized["document_name"], str)
        assert isinstance(serialized["court_name"], str)

        # 验证时间格式
        assert "T" in serialized["send_time"], "时间应该是 ISO 格式"

        # 反序列化并验证类型恢复
        deserialized = DocumentDeliveryRecord.from_dict(serialized)
        assert isinstance(deserialized.send_time, datetime)

    def test_property_10_empty_optional_fields_handling(self):
        """
        **Feature: court-document-auto-download, Property 10: DocumentDeliveryRecord round-trip**

        测试空的可选字段的处理

        **Validates: Requirements 9.1, 9.2, 9.3**
        """
        # 测试各种空值情况
        test_cases = [
            {"document_name": "", "court_name": ""},
            {"document_name": "文书", "court_name": ""},
            {"document_name": "", "court_name": "法院"},
        ]

        for case in test_cases:
            original = DocumentDeliveryRecord(
                case_number="测试案号",
                send_time=datetime.now(timezone.utc),
                element_index=0,
                document_name=case["document_name"],
                court_name=case["court_name"],
            )

            # Round-trip
            serialized = original.to_dict()
            deserialized = DocumentDeliveryRecord.from_dict(serialized)

            # 验证空字符串被正确保持
            assert deserialized.document_name == case["document_name"]
            assert deserialized.court_name == case["court_name"]
