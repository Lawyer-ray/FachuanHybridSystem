# 社交登录（apps/social_auth）

飞书 / 微信等第三方身份登录本系统。**核心规则：只有已绑定的社交身份才能登录，扫码不会自动建号。**

首次使用必须先用账号密码登录，到「账号绑定」页把社交身份挂到自己的律师账号上；之后才能用该身份扫码登录。这条规则是「扫码进来的到底是谁」的唯一答案来源——不再靠昵称/邮箱猜。

---

## 一、目录结构

| 路径 | 职责 |
|---|---|
| `providers/base.py` | `SocialProvider` 协议、`ProviderConfig`、`SocialProfile`、`LoginMode` 枚举 |
| `providers/feishu.py` | 飞书自建应用（`embedded_qr`：授权页内嵌二维码） |
| `providers/wechat.py` | 微信开放平台（`redirect`：整页跳转授权） |
| `providers/google.py` | Google（`redirect`：整页跳转授权，OAuth 2.0 授权码 / OIDC） |
| `providers/github.py` | GitHub（`redirect`：整页跳转授权，OAuth 2.0 授权码） |
| `providers/__init__.py` | `ProviderRegistry` 注册表，import 时注册内置 Provider |
| `models/social_account.py` | `SocialAccount`：一条记录 = 一个「律师 ↔ 某平台身份」绑定 |
| `models/temp_auth.py` | `TempAuth`：一次性授权码，5 分钟过期，用完即删 |
| `services/social_auth_service.py` | 绑定/解绑/解析用户；登录只放行已绑定身份 |
| `views.py` | `SocialLoginView` / `SocialCallbackView`（后端 302 回调，非 API） |
| `api/social_auth_api.py` | 前端调用的 7 个 API 端点（出入参 Schema 在 `api/social_auth_schemas.py`） |
| `admin.py` | `SocialAccountAdmin`（只读 + 可删，禁止手工新增） |
| `signals.py` | SystemConfig 变更 → 失效 Provider 配置缓存 |

依赖方向：`core` 不得反向 import `social_auth`（结构门禁 `test_core_no_business_deps` 会拦）。
配置变更清缓存因此由本 app 的 `signals.py` 监听 `SystemConfig` 完成。

---

## 二、数据模型

### SocialAccount

一行 = 一条绑定。**没有在 `lawyer` 表上加任何字段**，多平台、多律师都靠这张表表达：

- 一位律师绑多个平台 → 同一个 `user` 多行（飞书一行、微信一行）
- 不同律师走不同平台 → 各绑各的 `provider_uid`

两道唯一约束兜底：

| 约束 | 挡住的情形 |
|---|---|
| `unique_together (provider, provider_uid)` | 一个社交号被两位律师绑定 |
| `UniqueConstraint (user, provider)` | 一位律师在同一平台绑两个号 |

**换绑 = 先解绑再绑**（同平台第二行会被约束拒绝）。同一平台的多个账号（个人号 + 工作号）不支持，这是有意为之的取舍。

### TempAuth

后端回调成功后建一条 `TempAuth`，把一次性码带回前端换 JWT。

`token` 是主键且**必须带 `default=uuid.uuid4`**：回调只调 `TempAuth.objects.acreate(user=user)`，调用方不会传 token。历史上这里没有 default，导致列 NOT NULL 违规、扫码登录 500（见「踩坑记录」第 3 条）。

---

## 三、登录流程

```
前端登录页 ──POST /social/{provider}/session──> 后端建 AuthorizationRequest（含 state）
                                                  │ 存入 Django session（SameSite=Lax）
   内嵌二维码 / 整页跳转授权 <────────────────────┘
                    │
                    ▼ 用户扫码确认
   后端 /social/{provider}/callback/   ← 飞书/微信 302 打回（state 校验）
                    │
                    ├─ 身份已绑定 → 建 TempAuth，302 到 {FRONTEND}/social-callback?code=xxx&redirect=/
                    └─ 身份未绑定 → 302 到 {FRONTEND}/social-callback?error=unbound
                    │
   前端 SocialCallbackPage ──POST /social/token-exchange──> 换 access/refresh（并落 localStorage）
                    │
                    └─ navigate(redirect) → RequireAuth 看到 token → 进入系统
```

绑定流程同理，只是入口是 `POST /social/{provider}/bind-session`（需登录），
回调后把身份挂到**当前登录用户**身上（`bind_user_id` 存在 session 里），完成后跳回 `/settings/bindings?bound=<provider>`。

### 两种登录方式（LoginMode）

