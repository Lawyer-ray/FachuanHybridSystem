# deploy/ — 公网栈（nginx + gunicorn）

app.xlaw.top 的生产形态。与开发栈并行运行、互不干扰：

```
公网:  手机 → https://app.xlaw.top → Cloudflare(Access 门禁) → cloudflared 隧道
        → nginx :5091 ─ /、/assets/  → dist 副本（publish.sh 同步）
                     ├─ /api/ /social/ /media/ → gunicorn :8003（DEBUG=0）
                     └─ (qcluster 常驻，公网触发的异步任务不依赖开发终端)
开发:  localhost:5090 → Vite(HMR) → uvicorn :8002（DEBUG=1，完全不变）
```

两栈同一份代码、同一个数据库/Redis。开发造的数据公网立刻可见。

## macOS TCC 约束（本目录一切设计的根源）

仓库在 `~/Downloads` 下，而 macOS 拦截 **launchd 后台进程**读取
Desktop/Documents/Downloads（EPERM，且无头进程不弹授权框）——cloudflared
不受影响纯粹因为它的配置在 `~/.cloudflared`。因此：

- launchd 进程**读取**的文件（脚本、prod.env、nginx 配置、dist）全部放
  **运行时目录** `~/Library/Application Support/FachuanHybridSystem/`，
  由 `install.sh` 从本目录复制/生成；本目录下的同名文件是源文件；
- nginx 对仓库零直接读取：dist 走运行时副本，`/media/` 由 Django 鉴权后
  `FileResponse` 流式回发（**未启用 X-Accel**，单机单用户规模差异可忽略；
  若将来给 nginx 也授权完全磁盘访问，可在 prod.env 设
  `MEDIA_X_ACCEL_PREFIX=/protected_media/` 并恢复 internal location 直发）；
- gunicorn/qcluster 的 python 解释器必须**一次性手工授权**（见下）。

### 唯一的手工步骤：给 venv python 授予完全磁盘访问权限

系统设置 → 隐私与安全性 → 完全磁盘访问权限 → 点「+」添加（Cmd+Shift+G
输入路径跳转）：

```
/Users/huangsong21/Downloads/Coding/AI/FachuanHybridSystem/backend/.venv/bin/python
```

未授权时 gunicorn/qcluster 会以 `Operation not permitted` 反复重启
（ThrottleInterval 节流），`make prod-logs` 一眼可见。
（该符号链接指向 homebrew Cellar 的 python3.12——授权实际生效范围是这
个解释器二进制；它只跑你自己的代码，风险可控。）

## 文件

| 文件 | 作用 |
|---|---|
| `env/prod.env` | 公网实例环境覆盖（口径开关 + `FACHUAN_REPO`；无密钥，密钥仍在 `backend/.env`） |
| `gunicorn.conf.py` | gunicorn 配置（127.0.0.1:8003，UvicornWorker×2） |
| `nginx/nginx.conf` | 公网入口（127.0.0.1:5091）模板；`__RUNTIME__` 由 install.sh 替换 |
| `nginx/django_proxy.inc` | 转发 gunicorn 的公共代理参数 |
| `launchd/*.plist` | gunicorn / qcluster / nginx 三个常驻服务（KeepAlive，指向运行时目录） |
| `bin/gunicorn.sh` `bin/qcluster.sh` | launchd 入口（source 运行时 prod.env 后 exec venv python） |
| `install.sh` | 构建运行时目录 + 安装/更新三个 launchd 服务（重复执行安全） |
| `publish.sh` | 发布：`pnpm build` + dist 同步运行时 + `collectstatic`（即 `make publish`） |

## 日常操作

```bash
bash deploy/install.sh        # 首次安装 / 更新服务（改了 prod.env、nginx.conf、plist 后）
make publish                  # 发布前端改动（构建即生效，无需重启）
make prod-restart             # 发布后端改动后重启 gunicorn + qcluster
make prod-stop                # 停止整个公网栈（见「服务启停」）
make prod-start               # 启动整个公网栈
make prod-logs                # 跟随公网栈日志（gunicorn + nginx + qcluster）
launchctl list | grep fachuan # 看三个服务状态（PID 存在即活）
```

