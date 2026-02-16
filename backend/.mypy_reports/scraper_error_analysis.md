# Scraper 模块类型错误分析报告

## 执行命令
```bash
mypy apps/automation/services/scraper/ --strict
```

## 总体统计
- **总错误数**: 1798 个
- **涉及文件数**: 251 个文件
- **检查文件数**: 38 个源文件

## 错误类型分类统计

### 1. 函数类型注解缺失 (约 200+ 个错误)
- **[no-untyped-def]**: 62 个 - 函数缺少类型注解
- **[no-untyped-call]**: 42 个 - 调用未类型化的函数
- **Function is missing return type**: 51 个 - 函数缺少返回类型注解
- **Function is missing a type annotation**: 43 个 - 函数缺少参数类型注解

**示例错误**:
```
apps/automation/services/scraper/test_service.py:24:5: error: Function is missing a type annotation for one or more arguments
apps/automation/services/scraper/test_service.py:43:5: error: Function is missing a return type annotation
```

**修复策略**: 为所有函数添加完整的类型注解（参数和返回值）

---

### 2. 返回 Any 类型 (约 120+ 个错误)
- **[no-any-return]**: 76 个 - 从声明返回特定类型的函数返回 Any
- **Returning Any from function declared to return**: 42 个

**示例错误**:
```
apps/automation/services/document_delivery/court_document_api_client.py:293:17: error: Returning Any from function declared to return "dict[str, Any]"
apps/automation/services/document_delivery/playwright/document_delivery_playwright_service.py:417:25: error: Returning Any from function declared to return "str"
```

**修复策略**: 使用 `cast()` 或明确类型转换

---

### 3. Django ORM 动态属性错误 (约 90+ 个错误)
- **"CourtSMS" has no attribute**: 59 个
- **"ScraperTask" has no attribute**: 12 个
- **"Case" has no attribute**: 5 个

**示例错误**:
```
apps/automation/services/scraper/scrapers/court_document_download.py:53:12: error: "ScraperTask" has no attribute "case_id"
apps/automation/services/document_delivery/processor/document_delivery_processor.py:133:68: error: "CourtSMS" has no attribute "id"
```

**修复策略**: 
- 使用 `cast()` 处理动态属性
- 创建类型存根文件 (`.pyi`)
- 使用 `getattr()` 避免类型检查

---

### 4. 泛型类型参数缺失 (约 50+ 个错误)
- **[type-arg]**: 33 个 - 缺少泛型类型参数
- **Missing type parameters for generic type "dict"**: 17 个
- **Missing type parameters for generic type "list"**: 10 个

**示例错误**:
```
apps/documents/services/generation/litigation_llm_generator.py:29:45: error: Missing type parameters for generic type "dict"
apps/documents/services/generation/folder_generation_service.py:220:46: error: Missing type parameters for generic type "list"
```

**修复策略**: 
- `dict` → `dict[str, Any]`
- `list` → `list[Any]` 或具体类型

---

### 5. 类型不兼容错误 (约 60+ 个错误)
- **[assignment]**: 37 个 - 赋值类型不兼容
- **[arg-type]**: 20 个 - 参数类型不兼容
- **[return-value]**: 14 个 - 返回值类型不兼容

**示例错误**:
```
apps/automation/services/chat/owner_config_manager.py:130:43: error: Incompatible types in assignment (expression has type "int", target has type "str")
apps/automation/services/document_delivery/processor/document_delivery_processor.py:144:41: error: Incompatible types in assignment (expression has type "int", target has type "str | bool | None")
```

**修复策略**: 修正类型注解或使用类型转换

---

### 6. 变量未定义错误 (约 32 个错误)
- **[name-defined]**: 32 个

**示例错误**:
```
apps/documents/services/placeholders/litigation/defense_party_service.py:111:12: error: Name "is_our" is not defined
apps/documents/services/placeholders/litigation/defense_party_service.py:241:12: error: Name "total" is not defined
```

