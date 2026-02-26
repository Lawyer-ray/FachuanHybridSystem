# Documents Services 重构规划

## 一、当前状态分析

### 1.1 目录结构概览

```
services/ (共50个文件)
├── 根目录散落文件: 30个
│   ├── evidence_service.py
│   ├── evidence_query_service.py
│   ├── evidence_admin_service.py
│   ├── evidence_export_service.py
│   ├── evidence_storage.py
│   ├── evidence_list_placeholder_service.py
│   ├── placeholder_service.py
│   ├── placeholder_admin_service.py
│   ├── placeholder_usage_service.py
│   ├── template_service.py
│   ├── template_matching_service.py
│   ├── document_template_query_service.py
│   ├── document_template_admin_service.py
│   ├── document_template_dto_assembler.py
│   ├── contract_template_query_service.py
│   ├── contract_template_binding_service.py
│   ├── folder_template_admin_service.py
│   ├── folder_service.py
│   ├── generation_service.py
│   ├── pdf_utils.py
│   ├── pdf_merge_service.py
│   ├── pdf_merge_utils.py
│   ├── wiring.py
│   └── ...
│
├── 子文件夹: 6个 (共74个文件)
│   ├── generation/         (18个)
│   ├── placeholders/       (28个)
│   ├── document_template/  (7个)
│   ├── folder_template/    (9个)
│   ├── evidence/          (5个)
│   └── external_template/ (4个)
```

### 1.2 问题诊断

| 问题类型 | 具体表现 | 影响 |
|---------|---------|------|
| **职责分散** | evidence 相关功能散落在根目录和 evidence/ 文件夹 | 难以定位和维护 |
| **层级不一致** | 模板相关服务有 document_template/ 和 folder_template/，但 contract_template_query_service.py 在根目录 | 违反单一职责 |
| **命名冗余** | evidence_service.py 和 evidence/evidence_mutation_service.py 并存 | 功能边界不清 |
| **辅助工具散落** | pdf_utils.py, wiring.py 等基础设施在根目录 | 基础设施未归类 |

---

## 二、重构目标

1. **统一组织逻辑**: 按业务模块分包，不再散落
2. **消除冗余**: 合并功能重复的文件
3. **保持兼容**: 通过 `__init__.py` 导出确保现有导入不变
4. **提升可维护性**: 让目录结构直观反映业务领域

---

## 三、具体重构方案

### 3.1 目标目录结构

```
services/
├── evidence/                    # 证据模块（整合）
│   ├── __init__.py              # 合并导出
│   ├── evidence_service.py     # 从根目录移入
│   ├── evidence_query_service.py
│   ├── evidence_admin_service.py
│   ├── evidence_export_service.py
│   ├── evidence_storage.py
│   ├── evidence_list_placeholder_service.py
│   └── evidence/                # 保留原子文件夹
│       ├── __init__.py
│       ├── evidence_file_service.py
│       ├── evidence_mutation_service.py
│       ├── evidence_query_service.py
│       ├── evidence_merge_usecase.py
│       └── page_range_calculator.py
│
├── placeholders/                # 占位符模块（已有结构）
│   ├── __init__.py              # 新增根目录导出
│   ├── placeholder_service.py  # 从根目录移入
│   ├── placeholder_admin_service.py
│   ├── placeholder_usage_service.py
│   ├── base.py
│   ├── registry.py
│   ├── types.py
│   ├── context_builder.py
│   └── authorization_materials/ ...
│   └── basic/ ...
│   └── case/ ...
│   └── contract/ ...
│   └── lawyer/ ...
│   └── litigation/ ...
│   └── party/ ...
│   └── supplementary/ ...
│
├── template/                    # 模板模块（整合）
│   ├── __init__.py
│   ├── template_service.py     # 从根目录移入
│   ├── template_matching_service.py
│   ├── template_audit_log_service.py
│   ├── document_template/      # 保留
│   │   ├── __init__.py
│   │   ├── repo.py
│   │   ├── query_service.py    # 从根目录移入
│   │   ├── admin_service.py     # 从根目录移入
│   │   ├── dto_assembler.py    # 从根目录移入
│   │   └── ...
│   ├── folder_template/        # 保留
│   │   ├── __init__.py
│   │   ├── admin_service.py    # 从根目录移入
│   │   └── ...
│   └── contract_template/
│       ├── __init__.py
│       ├── query_service.py    # 从根目录移入
│       └── binding_service.py  # 从根目录移入
│
├── generation/                  # 文档生成模块（已有结构）
│   ├── __init__.py
│   ├── generation_service.py   # 从根目录移入
│   └── ...
│
├── infrastructure/              # 基础设施模块（新建）
│   ├── __init__.py
│   ├── pdf_utils.py           # 从根目录移入
│   ├── pdf_merge_utils.py     # 从根目录移入
│   ├── pdf_merge_service.py   # 从根目录移入
│   ├── wiring.py              # 从根目录移入
│   └── path_utils.py          # 建议从 generation/ 移入
│
└── code_placeholders/           # 代码占位符模块（整合）
    ├── __init__.py
    ├── registry.py            # 从根目录移入
    ├── catalog_service.py     # 从根目录移入
    ├── autodiscover.py        # 从根目录移入
    └── adapter.py             # prompt_version_service_adapter.py 重命名
```