| 模式 | 表现 | 代表 |
|---|---|---|
| `embedded_qr` | 授权页内嵌在登录卡里显示二维码 | 飞书 |
| `redirect` | 整页跳转到第三方授权页 | 微信、Google、GitHub |

新增 Provider 只需实现 `SocialProvider` 协议 + 在 `providers/__init__.py` 注册；
前端按 `login_mode` 自动派发到 `SocialQrPanel` / `SocialRedirectPanel`，**不需要改前端分支结构**。

---

## 四、API 端点

后端 router 挂载于 `/api/v1/social`（见 `apiSystem/apiSystem/api.py`）。

| 方法 | 路径 | 鉴权 | 用途 |
|---|---|---|---|
| GET | `/providers` | 无 | 登录页拉取**已启用**的登录方式 |
| POST | `/{provider}/session` | 无 | 建授权会话（返回二维码内容或跳转 URL） |
| POST | `/token-exchange` | 无 | 一次性码换 JWT |
| GET | `/provider-catalog` | 需登录 | 绑定页拉取**全部已注册**方式（含未启用的灰态） |
| GET | `/bindings` | 需登录 | 当前用户的绑定列表 |
| POST | `/{provider}/bind-session` | 需登录 | 发起绑定授权 |
| DELETE | `/{provider}/bind` | 需登录 | 解绑 |

后端 302 回调（不在 API 内）：`/social/{provider}/login/`、`/social/{provider}/callback/`（注册于 `apiSystem/apiSystem/urls.py`，本 app 内无 urls.py）。

前端路由：`/login`（登录）、`/social-callback`（回调落地）、`/settings/bindings`（账号绑定）。

---

## 五、配置

全部走 SystemConfig 的 `social_auth` 分类（Admin → 核心系统 → 系统配置）：

| key | 说明 |
|---|---|
| `SOCIAL_AUTH_FEISHU_APP_ID` / `_APP_SECRET` | 留空则复用「飞书配置」分类的 `FEISHU_APP_ID` / `FEISHU_APP_SECRET`（扫码与案件群聊共用同一自建应用） |
| `SOCIAL_AUTH_FEISHU_REDIRECT_URI` | **后端**可达地址，如 `http://127.0.0.1:8002/social/feishu/callback/`；必须在飞书后台「安全设置 → 重定向 URL」精确登记，否则授权页返回 `redirect_uri unmatch` |
| `SOCIAL_AUTH_FEISHU_SCOPE` | 最小集 `contact:user.base:readonly` |
| `SOCIAL_AUTH_FEISHU_ENABLED` | 填 `false` 可临时下线该登录方式 |
| `SOCIAL_AUTH_WECHAT_*` | 同上，微信未配置则登录页不显示微信入口 |
| `SOCIAL_AUTH_GOOGLE_APP_ID` / `_APP_SECRET` | Google Cloud Console → Google Auth Platform → 客户端创建，应用类型必须选「Web 应用」。**Google 没有可借的共用凭证，必须在本分类填**（留空则该入口自动隐藏） |
| `SOCIAL_AUTH_GOOGLE_REDIRECT_URI` | 必须与 Console 里「已获授权的重定向 URI」**完全一致**（精确匹配、不支持通配符、含结尾斜杠）：`http://localhost:8002/social/google/callback/`。**host 必须与「浏览器访问前端的 host」一致**——cookie 区分 host、不区分端口，本项目其余配置统一用 `localhost`。正式域名必须 HTTPS（Google 仅对 `localhost` / `127.0.0.1` 放行 http） |
| `SOCIAL_AUTH_GOOGLE_SCOPE` | `openid email profile`，空格分隔且必须以 `openid` 开头。全为非敏感范围，无需 Google 审核 |
| `SOCIAL_AUTH_GOOGLE_ENABLED` | 同飞书 |
| `SOCIAL_AUTH_GITHUB_APP_ID` / `_APP_SECRET` | GitHub → Settings → Developer settings → OAuth Apps 创建（免费、即时生效、无需审核），Client ID/Secret 填在此处。**没有可借的共用凭证，必须填**（留空则该入口自动隐藏） |
| `SOCIAL_AUTH_GITHUB_REDIRECT_URI` | 必须与 OAuth App 登记的 Callback URL **完全一致**（精确匹配、含结尾斜杠）：`http://localhost:8002/social/github/callback/`。host 须与浏览器访问前端的 host 一致（cookie 区分 host）。GitHub 允许 `localhost` 的 http 回调（回环地址端口可不同），正式域名需 HTTPS |
| `SOCIAL_AUTH_GITHUB_SCOPE` | `read:user user:email`，空格分隔。read:user 取昵称/头像，user:email 允许调 `/user/emails` 取私密邮箱（邮箱仅展示，身份判定用数字 id） |
| `SOCIAL_AUTH_GITHUB_ENABLED` | 同飞书 |

