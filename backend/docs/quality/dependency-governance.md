# 依赖锁定与漏洞 SLA 验收

本文件把“供应链安全”变成可执行的工程门禁：可复现构建 + 漏洞治理闭环。

## 1. 依赖锁定（Reproducible Builds）

验收标准：

- 生产构建必须使用锁定文件/约束文件，确保同一代码在不同环境安装得到一致依赖版本
- 锁定文件更新必须通过 PR，且 PR 内说明变更原因（功能/安全/兼容）
- 禁止在生产环境执行“漂移式升级”（例如无锁定的 `pip install -U`）

建议实践（可选其一）：

- requirements + constraints（当前选用）：以 `requirements.txt` + `requirements-dev.txt` + `requirements-test.txt` 配合 `constraints/py312.txt` 作为单一安装入口
- pip-tools / uv lock（可选升级）：仅当 CI/生产需要更强可复现性时，再引入 lock 文件并建立更新流程

## 1.1 Django 版本策略（项目约束）

- Django 版本以 `constraints/py312.txt` 为单一事实来源，并在 `requirements.txt` 里保持同版本钉死，避免区间漂移

## 2. 漏洞治理（Vulnerability Management）

### 2.1 分级与修复时限（SLA）

| 等级 | 示例 | 修复时限 | 说明 |
|---|---|---:|---|
| Critical | 远程代码执行、权限绕过 | 24-72 小时 | 可允许临时缓解措施 |
| High | 信息泄露、DoS 可利用 | 7 天 | 必须给出回滚/缓解方案 |
| Medium | 局部影响、需前置条件 | 30 天 | 合理排期 |
| Low | 低风险 | 90 天 | 常规维护 |

### 2.2 豁免流程

验收标准：

- 每个豁免必须包含：漏洞 ID、影响说明、缓解措施、到期时间、负责人
- 到期必须重新评估，否则 CI 失败

## 3. CI 门禁（最低要求）

- pip-audit / SCA 扫描：PR 必跑，阻断 Critical/High
- bandit / SAST：PR 必跑，阻断高危规则
- secrets 扫描：阻断任何新增的密钥/凭证

## 4. 依赖更新节奏（建议）

- 固定每月“依赖升级窗口”，集中处理兼容与回归
- 对安全升级可随时插队，但必须走最小回归测试集