### 3.2 文件移动清单

#### 移动到 evidence/

| 原路径 | 新路径 | 备注 |
|--------|--------|------|
| `evidence_service.py` | `evidence/evidence_service.py` | |
| `evidence_query_service.py` | `evidence/evidence_query_service.py` | 与子文件夹内重名，需合并 |
| `evidence_admin_service.py` | `evidence/evidence_admin_service.py` | |
| `evidence_export_service.py` | `evidence/evidence_export_service.py` | |
| `evidence_storage.py` | `evidence/evidence_storage.py` | |
| `evidence_list_placeholder_service.py` | `evidence/evidence_list_placeholder_service.py` | |

#### 移动到 placeholders/

| 原路径 | 新路径 | 备注 |
|--------|--------|------|
| `placeholder_service.py` | `placeholders/placeholder_service.py` | |
| `placeholder_admin_service.py` | `placeholders/placeholder_admin_service.py` | |
| `placeholder_usage_service.py` | `placeholders/placeholder_usage_service.py` | |

#### 移动到 template/

| 原路径 | 新路径 | 备注 |
|--------|--------|------|
| `template_service.py` | `template/template_service.py` | |
| `template_matching_service.py` | `template/template_matching_service.py` | |
| `template_audit_log_service.py` | `template/template_audit_log_service.py` | |
| `document_template_query_service.py` | `template/document_template/query_service.py` | |
| `document_template_admin_service.py` | `template/document_template/admin_service.py` | |
| `document_template_dto_assembler.py` | `template/document_template/dto_assembler.py` | |
| `folder_template_admin_service.py` | `template/folder_template/admin_service.py` | |
| `contract_template_query_service.py` | `template/contract_template/query_service.py` | |
| `contract_template_binding_service.py` | `template/contract_template/binding_service.py` | |

#### 移动到 infrastructure/

| 原路径 | 新路径 | 备注 |
|--------|--------|------|
| `pdf_utils.py` | `infrastructure/pdf_utils.py` | |
| `pdf_merge_utils.py` | `infrastructure/pdf_merge_utils.py` | |
| `pdf_merge_service.py` | `infrastructure/pdf_merge_service.py` | |
| `wiring.py` | `infrastructure/wiring.py` | |

#### 移动到 code_placeholders/

| 原路径 | 新路径 | 备注 |
|--------|--------|------|
| `code_placeholder_registry.py` | `code_placeholders/registry.py` | |
| `code_placeholder_catalog_service.py` | `code_placeholders/catalog_service.py` | |
| `code_placeholder_autodiscover.py` | `code_placeholders/autodiscover.py` | |
| `prompt_version_service_adapter.py` | `code_placeholders/adapter.py` | |

