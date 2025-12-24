# 👥 客户管理模块 (Client)

客户管理模块，提供客户信息的创建、查询、更新和删除功能，支持客户身份证件管理。

## 📚 模块概述

本模块负责管理法律服务客户的完整信息，包括：
- 客户基本信息管理
- 客户身份证件管理
- 客户类型管理（自然人/法人）
- 客户联系方式管理

## 📁 目录结构

```
client/
├── admin/              # Django Admin 配置
│   ├── client_admin.py         # 客户 Admin
│   └── clientidentitydoc_admin.py  # 身份证件 Admin
├── api/                # API 接口
│   ├── client_api.py           # 客户 API
│   └── clientidentitydoc_api.py    # 身份证件 API
├── services/           # 业务逻辑
│   ├── client_service.py       # 客户服务
│   └── text_parser.py          # 文本解析器
├── models.py           # 数据模型
├── schemas.py          # Pydantic Schemas
└── migrations/         # 数据库迁移
```

## 🚀 快速开始

### 1. Admin 后台

```bash
# 访问客户管理后台
open http://localhost:8000/admin/client/
```

### 2. API 使用

```python
import requests

BASE_URL = "http://localhost:8000/api/v1/clients"
headers = {"Authorization": "Bearer <your_jwt_token>"}

# 创建客户
response = requests.post(BASE_URL, json={
    "name": "张三",
    "client_type": "individual",
    "id_number": "110101199001011234",
    "phone": "13800138000",
    "address": "北京市朝阳区"
}, headers=headers)

client_id = response.json()["data"]["id"]

# 获取客户详情
response = requests.get(f"{BASE_URL}/{client_id}", headers=headers)
client = response.json()["data"]

# 更新客户
response = requests.put(f"{BASE_URL}/{client_id}", json={
    "phone": "13900139000"
}, headers=headers)

# 添加身份证件
response = requests.post(f"{BASE_URL}/{client_id}/identity-docs", json={
    "doc_type": "id_card",
    "doc_number": "110101199001011234",
    "doc_image": "base64_encoded_image"
}, headers=headers)
```

### 3. Service 层使用

```python
from apps.client.services.client_service import ClientService
from apps.client.schemas import ClientCreateSchema

service = ClientService()

# 创建客户
client = service.create_client(
    data=ClientCreateSchema(
        name="张三",
        client_type="individual",
        id_number="110101199001011234",
        phone="13800138000"
    ),
    user=request.user
)

# 获取客户
client = service.get_client(client_id=1, user=request.user)

# 更新客户
client = service.update_client(
    client_id=1,
    data=ClientUpdateSchema(phone="13900139000"),
    user=request.user
)
```

## 🔑 核心功能

### 客户管理
- ✅ 创建、查询、更新、删除客户
- ✅ 客户类型管理（自然人、法人）
- ✅ 客户身份证号管理
- ✅ 客户联系方式管理
- ✅ 客户地址管理
- ✅ 客户标记（是否为本所客户）

### 身份证件管理
- ✅ 添加、编辑、删除身份证件
- ✅ 证件类型（身份证、营业执照、护照等）
- ✅ 证件图片上传
- ✅ 证件有效期管理

### 文本解析
- ✅ 从文本中提取客户信息
- ✅ 智能识别姓名、电话、地址
- ✅ 批量导入客户

## 📊 数据模型

### Client (客户)
- `name`: 客户姓名/名称
- `client_type`: 客户类型（individual/company）
- `id_number`: 身份证号/统一社会信用代码
- `phone`: 联系电话
- `address`: 地址
- `is_our_client`: 是否为本所客户
- `created_by`: 创建人

### ClientIdentityDoc (身份证件)
- `client`: 关联客户
- `doc_type`: 证件类型
- `doc_number`: 证件号码
- `doc_image`: 证件图片
- `issue_date`: 签发日期
- `expiry_date`: 有效期
- `created_by`: 创建人

## 🔒 权限控制

### 功能级别权限
- `client.add_client`: 创建客户
- `client.view_client`: 查看客户
- `client.change_client`: 修改客户
- `client.delete_client`: 删除客户

### 对象级别权限
- 客户创建人可以查看和修改自己的客户
- 管理员可以查看和修改所有客户
- 同组织成员可以查看组织内的客户

## 🧪 测试

```bash
# 运行单元测试
cd backend
source venv311/bin/activate
python -m pytest tests/unit/test_client/ -v

# 运行集成测试
python -m pytest tests/integration/test_client_api/ -v

# 运行属性测试
python -m pytest tests/property/test_client_properties/ -v
```

## 📝 相关文档

- **[models.py](models.py)** - 数据模型定义
- **[schemas.py](schemas.py)** - API Schema 定义
- **[services/text_parser.py](services/text_parser.py)** - 文本解析器

## 🔗 依赖模块

- **cases**: 案件模块（案件当事人关联客户）
- **organization**: 组织模块（客户归属组织）
- **core**: 核心模块（异常、接口、验证器）

## 🎯 最佳实践

### 1. 使用 Service 层
```python
# ✅ 正确：使用 Service 层
service = ClientService()
client = service.create_client(data, user)

# ❌ 错误：直接操作 Model
client = Client.objects.create(name="张三")
```

### 2. 验证身份证号
```python
# ✅ 正确：使用验证器
from apps.client.validators import validate_id_number

try:
    validate_id_number("110101199001011234")
except ValidationError as e:
    print(f"身份证号无效: {e}")
```

### 3. 使用文本解析器
```python
# ✅ 正确：使用文本解析器提取信息
from apps.client.services.text_parser import TextParser

parser = TextParser()
info = parser.parse_client_info(
    "张三，电话：13800138000，地址：北京市朝阳区"
)
# info = {"name": "张三", "phone": "13800138000", "address": "北京市朝阳区"}
```

### 4. 处理客户类型
```python
# ✅ 正确：根据客户类型处理
if client.client_type == "individual":
    # 自然人客户
    validate_id_number(client.id_number)
elif client.client_type == "company":
    # 法人客户
    validate_credit_code(client.id_number)
```

## 🐛 常见问题

### Q1: 如何批量导入客户？
**A**: 使用 Django Admin 的导入功能，或调用 API 批量创建。

### Q2: 如何处理重复客户？
**A**: 系统会根据身份证号/统一社会信用代码检查重复，创建前会验证。

### Q3: 如何上传身份证件图片？
**A**: 使用 Base64 编码上传图片，或使用文件上传接口。

## 📈 性能优化

- ✅ 使用 `select_related` 预加载关联对象
- ✅ 使用索引优化查询（姓名、身份证号、电话）
- ✅ 使用缓存减少数据库查询
- ✅ 批量操作使用 `bulk_create`

## 🔄 版本历史

- **v1.0.0** (2024-01): 初始版本
- **v1.1.0** (2024-03): 添加身份证件管理
- **v1.2.0** (2024-06): 添加文本解析功能
- **v1.3.0** (2024-09): 优化客户搜索
