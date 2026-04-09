import { useNavigate } from 'react-router'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { FileSearch, Calculator, ArrowRight } from 'lucide-react'
import { PATHS } from '@/routes/paths'

/**
 * 自动化工具首页
 * 展示自动化工具模块的入口卡片
 * @validates Requirements 1.1, 1.2 - 自动化工具导航
 */
export default function AutomationIndexPage() {
  const navigate = useNavigate()

  const tools = [
    {
      title: '财产保全询价',
      description: '向多家保险公司询价，获取财产保全保费报价',
      icon: Calculator,
      path: PATHS.ADMIN_AUTOMATION_QUOTES,
    },
    {
      title: '文书智能识别',
      description: '上传法律文书，自动识别文书类型并绑定案件',
      icon: FileSearch,
      path: PATHS.ADMIN_AUTOMATION_RECOGNITION,
    },
  ]

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">自动化工具</h1>
        <p className="text-muted-foreground">
          使用自动化工具提高工作效率
        </p>
      </div>

      <div className="grid gap-6 md:grid-cols-2">
        {tools.map((tool) => (
          <Card
            key={tool.path}
            className="cursor-pointer transition-colors hover:bg-muted/50"
            onClick={() => navigate(tool.path)}
          >
            <CardHeader>
              <div className="flex items-center gap-4">
                <div className="rounded-lg bg-primary/10 p-3">
                  <tool.icon className="h-6 w-6 text-primary" />
                </div>
                <div className="flex-1">
                  <CardTitle className="text-lg">{tool.title}</CardTitle>
                  <CardDescription>{tool.description}</CardDescription>
                </div>
              </div>
            </CardHeader>
            <CardContent>
              <Button variant="ghost" className="w-full justify-between">
                进入
                <ArrowRight className="h-4 w-4" />
              </Button>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  )
}
