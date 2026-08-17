# CLAUDE.md

## Changelog 规则

### 文件结构
```
changelog/
  v26.XX/                   # 按次版本号建目录
    v26.XX.0.md             # 每个小版本一个文件
    v26.XX.1.md
```

### 命名规则
- 目录：`changelog/v{主版本}.{次版本}/`，如 `changelog/v26.53/`
- 文件：`v{主版本}.{次版本}.{补丁版本}.md`，如 `v26.53.2.md`
- **不要**用 `.md` 后缀作为目录名，**不要**省略补丁版本号

### 创建流程
1. 在 `changelog/v{次版本}/` 目录下创建 `v{完整版本号}.md`
2. 用户指定版本号时，严格按指定版本号命名
3. **不要**创建 `changelog/CHANGELOG.md` 主索引文件

### 版本号格式
- 完整版本号：`v26.53.2`
- 次版本目录：`v26.53`
- 文件名：`v26.53.2.md`

## Media 文件管理规范

### 禁止事项
- **禁止**直接用 `open(path, "wb")` / `path.write_bytes()` 写文件到 media 目录
- **禁止**手动拼接 `MEDIA_ROOT / "xxx" / filename` 路径
- **禁止**使用 `Path("media/...")` 相对路径
- **禁止**在 media 根目录直接存放文件

### 必须遵守
- 所有文件保存**必须**通过 `storage_service.save_uploaded_file()` 或 `default_storage.save()`
- 路径生成**必须**使用 `core/filesystem/upload_paths.py` 中的路径工厂类
- 文件名清洗**必须**使用 `upload_paths.sanitize_filename()`，不要自行实现
- media 目录 entity 名**必须**使用 `upload_paths.py` 中的常量，不要硬编码字符串

### 目录结构规则
- 一级目录 = 业务域（`cases/`, `contracts/`, `clients/`, `tools/`, `messages/`）
- 二级目录 = 具体实体（`logs/`, `documents/`, `payments/`）
- 三级目录 = 日期或 ID（`2026/06/` 或 `{entity_id}/`）
- 所有路径由 `DatedUUIDPath` / `EntityIdPath` 自动生成，不要手动拼接

### 新增 FileField 规范
- 新增 Model 字段**必须**使用 `FileField`（不是 `CharField` 存路径）
- `upload_to` **必须**使用 `upload_paths.py` 中的工厂类
- 有 `FileField` 的 Model **必须**有对应的 `post_delete` 信号清理（或使用 `django-cleanup`）

## OA Filing（律所 OA 对接）

`backend/apps/oa_filing/` 用于对接律所 OA 系统（立案、盖章、归档、发票申请、案件/客户导入）。

### 架构

采用**适配器模式**隔离各律所差异：

- `services/base_firm_adapter.py` — Protocol 定义（FilingAdapter/StampAdapter/ArchiveAdapter/CaseImportAdapter/ClientImportAdapter）
- `services/oa_firm_registry.py` — 按 `site_name` 注册和查找适配器
- `services/oa_data_models.py` — 通用数据类（OACaseData/OACustomerData 等）
- `services/script_executor_service.py` — 通用调度器（session 管理 + 凭证查找 + 线程调度），不含律所特有逻辑
- `services/oa_scripts/jtn/` — 金诚同达 OA 实现，完全自包含
  - `adapter.py` — 薄委托 + 字段映射（~440 行），不含 Playwright 逻辑
  - 每个功能模块（filing/stamp/archive/invoice/case_import/client_import）有自己的 `playwright_*.py`（mixin）和 `service.py`（门面）

### 两种操作模式

- **全自动**：脚本完成全部步骤 → `execute_filing` / `execute_stamp` / `execute_archive`
- **半自动**：脚本完成前几步，浏览器留给用户操作 → `open_oa_page` / `open_invoice_page` / `open_stamp_page`

### 新增律所

1. 创建 `oa_scripts/<firm>/adapter.py` 实现 Protocol
2. 在 `oa_firm_registry.py` 注册一行映射
3. 不需要修改任何现有文件

### 禁止事项

- **禁止**在 `jtn/` 以外 import JTN 特有模块
- **禁止**在通用层硬编码律所名称（`site_name` 通过参数传入，默认值仅为兼容）
- **禁止**在 adapter.py 中写 Playwright 交互逻辑（放各功能模块的 `playwright_*.py`）

> 详细架构说明见 `backend/CLAUDE.md` 中的「OA Filing（律所 OA 对接）」章节。

## 威科先行案例检索（Weike WKInfo）

`backend/apps/legal_research/services/sources/weike/` 封装了威科先行（law.wkinfo.com.cn）的案例检索能力，支持 Playwright DOM 检索和私有 API 检索两种模式。

### 快速调用（Django Shell）

```python
cd backend && .venv/bin/python3
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'apiSystem.apiSystem.settings')
django.setup()

from apps.legal_research.services.sources.weike.client import WeikeCaseClient
from apps.organization.models import AccountCredential

# 获取威科先行账号凭证（id=6 为威科先行，id=7 为 wkxx）
cred = AccountCredential.objects.get(id=6)

client = WeikeCaseClient()
session = client.open_session(username=cred.account, password=cred.password)

# 搜索案例
items = client.search_cases(
    session=session,
    keyword="关键词1 关键词2",    # 支持空格分隔多个关键词
    max_candidates=10,              # 最大返回数
    max_pages=2,                    # 最大翻页数
)

# 获取案例详情（含案号、法院、裁判日期、裁判要旨等）
for item in items[:5]:
    detail = client.fetch_case_detail(session=session, item=item)
    print(detail.document_number)   # 案号，如 (2025)粤06行终679号
    print(detail.court_text)        # 法院名称
    print(detail.judgment_date)     # 裁判日期
    print(detail.title)             # 案件标题
    print(detail.content_text[:500])# 判决书全文（HTML转文本）
    print(detail.detail_url)        # 威科先行详情页链接
```

