"""
Core utilities module

提供统一的工具类,供各模块使用.
"""

from .id_card_utils import IdCardInfo, IdCardUtils

__all__ = [
    "IdCardInfo",
    "IdCardUtils",
    "cast_model_id",
    "cast_model_pk",
    "get_queryset",
    "get_related_manager",
    "get_related_queryset",
    "cast_queryset",
    "cast_manager",
    "get_fk_id",
    "get_fk_instance",
    "ensure_model_id",
    "get_model_field_value",
    "has_model_field",
]
