import { useNavigate } from 'react-router'
import {
  Building2, Users, User, MessageSquare, Globe, Mail, Monitor,
  Brain, ScanLine, Database, Settings, ChevronRight, Plug,
} from 'lucide-react'
import { PATHS } from '@/routes/paths'

interface SettingItem {
  id: string
  icon: React.ElementType
  label: string
  desc: string
  path: string
}

interface SettingSection {
  title: string
  items: SettingItem[]
}

const sections: SettingSection[] = [
  {
    title: '机构管理',
    items: [
      { id: 'law-firm', icon: Building2, label: '律所设置', desc: '管理律所名称、地址、统一信用代码、联系方式等基本信息', path: PATHS.ADMIN_SETTINGS_LAW_FIRM },
      { id: 'team', icon: Users, label: '团队设置', desc: '创建和管理业务团队，配置团队负责人及成员', path: PATHS.ADMIN_SETTINGS_TEAM },
      { id: 'lawyer', icon: User, label: '律师设置', desc: '编辑个人资料、头像、执业证号、身份证号及专业领域', path: PATHS.ADMIN_SETTINGS_LAWYER },
    ],
  },
  {
    title: '消息平台',
    items: [
      { id: 'feishu', icon: MessageSquare, label: '飞书配置', desc: 'App ID、App Secret、默认负责人等飞书集成参数', path: `${PATHS.ADMIN_SETTINGS}/config/feishu` },
      { id: 'dingtalk', icon: MessageSquare, label: '钉钉配置', desc: 'App Key、App Secret、Agent ID 等钉钉集成参数', path: `${PATHS.ADMIN_SETTINGS}/config/dingtalk` },
      { id: 'wechat-work', icon: MessageSquare, label: '企业微信配置', desc: 'Corp ID、Agent ID、Secret 等企业微信集成参数', path: `${PATHS.ADMIN_SETTINGS}/config/wechat_work` },
      { id: 'telegram', icon: MessageSquare, label: 'Telegram 配置', desc: 'Bot Token、超级群组 ID 等 Telegram 集成参数', path: `${PATHS.ADMIN_SETTINGS}/config/telegram` },
      { id: 'email', icon: Mail, label: '邮件配置', desc: 'SMTP 服务器、端口、账号密码、发件人名称等', path: `${PATHS.ADMIN_SETTINGS}/config/email` },
      { id: 'court-sms', icon: Monitor, label: '法院短信配置', desc: '法院短信平台的接口参数配置', path: `${PATHS.ADMIN_SETTINGS}/config/court_sms` },
    ],
  },
  {
    title: 'AI 与数据服务',
    items: [
      { id: 'ai', icon: Brain, label: 'AI 服务配置', desc: 'SiliconFlow API Key、默认模型、Ollama 等 AI 接口参数', path: `${PATHS.ADMIN_SETTINGS}/config/ai` },
      { id: 'ocr', icon: ScanLine, label: 'OCR 服务配置', desc: 'PaddleOCR 的 API 地址、模型类型、Token 等参数', path: `${PATHS.ADMIN_SETTINGS}/config/ocr` },
      { id: 'enterprise', icon: Database, label: '企业数据配置', desc: '天眼查等企业信息查询接口的 API Key', path: `${PATHS.ADMIN_SETTINGS}/config/enterprise_data` },
      { id: 'scraper', icon: Globe, label: '爬虫配置', desc: '加密密钥、无头模式等网页爬取相关参数', path: `${PATHS.ADMIN_SETTINGS}/config/scraper` },
    ],
  },
  {
    title: '系统',
    items: [
      { id: 'system', icon: Plug, label: '系统连接', desc: '后端服务地址配置，修改后需刷新页面生效', path: `${PATHS.ADMIN_SETTINGS}/config/system` },
    ],
  },
]

export function SettingsOverview() {
  const navigate = useNavigate()

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold">系统设置</h1>
        <p className="text-muted-foreground text-sm mt-1">管理平台全局配置与个人资料</p>
      </div>

      {/* Search bar placeholder */}
      <div className="flex items-center gap-3 rounded-lg border bg-muted/50 px-4 py-3 text-muted-foreground text-sm cursor-pointer hover:bg-muted transition-colors">
        <Settings className="size-4" />
        <span>搜索设置项...</span>
      </div>

      {/* Settings sections */}
      {sections.map((section) => (
        <div key={section.title}>
          <h2 className="text-xs font-medium uppercase tracking-wider text-muted-foreground mb-3">{section.title}</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2">
            {section.items.map((item) => {
              const Icon = item.icon
              return (
                <div
                  key={item.id}
                  onClick={() => navigate(item.path)}
                  className="flex items-center gap-4 rounded-lg border p-4 cursor-pointer hover:bg-muted/50 transition-colors group"
                >
                  <div className="flex size-10 items-center justify-center rounded-md bg-muted">
                    <Icon className="size-5 text-muted-foreground" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-medium">{item.label}</div>
                    <div className="text-xs text-muted-foreground mt-0.5">{item.desc}</div>
                  </div>
                  <ChevronRight className="size-4 text-muted-foreground group-hover:text-foreground transition-colors" />
                </div>
              )
            })}
          </div>
        </div>
      ))}
    </div>
  )
}

export default SettingsOverview
