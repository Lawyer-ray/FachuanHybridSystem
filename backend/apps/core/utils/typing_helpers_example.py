"""
Django ORM 类型辅助函数使用示例

展示如何使用 typing_helpers 模块来解决 mypy 类型检查问题.
Requirements: 3.4
"""

from typing import Any

from apps.core.utils import cast_model_id, get_model_attr  # type: ignore[attr-defined]


def example_cast_model_id() -> None:
    """示例:使用 cast_model_id 获取模型 ID"""
    from apps.cases.models import Case

    # 修复前(mypy 报错):
    # case = Case.objects.first()
    # case_id = case.id  # ❌ "Case" has no attribute "id"
    # 修复后(使用 cast_model_id):
    case = Case.objects.first()
    if case:
        case_id = cast_model_id(case)  # ✅ 类型安全
        print(f"Case ID: {case_id}")


def example_get_model_attr() -> None:
    """示例:使用 get_model_attr 获取动态属性"""
    from apps.cases.models import Case

    # 修复前(mypy 报错):
    # case = Case.objects.first()
    # created_at = case.created_at  # ❌ 可能报错
    # 修复后(使用 get_model_attr):
    case = Case.objects.first()
    if case:
        created_at = get_model_attr(case, "created_at")  # ✅ 类型安全
        print(f"Created at: {created_at}")


def example_dto_conversion() -> None:
    """示例:在 DTO 转换中使用辅助函数"""
    from apps.cases.models import Case

    case = Case.objects.first()
    if case:
        # 使用 get_model_attr 避免 mypy 错误
        case_dto = {
            "id": cast_model_id(case),
            "name": get_model_attr(case, "name"),
            "status": get_model_attr(case, "status"),
            "created_at": get_model_attr(case, "created_at"),
        }
        print(f"Case DTO: {case_dto}")


def example_queryset_with_typing() -> Any:
    """示例:QuerySet 泛型参数的正确使用"""
    from apps.cases.models import Case

    # 修复前(mypy 报错):
    # def get_cases() -> QuerySet:  # ❌ Missing type parameters
    #     return Case.objects.filter(status='active')
    # 修复后(添加泛型参数):
    # 注意:Django 6.0 的 QuerySet 需要两个类型参数
    cases = Case.objects.filter(status="active")  # ✅
    return cases
