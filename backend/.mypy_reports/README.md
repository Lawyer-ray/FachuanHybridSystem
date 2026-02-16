# Backend

本目录包含后端 Django 项目代码（`apiSystem/`）与各业务应用（`apps/`），以及集中化测试（`tests/`）与工具脚本（`scripts/`）。

## 版本基线

- Python: 3.12（CI 默认使用），本地建议同版本以避免环境差异
- Django: 6.0.x（见 requirements.txt）
- 数据库: SQLite（默认），通过 `DATABASE_PATH` 指定路径

## 快速启动（本地）

1) 初始化环境变量

```bash
cp .env.example .env
```

2) 安装依赖

```bash
make VENV_DIR=.venv venv
source .venv/bin/activate
make VENV_DIR=.venv install-dev
```

如不使用 Makefile，可手动安装（效果一致）：
```bash
python -m pip install -U pip
python -m pip install -r requirements.txt -r requirements-dev.txt -r requirements-test.txt -c constraints/py312.txt
```

启动开发服务（带热重载）：
```bash
make VENV_DIR=.venv run-dev
```
3) 数据库迁移与创建管理员

```bash
python apiSystem/manage.py migrate
python apiSystem/manage.py createsuperuser
```

4) 启动服务

```bash
python apiSystem/manage.py runserver 0.0.0.0:8000
```

如需 WebSocket/ASGI（Channels），可使用 Makefile 的 daphne 启动方式（见 `make help`）。

5) 启动异步任务（可选）

```bash
python apiSystem/manage.py qcluster
```

## 常用命令

- 运行测试（推荐明确指定配置，避免不同工作目录拾取到不同 pytest.ini）

```bash
pytest -c pytest.ini --no-cov
```

- 仅跑结构门禁用例（CI 也使用这组）

```bash
pytest -c pytest.ini --no-cov -q \
  tests/structure/test_admin_organization_properties.py \
  tests/structure/test_api_organization_properties.py \
  tests/structure/test_cross_module_import_properties.py \
  tests/structure/test_documents_api_no_contracts_services_imports.py \
  tests/structure/test_case_service_adapter_no_model_objects.py \
  tests/structure/test_case_service_adapter_no_orm_writes.py
```

- 代码质量（本地）

```bash
pre-commit run --all-files
```

- 类型检查（mypy）

```bash
# 检查所有应用代码
mypy apps/

# 检查特定模块
mypy apps/cases/
mypy apps/contracts/services/

# 使用缓存加速（增量检查）
mypy apps/ --incremental
```

## 配置矩阵（启动必需 vs 业务可变）

- 启动必需：`.env`（示例见 `.env.example`）
- 业务可变：Admin 后台 -> 核心系统 -> 系统配置（热更新/动态配置）
- 生产安全开关：`apiSystem/settings.py` 中以 `DEBUG`/环境变量为开关的安全策略（HSTS、Secure cookies、SSL redirect 等）

## 生产/部署建议（要点）

- 反向代理限制：建议在 Nginx/Ingress 配置 `client_max_body_size` 并与 `DJANGO_DATA_UPLOAD_MAX_MEMORY_SIZE_MB` 对齐
- 日志：默认支持结构化日志字段（request_id/trace_id），生产建议集中收集 stdout/stderr
- 健康检查：`/api/v1/health`、`/api/v1/health/ready`、`/api/v1/health/live`
- 数据库：默认 SQLite；生产建议使用 Postgres（`DB_ENGINE=postgres`），容器可使用 `deploy/docker/docker-compose.yml` + `deploy/docker/docker-compose.postgres.yml`

## CI 与门禁

- 已提供 GitHub Actions：`.github/workflows/backend-ci.yml`
- 建议在 GitHub 开启 Branch Protection，要求 workflow checks 通过后才能合并到主分支

## 目录约定（补充）

- 类型检查配置：`mypy.ini`（固定入口，保留在 backend 根目录）
- 类型检查报告/快照：`docs/typecheck/reports/`（一次性输出请放这里，避免污染根目录）
- 开发工具脚本：`devtools/`（例如 `devtools/typecheck/cleanup_mypy_ignores.py`）
- 容器化入口：`deploy/docker/`（Dockerfile、docker-compose）

