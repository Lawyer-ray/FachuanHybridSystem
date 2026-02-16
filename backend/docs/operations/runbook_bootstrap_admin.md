## 安装期初始化（首位管理员）Runbook

### 目标
- 保留“首位用户可成为管理员”的产品设计，但把它限制在“安装期一次性动作”，避免公网被抢注。

### 生产环境必备配置
- 允许首位用户初始化为管理员：
  - `ALLOW_FIRST_USER_SUPERUSER=true`
  - `BOOTSTRAP_ADMIN_TOKEN=<强随机口令>`
- 可选：启用 admin 注册页面（不建议长期打开）：
  - `ALLOW_ADMIN_REGISTER=true`

注意：生产环境下当 `ALLOW_FIRST_USER_SUPERUSER=true` 且 `BOOTSTRAP_ADMIN_TOKEN` 为空时，服务会在启动阶段直接失败。

### 初始化方式一：API 注册（推荐）
- 接口：`POST /api/v1/organization/register`
- 请求头：`X-Bootstrap-Token: <BOOTSTRAP_ADMIN_TOKEN>`
- Body：`username/password/real_name/phone`
- 预期结果：创建首位用户并成为超级管理员；后续注册用户默认待审批。

### 初始化方式二：Admin 注册页（仅安装期临时开启）
- 路径：`/admin/register`
- 要求：
  - `ALLOW_ADMIN_REGISTER=true`
  - 页面中填写“安装期口令”（与 `BOOTSTRAP_ADMIN_TOKEN` 一致）
- 初始化完成后建议：
  - 关闭 `ALLOW_ADMIN_REGISTER`
  - 关闭/移除 `ALLOW_FIRST_USER_SUPERUSER`

### 初始化完成后的收尾检查
- 管理员可登录 admin 并审批待激活用户（API 或 admin）。
- 建议立即把 `BOOTSTRAP_ADMIN_TOKEN` 从运行环境移除（或改成无效值），避免运维误用。
