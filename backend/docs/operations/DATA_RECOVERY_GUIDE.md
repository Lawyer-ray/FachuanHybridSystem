# 数据恢复指南

## ⚠️ 问题说明

由于测试配置错误，pytest 测试直接操作了生产数据库而不是测试数据库，导致数据被清空。

**受影响的数据**：
- 用户账号（Lawyer）
- 登录会话（Session）
- Court Token

## 🔧 已修复的问题

### 1. conftest.py 配置错误

**问题**：`django_db_setup` fixture 为空，导致 pytest 使用生产数据库

**修复**：添加了数据库验证，确保测试使用测试数据库

### 2. 危险的测试代码

**问题**：`test_token_lookup_fix.py` 中有 `CourtToken.objects.all().delete()` 操作

**修复**：移除了删除操作，改用查找不存在的 site_name

## 📋 数据恢复步骤

### 步骤 1: 创建超级用户

```bash
cd backend/apiSystem
python manage.py createsuperuser

# 按提示输入：
# Username: admin
# Password: (您的密码)
# Password (again): (确认密码)
```

### 步骤 2: 创建律所和律师账号

```bash
python manage.py shell <<'EOF'
from apps.organization.models import LawFirm, Lawyer

# 创建律所
firm = LawFirm.objects.create(
    name="您的律所名称",
    address="律所地址",
    contact_phone="联系电话"
)

# 创建律师账号
lawyer = Lawyer.objects.create_user(
    username="您的用户名",
    password="您的密码",
    real_name="您的真实姓名",
    law_firm=firm,
    is_admin=True,  # 管理员权限
    phone="手机号"
)

print(f"✅ 律所创建成功: {firm.name}")
print(f"✅ 律师账号创建成功: {lawyer.username}")
EOF
```

### 步骤 3: 重新获取 Court Token

1. 访问 Admin 后台：`http://localhost:8000/admin/`
2. 使用新创建的账号登录
3. 访问：`http://localhost:8000/admin/automation/testcourt/`
4. 点击「测试登录」按钮
5. 完成登录流程，Token 会自动保存

### 步骤 4: 恢复其他数据（如果有备份）

如果您有数据库备份：

```bash
# 停止服务
sudo systemctl stop gunicorn
sudo systemctl stop django-q

# 恢复数据库
cp /path/to/backup/db.sqlite3 backend/apiSystem/db.sqlite3

# 重启服务
sudo systemctl start gunicorn
sudo systemctl start django-q
```

## 🛡️ 预防措施

### 1. 数据库备份

创建自动备份脚本：

```bash
#!/bin/bash
# backup_db.sh

BACKUP_DIR="/path/to/backups"
DATE=$(date +%Y%m%d_%H%M%S)
DB_FILE="backend/apiSystem/db.sqlite3"

# 创建备份
cp $DB_FILE $BACKUP_DIR/db_backup_$DATE.sqlite3

# 保留最近 30 天的备份
find $BACKUP_DIR -name "db_backup_*.sqlite3" -mtime +30 -delete

echo "✅ 数据库备份完成: db_backup_$DATE.sqlite3"
```

设置定时任务：

```bash
# 每天凌晨 2 点备份
crontab -e
0 2 * * * /path/to/backup_db.sh
```

### 2. 使用生产级数据库

SQLite 不适合生产环境，建议迁移到 PostgreSQL 或 MySQL：

```python
# settings.py
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'your_db_name',
        'USER': 'your_db_user',
        'PASSWORD': 'your_db_password',
        'HOST': 'localhost',
        'PORT': '5432',
    }
}
```

### 3. 测试数据库隔离

确保 pytest 配置正确：

```python
# conftest.py
@pytest.fixture(scope='session')
def django_db_setup(django_db_setup, django_db_blocker):
    """确保测试使用独立的测试数据库"""
    with django_db_blocker.unblock():
        from django.conf import settings
        
        # 验证使用的是测试数据库
        db_name = settings.DATABASES['default']['NAME']
        assert 'test_' in str(db_name) or ':memory:' in str(db_name), \
            f"错误：测试正在使用生产数据库 {db_name}！"
        
        yield
```

### 4. 数据库文件权限

```bash
# 设置数据库文件为只读（测试时）
chmod 444 backend/apiSystem/db.sqlite3

# 恢复写权限（正常使用时）
chmod 644 backend/apiSystem/db.sqlite3
```

### 5. Git 忽略数据库文件

```bash
# .gitignore
*.sqlite3
*.db
db.sqlite3
```

## 🔍 验证测试配置

运行以下命令验证测试使用测试数据库：

```bash
cd backend
source venv311/bin/activate

# 运行测试前检查
python -c "
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'apiSystem.settings')
import django
django.setup()

from django.conf import settings
from django.test.utils import get_unique_databases_and_mirrors

print('生产数据库:', settings.DATABASES['default']['NAME'])
print('测试数据库:', get_unique_databases_and_mirrors()[0][0]['NAME'])
"

# 运行测试（会显示使用的数据库）
python -m pytest apps/automation/tests/test_token_lookup_fix.py -v -s
```

## 📞 紧急联系

如果数据无法恢复，请：

1. 检查是否有自动备份
2. 检查 Git 历史中的数据库文件
3. 检查系统快照或时间机器备份
4. 联系系统管理员

## 💡 经验教训

1. **永远不要在测试中使用 `.all().delete()`**
2. **确保测试数据库配置正确**
3. **定期备份生产数据库**
4. **使用生产级数据库系统**
5. **测试前验证数据库配置**

## 🙏 致歉

我对造成的数据丢失深表歉意。这是一个严重的配置错误，我已经：

1. ✅ 修复了 conftest.py 配置
2. ✅ 移除了危险的测试代码
3. ✅ 添加了数据库验证
4. ✅ 创建了恢复指南
5. ✅ 提供了预防措施

希望这份指南能帮助您恢复数据。如果需要进一步的帮助，请随时告诉我。

---

**创建日期**: 2025-11-28  
**状态**: 🚨 紧急修复