日志位置：`~/Library/Logs/fachuan-{gunicorn,qcluster,nginx,nginx-error,nginx-access}.log`；
Django 侧请求日志与开发栈共用 `backend/logs/api.log`（两栈混流，按时间戳区分）。

## 服务启停（整套栈）

```bash
make prod-stop    # 停止三服务（nginx + gunicorn + qcluster）→ app.xlaw.top 变 502
make prod-start   # 启动三服务（plist 已安装；从未装过先 bash deploy/install.sh）
```

等价的手动命令（make 目标就是它们的循环）：

```bash
# 停止（bootout = 从 launchd 注销，KeepAlive 随之失效）
for svc in nginx gunicorn qcluster; do launchctl bootout gui/$(id -u)/com.user.fachuan-$svc; done
# 启动
for svc in nginx gunicorn qcluster; do launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.user.fachuan-$svc.plist; done
```

要点：

- **不要用 kill/pkill 停服务**——KeepAlive 会在数秒内把进程重新拉活；必须
  `bootout`（注销注册）才是真停。
- 单个服务同理，以 nginx 为例：`launchctl bootout gui/$(id -u)/com.user.fachuan-nginx`
  停、`launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.user.fachuan-nginx.plist`
  启、`launchctl kickstart -k gui/$(id -u)/com.user.fachuan-nginx` 只重启。
- plist 留在 `~/Library/LaunchAgents/`，**重启 Mac / 重新登录后会自动拉起**整个栈；
  想彻底禁用自启：`launchctl disable gui/$(id -u)/com.user.fachuan-nginx`（或把对应
  plist 移出 LaunchAgents），恢复用 `launchctl enable` + `prod-start`。
- 停公网栈期间若需外网继续可用：按「切换/回退隧道入口」把 cloudflared ingress
  切回 5090（需 vite dev 在跑），或干脆连同 cloudflared 一起停
  （`launchctl bootout gui/$(id -u)/com.user.cloudflared-fachuan`）。

## 媒体鉴权

生产实例 `MEDIA_REQUIRE_AUTH=true`（默认即开）：`/media/...` 由 Django 鉴权
（JWT 头 / `?token=` / admin session），未授权 403；文件由 Django
`FileResponse` 流式回发（X-Accel 缓议原因见上）。

## 安全口径

- 只监听 `127.0.0.1`，外网必经 cloudflared 隧道 + Cloudflare Access 门禁；
- `DJANGO_DEBUG=0`：黄页/环境变量泄漏关闭；生产 fail-fast 校验（强 SECRET_KEY、
  显式 CORS/CSRF、禁 LAN 模式）在 `apps/core/config/django_runtime.py`；
- `/admin/`、`/static/` 未对外暴露（与 vite 代理时代口径一致）。需要时在
  `nginx.conf` 加 location 转发，并核对 `CSRF_TRUSTED_ORIGINS`；
- `X-Forwarded-Proto` 由 cloudflared 透传，`DJANGO_SECURE_PROXY_SSL_HEADER=true`
  使 `request.is_secure()` 为真（社交登录回调、Secure cookie 依赖）。

## 切换/回退隧道入口

cloudflared ingress 指向 nginx（`~/.cloudflared/config.yml`）：

```yaml
- hostname: app.xlaw.top
  service: http://localhost:5091   # 原 http://localhost:5090（vite）
```

改后 `launchctl kickstart -k gui/$UID/com.user.cloudflared-fachuan`。
回退到开发态直出：把 5091 改回 5090 再 kickstart 即可。

## 已知口径

- SECRET_KEY 于 2026-10-05 升级为强密钥（原 37 字符过不了生产闸门），JWT/session
  全部失效过一次（需重新登录）；`backend/.env.bak-20261005` 留有升级前备份；
- 后端代码改动需 `make prod-restart` 才对公网生效（gunicorn 不热重载）；
- publish 不重启 gunicorn/nginx——前端产物与 collectstatic 都是磁盘读；
- 仓库路径（FACHUAN_REPO）若搬迁，需同步改 `deploy/env/prod.env` 并重跑
  `install.sh`（plist 与 nginx 配置不含仓库路径，无需改）。
