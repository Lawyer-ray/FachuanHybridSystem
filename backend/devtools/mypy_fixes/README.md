# mypy 修复脚本（归档入口）

历史上为快速推进 mypy 严格模式下的存量整改，曾在 `backend/` 根目录生成并使用过一批 `fix_*.py` 脚本。

这些脚本已统一归档到：

- `backend/devtools/_archive/mypy_fix_20260210/`

如确需查看或执行（不推荐在不清楚副作用时直接运行），可以在 `backend/` 目录下使用：

```bash
python -m devtools.mypy_fixes list
python -m devtools.mypy_fixes path fix_services_targeted.py
python -m devtools.mypy_fixes run fix_services_targeted.py --dangerously-run -- [args...]
```
