# 法穿AI案件管理系统V26.8.4

全自动处理/生成法院文书，Less is more

[English Version](README_EN.md)

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

- **后端**: Django 6.0 + Django Ninja (API)
- **数据库**: SQLite
- **缓存**: Django 内置缓存
- **任务队列**: Django-Q2
- **浏览器自动化**: Playwright
- **包管理**: uv

## 🚀 快速开始

### 🍎 macOS 用户 (推荐使用 Make 命令)

macOS 默认支持 Make 命令，使用更简单高效：

```bash
# 1. 克隆项目
git clone https://github.com/Lawyer-ray/FachuanHybridSystem.git
cd FachuanHybridSystem/backend

# 2. 安装 uv (如果还没装)
curl -LsSf https://astral.sh/uv/install.sh | sh
# 或: brew install uv

# 3. 查看所有可用命令（可跳过）
make help

# 4. 创建虚拟环境 (自动下载 Python 3.12，无需手动安装)
make venv
source .venv/bin/activate

# 5. 安装依赖
make install

# 5. 配置环境变量
cp .env.example .env

# 6. 数据库设置
make migrations        # 创建并运行迁移

# 7. 收集静态文件 (重要!)
make collectstatic    # 收集静态文件到正确位置

# 8. 启动服务
make run              # 启动开发服务器 (8002端口)
# 或者
make run-port PORT=8080  # 自定义端口

# 9. 启动任务队列 (要在新终端运行)
make qcluster
```

### 🐧 Linux/Windows 用户

```bash
# 1. 克隆项目
git clone https://github.com/Lawyer-ray/FachuanHybridSystem.git
cd FachuanHybridSystem/backend

# 2. 安装 uv (如果还没装)
curl -LsSf https://astral.sh/uv/install.sh | sh

# 3. 创建虚拟环境并安装依赖
uv sync

# 4. 激活虚拟环境
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 5. 配置环境变量
cp .env.example .env

# 6. 数据库迁移
cd apiSystem
python manage.py migrate

# 7. 创建管理员
python manage.py createsuperuser

# 8. 收集静态文件 (重要!)
python manage.py collectstatic --noinput

# 9. 启动开发服务器
python manage.py runserver 0.0.0.0:8002

# 10. 启动任务队列 (新终端)
python manage.py qcluster
```

## 🔧 开发环境要求

### 必需
- **包管理器**: [uv](https://docs.astral.sh/uv/)（会自动下载管理 Python 3.12，无需手动安装）
- **操作系统**: macOS (推荐) / Linux / Windows

### 推荐 (macOS)
- **Make**: 默认已安装，用于项目管理

### 安装 uv
```bash
# macOS
curl -LsSf https://astral.sh/uv/install.sh | sh

# 或使用 Homebrew
brew install uv

# 验证安装
uv --version
```

## 🤖 遇到问题？让 AI 帮你

本项目所有代码完全开源。遇到任何部署、配置、使用问题，最高效的方式是**直接把项目地址丢给 AI**：

```
https://github.com/Lawyer-ray/FachuanHybridSystem
```

把这个地址和你的问题一起发给 ChatGPT、Claude、Kiro 等任何 AI，它们可以读取完整代码后给出针对性的解答，效果远比搜索引擎好。

> 代码开源意味着你可以自己动手改、自己动手查。遇到问题先读代码、问 AI，培养独立解决问题的能力。

## 📚 相关文档

- [更新日志](CHANGELOG.md) - 版本更新记录
- [Django 官方文档](https://docs.djangoproject.com/)
- [Django Ninja API 文档](https://django-ninja.rest-framework.com/)
- [uv 包管理器文档](https://docs.astral.sh/uv/)
- [Make 命令教程](https://www.gnu.org/software/make/manual/make.html)

## 📄 许可证

本项目采用自定义商业源码许可证：

- ✅ **免费使用**：个人（单人）或 ≤10 人团队，可免费商业使用
- 💰 **付费授权**：超过 10 人使用，按 **200 元/人** 捐赠授权

**授权方式**：通过下方微信赞赏码按人数捐赠（备注"商业授权+人数"），捐赠即视为取得授权。

详见 [LICENSE](LICENSE)

## 🤝 贡献

欢迎提交 Issue 和 Pull Request。

## 💡 开源理念

前人虽未照我，但本项目必定照后人。开源利己利他，愿以此推动中国法律科技行业进步。

## 💝 致谢

本项目主要通过 **[Kiro](https://kiro.dev)** 和 **[Trae](https://trae.ai)** 两款 AI IDE 完成开发，感谢它们极大地提升了开发效率。

## 💖 支持项目

如果这个项目对你有帮助，欢迎支持项目发展：

### 微信赞赏
<img src="backend/apps/core/static/core/images/赞赏码.png" width="200" alt="微信赞赏码">

### 加密货币
- **USDT (TRC20)**: `TGs89x2uz1Qf7vALBboKcSFsZiP3J5T4h2`
- **比特币**: `bc1p39an4kulcgl8ce6lc23zd6yjv3j29uctgkt7szaxlljwjlfsq6eqll7kk8`

## 📞 联系方式

<img src="backend/apps/core/static/core/images/wechat.jpg" width="200" alt="微信二维码">

扫码添加作者微信
