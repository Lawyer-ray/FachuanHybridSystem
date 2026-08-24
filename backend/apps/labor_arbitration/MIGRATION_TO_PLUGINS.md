# 迁移指南：labor_arbitration → plugins

本文说明如何把 `apps/labor_arbitration/` 这个 Django app 迁移到 `plugins/`，遵循项目既有的插件架构（以 `message_hub` 为范例）。

## 一、先理解项目的插件架构（关键前提）

`backend/plugins/` 是一个**独立的 git submodule**（`backend/plugins` → `https://github.com/Lawyer-ray/FachuanPlugins.git`，branch `main`），**不在 `INSTALLED_APPS` 里**，通过 `plugins/__init__.py` 的 `has_xxx_plugin()` 动态检测、可选加载。

项目对「app + 插件」的分层惯例是**数据与逻辑分离**（`message_hub` 就是已完成的范例）：

| 层 | 位置 | 内容 | 是否在 INSTALLED_APPS |
|---|---|---|---|
| **数据层** | `apps/{name}/` | `models/` + `migrations/` + `apps.py`（AppConfig）+ `admin/__init__.py`（留空转发） | ✅ 是 |
| **逻辑层** | `plugins/{name}/` | `services/` + `admin/`（Admin 类）+ `api/` + `tasks.py` + `templates/` + `static/` | ❌ 否 |

对照 `message_hub`：
- `apps/message_hub/`：`models/`、`migrations/0001~0009`、`apps.py`（`ready()` 转发 plugins 的 `_register_schedule`）、`admin/__init__.py`（仅一行注释「已迁移到 plugins」）。
- `plugins/message_hub/`：`admin/`、`services/`、`api/`、`tasks.py`、`templates/`、`static/`。

**三个关键机制**：
1. **admin 注册**：plugins 里的 Admin 类用 `@admin.register(Model)` 装饰器；主项目在 `apiSystem/apiSystem/admin_customization.py`（约 576 行）里显式 `import plugins.xxx.admin` 触发注册（因为 plugins 不在 INSTALLED_APPS，Django 的 `autodiscover` 不会自动加载）。
2. **templates/static**：在 `settings.py` 里用 `has_xxx_plugin()` 检测后，显式把 plugins 的 `templates`/`static` 目录追加进 `TEMPLATE_DIRS`/`STATICFILES_DIRS`。
3. **可选检测**：`plugins/__init__.py` 增加 `has_labor_arbitration_plugin()`，主项目可据此判断插件是否安装、做降级。

## 二、labor_arbitration 现状与依赖

`apps/labor_arbitration/` 是一个**完整 app**（models + migrations + admin + services + tasks + 管理命令），迁移前需要先理清两类引用：

**跨 app 依赖（迁移后保持不变，仍是主项目 app）**：
- `apps.document_parsing.services` → `get_document_parser`
- `apps.core.tasking` → `submit_task`
- `apps.core.filesystem.upload_paths` → `DatedUUIDPath`、`MediaEntity`

**自引用 dotted path（字符串，需手改，共 3 处）**：
| 文件:行 | 现值 | 迁移后 |
|---|---|---|
| `models/source.py:108` | `apps.labor_arbitration.tasks.crawl_source` | `plugins.labor_arbitration.tasks.crawl_source` |
| `models/document.py:98` | `apps.labor_arbitration.tasks.parse_document` | `plugins.labor_arbitration.tasks.parse_document` |
| `models/document.py:113` | `apps.labor_arbitration.tasks.recrawl_document` | `plugins.labor_arbitration.tasks.recrawl_document` |

> 这三处是 `submit_task()` 的**字符串参数**，`import` 不会被 IDE/工具自动改，漏改会导致后台任务找不到函数（`module not found`）。

## 三、推荐方案：按 message_hub 模式「拆分迁移」

**保留在 `apps/labor_arbitration/`（数据层）**：
- `models/`（`source.py` / `document.py` / `signals.py` / `__init__.py`）
- `migrations/`（`0001~0003`，**不动**，表名/app_label 不变，历史数据无需迁移）
- `apps.py`（`LaborArbitrationConfig`，`ready()` 里保留 `register_signals()`）
- `admin/__init__.py`（改为一行注释「Admin 已迁移到 plugins」）
- `__init__.py`

**迁移到 `plugins/labor_arbitration/`（逻辑层）**：
- `services/`（`crawler.py` / `parsing_service.py`）
- `admin/`（`source_admin.py` / `document_admin.py`）
- `tasks.py`
- `README.md`、`MIGRATION_TO_PLUGINS.md`（本文档）

### 步骤

1. **建目录并移动文件**：
   ```bash
   cd backend
   mkdir -p plugins/labor_arbitration
   git mv apps/labor_arbitration/services plugins/labor_arbitration/services
   git mv apps/labor_arbitration/admin plugins/labor_arbitration/admin
   git mv apps/labor_arbitration/tasks.py plugins/labor_arbitration/tasks.py
   ```
   （plugins 是 submodule，需在 submodule 内用其自身的 git 操作，见第五节。）

2. **改 3 处 dotted path**（上表），`apps.labor_arbitration.tasks.` → `plugins.labor_arbitration.tasks.`。

