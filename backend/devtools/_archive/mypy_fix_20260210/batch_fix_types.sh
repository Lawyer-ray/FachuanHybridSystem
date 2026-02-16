#!/bin/bash

# 批量修复 services 层的类型注解错误

echo "=== 开始批量修复类型错误 ==="

# 1. 修复 any -> Any
echo "1. 修复 any -> Any..."
find apps/*/services/ -name "*.py" -type f -exec grep -l ": any" {} \; | while read file; do
    # 检查是否已经导入 Any
    if ! grep -q "from typing import.*Any" "$file" && ! grep -q "from typing import Any" "$file"; then
        # 在第一个 import 后添加 Any 导入
        sed -i '' '1,/^from\|^import/s/^\(from\|import\)/from typing import Any\n\1/' "$file"
    fi
    # 替换 any 为 Any
    sed -i '' 's/: any/: Any/g' "$file"
    sed -i '' 's/, any/, Any/g' "$file"
    echo "  修复: $file"
done

# 2. 修复 __init__ 缺少 -> None
echo "2. 修复 __init__ 缺少 -> None..."
find apps/*/services/ -name "*.py" -type f -exec grep -l "def __init__" {} \; | while read file; do
    # 只修复没有返回类型注解的 __init__
    sed -i '' 's/def __init__(\(.*\)):$/def __init__(\1) -> None:/g' "$file"
    echo "  修复: $file"
done

# 3. 修复空列表和空字典的类型注解
echo "3. 修复空列表和空字典的类型注解..."
find apps/*/services/ -name "*.py" -type f | while read file; do
    # 修复 var = []
    sed -i '' 's/\([a-zA-Z_][a-zA-Z0-9_]*\) = \[\]/\1: list = []/g' "$file"
    # 修复 var = {}
    sed -i '' 's/\([a-zA-Z_][a-zA-Z0-9_]*\) = {}/\1: dict = {}/g' "$file"
done

echo "=== 批量修复完成 ==="
echo ""
echo "运行 mypy 检查剩余错误..."
./venv312/bin/python -m mypy --config-file mypy.ini apps/automation/services/ apps/cases/services/ apps/client/services/ apps/contracts/services/ apps/documents/services/ 2>&1 | grep "Found"
