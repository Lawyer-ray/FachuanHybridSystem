# 冲刺 10/10：Backend 审计清单（更苛刻口径）

本清单用于把“10/10”具体化为可审计的验收项。建议在每次大版本发布前做一次完整自查，并在 CI/监控/Runbook 中固化。

## 0. 必备输出物（缺一不可）

- 权限矩阵与门禁验收：[operations/authorization-matrix.md](../../operations/authorization-matrix.md)
- 可观测性 SLO/告警/Runbook：[operations/observability/slo-and-runbooks.md](../../operations/observability/slo-and-runbooks.md)
- 依赖锁定与漏洞 SLA：[quality/dependency-governance.md](../dependency-governance.md)
- 备份恢复与密钥轮换演练：[operations/backup-and-key-rotation.md](../../operations/backup-and-key-rotation.md)

## 1. P0 安全（任何一项不满足都不算 10/10）

- [ ] 所有敏感端点（诊断/配置/导出/批处理/影响系统状态）均为 admin-only
- [ ] 敏感端点有结构测试/属性测试门禁，防止未来回归
- [ ] 返回体通过敏感字段扫描（禁止 secret/token/key 类字段）
- [ ] 影响系统状态的操作有审计日志（含 request_id、actor、resource、result）
- [ ] 外部调用具备超时 + 重试（退避）+ 降级/断路策略，并可观测

## 2. P0 供应链（构建可复现 + 漏洞治理闭环）

- [ ] 生产依赖不可漂移（锁定文件/约束文件 + CI 校验）
- [ ] Critical/High 漏洞有明确修复 SLA，并在 CI 阻断
- [ ] 豁免流程可审计（漏洞 ID、原因、缓解措施、到期时间、负责人）
- [ ] secrets 扫描覆盖新增文件与配置，阻断任何密钥入库

## 3. P1 可观测性（能发现问题、能定位问题、能复盘改进）

- [ ] API：RPS、错误率、P50/P95/P99、饱和度指标可用
- [ ] 任务：队列积压、耗时分布、失败率/重试率、超时率可用
- [ ] 外部依赖：按 host 统计成功率/时延/超时率可用
- [ ] 至少 3 条 SLO 定义完成并落地告警
- [ ] 至少 5 条核心告警具备 Runbook，且可在 5 分钟内定位到主要原因域
- [ ] 日志具备 request_id 关联；关键链路建议具备 trace/span

## 4. P1 可靠性（抗事故、抗流量、抗变更）

- [ ] 资源型任务有超时/并发控制/隔离队列
- [ ] 任务具备幂等语义（重复提交不产生重复副作用）
- [ ] 数据库迁移具备回滚策略；重大迁移有灰度/双写方案
- [ ] readiness/liveness 语义清晰且可靠（不会误杀/不会放行错误依赖）

## 5. P2 测试体系（能挡回归）

- [ ] 单元测试覆盖关键纯逻辑
- [ ] 集成测试覆盖关键写路径（含权限与多租户隔离）
- [ ] e2e 覆盖最小用户旅程（登录→关键业务→导出/任务）
- [ ] 结构测试覆盖架构边界与安全门禁关键约束

## 6. P2 运维治理（可运行）

- [ ] 明确 RPO/RTO 并有演练记录
- [ ] 密钥轮换有双验窗口与回滚方案，并有演练记录
- [ ] 事故分级、应急流程、发布回滚流程可执行
