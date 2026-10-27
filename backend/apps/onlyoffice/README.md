# 📝 OnlyOffice 文档编辑器（onlyoffice）

法穿 SI Copilot 的在线文档画布：合同复审工作台把 docx 交给 OnlyOffice
Document Server（下称 **DS**）渲染与编辑，修订痕迹（`w:ins`/`w:del`）与批注
由 DS 原生呈现；律师改完保存，DS 回调把编辑产物落回业务实体。

> 曾有并列的云版集成 `apps/docspace`（OnlyOffice DocSpace REST 2.0），已随
> #576 整体下线，勿再引用。

## 目录

- [一、架构与三条链路](#一架构与三条链路)
- [二、配置项](#二配置项)
- [三、DS 版本与依赖矩阵](#三ds-版本与依赖矩阵)
- [四、升级流程（DS 换版本）](#四升级流程ds-换版本)
- [五、升级后验收（5 项，缺一不可）](#五升级后验收5-项缺一不可)
- [六、回滚](#六回滚)
- [七、字体](#七字体)
- [八、已知坑](#八已知坑)
- [九、排障命令](#九排障命令)
- [十、目录结构](#十目录结构)

## 一、架构与三条链路

```
浏览器                    Django(:8002)                    DS 容器(:9980)
  │                          │                                │
  │ 1. GET editor-config ───►│ 读 SystemConfig → 签 JWT       │
  │ ◄── 已签名 config ───────│                                │
  │                          │                                │
  │ 2. 加载 <DS>/web-apps/apps/api/documents/api.js ─────────►│
  │    new DocsAPI.DocEditor(placeId, config) ───────────────►│ 按 key 拉文档
  │                          │                                │
  │                          │ ◄── GET /onlyoffice/file?src=&sig=  （DS 回源取文件）
  │                          │     验 HMAC → 复算业务权限 → FileResponse
  │                          │                                │
  │                          │ ◄── POST /onlyoffice/callback  （status=2/6 带编辑后 url）
  │                          │     验 JWT → 下载产物 → 落回 ReviewTask → 轮换 key
```

**① 配置签发**（`services/signing.py`）

DS 开启 JWT 后，编辑器 config **整体**要签名（`config.token = HS256(config, JWT_SECRET)`，
token 放 config 根、覆盖全部字段）。签名必须后端做——浏览器里放密钥等于把密钥发给所有人。

- `mode` 一律传 `"edit"`：`view` 模式下 DS **不创建可交互画布**（实测无 iframe、无报错）。
  「只读 / 锁定修订 / 完全编辑」由 `permissions` 字典逐项声明：

  | 前端 mode | permissions 组合 | 效果 |
  |---|---|---|
  | `view` | `edit/review/comment` 全 false | 查看器 |
  | `review` | `review/comment` true + `customization.review.trackChanges` | 锁定修订（只能留痕不能直接改正文） |  | `edit` | `edit/review/comment` 全 true | 完全编辑 |

- `copy: true`（律师要复制条款）、`chat: false`（内置协作聊天会让文本过 DS，法律保密场景不放开）。
- `customization.forcesave: true`：默认保存只在「最后一个用户关闭文档」时回调，工作台一直挂着
  就永远不落盘。
- `customization.review.reviewDisplay: "markup"`（**三种模式都给**）：控制**已有**修订痕迹
  （`w:ins`/`w:del`/批注框）要不要画出来。DS 默认 `"original"`（按修订前原文渲染），
  于是 WPS/Word 里满篇修订的同一份 docx 在 OnlyOffice 画布上**干干净净**——看着像
  「AI 根本没改成」。`trackChanges` 是**录制**开关（我敲字要不要留痕），
  `reviewDisplay` 是**回放**开关（文件里已有的痕迹要不要显示），两者不可互替；
  `showReviewChanges: true` 让审阅工具的修订视图默认展开。回归测试：
  `tests/ci/unit/onlyoffice/test_editor_config_revisions.py`。

**② DS 取文件**（`services/file_proxy.py` + `api/onlyoffice_api.py::serve_file`）

DS 在独立容器里，带不了 `Authorization` 头，且会**重试**（首拉超时、缓存逐出、forcesave 重组），
一次性下载票据首拉即失效。所以走 `/api/v1/onlyoffice/file?src=&sig=`：

- `sig` = `sign_file_token()` 签的**可重复使用** HMAC（`src|user_id|exp`，TTL 4 小时）；
- `src` 必须 `/api/` 开头且不含 `://`（否则就是开放代理）；
- 取文件时**按签名里的用户身份**去原端点取，`contract_review` 的权限判定照常生效（属主或超管）；
- Django 解析查询串时已解码过一次，`serve_file` **不得再 unquote**（否则含 `%` 编码的路径签名错位 → 稳定 403）。

**③ 保存回写**（`services/callback_service.py`）

`status=2`（最后一人关闭 10s 后）与 `status=6`（forcesave/点保存）时 body 带 `url` 指向编辑后文档：

- **必须**先下载落盘再应答 `{"error": 0}`——不落盘就应答等于告诉 DS「已保存」，DS 随即清理临时副本，
  修订不可恢复地丢失；失败回 `{"error": 1}` 让 DS 重试；
- 验签策略：token 存在但验不过 → 直接 `{"error": 1}`，**绝不**回落信任 raw body（伪造 url 就是 SSRF/任意覆盖）；
  `status=2/6` 必须持有效签名；
- 落盘后轮换 key：`saved_version + 1` → 下次签发新 key，否则 DS 继续用缓存旧内容；
- 旧产物路径留在 `EditorSession.prev_output_file`（物理文件保留，可手工恢复）。

### 过期画布的保存必须丢弃（AI 直改的数据丢失防线）

`status=2/6` 交回来的是**编辑器内存里的画布内容**，不是你磁盘上的文件。AI 划词直改走后端
直接改 docx（`direct_edit_service`），磁盘变了、画布还是旧的；一旦这份旧画布被回写，
AI 刚落的 `w:ins`/`w:del` 就被整篇静默覆盖。真机现象：

```
AI 说「已改好，可在审阅里看到修订」
→ 关掉编辑器再打开，又变回旧文
```

防线：**两个字段，职责必须分开**（写错过一版，下面是血泪）。

| 字段 | 含义 | 会随外部写增长？ |
|---|---|---|
| `external_write_seq` | 文档现在处于第几代（文档级计数器） | **会**（bump 时 +1） |
| `canvas_seq` | 这份画布是**按第几代**签发的（快照） | **不会**（只在签发新 key 时重设） |

- `bump_external_write()`（AI 落盘后调）只抬 `external_write_seq`；
- 签发新 key / 回写成功时把 `canvas_seq` **登记**为当时的文档级值；
- `stale_canvas_reason()` 比对：`external_write_seq(文档级 max) > canvas_seq` = 画布旧了；
- 命中则**丢弃这次保存**并 `return True`（应答成功）。

### 为什么不能用单个字段（守卫曾因此变成死代码）

第一版拿「文档级 max(external_write_seq)」去比「会话自己的 external_write_seq」。
问题在于 `bump_external_write` 用的是 `UPDATE ... external_write_seq = F(...) + 1`，
**把同一行的这个字段也抬了**，于是两边永远相等 → 判据恒假 → 守卫从未生效，
AI 的修订照样被旧画布覆盖。

更坑的是当时单测拿的是**未刷新的内存对象**（还是 bump 前的旧值），所以一直是绿的。
DS 回调实际走 `load_session_by_key()` **从库里重新取**，取到的已经是抬过的值。
所以回归测试现在**一律通过 `load_session_by_key()` 取会话**，并额外断言
`refresh_from_db()` 后也判过期：`tests/ci/unit/onlyoffice/test_stale_canvas_guard.py`。

### 两道防线叠加（别只依赖其中一道）

1. **旧 key 解析不到**：换 key 会把该行的 `document_key` 改写成新值，老 key 在库里
   不复存在 → `load_session_by_key` 返 `None` → 回调直接 `{"error": 1}`（fail-closed）；
2. **stale 判据**：多用户场景下 key 可能仍是同一个（协同共用），这时靠代次比对拦。

最后一点容易写错：命中 stale 时必须回**成功**而非 `{"error": 1}`。DS 重试交回来的
还是同一份旧画布，`error 1` 只会无限循环；丢掉这一次保存才是正确结果。

**document key 规则**（`make_document_key`）：`sha256(source_path | version | saved_version)[:32]`。

- key 标识**文档版本**：同文件同版本对所有用户算出同一 key —— 这是 DS 实时协同的前提；
- 签名参数**绝不能**进 key（`sig` 含时间戳，混进去就是每次签发 key 必变）。

数据模型见 `models.py`（`EditorSession`：一个「用户 × 业务文档」的绑定）。`task_id` 用 UUID
弱引用而非外键——onlyoffice 不硬依赖 `contract_review` 的模型层。

## 二、配置项

三项，全部走 `SystemConfig`（key 前缀 `ONLYOFFICE_`）→ `settings` → 环境变量三级回落，
带 60 秒 TTL 缓存（Admin 改完最长 1 分钟生效，或 `clear_config_cache()` 立即生效）：

| key | 含义 | 开发默认值 |
|---|---|---|
| `ONLYOFFICE_DOCSERVER_URL` | **浏览器**可达的 DS 地址（前端加载 `api.js`） | `http://127.0.0.1:9980` |
| `ONLYOFFICE_INTERNAL_URL` | **DS 容器**可达的本服务地址（DS 回源取文件 + 回写回调） | `http://host.docker.internal:8002` |
| `ONLYOFFICE_JWT_SECRET` | DS 容器的 `JWT_SECRET`（`is_secret=True`，经 SecretCodec 加解密） | 空（必须填） |

三项缺一即 `enabled=False`，前端显示「OnlyOffice 未启用」。
种子迁移：`apps/core/migrations/0037_seed_onlyoffice_config.py`。

> 早期蓝图 `docs/new-plans/si-copilot-demo-plan.md` 里的 `ONLYOFFICE_DS_URL` /
> `ONLYOFFICE_DS_JWT_SECRET` / `ONLYOFFICE_DS_CALLBACK_BASE` 是**未落地的旧命名**，按那个配会直接失败。

`JWT_SECRET` 长度 < 32 字节会告警一次（每个不同值报一次，不刷屏）。

## 三、DS 版本与依赖矩阵

| 项 | 当前值 |
|---|---|
| 镜像 | `onlyoffice/documentserver:9.4.0.1` |
| 社区版并发 | 9.4 起**无并发限制**（9.3 及以前有 20 连接限制） |
| 架构 | arm64 原生（OrbStack / Apple Silicon，无模拟） |
| 端口 | `9980:80` |
| 编排文件 | 仓库内 `deploy/onlyoffice/compose.yaml`（源），实际运行目录 `~/Downloads/Coding/AI/onlyoffice-dev/` |
| 数据卷 | `onlyoffice-dev_onlyoffice_data`（DS 缓存）、`onlyoffice-dev_onlyoffice_log` |
| 容器 | `onlyoffice`，`restart: unless-stopped` |
| 前置 | Python `pyjwt`（HS256）、`httpx`（回写下载，`trust_env=False` 绕过系统代理） |
| 前端 | `frontend/src/components/shared/onlyoffice/`（`OfficeView.tsx` + `api.ts`） |

**DS 数据卷里没有业务数据**，只有转换缓存、日志与字体索引。文档始终在 Django 侧
（`contract_review` 产物文件 + `EditorSession` 表）——所以升级的实质是「换镜像 + 重建缓存」，
**修订/批注不会因为换版本丢失**，真正必须保住的是 **JWT_SECRET 和字体**。

### 升级时必须复核的 API 面（本仓库用到的全部契约）

DS 每次升小版本都可能动这些语义，升级前对照官方 Release Notes 逐条确认：

| 用到的能力 | 位置 | 复核点 |
|---|---|---|
| `config.token` 整体签名（HS256，放根） | `signing.build_editor_config` | 签名载荷格式是否变化 |
| `permissions.edit/review/comment/download/print/copy/chat` | `signing.PERMISSIONS_*` | 键名或默认值变更 |
| `customization.review.trackChanges` | `signing`（review 模式） | 是否仍是锁定修订的强保证 |
| `customization.review.reviewDisplay` / `showReviewChanges` | `signing`（**全模式**） | 默认值是否仍为 `original`（隐藏已有修订）；改成 `markup` 才能回放 `w:ins`/`w:del` |
| `customization.forcesave` | `signing` | forcesave 触发条件、status 值 |
| `document.key` / `fileType` / `documentType` | `signing._DOC_TYPE` | 支持格式清单、未知后缀行为 |
| callback `status` 0/1/2/3/4/6/7 | `callback_service` | 2/6 的 `url` 语义、重试规则 |
| callback token / `Authorization: Bearer` | `api.document_callback` | 出站签名头格式 |
| `<DS>/web-apps/apps/api/documents/api.js` | `OfficeView.tsx::loadApiJs` | 路径与全局 `DocsAPI` |
| `DocsAPI.DocEditor(placeholderId, config)` | `OfficeView.tsx` | 官方签名是「元素 id」而非元素（传元素在部分版本静默失败） |
| `instance.destroyEditor()` | `OfficeView.tsx` cleanup | 方法是否仍存在 |
| `/healthcheck` | 运维探活 | 仍返回 `true` |

## 四、升级流程（DS 换版本）

```bash
# 运行目录（本机开发环境；DS 编排的源文件在仓库 deploy/onlyoffice/）
cd ~/Downloads/Coding/AI/onlyoffice-dev

# ── 0) 前置确认 ─────────────────────────────────────────
curl -s http://127.0.0.1:9980/healthcheck                 # 期望 true
docker exec onlyoffice printenv JWT_SECRET | head -c 8     # 记下前 8 位，升级后比对
docker ps --filter name=onlyoffice                          # 确认没有人在编辑（挂着的未保存会话会丢）

# ── 1) 备份唯一不可重建的东西：.env + compose + 字体 ────
cp .env .env.bak.$(date +%F)
cp compose.yaml compose.yaml.bak.$(date +%F)
ls fonts/ | wc -l                                          # 应为 14（见第七节）
docker volume ls | grep onlyoffice                          # 记下卷名

# ── 2) 改 tag ───────────────────────────────────────────
# 先确认 Docker Hub 上**确实存在**该 tag（踩过坑：10.0 没发布镜像）
# 改仓库 deploy/onlyoffice/compose.yaml 的 image，再同步到运行目录：
#   镜像 tag 是代码变更 → 走 PR，可 review、可回滚
# docker manifest inspect onlyoffice/documentserver:<新tag>   # 查存在性

# ── 3) 换镜像 + 清缓存卷 ─────────────────────────────────
docker compose stop
docker compose pull
docker volume rm onlyoffice-dev_onlyoffice_data             # 只删缓存，不动 log
docker compose up -d

# ── 4) 等健康检查，重刷字体索引（关键，否则中文全豆腐块）──
until [ "$(curl -s http://127.0.0.1:9980/healthcheck)" = "true" ]; do sleep 2; done
docker exec onlyoffice documentserver-generate-allfonts.sh
#    该脚本会重启 docservice，期间编辑器报「失去网络连接」，属正常，跑完自动恢复

# ── 5) 校验 ─────────────────────────────────────────────
curl -s http://127.0.0.1:9980/healthcheck                   # true
docker exec onlyoffice printenv JWT_SECRET | head -c 8      # 与 0) 一致（变了说明 .env 丢了）
docker exec onlyoffice fc-list :lang=zh file | wc -l        # 中文字体仍在
docker compose logs onlyoffice --tail 100 | grep -i error    # 无致命报错
```

**为什么必须删缓存卷**：DS 按 `document.key` + 本地缓存文件工作。跨版本残留的旧缓存文件
会被新版本解析失败，表现为**旧内容、空白画布或转换报错**。只删 `_data` 卷不动 `_log`。

**升级后不需要手动清 `EditorSession`**：`saved_version` 逻辑不变，`make_document_key`
算出的 key 照旧可用；DS 侧缓存已随卷删除。

## 五、升级后验收（5 项，缺一不可）

技术校验通过 ≠ 业务可用。**只做前面的 healthcheck 不算升级完成**，必须在法穿里跑通闭环：

| # | 验收项 | 判定标准 |
|---|---|---|
| 1 | 打开合同复审文档 | 编辑器出画布（有 iframe）、无「正在打开文档…」卡死；`OfficeView` 的 6 秒僵死探活不触发重挂 |
| 2 | **修订与批注**（跨版本最易翻车） | `w:ins`/`w:del` 删除线与下划线正确渲染；`comments.xml` 批注可展开；review 模式下改字留痕而非直改 |
| 3 | 保存回写闭环 | 改一笔 → 保存 → 后端日志出现「OnlyOffice 保存回写完成」；`EditorSession.saved_version` +1；`ReviewTask.output_file` 已更新；旧产物在 `prev_output_file` |
| 4 | 中文与字体 | 无豆腐块、无问号；宋体/黑体按文档声明生效 |
| 5 | 协同与 key | 两名用户同开同一文档算出**同一 key**（互相能看到修订）；保存后 key 变化（下次打开是新内容） |

配套自动化（不含真 DS，覆盖协议层）：`backend/tests/ci/integration/onlyoffice/test_onlyoffice_endpoints.py`。

## 六、回滚

DS 卷里没有业务数据，回滚是安全的：

```bash
cd ~/Downloads/Coding/AI/onlyoffice-dev
# 1. 把 compose 的 image 改回旧 tag（git revert deploy/onlyoffice/compose.yaml 的改动）
docker compose stop
docker compose pull
docker volume rm onlyoffice-dev_onlyoffice_data
docker compose up -d
until [ "$(curl -s http://127.0.0.1:9980/healthcheck)" = "true" ]; do sleep 2; done
docker exec onlyoffice documentserver-generate-allfonts.sh
```

回滚后同样跑第五节的 5 项验收——**降级也可能丢修订渲染**（新版写入的 `w:ins`/批注
结构旧版未必能解），所以第 2 项尤其要确认。

## 七、字体

容器内中文靠 bind mount 注入：`onlyoffice-dev/fonts` → `/usr/share/fonts/custom`（`ro`）+ 内置
`custom` 卷。

**硬约束：`fonts/` 只放支持中文的字体（当前 14 个）**——宋体 Songti SC / STSong / 华文中宋、
黑体 Heiti SC / STXihei / 冬青黑、汉仪旗黑、阿里普惠体、抖音美好体、Arial Unicode 等。

> 2026-10-01 实测翻车：曾把本机 388 个字体全量同步进去，结果**中文全部变豆腐问号**——
> 纯西文的「真 Arial」进入字体清单后抢占了默认字体解析，加上 macOS 的 LastResort
> 兜底字体混入 fallback 链。修复 = 只放中文字体 + 文档生成时显式声明 eastAsia 字体。

```bash
docker exec onlyoffice fc-list :lang=zh file    # 筛选工具：看容器实际识别到的中文字体
ls ~/Downloads/Coding/AI/onlyoffice-dev/fonts/  # 宿主侧清单
```

**授权红线**：`fonts/` 里的商业字体（汉仪旗黑 / 阿里普惠体 / 抖音美好体 / 华康）**仅限本机开发调试**。
交付律所服务器**不能直接拷贝**，必须换开源字体（思源宋体/黑体、Noto Sans/Serif CJK）或采购授权。

## 八、已知坑

| 坑 | 原因 / 处置 |
|---|---|
| `mode: "view"` 打开是空白 | DS 在 view 下不创建可交互画布。一律传 `mode: "edit"`，只读靠 `permissions` |
| 未知后缀被当 word 打开 → 空白画布 | `document_type_of()` 未命中返回**空串**（不伪装成 word），调用方应提示「暂不支持在线预览」 |
| DS 反复 401 取不到文件 | 用了**一次性**下载票据。必须用 `sign_file_token` 的可复用 HMAC（TTL 4h） |
| 含中文/`%` 编码路径稳定 403 | `serve_file` 里又 unquote 了一次，导致签名与验签不是同一字符串 |
| 每次打开都重新转换、两人协同互相看不见 | 签名参数混进了 `document.key`（`sig` 含时间戳）。key 只用 `source_path|version|saved_version` |
| 改了内容但看到旧版 | 保存后没轮换 key，或 DS 缓存没清 |
| 工作台挂一天，修订没落盘 | 没开 `customization.forcesave`；默认只在最后一人关闭 10s 后才回调 |
| **AI 说改好了，重开文档又变回旧文** | 编辑器旧画布把 AI 落盘的内容盖了。看 `EditorSession.external_write_seq`（计数器）与 `canvas_seq`（画布快照）是否分离、日志「忽略过期画布的保存回调」；机制见「③ 保存回写」 |
| **WPS/Word 里满是修订，OnlyOffice 画布干净得更新文档一样** | 没给 `customization.review.reviewDisplay: "markup"`。DS 默认 `"original"` = 按修订前原文渲染，已有 `w:ins`/`w:del` **一律不画**。
注意 `trackChanges` 是**录制**开关（我敲字要不要留痕），不是**显示**开关（文件里已有痕迹要不要画），两者不可互替。
先用 `unzip -p x.docx word/document.xml \| grep -c '<w:ins \|'` 确认文件真带痕迹，再查 config。 |
| 「点了没反应、不报错」（插件场景） | `callCommand` 第二参必须传 `false`，传 `true` 会销毁插件 iframe |
| `Asc.scope` 只能传字符串 | 传对象时回调静默丢失，统一 `Asc.scope.key = JSON.stringify(payload)` |
| `host.docker.internal` 不可达 | 依赖 compose 的 `extra_hosts: host.docker.internal:host-gateway`；OrbStack 默认支持，失败时回落 LAN IP 排障 |
| 编辑器报「失去网络连接」 | `documentserver-generate-allfonts.sh` 正在重启 docservice，等它跑完 |
| 容器内存占用高 | 开发期不用就 `docker compose stop` 归零，镜像与卷保留 |
| 全屏层被弹窗盖住或反过来 | 前端的全屏层 z-index 须低于弹窗基线 `z-[130]` |

## 九、排障命令

```bash
# ── 服务状态 ──
curl -s http://127.0.0.1:9980/healthcheck                  # true / false
docker ps --filter name=onlyoffice --format '{{.Status}}\t{{.Ports}}'
docker compose logs -f onlyoffice | grep -iE 'error|fatal'

# ── 密钥一致性（后端 SystemConfig 必须 == 容器 JWT_SECRET）──
docker exec onlyoffice printenv JWT_SECRET
#    后端侧：Admin → 系统配置 → 分类 onlyoffice → ONLYOFFICE_JWT_SECRET

# ── 清 DS 缓存（换了同名文件 / 换文档调试时）──
docker exec onlyoffice rm -rf /var/lib/onlyoffice/documentserver/App_Data/cache/files/data/*

# ── 容器回连宿主是否通（DS 取文件/回写的命门）──
#    期望拿到 422 / 403（= 连上了、参数被拒）；若报 "could not connect" 才是回连不通
docker exec onlyoffice curl -s -o /dev/null -w '%{http_code}\n' \
  "http://host.docker.internal:8002/api/v1/onlyoffice/file?src=/api/&sig=x"

# ── 字体 ──
docker exec onlyoffice fc-list :lang=zh file | head
docker exec onlyoffice documentserver-generate-allfonts.sh   # 全量重建索引（会重启 docservice）

# ── 会话与回调痕迹 ──
#    Django Admin → 编辑器会话（EditorSession）：看 document_key / saved_version /
#    last_callback_status / last_saved_at / prev_output_file
#    后端日志关键词：'OnlyOffice 回调'、'保存回写完成'、'验签失败'、'代理拒绝越权'

# ── 镜像 tag 是否存在（Docker Hub 需代理时加 -x http://127.0.0.1:7897）──
docker manifest inspect onlyoffice/documentserver:<tag> >/dev/null && echo 存在 || echo 不存在
```

## 十、目录结构

```
onlyoffice/
├── apps.py                  # OnlyOfficeAppConfig（注意与 config.OnlyOfficeConfig 仅重名）
├── config.py                # 三项配置读取（SystemConfig→settings→env，60s TTL 缓存）
├── models.py                # EditorSession（保存回写锚点 + key 轮换）
├── api/onlyoffice_api.py    # 3 个端点：editor-config / callback / file
└── services/
    ├── signing.py           # config JWT 签名、权限字典、格式表、key 计算、文件令牌
    ├── file_proxy.py        # DS 取文件代理：路径白名单 + 按签名用户复算权限
    └── callback_service.py  # 会话解析 + status=2/6 下载落盘 + key 轮换
```

前端：`frontend/src/components/shared/onlyoffice/`（`OfficeView.tsx` 挂载与僵死探活、`api.ts` 取配置）。

## API 端点

前缀 `/api/v1/onlyoffice`：

| 方法 | 路径 | 鉴权 | 说明 |
|---|---|---|---|
| GET | `/editor-config` | JWT/Session | 按文件签发已签名 config（`file_url` / `file_name` / `mode` / `version`） |
| POST | `/callback` | DS 回调签名 | DS 状态回调；status=2/6 落盘并轮换 key |
| GET | `/file` | HMAC 签名 | DS 回源取文件代理（`?src=&sig=`，可重复访问） |

> `/editor-config` 与 `/file` 的路径白名单由 `services/domain_registry.py` 的业务域
> 注册表决定：`contract_review`（复审产物）、`contract_folder`（合同绑定文件夹）、
> `case_folder`（案件绑定文件夹，2026-10 起诉讼详情页的案件文件走这里）。
> 新业务域接入只需在注册表加一条（取文件/保存回写/权限钩子随域声明），
> 三处调用点（config 签发、文件代理、保存回调）自动支持。