3. **改 plugins 内代码的 import**：
   - 引用 models 的保持 `from apps.labor_arbitration.models import ...`（models 仍在 apps 层）。
   - 引用 services/tasks 的改为 `from plugins.labor_arbitration.services import ...`。
   - `tasks.py` 内 `from apps.labor_arbitration.services.crawler import FoshanLaborAwardCrawler` → `from plugins.labor_arbitration.services.crawler import ...`。

4. **admin 注册改造**：
   - `plugins/labor_arbitration/admin/` 里的 Admin 类改 `@admin.register(Model)` 装饰器（参照 `plugins/message_hub/admin/inbox_message_admin.py`）。
   - `apps/labor_arbitration/admin/__init__.py` 清空为一行注释。
   - `apiSystem/apiSystem/admin_customization.py` 增加 `import plugins.labor_arbitration.admin`（参照 576 行的 message_hub 写法）。

5. **管理命令处理（重要，易踩坑）**：
   Django 的 `manage.py` 只在 `INSTALLED_APPS` 里发现 `management/commands/`，plugins 不在其中，所以**管理命令必须留在 apps 层**，否则 `manage.py crawl_labor_arbitration` 会失效。做法：`apps/labor_arbitration/management/commands/` 保留，命令内 import 改 `from plugins.labor_arbitration.services.crawler import ...`。

6. **`plugins/__init__.py` 加检测函数**（可选，用于降级/模板加载）：
   ```python
   def has_labor_arbitration_plugin() -> bool:
       try:
           from plugins.labor_arbitration import tasks  # noqa: F401
           return True
       except ImportError:
           return False
   ```

7. **settings.py**：`INSTALLED_APPS` **保留** `apps.labor_arbitration`（数据层）；**不要**注册 `plugins.labor_arbitration`。labor_arbitration 无 `templates/`/`static/`，无需追加目录。

## 四、迁移后验证

```bash
cd backend
.venv/bin/python apiSystem/manage.py check                 # 系统检查
.venv/bin/python apiSystem/manage.py makemigrations --check # 应无新迁移（模型未变）
.venv/bin/python apiSystem/manage.py migrate                # 应无待执行迁移
.venv/bin/python apiSystem/manage.py seed_labor_arbitration_sources
.venv/bin/python apiSystem/manage.py crawl_labor_arbitration --source 1 --limit 5
```

重启 worker 后，在 Admin 验证「增量更新 / 调用文档解析 / 重试抓取」按钮均正常提交 Django-Q 任务。

## 五、submodule 提交（务必注意）

`plugins/` 是独立仓库，迁移后的代码**必须在 submodule 内单独 commit + push**：

```bash
cd backend/plugins
git status                 # 应看到 labor_arbitration/ 的新增/移动
git add labor_arbitration
git commit -m "feat(labor_arbitration): 迁移逻辑层到 plugins"
git push origin main       # FachuanPlugins.git
```

然后回到主仓库，提交「apps 层保留部分 + dotted path 修改 + submodule 指针更新」：

```bash
cd backend/..              # 回到主仓库根
git add backend/apps/labor_arbitration backend/plugins
git commit -m "refactor(labor_arbitration): 逻辑层迁移到 plugins submodule"
```

## 六、为什么不建议「字面全部迁移」（含 models）

若把 `models/` + `migrations/` 也搬进 `plugins/labor_arbitration/`，等于让 plugins 变成标准 Django app，会带来一串与项目架构冲突的问题：

1. **plugins 不在 `INSTALLED_APPS`**，Django 不会识别它的 models，也不会执行 migrations、不会建表。
2. 要让 models 生效，必须把 `plugins.labor_arbitration` 加入 `INSTALLED_APPS` 并自带 `apps.py` + `migrations/`——这违背项目「plugins 可选加载、不进 INSTALLED_APPS」的约定。
3. **migrations 依赖 app_label**：`apps.py` 的 `label` 若变化，`django_migrations` 表里的历史记录会对不上，已有数据表无法被正确关联。
4. submodule 的独立版本管理会让 migrations 的演进与主项目解耦，容易造成部署时迁移顺序不一致。

因此本项目惯例是：**models/migrations 留在 apps 层（数据），逻辑放 plugins 层（行为）**。若要「全部迁走」，建议先与团队确认是否愿意打破该架构约定。

## 附：迁移清单速查

- [ ] 移动 `services/`、`admin/`、`tasks.py` → `plugins/labor_arbitration/`
- [ ] 改 3 处 dotted path（`source.py:108`、`document.py:98/113`）
- [ ] 改 plugins 内 import（models 用 `apps.`，services/tasks 用 `plugins.`）
- [ ] admin 改 `@admin.register` + `admin_customization.py` 显式 import
- [ ] 管理命令留在 apps 层，import 改 plugins 路径
- [ ] `plugins/__init__.py` 加 `has_labor_arbitration_plugin()`
- [ ] `apps/labor_arbitration/admin/__init__.py` 清空
- [ ] submodule 内 commit + push，主仓库更新指针
- [ ] `manage.py check` + `makemigrations --check` + `migrate` + seed/crawl 验证
