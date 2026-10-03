# FachuanHybridSystem · backend

> ⚠️ 本文件由助手重建(2026-10-02):原 README.md 意外被覆盖且未被 git 跟踪,内容无法恢复。
> 以下为基于仓库事实的最小索引;若你记得原文有其他内容,请补充或从备份恢复后删除本段。

Django 6.1 + Django Ninja + Django-Q2 的法律服务后端(法穿 AI Copilot)。

## 快速开始

```bash
# 开发服务(8002)
cd backend/apiSystem && ../.venv/bin/python manage.py runserver 0.0.0.0:8002
# 本地 CI(ruff+mypy+bandit+pip-audit 等)——make ci/ci-full 在仓库根目录执行；backend/ 下另有镜像远端 CI 的 make ci-check
make ci          # 快速(无数据库)
make ci-full     # 完整(需 PostgreSQL)
# 容器栈(postgres16 + valkey + web + qcluster)——compose 文件在 backend/
cd backend && docker compose up
```

## 结构

- `apiSystem/` — Django 根(settings / urls / manage.py)
- `apps/` — 业务应用(cases、contracts、client、organization、reminders、materials、contract_review、automation、finance、evidence、doc_convert …各 app 有自己的 README，清单以 settings.py / api.py 注册为准)
- `plugins/` — git 子模块(改动需先 PR plugins 再更新指针)
- `tests/` — 测试;`scripts/` — 本地 CI 与工具脚本

规范唯一权威来源:`backend/CLAUDE.md`(四层架构、分支纪律、迁移纪律、批量脚本红线等)。
