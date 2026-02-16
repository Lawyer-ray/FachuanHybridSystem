# 架构违规报告

扫描时间: 2026-02-11 12:25:45

## 总览

违规总数: **1**

### 按类型统计

| 类型 | 数量 |
| --- | --- |
| service_cross_module_import | 1 |

### 按严重程度统计

| 严重程度 | 数量 |
| --- | --- |
| high | 1 |

## 详细违规列表

### service_cross_module_import (1个)

- **/Users/huangsong21/Downloads/Coding/AI/FachuanHybridSystem/backend/apps/contracts/services/contract_admin_service.py** (行 113)
  - 严重程度: high
  - 描述: Service层跨模块Model导入: from apps.cases.models import Case, CaseParty, CaseAssignment, SimpleCaseType
  - 代码片段:
    ```python
    from apps.cases.models import Case, CaseParty, CaseAssignment, SimpleCaseType
    ```
