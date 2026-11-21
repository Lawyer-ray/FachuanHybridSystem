"""表格几何的开关：总开关 / 均分回退开关 / 一次读两个（SystemConfig）。

## 这个文件只放什么 / 不许放什么

只放**读开关**这一件事：键名、``_as_flag`` 取值解析、读不到时的默认值与留痕。

**不许放**几何数学或任何 IO（不 import fitz、不碰 PDF/引擎/网络），也不许放产物拼装——
那两件事在 ``table_geometry.py``（纯数学）与 ``table_geometry_pass.py``（pass）。
本文件唯一的应用依赖是 ``SystemConfigService``，且**延迟到函数内 import**：``apps.core``
依赖 Django，模块级引入会让「只想读一个布尔」的调用方也背上 Django 的导入成本。

## 为什么这三个函数必须在一起

三个 ``build_segments_markdown`` 调用点都只调 ``switches()``（理由见它自己的 docstring）：
分别读两个键迟早会出现「某一条路径读了回滚开关、另一条没读」的劈叉。

## L2 开关为什么不进 ``switches()``

``local_lines_enabled()`` 是**几何来源**的选择（本地线条兜底），不是``build_segments_markdown``
的定位策略，只被几何 pass 的调用点读一次。把它塞进 ``switches()`` 的返回元组会改动三个
调用点的解包（它们只要 ``(enabled, legacy_uniform)``），是纯粹的形状破坏。
"""

from __future__ import annotations

import logging

logger = logging.getLogger("apps.pdf_splitting")


#: 几何 pass 总开关（SystemConfig；默认开）。关掉后不调用引擎、不写产物。
TABLE_GEOMETRY_ENABLED_KEY = "PDF_SPLIT_TABLE_GEOMETRY_ENABLED"

#: 回滚开关（SystemConfig；默认关）：几何缺失时是否退回旧的「行列均分」框。
#:
#: 默认关 = 缺几何就整表框 —— 均分不可能用任何便宜判据证明可靠（列宽离散度拿不到），
#: 留着它等于留着一个已知会指错地方的路径（DESIGN §1）。
TABLE_UNIFORM_FALLBACK_KEY = "PDF_SPLIT_TABLE_UNIFORM_FALLBACK"

#: L2 本地线条兜底开关（SystemConfig；默认关）。
#:
#: 默认关的理由是**实测**：本卷宗 22 个候选页里 PP 漏检的那 7 页 ``no_table_detected``，
#: 本地线条一页也救不了（4 页银行流水无印刷框线、1 页标签:值清单、1 页只有横线的手写表单、
#: 1 页整页旋转 90° → 0/7）。它的价值在**另一类卷宗**：有印刷框线但 PP 不出表 / 服务不可用。
#: 所以开关用于这类卷宗，开启前先看一眼 summary 的 ``raster_lines_matched`` 计数
#: （``table_geometry_pass.summary_block`` 恒给这个键，关着时是 0）。
TABLE_GEOMETRY_LOCAL_LINES_KEY = "PDF_SPLIT_TABLE_GEOMETRY_LOCAL_LINES_ENABLED"


def geometry_enabled() -> bool:
    """``PDF_SPLIT_TABLE_GEOMETRY_ENABLED``（默认 ``1``）。"""
    return _as_flag(_system_value(TABLE_GEOMETRY_ENABLED_KEY, "1"), default=True)


def uniform_fallback_enabled() -> bool:
    """``PDF_SPLIT_TABLE_UNIFORM_FALLBACK``（默认 ``0``）。"""
    return _as_flag(_system_value(TABLE_UNIFORM_FALLBACK_KEY, "0"), default=False)


def local_lines_enabled() -> bool:
    """``PDF_SPLIT_TABLE_GEOMETRY_LOCAL_LINES_ENABLED``（默认 ``0``）。

    关着时几何 pass 一个字节都不多写（不渲染页图、不跑 L2）：开关的默认值就是「今天的行为」。
    理由与适用卷宗见 ``TABLE_GEOMETRY_LOCAL_LINES_KEY`` 的注释。
    """
    return _as_flag(_system_value(TABLE_GEOMETRY_LOCAL_LINES_KEY, "0"), default=False)


def switches() -> tuple[bool, bool]:
    """一次读两个开关 → ``(enabled, legacy_uniform)``。

    三个 ``build_segments_markdown`` 调用点都只调这一个函数：分别读两个键迟早会
    出现“某一条路径读了回滚开关、另一条没读”的劈叉，而那种劈叉的表现是
    “同一份卷宗在不同入口的绿框不一样”。
    """
    return geometry_enabled(), uniform_fallback_enabled()


def _system_value(key: str, default: str) -> str:
    """读 SystemConfig 的一个开关值；读不到就回落默认值并留痕，绝不抛。

    两条理由解释了为什么这里必须收 ``RuntimeError``（而**不是**兜住所有异常的最宽写法）：

    1. pytest-django 在没打 ``django_db`` 的用例里用
       ``RuntimeError("Database access not allowed")`` 拒绝访问；``analyze_pdf`` 那类
       端到端用例本来就不该为了读一个开关去开库，只收少数具体类型会让它们整条链挂掉。
    2. 开关是运维的「停用按钮」：读不出来时应该走默认路径继续干活，而不是让整条分段链
       挂掉——比 ``RuntimeError`` 更宽的类型仍然不许（pre-commit 的 broad-except 棘轮）。

    延迟 import（``apps.core`` 依赖 Django）：模块级引入会让「只想读一个布尔」的调用方
    也背上 Django 的导入成本。
    """
    try:
        from apps.core.services.system_config_service import SystemConfigService

        return str(SystemConfigService().get_value(key, default) or "")
    except (ImportError, AttributeError, ValueError, TypeError, RuntimeError):
        logger.warning("pdf_split_table_geometry_config_unreadable", extra={"key": key})
        return default


def _as_flag(raw: str, *, default: bool) -> bool:
    """``"1"/"true"/"yes"/"on"`` → True；``"0"/"false"/"no"/"off"`` → False；空串/怪值用默认。"""
    value = raw.strip().lower()
    if not value:
        return default
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    return default