另需在 `backend/.env` 配 `FRONTEND_BASE_URL`（默认 `http://localhost:5090`），用于拼回调跳转地址与 CORS/CSRF 白名单。

> **配置生效时机**：Admin 保存即时生效（同进程信号失效缓存）；但**脚本直写 SystemConfig**
> （如 `manage.py shell` / 初始化脚本）或**多 worker 部署下其它 worker 改配置**收不到信号，
> 由 30 秒 TTL 兜底自动重建（`providers/__init__.py` 的 `_CONFIG_TTL_SECONDS`），无需重启后端。

> `SOCIAL_AUTH_*` 前缀不能省：`SystemConfig.key` 全局唯一，不能与 IM 群聊分类下的 `FEISHU_APP_ID` 重名。

---

## 六、后台位置

社交登录后台**不在侧边栏**（`admin_customization.py` 的 `_HIDDEN_APP_LABELS` 隐藏了 `social_auth`），
入口在 **其他工具 → 社交登录**（`/admin/automation/other-tools/`），直链 `/admin/social_auth/socialaccount/` 仍可用。

它是排查「律师说扫码进不去」的第一现场：能反查某个飞书/微信身份对应哪位律师，也能替律师解绑换号。
`has_add_permission` 返回 `False`——绑定关系只能由本人扫码产生，后台手工新增会造出指向错误律师的记录。

---

## 七、踩坑记录（务必先读）

这四条都是「代码看着对、跑起来不通」，且都不在单元测试的覆盖范围内，一次登录联调才全部暴露。

### 1. Vite 代理把前端路由吃掉了

`vite.config.ts` 里字符串形式的 proxy key 是**前缀匹配**（`url.startsWith(context)`），
写 `'/social'` 会把前端路由 `/social-callback` 也转发给 Django，Django 没有该路由 → 回调页 404。

**规范**：代理 key 用正则精确匹配后端真实路径前缀（`'^/social/'`），不要用裸字符串。
同理，任何与后端路径「前缀相同」的前端路由都要留神（`/social-callback` vs `/social/...`）。

### 2. 前端请求路径缺前导斜杠

ky 按「当前文档目录」解析相对路径。`api/v1/social/...` 在 `/login`（单段路径）下恰好落到
`/api/v1/...`，但在 `/settings/bindings` 下会解析成 `/settings/api/v1/...`——既不匹配 Vite 的
`/api` 代理，又被 SPA fallback 返回 `index.html`，`.json()` 解析 HTML 抛错。

**规范**：`social-api.ts` 里一律用以 `/` 开头的同源路径。这个坑最初被「错误吞成空列表」掩盖
（页面显示成「暂无可绑定的登录方式」），所以绑定页现在区分「加载失败」与「真的没有」。

### 3. `TempAuth.token` 没有 default

`token` 是主键却没有 `default`，而回调只调 `acreate(user=user)` → `null value in column "token"
violates not-null constraint`。

**规范**：主键型 UUID 字段必须自带 `default=uuid.uuid4`，不要指望调用方传。
这个坑从异步化改造起就存在，但一直没暴露——因为在此之前未绑定的身份会被更早地拒绝，
根本走不到建 TempAuth 那行，直到绑定功能上线才第一次真正走通登录。

### 4. 回调页没把 JWT 落 localStorage

`exchangeToken` 只把响应原样返回，从不 `setTokens`。回调页 `navigate('/')` 后，
`RequireAuth` 只看 `hasToken()`，判定未登录 → 立刻弹回 `/login`。表现是「扫码成功但没进系统」，
且后端日志里**看不到 `/organization/me`**（压根没进主界面）。

**规范**：token 落盘是 **API 层**的责任（与 `authApi.login` 同一约定），不要放在页面组件里。
排查这类「静默跳回登录页」时，先看后端日志有没有 `/organization/me`——没有就是前端没带上 token。

### 5. 改完 `vite.config.ts` 必须重启 dev server

配置不热更新。改了代理却只刷新页面，会误判成「改了没用」。

### 6. Google：`scope` 必须编码，且后端进程要能出网

`scope` 是空格分隔的多值（`openid email profile`），**裸空格会让授权页直接报错**。
飞书的 scope 是单值，这坑到接 Google 才暴露。

