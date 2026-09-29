# 🧪 测试工厂（testing）

跨 app 共享的极简测试工厂包。**这不是注册的 Django app**（不在 `INSTALLED_APPS`，无 AppConfig / models / migrations），纯粹为 CI 单测提供无 factory_boy 依赖的模型构造函数。

## 提供的工厂函数

`apps/testing/factories.py` 提供六个工厂（普通函数而非类）：

| 工厂 | 构造模型 | 说明 |
|------|----------|------|
| `LawyerFactory` | organization.Lawyer | 用户 |
| `ClientFactory` | client.Client | 法人/非法人客户自动填 legal_representative |
| `ClientIdentityDocFactory` | client.ClientIdentityDoc | 自然人默认身份证、机构客户默认营业执照 |
| `ContractFactory` | contracts.Contract | 合同 |
| `CaseFactory` | cases.Case | 自动挂 Contract |
| `CaseLogFactory` | cases.CaseLog | 自动挂 Case + Lawyer |

- 全部基于 `Model.objects.create(**kwargs)`，模块级 `itertools.count` 生成唯一后缀 token 防唯一约束冲突
- 关键字段可通过 kwargs 覆盖

## 使用方式

```python
from apps.testing.factories import CaseFactory, LawyerFactory

lawyer = LawyerFactory()
case = CaseFactory(created_by=lawyer)
```

被 `backend/tests/ci/unit/` 下 25+ 个测试文件与 `tests/ci/integration/` 引用。注意它与 backend 根的 `tests/`（pytest 套件）是两套东西：本包只服务需要 Django ORM 的工厂构造。
