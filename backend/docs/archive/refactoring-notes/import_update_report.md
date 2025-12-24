# 导入路径更新报告

生成时间: 2025-12-01 20:22:31

## 统计信息

- 扫描文件数: 287
- 更新文件数: 2
- 更新总数: 2

## 更新模式统计

- factories_imports: 2 处

## 详细更新列表

### apps/tests/utils.py

更新数: 1

**行 20** [factories_imports]

```python
# 旧:
from apps.tests.factories import LawyerFactory
# 新:
from tests.factories import LawyerFactory
```

### tests/admin/scripts/create_test_data.py

更新数: 1

**行 16** [factories_imports]

```python
# 旧:
from apps.tests.factories import (
# 新:
from tests.factories import (
```