更硬的门槛在网络——Google 端点在国内**直连超时**（实测 `oauth2.googleapis.com`
直连 10s 超时、经代理 0.58s 通；对照飞书直连 0.28s 通）。涉及两条独立链路：

1. **后端进程**要能访问 `oauth2.googleapis.com` / `openidconnect.googleapis.com`。
   `httpx` 默认 `trust_env=True` 会读 `HTTPS_PROXY`，所以**启动后端的那个终端
   必须先 `proxy_on`**，否则授权成功、回调却报 `exchange_failed`。
2. **用户浏览器**要能打开 `accounts.google.com` 授权页。

推论：**部署在无出口代理的国内服务器上，Google 登录必然失效**，上线前要先定出网方案。

### 7. Google：身份唯一键必须用 `sub`，不能用 `email`

Google 官方明文警告：

> 在实现账号管理系统时，**不应**使用 ID 令牌中的 `email` 字段作为用户的唯一标识符。
> 请始终使用 `sub` 字段，因为即使电子邮件地址发生更改，该字段对于 Google 账号也是唯一的。

邮箱可变，且 Google Workspace 域内可被管理员回收后重新分配给他人——拿它当唯一键
存在账号接管风险。这与本文开头「扫码进来的到底是谁」的唯一答案来源是同一条原则。

### 8. 本分类的 App Secret 存的是密文，读取侧必须解密

`SystemConfigAdminForm.clean_value` 对 `is_secret=True` 的值做 `SecretCodec.encrypt`，
所以**后台填进去的 secret 在库里是密文**。而 `_build_config` 一度只对「借用共用分类」
的凭证解密，本分类的 `client_secret` 直接取 `row.value`——等于把密文当密钥发给 Provider。

症状隐蔽：**授权页能正常打开，回调换 token 才失败**。飞书长期没暴露是因为它的凭证走
borrowed 路径（有解密）；微信从未配置过；Google 必须用本分类凭证，才首次触发。

现已统一走 `ProviderRegistry._decrypt_secret`（未加密的值原样返回、解密失败返回空串，
绝不把密文当密钥用），`_build_config` 与 `_borrow_credentials` 共用，单测
`test_own_secret_is_decrypted` 兜住。**新增 Provider 若使用本分类凭证，勿绕过这条路径。**

### 9. GitHub：token 响应必须协商 JSON，身份键用数字 id

1. token 端点（`github.com/login/oauth/access_token`）按请求头协商响应格式，
   **必须带 `Accept: application/json`**，否则返回 `access_token=...&scope=...`
   的 urlencoded 纯文本，`resp.json()` 直接抛解析异常。且 GitHub 对无效 code
   可能返回 **HTTP 200 + error body**，不能只看状态码。
2. 身份唯一键用数字 `id`。`login`（用户名）可以改名、`email` 可以更换或始终
   私密——拿它们当唯一键会导致改名后登录身份漂移（与 Google 用 `sub` 同一原则）。
3. 私密邮箱在 `/user` 里是 null，要单独调 `/user/emails` 取 primary（需
   `user:email` scope）。邮箱只是展示信息，取不到不影响登录。
4. 网络门槛同 Google 踩坑 6：**后端进程**要能访问 `github.com` /
   `api.github.com`（httpx 读 `HTTPS_PROXY`，启动后端的终端先 `proxy_on`）；
   **用户浏览器**要能打开 `github.com/login/oauth/authorize` 授权页。国内
   直连 github 多数时间可达但间歇性超时，无出口代理的国内服务器上该登录方式
   不保证可用。

---

## 八、本地自测清单

改完本模块后按顺序走一遍（单测不覆盖这些链路）：

1. `migrate social_auth`，重启后端（模型改动不热更新）
2. 登录页：`GET /api/v1/social/providers` 返回已启用方式，二维码能出图
3. 扫码（未绑定身份）→ 回调页提示「尚未绑定」，**不是** 404
4. 账号密码登录 → `/settings/bindings` 显示各平台绑定状态（未配置的平台显示灰态）
5. 点「绑定」→ 扫码 → 跳回并提示绑定成功
6. 退出 → 用刚绑定的身份扫码 → 进入系统，日志出现 `GET /api/v1/organization/me 200`
7. 换绑：先「解绑」再绑新号（同平台直绑会被唯一约束拒绝）

后端单测：`tests/ci/unit/social_auth/`（services / views / callback 全链路）。
前端单测：`features/auth/social-callback-domain.test.ts`、`features/auth/social-api.test.ts`。