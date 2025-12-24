# 案件群聊功能配置指南

## 问题诊断

如果案件不能手动创建群聊，通常是因为群聊平台配置缺失导致的。

## 配置步骤

### 1. 检查环境变量配置

确保在 `backend/.env` 文件中配置了飞书相关的环境变量：

```bash
# 飞书配置
FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/your-webhook-token
FEISHU_APP_ID=cli_your_app_id_here
FEISHU_APP_SECRET=your_app_secret_here
FEISHU_TIMEOUT=30
```

### 2. 获取飞书配置信息

#### 2.1 创建飞书应用

1. 访问 [飞书开放平台](https://open.feishu.cn/)
2. 登录并创建企业自建应用
3. 获取应用的 `App ID` 和 `App Secret`

#### 2.2 配置应用权限

在飞书应用管理后台，需要开通以下权限：
- `im:chat` - 获取与发送单聊、群聊消息
- `im:chat:readonly` - 获取群信息
- `im:message` - 获取与发送单聊、群聊消息
- `im:message:send_as_bot` - 以应用的身份发送消息

#### 2.3 获取 Webhook URL（可选 - 用于传统通知）

如果需要使用传统的飞书 Webhook 通知（向固定群聊发送所有通知），可以配置 Webhook URL：

1. 在飞书中创建一个群聊
2. 在群聊中添加自定义机器人：
   - 点击群聊右上角的设置按钮
   - 选择"机器人" → "添加机器人" → "自定义机器人"
   - 设置机器人名称和描述
   - 复制生成的 Webhook URL
3. 将 Webhook URL 配置到 `FEISHU_WEBHOOK_URL`

**注意**：这是可选配置，新的案件群聊功能不需要此配置。

### 3. 验证配置

运行以下命令验证配置是否正确：

```bash
cd backend
source venv311/bin/activate
cd apiSystem
python manage.py shell -c "
from apps.automation.services.chat.factory import ChatProviderFactory
from apps.core.enums import ChatPlatform

provider = ChatProviderFactory.get_provider(ChatPlatform.FEISHU)
print(f'飞书提供者可用性: {provider.is_available()}')

available_platforms = ChatProviderFactory.get_available_platforms()
print(f'可用平台: {available_platforms}')
"
```

如果输出显示：
- `飞书提供者可用性: True`
- `可用平台: [ChatPlatform.FEISHU]`

则说明配置成功。

### 4. 使用群聊功能

配置完成后，可以通过以下方式创建群聊：

#### 4.1 在Django Admin中批量创建（推荐）

1. **进入Django后台**
   - 访问 `http://localhost:8000/admin/`
   - 使用账号：`黄崧`，密码：`532121wsx`

2. **进入案件管理**
   - 点击 "Cases" → "Cases"

3. **批量创建群聊**
   - 勾选你想要创建群聊的案件（可以多选）
   - 在页面下方的"操作"下拉菜单中选择 **"为选中案件创建飞书群聊"**
   - 点击"执行"按钮

#### 4.2 查看案件群聊

1. **进入具体案件**
   - 点击任意案件进入详情页

2. **查看群聊状态**
   - 在案件详情页面底部，你会看到 **"案件群聊"** 内联区域
   - 这里会显示该案件的所有群聊记录，包括：
     - 🚀 平台类型（飞书）
     - 群聊名称
     - 群聊ID
     - 状态（有效/已解绑）
     - 创建时间

#### 4.3 通过代码创建

```python
from apps.cases.services.case_chat_service import CaseChatService
from apps.core.enums import ChatPlatform

service = CaseChatService()
chat = service.create_chat_for_case(
    case_id=123,
    platform=ChatPlatform.FEISHU
)
```

## 常见问题

### Q: 提示"飞书提供者不可用"
A: 检查 `.env` 文件中的 `FEISHU_APP_ID` 和 `FEISHU_APP_SECRET` 是否正确配置。

### Q: 创建群聊时提示"配置不完整"
A: 确保飞书应用已经开通了必要的权限，特别是群聊相关权限。

### Q: API调用失败
A: 检查网络连接，确保可以访问飞书开放平台API。

### Q: 群聊创建成功但无法发送消息
A: 检查飞书应用是否有消息发送权限，以及机器人是否已加入群聊。

## 支持的平台

当前系统支持以下群聊平台：
- ✅ 飞书 (Feishu) - 已实现
- 🚧 钉钉 (DingTalk) - 预留接口
- 🚧 企业微信 (WeChat Work) - 预留接口  
- 🚧 Telegram - 预留接口
- 🚧 Slack - 预留接口

## 架构说明

系统采用策略模式和工厂模式设计，支持多平台扩展：

```
CaseChatService -> ChatProviderFactory -> FeishuChatProvider
                                      -> DingTalkProvider (预留)
                                      -> WeChatWorkProvider (预留)
```

每个平台提供者实现统一的 `ChatProvider` 接口，确保业务逻辑与具体平台解耦。