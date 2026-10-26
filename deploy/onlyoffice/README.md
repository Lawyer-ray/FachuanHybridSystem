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

## 插件目录的 `.gz` 必须随文件一起同步

`plugins/fachuan-rewrite/` 下除了源文件，还有 `config.json.gz` / `index.html.gz` /
`plugin.js.gz`——**不是构建产物，是必需文件**，必须与源文件一同提交、一同同步到运行目录。

原因：DS 对自己的静态资源走 nginx `gzip_static`，只在**镜像构建时**预压缩。我们后挂进去
的目录它不会再压一遍，缺 `.gz` 时表现为：

- 编辑器弹「**The connection is too slow, some of the components could not be loaded**」
- 且**没有任何报错日志**（曾经给挂载加 `:ro`，DS 启动时 `gzip: Read-only file system`
  被淹没在日志里，排查了很久）

改了插件源码要重压：

```bash
cd ~/onlyoffice-dev/plugins/fachuan-rewrite
for f in config.json index.html plugin.js; do gzip -9 -kf "$f"; done
docker compose restart onlyoffice      # DS 不热加载插件注册表
```

验证（三项均 200 且 gzip 取到的字节数接近 `.gz` 大小才算通）：

```bash
for f in config.json index.html plugin.js; do
  curl -s -H 'Accept-Encoding: gzip' -o /dev/null -w "$f %{http_code} %{size_download}\n" \
    http://127.0.0.1:9980/sdkjs-plugins/fachuan-rewrite/$f
done
```
