# 法院文书下载功能配置说明

## 📋 概述

本文档详细说明法院文书下载优化功能的所有配置项，包括环境变量、Django settings 配置、数据库配置等。

## 🔧 Django Settings 配置

在 `backend/apiSystem/apiSystem/settings.py` 中添加以下配置：

### 基础配置

```python
import os
from pathlib import Path

# 文书下载目录
COURT_DOCUMENT_DOWNLOAD_DIR = os.path.join(MEDIA_ROOT, "court_documents")

# API 拦截超时（毫秒）
COURT_DOCUMENT_API_TIMEOUT = int(os.environ.get('COURT_DOCUMENT_API_TIMEOUT', 30000))

# 文件下载超时（毫秒）
COURT_DOCUMENT_DOWNLOAD_TIMEOUT = int(os.environ.get('COURT_DOCUMENT_DOWNLOAD_TIMEOUT', 60000))

# 下载延迟范围（秒）
COURT_DOCUMENT_DOWNLOAD_DELAY = (
    int(os.environ.get('COURT_DOCUMENT_DOWNLOAD_DELAY_MIN', 1)),
    int(os.environ.get('COURT_DOCUMENT_DOWNLOAD_DELAY_MAX', 2))
)
```

### 配置项详解

#### 1. COURT_DOCUMENT_DOWNLOAD_DIR

**类型**: `str`  
**默认值**: `MEDIA_ROOT/court_documents`  
**说明**: 文书文件保存目录

**示例**:
```python
# 使用默认值（推荐）
COURT_DOCUMENT_DOWNLOAD_DIR = os.path.join(MEDIA_ROOT, "court_documents")

# 自定义路径
COURT_DOCUMENT_DOWNLOAD_DIR = "/data/court_documents"

# 使用环境变量
COURT_DOCUMENT_DOWNLOAD_DIR = os.environ.get(
    'COURT_DOCUMENT_DOWNLOAD_DIR',
    os.path.join(MEDIA_ROOT, "court_documents")
)
```

**注意事项**:
- 确保目录存在且有写权限
- 生产环境建议使用绝对路径
- 定期清理旧文件，避免磁盘空间不足

#### 2. COURT_DOCUMENT_API_TIMEOUT

**类型**: `int`  
**默认值**: `30000`（30 秒）  
**单位**: 毫秒  
**说明**: API 拦截最大等待时间

**推荐值**:
- 开发环境: 30000（30 秒）
- 生产环境: 30000-60000（30-60 秒）
- 网络较慢: 60000（60 秒）

**示例**:
```python
# 开发环境（默认）
COURT_DOCUMENT_API_TIMEOUT = 30000

# 生产环境（网络较慢）
COURT_DOCUMENT_API_TIMEOUT = 60000

# 从环境变量读取
COURT_DOCUMENT_API_TIMEOUT = int(os.environ.get('COURT_DOCUMENT_API_TIMEOUT', 30000))
```

**注意事项**:
- 超时后会自动触发回退机制
- 不建议设置过长，影响用户体验
- 如果经常超时，检查网络连接

#### 3. COURT_DOCUMENT_DOWNLOAD_TIMEOUT

**类型**: `int`  
**默认值**: `60000`（60 秒）  
**单位**: 毫秒  
**说明**: 单个文件下载超时时间

**推荐值**:
- 小文件（< 1MB）: 30000（30 秒）
- 中等文件（1-10MB）: 60000（60 秒）
- 大文件（> 10MB）: 120000（120 秒）

**示例**:
```python
# 默认配置
COURT_DOCUMENT_DOWNLOAD_TIMEOUT = 60000

# 大文件场景
COURT_DOCUMENT_DOWNLOAD_TIMEOUT = 120000

# 从环境变量读取
COURT_DOCUMENT_DOWNLOAD_TIMEOUT = int(os.environ.get('COURT_DOCUMENT_DOWNLOAD_TIMEOUT', 60000))
```

**注意事项**:
- 根据文件大小和网络速度调整
- 超时会标记为下载失败，可重试
- 监控下载失败率，及时调整

#### 4. COURT_DOCUMENT_DOWNLOAD_DELAY

