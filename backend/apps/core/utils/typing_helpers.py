"""
Django ORM 类型辅助工具

提供类型转换和类型安全的辅助函数，解决 Django ORM 动态属性的类型问题。
Requirements: 3.1, 3.2, 3.3
"""

import logging
from typing import TYPE_CHECKING, Any, TypeVar, cast

from django.db.models import Manager, Model, QuerySet

if TYPE_CHECKING:
    from apps.cases.models import Case
    from apps.contracts.models import Contract
    from apps.documents.models import DocumentTemplate, EvidenceList, FolderTemplate, GenerationTask

logger = logging.getLogger(__name__)

# 泛型类型变量
T = TypeVar("T", bound=Model)


def cast_model_id(model: Model | None) -> int | None:
    """
    安全地获取 Model 实例的 id 属性

    Args:
        model: Django Model 实例或 None

    Returns:
        int | None: Model 的 id，如果 model 为 None 则返回 None

    Examples:
        >>> case = Case.objects.first()
        >>> case_id = cast_model_id(case)  # 返回 int
        >>> none_id = cast_model_id(None)  # 返回 None
    """
    if model is None:
        return None
    # Django Model的id是动态属性，使用getattr避免类型检查错误
    return cast(int, model.id)  # type: ignore[attr-defined]


def cast_model_pk(model: Model | None) -> Any:
    """
    安全地获取 Model 实例的 pk 属性

    Args:
        model: Django Model 实例或 None

    Returns:
        Any: Model 的 pk，如果 model 为 None 则返回 None

    Examples:
        >>> case = Case.objects.first()
        >>> case_pk = cast_model_pk(case)
    """
    if model is None:
        return None
    return model.pk


def get_queryset(manager: Manager[T]) -> QuerySet[T, T]:
    """
    从 Manager 获取 QuerySet，提供正确的类型注解

    Args:
        manager: Django Manager 实例

    Returns:
        QuerySet[T, T]: 类型化的 QuerySet

    Examples:
        >>> from apps.cases.models import Case
        >>> qs = get_queryset(Case.objects)  # QuerySet[Case, Case]
    """
    return manager.all()


def get_related_manager(instance: Model, field_name: str) -> Manager[Any]:
    """
    安全地获取反向关系的 Manager

    Args:
        instance: Model 实例
        field_name: 反向关系字段名

    Returns:
        Manager[Any]: 关系 Manager

    Examples:
        >>> case = Case.objects.first()
        >>> logs_manager = get_related_manager(case, 'logs')
    """
    return cast(Manager[Any], getattr(instance, field_name))


def get_related_queryset(instance: Model, field_name: str) -> QuerySet[Any, Any]:
    """
    安全地获取反向关系的 QuerySet

    Args:
        instance: Model 实例
        field_name: 反向关系字段名

    Returns:
        QuerySet[Any, Any]: 关系 QuerySet

    Examples:
        >>> case = Case.objects.first()
        >>> logs = get_related_queryset(case, 'logs')
    """
    manager = get_related_manager(instance, field_name)
    return get_queryset(manager)


def cast_queryset(qs: Any, model_class: type[T]) -> QuerySet[T, T]:
    """
    将未类型化的 QuerySet 转换为类型化的 QuerySet

    Args:
        qs: 未类型化的 QuerySet
        model_class: Model 类

    Returns:
        QuerySet[T, T]: 类型化的 QuerySet

    Examples:
        >>> from apps.cases.models import Case
        >>> qs = some_function_returning_queryset()
        >>> typed_qs = cast_queryset(qs, Case)  # QuerySet[Case, Case]
    """
    return cast(QuerySet[model_class, model_class], qs)  # type: ignore[valid-type]