## 类型检查（Mypy）

本项目使用 mypy 进行静态类型检查，确保代码类型安全。所有新代码必须通过 `mypy --strict` 检查。

### 配置说明

mypy 配置位于 `backend/mypy.ini`，主要配置项：

- **Python 版本**: 3.12
- **严格模式**: 启用 `disallow_untyped_defs`、`disallow_incomplete_defs`
- **警告**: 启用返回值类型检查、未使用配置警告等
- **第三方库**: 自动忽略缺少类型注解的第三方库（如 rapidocr、selenium、PIL）

### 运行类型检查

```bash
# 检查所有应用代码
mypy apps/

# 检查特定模块
mypy apps/cases/
mypy apps/contracts/services/

# 使用缓存加速（增量检查）
mypy apps/ --incremental

# 生成详细报告
mypy apps/ --strict > typecheck_report.txt
```

### 处理类型错误

#### 1. 函数类型注解

所有函数必须包含完整的参数和返回值类型注解：

```python
# ❌ 错误：缺少类型注解
def process_data(data):
    return data.strip()

# ✅ 正确：完整类型注解
def process_data(data: str) -> str:
    return data.strip()

# ✅ 正确：无返回值使用 None
def log_message(message: str) -> None:
    logger.info(message)
```

#### 2. 泛型类型参数

dict、list 等泛型类型必须指定类型参数：

```python
# ❌ 错误：缺少类型参数
def get_config() -> dict:
    return {"key": "value"}

# ✅ 正确：指定类型参数
from typing import Any

def get_config() -> dict[str, Any]:
    return {"key": "value"}

# ✅ 更好：使用具体类型
def get_ids() -> list[int]:
    return [1, 2, 3]
```

#### 3. Django ORM 动态属性

Django Model 的动态属性（如 id、created_at）需要特殊处理：

```python
from typing import cast
from django.db.models import QuerySet

# 方案 A：使用 cast() 类型转换
def get_case_id(case: Case) -> int:
    return cast(int, case.id)

# 方案 B：使用 getattr() 避免类型检查
def get_case_id(case: Case) -> int:
    return getattr(case, 'id')

# 方案 C：QuerySet 添加泛型参数
def get_active_cases() -> QuerySet[Case]:
    return Case.objects.filter(status='active')
```

#### 4. 可选类型

使用 `| None` 语法表示可选类型（Python 3.10+）：

```python
# ✅ 推荐：使用 | None
def find_user(user_id: int) -> User | None:
    try:
        return User.objects.get(id=user_id)
    except User.DoesNotExist:
        return None

# ✅ 也可以：使用 Optional（需要导入）
from typing import Optional

def find_user(user_id: int) -> Optional[User]:
    ...
```

#### 5. 第三方库类型问题

对于缺少类型注解的第三方库，已在 `mypy.ini` 中配置忽略：

```python
# 这些库已配置 ignore_missing_imports = True
from rapidocr_onnxruntime import RapidOCR  # 自动忽略
from selenium import webdriver  # 自动忽略
from PIL import Image  # 自动忽略
```

如需为新的第三方库添加忽略，在 `mypy.ini` 中添加：

```ini
[mypy-library_name.*]
ignore_missing_imports = True
```

### CI 集成

类型检查已集成到 CI 流程中：

- **Pre-commit Hook**: 提交前自动运行 mypy 检查
- **GitHub Actions**: PR 合并前必须通过类型检查
- **失败处理**: 类型检查失败会阻止代码合并

### 常见问题

**Q: mypy 检查太慢怎么办？**

A: 使用增量检查和缓存：
```bash
mypy apps/ --incremental --cache-dir=.mypy_cache
```

**Q: 如何临时忽略某行的类型错误？**

A: 使用 `# type: ignore` 注释（仅在必要时使用）：
```python
result = some_untyped_function()  # type: ignore
```

**Q: 如何查看某个模块的类型检查状态？**

A: 检查 `mypy.ini` 中是否有该模块的 `ignore_errors = True` 配置。

**Q: 新增模块需要配置 mypy 吗？**

A: 不需要。所有 `apps/` 下的新模块会自动包含在类型检查范围内。