**类型**: `tuple[int, int]`  
**默认值**: `(1, 2)`  
**单位**: 秒  
**说明**: 下载间隔随机延迟范围

**推荐值**:
- 开发环境: (0, 1)
- 生产环境: (1, 2)
- 严格反爬: (2, 5)

**示例**:
```python
# 默认配置（推荐）
COURT_DOCUMENT_DOWNLOAD_DELAY = (1, 2)

# 开发环境（快速测试）
COURT_DOCUMENT_DOWNLOAD_DELAY = (0, 1)

# 严格反爬环境
COURT_DOCUMENT_DOWNLOAD_DELAY = (2, 5)

# 从环境变量读取
COURT_DOCUMENT_DOWNLOAD_DELAY = (
    int(os.environ.get('COURT_DOCUMENT_DOWNLOAD_DELAY_MIN', 1)),
    int(os.environ.get('COURT_DOCUMENT_DOWNLOAD_DELAY_MAX', 2))
)
```

**注意事项**:
- 避免触发反爬机制
- 延迟过长影响下载效率
- 生产环境建议 1-2 秒

## 🌍 环境变量配置

在 `.env` 文件中配置（推荐）：

```bash
# 法院文书下载配置
COURT_DOCUMENT_DOWNLOAD_DIR=/data/court_documents
COURT_DOCUMENT_API_TIMEOUT=30000
COURT_DOCUMENT_DOWNLOAD_TIMEOUT=60000
COURT_DOCUMENT_DOWNLOAD_DELAY_MIN=1
COURT_DOCUMENT_DOWNLOAD_DELAY_MAX=2
```

### 环境变量优先级

1. 环境变量（最高优先级）
2. `.env` 文件
3. Django settings 默认值

### 示例：使用环境变量

```python
# settings.py
import os

# 从环境变量读取，提供默认值
COURT_DOCUMENT_API_TIMEOUT = int(
    os.environ.get('COURT_DOCUMENT_API_TIMEOUT', 30000)
)
```

## 🗄️ 数据库配置

### 迁移文件

确保已运行迁移：

```bash
cd backend/apiSystem
python manage.py migrate automation
```

### 数据库索引

系统已自动创建以下索引：

```python
class Meta:
    indexes = [
        models.Index(fields=["scraper_task", "download_status"]),
        models.Index(fields=["case"]),
        models.Index(fields=["c_wsbh"]),
        models.Index(fields=["c_fymc"]),
        models.Index(fields=["download_status"]),
        models.Index(fields=["created_at"]),
    ]
```

### 唯一约束

```python
class Meta:
    unique_together = [["c_wsbh", "c_sdbh"]]  # 文书编号+送达编号唯一
```

## 🎭 Playwright 配置

### 浏览器配置

```python
# settings.py

# Playwright 浏览器配置
PLAYWRIGHT_BROWSER_TYPE = os.environ.get('PLAYWRIGHT_BROWSER_TYPE', 'chromium')
PLAYWRIGHT_HEADLESS = os.environ.get('PLAYWRIGHT_HEADLESS', 'true').lower() == 'true'
PLAYWRIGHT_SLOW_MO = int(os.environ.get('PLAYWRIGHT_SLOW_MO', 0))
```

### 环境变量

```bash
# .env
PLAYWRIGHT_BROWSER_TYPE=chromium
PLAYWRIGHT_HEADLESS=true
PLAYWRIGHT_SLOW_MO=0
```

### 安装浏览器

```bash
# 激活虚拟环境
source backend/venv311/bin/activate

# 安装 Playwright 浏览器
playwright install chromium
```

## 📁 文件存储配置

### MEDIA 配置

```python
# settings.py

# Media files
MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

# 确保目录存在
os.makedirs(MEDIA_ROOT, exist_ok=True)
os.makedirs(COURT_DOCUMENT_DOWNLOAD_DIR, exist_ok=True)
```

### 文件权限

```bash
# 设置目录权限
chmod 755 backend/apiSystem/media
chmod 755 backend/apiSystem/media/court_documents

# 设置所有者（如果需要）
chown -R www-data:www-data backend/apiSystem/media
```

## 🔐 安全配置

### 文件上传限制