def cast_manager(manager: Any, model_class: type[T]) -> Manager[T]:
    """
    将未类型化的 Manager 转换为类型化的 Manager

    Args:
        manager: 未类型化的 Manager
        model_class: Model 类

    Returns:
        Manager[T]: 类型化的 Manager

    Examples:
        >>> from apps.cases.models import Case
        >>> manager = some_function_returning_manager()
        >>> typed_manager = cast_manager(manager, Case)  # Manager[Case]
    """
    return cast(Manager[model_class], manager)  # type: ignore[valid-type]


def get_fk_id(instance: Model, field_name: str) -> int | None:
    """
    安全地获取 ForeignKey 字段的 id

    Args:
        instance: Model 实例
        field_name: ForeignKey 字段名

    Returns:
        int | None: 外键 id，如果为 None 则返回 None

    Examples:
        >>> case = Case.objects.first()
        >>> contract_id = get_fk_id(case, 'contract')  # 返回 int | None
    """
    fk_id_field = f"{field_name}_id"
    return cast(int | None, getattr(instance, fk_id_field, None))


def get_fk_instance(instance: Model, field_name: str) -> Model | None:
    """
    安全地获取 ForeignKey 字段的实例

    Args:
        instance: Model 实例
        field_name: ForeignKey 字段名

    Returns:
        Model | None: 外键实例，如果为 None 则返回 None

    Examples:
        >>> case = Case.objects.first()
        >>> contract = get_fk_instance(case, 'contract')  # Contract | None
    """
    return cast(Model | None, getattr(instance, field_name, None))


def ensure_model_id(model_or_id: Model | int | None) -> int | None:
    """
    确保返回 Model 的 id，无论输入是 Model 实例还是 id

    Args:
        model_or_id: Model 实例、id 或 None

    Returns:
        int | None: Model 的 id，如果输入为 None 则返回 None

    Examples:
        >>> case = Case.objects.first()
        >>> id1 = ensure_model_id(case)  # 返回 case.id
        >>> id2 = ensure_model_id(123)   # 返回 123
        >>> id3 = ensure_model_id(None)  # 返回 None
    """
    if model_or_id is None:
        return None
    if isinstance(model_or_id, int):
        return model_or_id
    if isinstance(model_or_id, Model):
        return cast_model_id(model_or_id)
    return None


def get_model_field_value(instance: Model, field_name: str, default: Any | None = None) -> Any:
    """
    安全地获取 Model 字段值，提供默认值

    Args:
        instance: Model 实例
        field_name: 字段名
        default: 默认值

    Returns:
        Any: 字段值或默认值

    Examples:
        >>> case = Case.objects.first()
        >>> name = get_model_field_value(case, 'name', '未命名')
    """
    return getattr(instance, field_name, default)


def has_model_field(instance: Model, field_name: str) -> bool:
    """
    检查 Model 实例是否有指定字段

    Args:
        instance: Model 实例
        field_name: 字段名

    Returns:
        bool: 是否有该字段

    Examples:
        >>> case = Case.objects.first()
        >>> has_name = has_model_field(case, 'name')  # True
        >>> has_invalid = has_model_field(case, 'invalid_field')  # False
    """
    return hasattr(instance, field_name)


# 特定模型的类型辅助函数


def cast_case_id(case: "Case | None") -> int | None:
    """获取 Case 实例的 id"""
    return cast_model_id(case)


def cast_contract_id(contract: "Contract | None") -> int | None:
    """获取 Contract 实例的 id"""
    return cast_model_id(contract)


def cast_document_template_id(template: "DocumentTemplate | None") -> int | None:
    """获取 DocumentTemplate 实例的 id"""
    return cast_model_id(template)


def cast_folder_template_id(template: "FolderTemplate | None") -> int | None:
    """获取 FolderTemplate 实例的 id"""
    return cast_model_id(template)


def cast_evidence_list_id(evidence_list: "EvidenceList | None") -> int | None:
    """获取 EvidenceList 实例的 id"""
    return cast_model_id(evidence_list)


def cast_generation_task_id(task: "GenerationTask | None") -> int | None:
    """获取 GenerationTask 实例的 id"""
    return cast_model_id(task)