**修复策略**: 
- 补充缺失的变量定义
- 删除无效代码（如果是遗留代码）

---

### 7. 需要类型注解的变量 (约 16 个错误)
- **[var-annotated]**: 16 个

**示例错误**:
```
apps/documents/services/generation/context_builder.py:265:27: error: Need type annotation for "parties_by_role"
apps/automation/services/chat/feishu_provider.py:797:25: error: Need type annotation for "file_data"
```

**修复策略**: 为变量添加明确的类型注解

---

### 8. 对象属性访问错误 (约 20 个错误)
- **"object" has no attribute**: 20 个

**示例错误**:
```
apps/automation/services/scraper/test_service.py:103:17: error: "object" has no attribute "append"
```

**修复策略**: 为变量添加正确的类型注解，避免推断为 `object`

---

### 9. 其他错误类型
- **[attr-defined]**: 约 100+ 个 - 属性不存在
- **[misc]**: 约 20 个 - 各种杂项错误
- **[index]**: 约 10 个 - 索引错误
- **[union-attr]**: 约 7 个 - 联合类型属性访问

---

## 按模块分类的错误分布

### 高错误模块 (>50 个错误)
1. **document_delivery** - 约 200+ 个错误
   - playwright_service.py
   - document_delivery_service.py
   - api_service.py
   - processor.py

2. **sms** - 约 150+ 个错误
   - submission/sms_submission_service.py
   - stages/*.py
   - matching/*.py

3. **scraper** - 约 100+ 个错误
   - scrapers/court_document_download*.py
   - test_service.py
   - core/*.py

4. **insurance** - 约 80+ 个错误
   - preservation_quote_service.py
   - court_insurance_client.py

5. **documents/services** - 约 150+ 个错误
   - generation/*.py
   - placeholders/litigation/*.py

6. **cases/services** - 约 100+ 个错误
   - party/*.py
   - data/*.py
   - material/*.py

7. **contracts/services** - 约 80+ 个错误
   - contract/*.py
   - payment/*.py

---

## 修复优先级建议

### 高优先级 (快速修复)
1. **泛型类型参数缺失** - 批量替换，风险低
2. **函数返回类型缺失** - 批量添加 `-> None` 或具体类型
3. **变量类型注解缺失** - 添加明确类型注解

### 中优先级 (需要分析)
1. **Django ORM 动态属性** - 使用 cast() 或类型存根
2. **返回 Any 类型** - 使用 cast() 修正
3. **类型不兼容** - 逐个分析修复

### 低优先级 (复杂问题)
1. **变量未定义** - 需要检查代码逻辑
2. **第三方库类型问题** - 使用 type: ignore 或类型存根

---

## 修复策略总结

### 批量修复脚本
1. 泛型类型参数修复
2. 函数返回类型修复
3. 变量类型注解修复

### 手动修复
1. Django ORM 动态属性
2. 变量未定义错误
3. 复杂类型不兼容问题

### 配置调整
1. 在 mypy.ini 中为第三方库添加 ignore_missing_imports
2. 创建常用 Model 的类型存根文件

---

## 下一步行动

1. **执行批量修复脚本** (任务 20.2)
   - 修复泛型类型参数
   - 修复返回类型缺失
   - 为所有函数添加类型注解

2. **修复第三方库类型问题** (任务 20.3)
   - 使用 type: ignore 处理 selenium 类型问题
   - 使用 cast() 处理返回值类型

3. **修复 Django ORM 类型** (任务 20.4)
   - 使用 cast() 处理 Model 动态属性
   - 为 QuerySet 添加泛型参数

4. **修复变量未定义错误** (任务 20.5)
   - 检查并修复 [name-defined] 错误
   - 补充缺失的变量定义或删除无效代码

5. **最终验证** (任务 20.6)
   - 执行 `mypy apps/automation/services/scraper/ --strict`
   - 确认零错误