#### 移动到 generation/

| 原路径 | 新路径 | 备注 |
|--------|--------|------|
| `generation_service.py` | `generation/generation_service.py` | |

#### 移动到根目录（保留 `folder_service.py）

-` - 文件夹服务（业务逻辑较独立）
- `document_service_adapter.py` - 外部适配器（需要保持在根目录供外部调用）

---

## 四、兼容性保障

### 4.1 使用 __init__.py 维持向后兼容

在每个模块的 `__init__.py` 中重新导出原有路径的类/函数，确保以下导入方式仍然有效：

```python
# 旧导入方式（保持兼容）
from apps.documents.services import EvidenceService
from apps.documents.services import PlaceholderService

# 新导入方式（推荐）
from apps.documents.services.evidence import EvidenceService
from apps.documents.services.placeholders import PlaceholderService
```

### 4.2 兼容性导出示例

```python
# services/evidence/__init__.py
from .evidence_service import EvidenceService
from .evidence_query_service import EvidenceQueryService
from .evidence_admin_service import EvidenceAdminService

__all__ = [
    "EvidenceService",
    "EvidenceQueryService", 
    "EvidenceAdminService",
    # 兼容旧导入
]
```

---

## 五、实施步骤

### 阶段一：创建新目录结构（无风险）

1. 创建 `template/` 目录
2. 创建 `template/document_template/`, `template/folder_template/`, `template/contract_template/` 子目录
3. 创建 `infrastructure/` 目录
4. 创建 `code_placeholders/` 目录

### 阶段二：移动文件并更新导入（低风险）

按模块顺序执行：

1. **移动 infrastructure/** - 基础设施，依赖最少
2. **移动 code_placeholders/** - 基础设施之上，依赖较少
3. **移动 template/** - 模板相关
4. **移动 evidence/** - 证据相关
5. **移动 placeholders/** - 占位符相关
6. **移动 generation/** - 生成相关

每个模块完成后：
- 更新该模块内的相对导入
- 更新 `__init__.py` 导出
- 运行测试确保功能正常

### 阶段三：清理与验证（收尾）

1. 删除不再需要的旧文件
2. 更新外部调用方的导入路径（可选，保持兼容则跳过）
3. 运行完整测试套件
4. 更新相关文档

---

## 六、风险评估与缓解

| 风险 | 级别 | 缓解措施 |
|------|------|----------|
| 外部调用方导入路径失效 | 高 | 使用 `__init__.py` 保持向后兼容 |
| 循环依赖 | 中 | 移动前分析依赖图，按正确顺序执行 |
| 测试失败 | 中 | 每阶段完成后运行测试，及时发现问题 |
| 合并冲突 | 低 | 使用 IDE 重构功能，避免手动移动 |

---

## 七、预计工作量

| 阶段 | 工作内容 | 预估文件数 |
|------|----------|-----------|
| 阶段一 | 创建目录 | 4个目录 |
| 阶段二 | 移动并修复导入 | 约25个文件 |
| 阶段三 | 清理与验证 | - |

---

## 八、建议执行顺序

1. **先创建新目录结构**（创建空目录和 `__init__.py`）
2. **按依赖顺序移动文件**：基础设施 → 代码占位符 → 模板 → 证据 → 占位符 → 生成
3. **每移动一个模块，同时更新该模块的 `__init__.py`**
4. **保持根目录的 `__init__.py` 导出所有公共接口**
5. **最后进行清理和验证**

---

## 附录：依赖关系图（简略）

```
infrastructure/          ← 无依赖
    ↑
code_placeholders/       ← 依赖 infrastructure
    ↑
placeholders/            ← 依赖 code_placeholders
    ↑
generation/              ← 依赖 placeholders, infrastructure
    ↑
template/                ← 依赖 placeholders
    ↑
evidence/                ← 依赖 placeholders
```
