# OnlyOffice Document Server —— 开发环境编排（OrbStack）

法穿 SI Copilot 的在线文档画布。DS 是**独立 Docker 容器**，不在 Django 里、不由 uv 管理。

> **接入 / 升级的权威说明：[`backend/apps/onlyoffice/README.md`](../../backend/apps/onlyoffice/README.md)**
> 本目录只负责「怎么把它跑起来」，三条链路、版本矩阵、升级流程、验收清单、已知坑都在那份。

## 现状

| 项 | 值 |
|---|---|
| 镜像 | `onlyoffice/documentserver:9.4.0.1`（社区版 9.4 起无并发限制） |
| 架构 | arm64 原生（Apple Silicon / OrbStack，无模拟） |
| 端口 | `9980:80` |
| 容器名 | `onlyoffice`，`restart: unless-stopped` |
| 数据卷 | `onlyoffice_data`（转换缓存）、`onlyoffice_log` |
| JWT | **开启**，密钥与后端 `ONLYOFFICE_JWT_SECRET` 必须一致 |
| 字体 | `./fonts` → `/usr/share/fonts/custom:ro`（**只放中文字体**，见下） |
| 回连宿主 | `extra_hosts: host.docker.internal:host-gateway` |

## 为什么编排文件在仓库里

镜像 tag 就是**代码变更**：放仓库才能 PR review、git revert 回滚、看到版本历史。
运行目录（`~/onlyoffice-dev/`）只放**密钥和字体**——这两个不该入库。

## 首次部署（或新机器重建）

```bash
mkdir -p ~/onlyoffice-dev
cd ~/onlyoffice-dev

# 1. 取编排文件（本目录）
cp <仓库>/deploy/onlyoffice/compose.yaml .
cp <仓库>/deploy/onlyoffice/.env.example .env

# 2. 填密钥：与后端 SystemConfig 的 ONLYOFFICE_JWT_SECRET 保持一致
python3 -c 'import secrets; print(secrets.token_hex(32))'   # 生成 ≥32 字节
#    → 写进 .env 的 ONLYOFFICE_JWT_SECRET
#    → 同一串写进 Admin → 系统配置（分类 onlyoffice）→ ONLYOFFICE_JWT_SECRET

# 3. 放字体（只放支持中文的，当前 14 个）
mkdir -p fonts && cp <中文字体文件> fonts/
ls fonts/ | wc -l        # 14

# 4. 起服务
docker compose up -d
until [ "$(curl -s http://127.0.0.1:9980/healthcheck)" = "true" ]; do sleep 2; done
docker exec onlyoffice documentserver-generate-allfonts.sh   # 建字体索引（会重启 docservice）
docker exec onlyoffice fc-list :lang=zh file | wc -l         # 中文字体已识别
```

后端侧再确认三项配置（Admin → 系统配置 → 分类 `onlyoffice`）：

| key | 开发值 |
|---|---|
| `ONLYOFFICE_DOCSERVER_URL` | `http://127.0.0.1:9980`（浏览器可达） |
| `ONLYOFFICE_INTERNAL_URL` | `http://host.docker.internal:8002`（DS 容器可达） |
| `ONLYOFFICE_JWT_SECRET` | 与 `.env` 同一串 |

## 日常

```bash
docker compose up -d            # 起（healthcheck ~20s）
docker compose stop             # 停（不用时归零内存，镜像与卷保留）
docker compose logs -f onlyoffice | grep -iE 'error|fatal'
curl -s http://127.0.0.1:9980/healthcheck     # true
```

## 升级

**不要只改本机运行目录**：改本仓库 `compose.yaml` 的 `image`，走 PR；再同步到运行目录。
完整步骤（备份 → 换 tag → **删缓存卷** → 重刷字体 → 校验 → **5 项业务验收** → 回滚）：

→ [`backend/apps/onlyoffice/README.md`](../../backend/apps/onlyoffice/README.md) 第四节

## 字体红线

`fonts/` **只放支持中文的字体**（当前 14 个）。2026-10-01 实测：曾把本机 388 个字体全量同步，
结果**中文全部变豆腐问号**——纯西文的「真 Arial」抢占默认字体解析，加上 macOS 的 LastResort
兜底字体混入 fallback 链。

商业字体（汉仪旗黑 / 阿里普惠体 / 抖音美好体 / 华康）**仅限本机开发调试**，交付律所服务器
不能直接拷贝，须换开源字体（思源宋体/黑体、Noto Sans/Serif CJK）或采购授权。

## 文件

| 文件 | 作用 |
|---|---|
| `compose.yaml` | DS 编排（镜像 tag 锁版本、JWT、端口、字体挂载、回连宿主） |
| `.env.example` | 密钥模板（`ONLYOFFICE_JWT_SECRET`），复制成 `.env` 后填值 |
| `plugins/fachuan-rewrite/` | 法穿 AI 改写插件（幕后桥）：划词直改的选区通道 |
| `README.md` | 本文件 |

