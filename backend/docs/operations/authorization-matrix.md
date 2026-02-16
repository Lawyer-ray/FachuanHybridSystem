# 权限矩阵与敏感端点门禁验收

本文件用于把“权限策略”变成可审计、可测试、可持续演进的工程资产。

## 1. 角色与身份（示例，可按实际调整）

| 角色 | 描述 | 典型能力 |
|---|---|---|
| anonymous | 未登录 | 仅访问公开内容（若存在） |
| user | 已登录普通用户 | 仅访问所属组织的数据与功能 |
| staff | 运维/管理员账号（Django staff） | 可访问诊断/运维类接口 |
| superuser | 超级管理员 | 全域管理 |

建议统一管理员判定：`is_admin` / `is_staff` / `is_superuser`。

## 2. 资源与动作（必须显式列出）

| 资源域 | 资源 | 动作 | 备注 |
|---|---|---|---|
| organization | team / lawyer / lawfirm | read / write / manage | 多租户隔离关键 |
| cases | case / party / log | read / write / export | 写路径需要审计 |
| documents | template / generation | read / write / download | 涉及文件访问与路径校验 |
| automation | token / scraper / sms | read / write / trigger | 高风险（外部调用/自动化） |
| chat_records | recording / screenshot | read / write / export | 资源型任务（ffmpeg/ocr） |

## 3. 敏感端点分类（必须维持白名单）

以下类型的端点必须为管理员可访问（admin-only），并建议配置独立限流策略（如 ADMIN 级别）：

- 诊断/监控：health detail、性能指标、资源占用、缓存统计
- 影响系统状态：清缓存、重置指标、清理锁/资源、触发后台任务
- 配置回显：任何包含配置的接口（即使已脱敏也建议 admin-only）
- 导出/批处理：容易触发数据外泄与资源消耗

验收标准：

- 任意新增或修改上述端点，必须同步加上门禁测试（结构测试/属性测试）
- 端点返回体必须通过“敏感字段扫描”（禁止 secret/token/key 等字段）

## 4. 测试门禁（建议落点）

### 4.1 结构测试（强制）

- 检查所有敏感端点是否调用管理员门禁函数（如 `ensure_admin_request`）
- 检查敏感端点是否使用 ADMIN 级别限流策略

### 4.2 单元测试（强制）

- anonymous/user 访问敏感端点返回 403
- staff/superuser 访问成功
- 返回体不包含敏感字段

## 5. 审计日志（强制）

对以下操作必须写审计事件（建议独立 logger 或独立表）：

- 清缓存/重置指标/资源清理
- 批量导出/批量删除/批量变更
- 密钥轮换/配置变更（若提供界面）

审计事件字段建议：

- actor_id / actor_role / org_id
- action / resource_type / resource_id
- result / error_code
- request_id / ip / user_agent
- created_at
