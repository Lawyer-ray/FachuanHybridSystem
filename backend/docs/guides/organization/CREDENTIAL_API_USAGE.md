# 账号凭证 API 使用指南

## 接口地址

`GET /api/v1/organization/credentials`

## 功能说明

获取账号凭证列表，支持多种过滤方式。

## 查询参数

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `lawyer_id` | int | 否 | 按律师 ID 精确过滤 |
| `lawyer_name` | string | 否 | 按律师姓名模糊过滤（支持 real_name 或 username） |

## 使用示例

### 1. 获取所有凭证

```bash
GET /api/v1/organization/credentials
```

**响应示例：**
```json
[
  {
    "id": 1,
    "lawyer": 1,
    "site_name": "广东法院网",
    "url": "https://court.gd.gov.cn",
    "account": "zhangsan@example.com",
    "password": "password123",
    "created_at": "2024-01-01T10:00:00Z",
    "updated_at": "2024-01-01T10:00:00Z"
  },
  {
    "id": 2,
    "lawyer": 2,
    "site_name": "检察院网站",
    "url": "https://procuratorate.example.com",
    "account": "lisi@example.com",
    "password": "password456",
    "created_at": "2024-01-02T10:00:00Z",
    "updated_at": "2024-01-02T10:00:00Z"
  }
]
```

---

### 2. 按律师 ID 查询

```bash
GET /api/v1/organization/credentials?lawyer_id=1
```

**说明：** 返回律师 ID 为 1 的所有凭证

---

### 3. 按律师姓名查询（精确匹配）

```bash
GET /api/v1/organization/credentials?lawyer_name=张三
```

**说明：** 返回真实姓名或用户名包含"张三"的律师的所有凭证

---

### 4. 按律师姓名查询（模糊匹配）

```bash
GET /api/v1/organization/credentials?lawyer_name=张
```

**说明：** 返回真实姓名或用户名包含"张"的律师的所有凭证

**匹配规则：**
- 匹配 `lawyer.real_name` 字段（如：张三、张伟）
- 匹配 `lawyer.username` 字段（如：zhangsan、zhang123）
- 不区分大小写（对英文有效）

---

### 5. 按用户名查询

```bash
GET /api/v1/organization/credentials?lawyer_name=zhangsan
```

**说明：** 返回用户名包含"zhangsan"的律师的所有凭证

---

### 6. 组合查询

```bash
GET /api/v1/organization/credentials?lawyer_id=1&lawyer_name=张三
```

**说明：** 同时满足两个条件（取交集）

---

## 前端使用示例

### JavaScript/TypeScript

```typescript
// 获取所有凭证
const getAllCredentials = async () => {
  const response = await fetch('/api/v1/organization/credentials');
  const data = await response.json();
  return data;
};

// 按律师 ID 查询
const getCredentialsByLawyerId = async (lawyerId: number) => {
  const response = await fetch(
    `/api/v1/organization/credentials?lawyer_id=${lawyerId}`
  );
  const data = await response.json();
  return data;
};

// 按律师姓名查询
const getCredentialsByLawyerName = async (lawyerName: string) => {
  const response = await fetch(
    `/api/v1/organization/credentials?lawyer_name=${encodeURIComponent(lawyerName)}`
  );
  const data = await response.json();
  return data;
};

// 组合查询
const getCredentials = async (filters: {
  lawyerId?: number;
  lawyerName?: string;
}) => {
  const params = new URLSearchParams();
  
  if (filters.lawyerId) {
    params.append('lawyer_id', filters.lawyerId.toString());
  }
  
  if (filters.lawyerName) {
    params.append('lawyer_name', filters.lawyerName);
  }
  
  const response = await fetch(
    `/api/v1/organization/credentials?${params.toString()}`
  );
  const data = await response.json();
  return data;
};
```

### React 示例

```tsx
import { useState, useEffect } from 'react';

function CredentialList() {
  const [credentials, setCredentials] = useState([]);
  const [lawyerName, setLawyerName] = useState('');

  useEffect(() => {
    fetchCredentials();
  }, [lawyerName]);

  const fetchCredentials = async () => {
    const params = new URLSearchParams();
    if (lawyerName) {
      params.append('lawyer_name', lawyerName);
    }

    const response = await fetch(
      `/api/v1/organization/credentials?${params.toString()}`
    );
    const data = await response.json();
    setCredentials(data);
  };

  return (
    <div>
      <input
        type="text"
        placeholder="搜索律师姓名..."
        value={lawyerName}
        onChange={(e) => setLawyerName(e.target.value)}
      />
      
      <ul>
        {credentials.map((cred) => (
          <li key={cred.id}>
            {cred.site_name} - {cred.account}
          </li>
        ))}
      </ul>
    </div>
  );
}
```

---

## 常见使用场景

### 场景 1：律师个人凭证管理
用户登录后，查看自己的所有账号凭证：

```bash
GET /api/v1/organization/credentials?lawyer_id={当前用户ID}
```

### 场景 2：管理员搜索凭证
管理员通过律师姓名搜索凭证：

```bash
GET /api/v1/organization/credentials?lawyer_name=张三
```

### 场景 3：自动填充表单
在创建爬虫任务时，根据律师姓名自动填充账号密码：

```typescript
// 1. 用户输入律师姓名
const lawyerName = "张三";

// 2. 查询该律师的凭证
const credentials = await fetch(
  `/api/v1/organization/credentials?lawyer_name=${lawyerName}`
).then(r => r.json());

// 3. 自动填充表单
if (credentials.length > 0) {
  const cred = credentials[0];
  form.setFieldsValue({
    account: cred.account,
    password: cred.password,
  });
}
```

---

## 注意事项

1. **权限控制**：当前接口未做权限限制，生产环境建议添加权限校验
2. **密码安全**：密码以明文返回，建议前端不要在日志中记录
3. **性能优化**：使用了 `select_related("lawyer")` 优化查询性能
4. **模糊匹配**：使用 `icontains` 实现不区分大小写的模糊匹配

---

## 测试

运行测试：

```bash
cd backend
make test apps/organization/tests/test_credential_api.py
```

或者：

```bash
PYTHONPATH=apiSystem:. pytest apps/organization/tests/test_credential_api.py -v
```

---

## 更新日志

- **2024-01-XX**: 新增 `lawyer_name` 参数，支持按律师姓名模糊查询