**不入库**：`.env`（真密钥）、`fonts/`（体积大 + 授权受限）。

## 插件目录的 `.gz` 是 DS 生成的产物，**不要入库**

`plugins/fachuan-rewrite/` 下只有 `config.json` / `index.html` / `plugin.js` 三个源文件入库。
同目录的 `*.gz` 由 **DS 容器自己生成**：`/var/www/onlyoffice/documentserver` 启动时执行
`documentserver-static-gzip.sh`，它对 `sdkjs-plugins` 下的 js/json/html 跑
`gzip -kf9`（`-f` = **强制覆盖**），供 nginx `gzip_static` 使用。

所以：**改了源文件，重启容器即可**，不需要手工重压：

```bash
cd ~/onlyoffice-dev           # 实际挂载目录（见 compose 的 ./plugins/...）
docker compose restart onlyoffice    # DS 不热加载插件注册表
```

### 曾经踩过的两个坑（都与 `.gz` 有关）

**坑一：挂载加 `:ro`** —— DS 的 gzip 预压缩写不进去（`gzip: Read-only file system`
被淹没在日志里），`.gz` 一个都不生成，插件加载**静默失败**。compose 里已注释说明，别再加 `:ro`。

**坑二（更隐蔽）：把 `.gz` 提交进仓库** —— 一旦入库，它就成了「源文件的过期副本」：
git 里 `plugin.js` 是新的、`plugin.js.gz` 还是旧的，谁在别处部署都会拿到**旧插件**，
而且症状极难定位：

- `docker exec grep 新代码 plugin.js` **能搜到**（误导性极强：以为已生效）
- 只有看**实际下发**的字节才发现不对

真机踩过：`plugin.js` 已 17243 字节，下发的 `Content-Length` 仍是旧值 3899，
于是 apply-revision 一直停在最脆的「精确子串匹配」层，AI 改完就降级成整页重载。

因此 `.gitignore` 已排除 `deploy/onlyoffice/plugins/*/*.gz`。**排查任何「改了插件没反应」，
第一步都是核对实际下发的那一份**：

```bash
curl -s -H 'Accept-Encoding: gzip' -D - -o /tmp/p.js \
  http://127.0.0.1:9980/sdkjs-plugins/fachuan-rewrite/plugin.js | grep -iE 'content-length|last-modified'
wc -c < /tmp/p.js                                   # 应等于源文件字节数
grep -c '你在新代码里加的标记' /tmp/p.js              # 期望 >= 1
```

## 就地落修订（apply-revision）的定位策略

AI 直改走两条路：**优先**经插件桥在当前画布里就地写修订（不重载）；
就地失败才降级为换 document key 重建画布。重建意味着 5–15 秒白屏，
体感上就是「**AI 改完之后整页刷一下**」，所以降低就地失败率是体验的关键。

插件内核侧的 `__find` 不是单纯 `doc.Search(anchor)`，而是**四层降级**
（`WordAdapter.apply` 里，注释有完整说明）：

| 层 | 手段 | 治什么 |
|---|---|---|
| 1 | `doc.Search(raw)` | 干净原文 |
| 2 | 逐元素 `GetText` 包含 | 跨 run 但同段 |
| 3 | 归一化包含（去空白/零宽、NFKC 全半角折叠） | 空格多余/丢失、全角标点 |
| 4 | 取开头 40 字再匹配 | 原文尾部被模型顺手改写 |

两条**实测红线**（写错过，排查了很久）：

1. **`ApiRange` 没有 `SetStart`/`SetEnd`**——实测 `typeof` 均为 `undefined`，
   真实 API 是 **`SetStartPos` / `SetEndPos`**。照着想当然写会让归一化层
   **恒假且不报错**（永远落到最后一层失败）。
2. **`Asc.scope` 只能传字符串**，对象会静默丢失（统一 `JSON.stringify`）。

插件超时 `COMMAND_TIMEOUT_MS = 8000`，前端 `APPLY_TIMEOUT_MS = 10000`（
`use-live-rewrite-apply.ts`）——**前端必须比插件长**，否则插件还没回结论
前端就先超时降级，白白多一次重建。

就地成功与否可直接验证（不依赖肉眼）：

```js
// 在页面里统计 DocEditor 构造次数：>1 说明画布被重建了
// 并盯 fachuan-plugin 的 applied 消息：{ok:true, how:'normalized'}
window.addEventListener('message', e => {
  if (e.data && e.data.source === 'fachuan-plugin') console.log(e.data.type, e.data.result)
})
```