### 高级检索参数

```python
# 指定字段检索（title/caseNumber/fullText/causeOfAction 等）
items = client.search_cases(
    session=session, keyword="工伤认定",
    advanced_query=[{"field": "title", "keyword": "超龄"}],
    max_candidates=10, max_pages=2,
)

# 日期范围过滤
items = client.search_cases(
    session=session, keyword="超龄 工伤",
    date_from="2024-01-01",
    date_to="2026-12-31",
    max_candidates=10, max_pages=2,
)
```

### 账号凭证

| ID | 账号 | 站点 | 用途 |
|---|---|---|---|
| 6 | jtnfalawoa | 威科先行 | 案例检索（推荐） |
| 7 | jtnfalawoa | wkxx | 备用账号 |

密码存储在 `AccountCredential.password`（加密存储），通过 `open_session()` 自动解密使用。

### 注意事项

- `open_session()` 会启动 Playwright 浏览器实例（首次调用较慢，约10-15秒）
- `search_cases()` 默认走私有 API（快速），若 API 不可用自动回退 DOM 检索
- `fetch_case_detail()` 的 `content_text` 返回判决书全文（HTML 转纯文本）
- 搜索关键词支持空格、逗号、分号分隔，建议使用2-4个核心关键词
- 每次搜索后建议关闭 session 释放资源

## Plugins 子模块推送规则

`backend/plugins` 是独立 Git 仓库（子模块），有改动时**必须分别推送**，顺序如下：

1. **先推送子模块**：`cd backend/plugins && git push origin <子模块分支名>`
2. **再推送主仓库**：`cd ../.. && git push origin <主仓库分支名>`

### 原因
主仓库通过 commit hash 引用子模块。如果只推主仓库不推子模块，远程的子模块引用会指向一个不存在的 commit，其他人 clone 后 `git submodule update` 会失败。

### 注意事项
- 子模块内的 commit 必须在子模块目录内操作（`git add`、`git commit`）
- **禁止**从主仓库 `git add backend/plugins/xxx`，必须 `cd backend/plugins` 后操作
- 主仓库只 `git add backend/plugins` 来更新子模块指针

### 自动指针同步

FachuanPlugins 仓库配置了 GitHub Actions（`.github/workflows/sync-main-repo-pointer.yml`），当 plugins PR 合并到 main 时，**自动在主仓库创建一个指针更新 PR**。这解决了「plugins PR 合并后 merge commit 导致指针 stale」的问题。

> **注意**：涉及 plugins 的 PR 仍需手动更新子模块指针（因为 PR 合并前指针可能还不是最终值）。自动同步处理的是「PR 合并后产生新 merge commit」的情况。

### 标准 PR 流程

涉及 plugins 改动时，需要**两个 PR**，严格按顺序：

#### 第一步：PR plugins 子模块
```bash
cd backend/plugins
git checkout -b feat/xxx
# 修改代码...
git add -A && git commit -m "feat: xxx"
git push origin feat/xxx
# 在 GitHub 上创建 PR → 合并到 main
```

#### 第二步：PR 主仓库
```bash
cd ../..
git checkout -b feat/xxx
# 更新子模块指针到最新 commit
cd backend/plugins && git checkout main && git pull && cd ../..
git add backend/plugins
# 如有其他主仓库改动，一并 commit
git commit -m "feat: xxx（含 plugins 子模块更新）"
git push origin feat/xxx
# 在 GitHub 上创建 PR → 合并到 main
```

#### 为什么必须先 PR plugins
- 主仓库的 PR 里 `backend/plugins` 指向一个 commit hash
- 如果 plugins 的 PR 还没合并，这个 hash 在远程不存在
- 其他人 clone 后 `git submodule update` 会失败
- CI 也会因为拉不到子模块而报错

#### 快捷方式（同时改动 plugins + 主仓库时）
如果改动很小且不需要单独 review plugins，可以：
1. 先 push plugins **分支**到远程（不合并，不推 main）
2. 创建主仓库 PR（review 主仓库改动）
3. 主仓库 PR 合并前，先为 plugins 分支创建 PR 并合并
4. 主仓库 PR 中更新子模块指针后合并

**禁止**将 plugins 直接 push 到 main，必须走 PR 流程。

### PR 合并后本地清理

PR 在 GitHub 上合并后，本地必须执行：

```bash
git checkout main
git pull origin main                # 拉取刚合并的代码
git branch -d <已合并的分支名>   # 删除已合并的本地分支
```

如有子模块变动，追加 `git submodule update --init`。

**Why:** 残留已合并分支会导致下次 `git checkout -b feat/xxx` 时包含旧代码，diff 混乱。

### PR 合并后审计清单

PR 合并并完成本地清理后，**必须**执行以下审计，防止遗漏未合并的代码：

1. **检查主仓库未合并分支**：`git branch` 列出所有本地分支
2. **检查子模块未合并分支**：`cd backend/plugins && git branch` 同样检查
3. **验证分支是否真的未合并**：对每个非 main 分支，用 `git cherry -v main <branch>` 检测是否已等价合入（`-` = 已合入，`+` = 未合入）
4. **处理真正未合并的分支**：确认是遗忘、废弃还是待合并，分别处理（合并 / 删除 / 保留）

**Why:** 多次发生过 PR 走完后，仍有 feature 分支遗漏未合并的情况（如 perf/async-upgrade-batch-1 遗漏 7 周）。

