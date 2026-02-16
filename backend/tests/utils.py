"""
测试辅助函数

从 apps/tests/utils.py 迁移
"""
from typing import Any, Dict, List, Optional
from django.test import Client
from django.contrib.auth import get_user_model


def create_authenticated_client(user=None, **user_kwargs) -> Client:
    """
    创建已认证的测试客户端
    
    Args:
        user: 用户对象（可选）
        **user_kwargs: 用户创建参数
        
    Returns:
        Client: 已认证的测试客户端
    """
    from tests.factories import LawyerFactory
    
    client = Client()
    
    if user is None:
        user = LawyerFactory(**user_kwargs)
    
    client.force_login(user)
    return client


def assert_response_success(response, expected_status=200):
    """
    断言响应成功
    
    Args:
        response: HTTP 响应对象
        expected_status: 期望的状态码
        
    Raises:
        AssertionError: 如果响应失败
    """
    if response.status_code != expected_status:
        try:
            error_data = response.json()
            error_msg = error_data.get('error', 'Unknown error')
        except:
            error_msg = response.content.decode('utf-8')
        
        raise AssertionError(
            f"Expected status {expected_status}, got {response.status_code}. "
            f"Error: {error_msg}"
        )


def assert_response_error(response, expected_status=400, expected_code=None):
    """
    断言响应错误
    
    Args:
        response: HTTP 响应对象
        expected_status: 期望的状态码
        expected_code: 期望的错误码（可选）
        
    Raises:
        AssertionError: 如果响应不符合预期
    """
    if response.status_code != expected_status:
        raise AssertionError(
            f"Expected status {expected_status}, got {response.status_code}"
        )
    
    if expected_code:
        try:
            error_data = response.json()
            actual_code = error_data.get('code')
            if actual_code != expected_code:
                raise AssertionError(
                    f"Expected error code '{expected_code}', got '{actual_code}'"
                )
        except ValueError:
            raise AssertionError("Response is not JSON")


def assert_dict_contains(actual: Dict, expected: Dict):
    """
    断言字典包含期望的键值对
    
    Args:
        actual: 实际字典
        expected: 期望的键值对
        
    Raises:
        AssertionError: 如果不包含期望的键值对
    """
    for key, value in expected.items():
        if key not in actual:
            raise AssertionError(f"Key '{key}' not found in actual dict")
        
        if actual[key] != value:
            raise AssertionError(
                f"Value mismatch for key '{key}': "
                f"expected {value}, got {actual[key]}"
            )


def assert_queryset_equal(qs1, qs2, ordered=False):
    """
    断言两个查询集相等
    
    Args:
        qs1: 查询集1
        qs2: 查询集2
        ordered: 是否考虑顺序
        
    Raises:
        AssertionError: 如果查询集不相等
    """
    list1 = list(qs1)
    list2 = list(qs2)
    
    if ordered:
        if list1 != list2:
            raise AssertionError(
                f"QuerySets are not equal (ordered): "
                f"{list1} != {list2}"
            )
    else:
        if set(list1) != set(list2):
            raise AssertionError(
                f"QuerySets are not equal (unordered): "
                f"{set(list1)} != {set(list2)}"
            )


def get_json_response(response) -> Dict[str, Any]:
    """
    获取 JSON 响应数据
    
    Args:
        response: HTTP 响应对象
        
    Returns:
        dict: JSON 数据
        
    Raises:
        AssertionError: 如果响应不是 JSON
    """
    try:
        return response.json()
    except ValueError:
        raise AssertionError(
            f"Response is not JSON. Content: {response.content.decode('utf-8')}"
        )


def create_test_file(filename: str = "test.txt", content: str = "test content"):
    """
    创建测试文件
    
    Args:
        filename: 文件名
        content: 文件内容
        
    Returns:
        File: Django 文件对象
    """
    from django.core.files.uploadedfile import SimpleUploadedFile
    
    return SimpleUploadedFile(
        filename,
        content.encode('utf-8'),
        content_type='text/plain'
    )


def freeze_time(frozen_time):
    """
    冻结时间（用于测试）
    
    Args:
        frozen_time: 冻结的时间
        
    Returns:
        上下文管理器
        
    使用方法：
        from datetime import datetime
        
        with freeze_time(datetime(2024, 1, 1)):
            # 在这个块中，时间被冻结在 2024-01-01
            case = CaseFactory()
            assert case.start_date == datetime(2024, 1, 1).date()
    """
    try:
        from freezegun import freeze_time as _freeze_time
        return _freeze_time(frozen_time)
    except ImportError:
        raise ImportError(
            "freezegun is not installed. "
            "Install it with: pip install freezegun"
        )
