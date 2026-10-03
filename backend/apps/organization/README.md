# 🏢 组织管理（organization）

用户（Lawyer，系统用户模型）、律所、团队（律师团队 / 业务团队）、外部账号凭证（加密存储 + 法院在线服务自动登录）以及认证体系（JWT / 会话登录、注册、密码重置三步流程、首用户引导）。

## 功能概述

- 律所 / 律师 / 团队 CRUD；律师两组 M2M（lawyer_teams / biz_teams，成员关系定义在 Lawyer 侧）；特权字段管制：`is_admin` 授予/变更与跨所迁移仅 superuser，self 更新限个人资料字段（v27.2.7）
- 外部账号凭证：AccountCredential（密码经 EncryptedTextField 加密）、自动登录（当前仅支持 `court_zxfw` 一张网平台，SUPPORTED_SITE 常量）、批量自动登录与成功率统计
- 认证：登录 / 登出 / 注册 / `/me`；密码重置三步流程（request / verify / confirm）
- **首用户自动注册引导**：AUTO_REGISTER_BOOTSTRAP_USERNAME + first_user_setup_service，首个用户免初始化直接进系统（生产环境需随请求携带 `bootstrap_token` 并与 `BOOTSTRAP_ADMIN_TOKEN` 匹配，v27.2.7）
- **OrgAccessMiddleware**：组织权限计算（request.org_access + Redis 缓存、PERM_OPEN_ACCESS 开关、sync/async 双模）；另有 ApiTrailingSlashMiddleware（统一去尾斜杠）
- 律师导入（LawyerImportService）

## 目录结构

```
organization/
├── models/               # Lawyer(AbstractUser)、LawFirm、Team、AccountCredential
├── api/                  # auth、lawyer、lawfirm、team、credential + utils_api（公共辅助）
├── services/
│   ├── auth/             # AuthService + PasswordResetService
│   ├── credential/       # AccountCredentialService + AccountCredentialAdminService（自动登录）
│   ├── lawyer/           # facade / mutation / query / upload + LawyerImportService、LawyerResolveService
│   ├── access/           # org_access_computation、organization_access_policy
│   ├── setup/            # first_user_setup_service
│   ├── LawFirmService、TeamService、OrganizationServiceAdapter、wiring、dtos
├── admin/                # LawFirmAdmin、LawyerAdmin、TeamAdmin、AccountCredentialAdmin
├── middleware.py         # OrgAccessMiddleware、ApiTrailingSlashMiddleware、invalidate_user_org_cache
└── views.py + forms.py   # Django 会话登录 AuthLoginView、注册/首用户视图
```

## 数据模型

- `Lawyer` — 用户模型（继承 AbstractUser：real_name、phone、email、license_no、id_card、law_firm FK、is_admin、license_pdf、avatar、lawyer_teams / biz_teams 两组 M2M）
- `LawFirm` — 律所（name、address、phone、social_credit_code、bank_name、bank_account）
- `Team` — 团队（name、team_type=lawyer/biz、law_firm FK；无 leader 字段，成员在 Lawyer 侧）
- `AccountCredential` — 外部账号凭证（site_name、url、account、password=EncryptedTextField、last_login_success_at、login_success_count、login_failure_count、success_rate 属性）

## API 端点

前缀 `/api/v1/organization`：

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/login`、`/logout`、`/register` | 认证 |
| GET | `/me` | 当前用户 |
| POST | `/password-reset/{request,verify,confirm}` | 密码重置三步 |
| — | `/lawyers`、`/lawfirms`、`/teams`、`/credentials` | 各自完整 CRUD（`/credentials` 写操作要求 can_update_lawyer：本人 / 同所 is_admin / superuser） |

创建凭证用 `site_name`（非 platform）；创建律师用 username / real_name / license_no。

## 依赖模块

- `apps.core`（异常、认证、ServiceLocator）、`apps.documents`、`apps.social_auth`；自动登录经 core 依赖间接使用 automation