```python
# settings.py

# 文件上传大小限制（字节）
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024  # 10MB
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024  # 10MB
```

### CORS 配置（如果需要）

```python
# settings.py

# CORS 配置
CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "https://your-frontend-domain.com",
]

CORS_ALLOW_CREDENTIALS = True
```

## 📊 日志配置

### 日志设置

```python
# settings.py

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'file': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': os.path.join(BASE_DIR.parent, 'logs', 'api.log'),
            'maxBytes': 10 * 1024 * 1024,  # 10MB
            'backupCount': 5,
            'formatter': 'verbose',
        },
        'error_file': {
            'level': 'ERROR',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': os.path.join(BASE_DIR.parent, 'logs', 'error.log'),
            'maxBytes': 10 * 1024 * 1024,  # 10MB
            'backupCount': 5,
            'formatter': 'verbose',
        },
    },
    'loggers': {
        'apps.automation': {
            'handlers': ['file', 'error_file'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}
```

### 日志目录

```bash
# 创建日志目录
mkdir -p backend/logs

# 设置权限
chmod 755 backend/logs
```

## 🚀 生产环境配置

### 完整配置示例

```python
# settings.py (生产环境)

import os
from pathlib import Path

# 基础配置
BASE_DIR = Path(__file__).resolve().parent.parent

# 安全配置
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY')
DEBUG = False
ALLOWED_HOSTS = os.environ.get('DJANGO_ALLOWED_HOSTS', '').split(',')

# 数据库配置
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ.get('DB_NAME'),
        'USER': os.environ.get('DB_USER'),
        'PASSWORD': os.environ.get('DB_PASSWORD'),
        'HOST': os.environ.get('DB_HOST'),
        'PORT': os.environ.get('DB_PORT', '5432'),
    }
}

# 文书下载配置
COURT_DOCUMENT_DOWNLOAD_DIR = os.environ.get(
    'COURT_DOCUMENT_DOWNLOAD_DIR',
    '/data/court_documents'
)
COURT_DOCUMENT_API_TIMEOUT = int(os.environ.get('COURT_DOCUMENT_API_TIMEOUT', 30000))
COURT_DOCUMENT_DOWNLOAD_TIMEOUT = int(os.environ.get('COURT_DOCUMENT_DOWNLOAD_TIMEOUT', 60000))
COURT_DOCUMENT_DOWNLOAD_DELAY = (
    int(os.environ.get('COURT_DOCUMENT_DOWNLOAD_DELAY_MIN', 1)),
    int(os.environ.get('COURT_DOCUMENT_DOWNLOAD_DELAY_MAX', 2))
)

# Playwright 配置
PLAYWRIGHT_BROWSER_TYPE = 'chromium'
PLAYWRIGHT_HEADLESS = True
PLAYWRIGHT_SLOW_MO = 0

# 确保目录存在
os.makedirs(COURT_DOCUMENT_DOWNLOAD_DIR, exist_ok=True)
```

### 环境变量文件

```bash
# .env.production

# Django 配置
DJANGO_SECRET_KEY=your-secret-key-here
DJANGO_DEBUG=false
DJANGO_ALLOWED_HOSTS=your-domain.com,www.your-domain.com

# 数据库配置
DB_NAME=fachuandb
DB_USER=fachuanuser
DB_PASSWORD=your-db-password
DB_HOST=localhost
DB_PORT=5432

# 文书下载配置
COURT_DOCUMENT_DOWNLOAD_DIR=/data/court_documents
COURT_DOCUMENT_API_TIMEOUT=30000
COURT_DOCUMENT_DOWNLOAD_TIMEOUT=60000
COURT_DOCUMENT_DOWNLOAD_DELAY_MIN=1
COURT_DOCUMENT_DOWNLOAD_DELAY_MAX=2

# Playwright 配置
PLAYWRIGHT_BROWSER_TYPE=chromium
PLAYWRIGHT_HEADLESS=true
PLAYWRIGHT_SLOW_MO=0
```

## 🧪 测试环境配置

### 测试配置

