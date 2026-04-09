/**
 * Dashboard 首页
 * 后台管理系统的默认首页
 */

import { Link } from 'react-router'
import { Users, FileText, Briefcase, FolderOpen } from 'lucide-react'

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { PATHS } from '@/routes/paths'

/**
 * 快捷入口卡片数据
 */
const quickLinks = [
  {
    title: '当事人管理',
    description: '管理案件当事人信息',
    icon: Users,
    href: PATHS.ADMIN_CLIENTS,
    color: 'text-blue-500',
  },
  {
    title: '案件管理',
    description: '查看和管理案件',
    icon: Briefcase,
    href: PATHS.ADMIN_CASES,
    color: 'text-green-500',
  },
  {
    title: '合同管理',
    description: '管理委托合同',
    icon: FileText,
    href: PATHS.ADMIN_CONTRACTS,
    color: 'text-orange-500',
  },
  {
    title: '文档管理',
    description: '管理法律文书',
    icon: FolderOpen,
    href: PATHS.ADMIN_DOCUMENTS,
    color: 'text-purple-500',
  },
]

export default function DashboardPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">工作台</h1>
        <p className="text-muted-foreground">欢迎使用法穿 AI 律师助手</p>
      </div>

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        {quickLinks.map((link) => (
          <Link key={link.href} to={link.href}>
            <Card className="hover:bg-accent/50 transition-colors cursor-pointer h-full">
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">{link.title}</CardTitle>
                <link.icon className={`h-4 w-4 ${link.color}`} />
              </CardHeader>
              <CardContent>
                <CardDescription>{link.description}</CardDescription>
              </CardContent>
            </Card>
          </Link>
        ))}
      </div>
    </div>
  )
}
