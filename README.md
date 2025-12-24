# 法穿案件管理系统

一个专为律师事务所设计的案件管理系统，提供案件全生命周期管理、合同管理、客户管理等功能，并集成了法院文书自动化处理能力。

## ✨ 主要功能

- **案件管理** - 案件创建、分配、进度跟踪、案号管理
- **客户管理** - 客户信息、身份证件、财产线索管理
- **合同管理** - 合同创建、补充协议、付款跟踪、律师分配
- **组织管理** - 团队、律师、账号凭证管理
- **自动化功能**
  - 法院短信解析与文书下载
  - 法院文书自动抓取
  - 财产保全保险询价
  - 飞书群消息通知

## 🛠 技术栈

- **后端**: Django 5.x + Django Ninja (API)
- **数据库**: SQLite (默认) / PostgreSQL
- **缓存**: Redis
- **任务队列**: Django-Q2
- **浏览器自动化**: Playwright
- **部署**: Docker + Gunicorn

## 🚀 快速开始

### Docker 部署 (推荐)

详细部署说明请参考 [Docker 快速部署指南](DOCKER_QUICKSTART.md)

### 本地开发

```bash
# 1. 进入后端目录
cd backend

# 2. 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 3. 安装依赖
pip install -r requirements.txt

# 4. 配置环境变量
cp .env.example .env

# 5. 数据库迁移
cd apiSystem
python manage.py migrate

# 6. 创建管理员
python manage.py createsuperuser

# 7. 启动开发服务器
python manage.py runserver 0.0.0.0:8002
```

## 📁 项目结构

```
.
├── backend/                 # Django 后端
│   ├── apiSystem/          # Django 项目配置
│   ├── apps/               # 应用模块
│   │   ├── cases/          # 案件管理
│   │   ├── client/         # 客户管理
│   │   ├── contracts/      # 合同管理
│   │   ├── organization/   # 组织管理
│   │   ├── automation/     # 自动化功能
│   │   └── core/           # 核心模块
│   └── docs/               # 开发文档
├── docker/                  # Docker 配置
├── docker-compose.yml       # 生产环境编排
└── docker-compose.dev.yml   # 开发环境编排
```

## 📖 文档

- [Docker 快速部署](DOCKER_QUICKSTART.md)
- [Docker Quick Start (English)](DOCKER_QUICKSTART_EN.md)

## 📄 许可证

本项目采用自定义商业源码许可证：

- ✅ **免费使用**: 个人学习、研究、≤10人小团队非商业使用
- 💰 **商业授权**: 超过10人使用、律所部署、商业用途需付费授权

详见 [LICENSE](LICENSE)

## 🤝 贡献

欢迎提交 Issue 和 Pull Request。

## 📞 联系方式

商业授权咨询请联系：SongAIGC