```python
# settings_test.py

from .settings import *

# 使用内存数据库
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    }
}

# 测试文件目录
COURT_DOCUMENT_DOWNLOAD_DIR = '/tmp/test_court_documents'

# 缩短超时时间
COURT_DOCUMENT_API_TIMEOUT = 5000
COURT_DOCUMENT_DOWNLOAD_TIMEOUT = 10000
COURT_DOCUMENT_DOWNLOAD_DELAY = (0, 0)

# 禁用日志
LOGGING = {}
```

### 运行测试

```bash
# 使用测试配置
python manage.py test --settings=apiSystem.settings_test
```

## 📝 配置检查清单

部署前请检查以下配置：

- [ ] `COURT_DOCUMENT_DOWNLOAD_DIR` 目录存在且有写权限
- [ ] `COURT_DOCUMENT_API_TIMEOUT` 根据网络情况调整
- [ ] `COURT_DOCUMENT_DOWNLOAD_TIMEOUT` 根据文件大小调整
- [ ] `COURT_DOCUMENT_DOWNLOAD_DELAY` 避免触发反爬
- [ ] Playwright 浏览器已安装
- [ ] 数据库迁移已执行
- [ ] 日志目录已创建
- [ ] 环境变量已配置
- [ ] 文件权限已设置
- [ ] 安全配置已启用（生产环境）

## 🔍 配置验证

### 验证脚本

```python
# scripts/verify_court_document_config.py

import os
import sys
from pathlib import Path

# 添加项目路径
sys.path.append(str(Path(__file__).parent.parent))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'apiSystem.settings')

import django
django.setup()

from django.conf import settings

def verify_config():
    """验证配置"""
    print("🔍 验证法院文书下载配置...\n")
    
    # 检查下载目录
    download_dir = settings.COURT_DOCUMENT_DOWNLOAD_DIR
    print(f"📁 下载目录: {download_dir}")
    if os.path.exists(download_dir):
        print("   ✅ 目录存在")
        if os.access(download_dir, os.W_OK):
            print("   ✅ 有写权限")
        else:
            print("   ❌ 无写权限")
    else:
        print("   ❌ 目录不存在")
    
    # 检查超时配置
    print(f"\n⏱️  API 拦截超时: {settings.COURT_DOCUMENT_API_TIMEOUT}ms")
    print(f"⏱️  文件下载超时: {settings.COURT_DOCUMENT_DOWNLOAD_TIMEOUT}ms")
    print(f"⏱️  下载延迟: {settings.COURT_DOCUMENT_DOWNLOAD_DELAY}s")
    
    # 检查数据库
    print(f"\n🗄️  数据库: {settings.DATABASES['default']['ENGINE']}")
    
    # 检查 Playwright
    print(f"\n🎭 Playwright 浏览器: {settings.PLAYWRIGHT_BROWSER_TYPE}")
    print(f"🎭 Headless 模式: {settings.PLAYWRIGHT_HEADLESS}")
    
    print("\n✅ 配置验证完成")

if __name__ == '__main__':
    verify_config()
```

### 运行验证

```bash
cd backend
python scripts/verify_court_document_config.py
```

## 📞 故障排查

### 常见配置问题

#### 1. 目录权限错误

**错误**: `PermissionError: [Errno 13] Permission denied`

**解决**:
```bash
chmod 755 backend/apiSystem/media/court_documents
chown -R $USER backend/apiSystem/media/court_documents
```

#### 2. 环境变量未生效

**错误**: 使用了默认值而不是环境变量

**解决**:
```bash
# 检查环境变量
echo $COURT_DOCUMENT_API_TIMEOUT

# 重新加载环境变量
source .env

# 重启服务
python manage.py runserver
```

#### 3. Playwright 浏览器未安装

**错误**: `playwright._impl._api_types.Error: Executable doesn't exist`

**解决**:
```bash
source backend/venv311/bin/activate
playwright install chromium
```

## 🔗 相关文档

- **使用指南**: `docs/guides/COURT_DOCUMENT_DOWNLOAD_GUIDE.md`
- **设计文档**: `.kiro/specs/court-document-api-optimization/design.md`
- **需求文档**: `.kiro/specs/court-document-api-optimization/requirements.md`

---

**最后更新**: 2024-12
**维护者**: 开发团队
