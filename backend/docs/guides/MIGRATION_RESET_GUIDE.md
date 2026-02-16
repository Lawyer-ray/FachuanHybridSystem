# 迁移清空与重建指南（上线前重置用）

本指南只适用于“上线时使用全新数据库”的场景：你计划在上线前清空迁移文件并重新生成 initial migrations。

## 何时可以清空迁移

- ✅ 可以：上线前**新建全新数据库**（或直接删库重建），并且不需要保留任何历史数据。
- ❌ 不建议：需要保留生产数据、或已有环境需要增量升级。此时应使用 squash（压缩迁移）或继续追加迁移。

## 推荐的安全流程（新库重建）

1. 确保环境变量指向一个全新的数据库（sqlite 用 `DATABASE_PATH`，其他数据库用对应连接串）。
2. 删除各 app 的历史迁移文件（保留 `migrations/__init__.py`）。
3. 在项目根目录执行：
   - `python manage.py makemigrations`
   - `python manage.py migrate`
4. 跑一次冒烟（建议使用 `python manage.py smoke_check`）。

## 特别注意：跨 app 复用表名会导致迁移“互相踩脚”

当前存在一个跨 app 复用同一张表的设计：

- `litigation_ai.LitigationSession` 显式指定了 `db_table = "documents_litigationsession"`（见 `apps/litigation_ai/models/session.py`）。

这意味着：如果你清空迁移并重建，很容易出现“两个 app 都想创建/管理同一张表”的情况，导致：

- 一方迁移以为表不存在（去创建）但实际上已存在；
- 或一方迁移以为表存在（去加索引）但表还没创建；
- 进而出现 `no such table` / `table already exists` 等问题。

### 重建时的硬性规则（必须满足其一）

- 规则 A（推荐）：**只有一个 app 的迁移负责创建这张表**，另一个 app 只保留“状态”或根本不声明该模型的建表迁移。
- 规则 B：彻底消除复用表名，让 `litigation_ai` 的表名归到自己的命名空间（例如 `litigation_ai_litigationsession`），然后用一次迁移完成重命名（仅适用于你愿意改表名且新库可直接建新表）。

如果你上线时“确定是新库”，规则 B 最省事：直接改成新表名，然后生成新的 initial migrations 即可。

## 迁移清空后，建议做的最小校验

- `python manage.py check`
- `python manage.py makemigrations --check --dry-run`
- `python manage.py migrate`
- `python manage.py smoke_check`

