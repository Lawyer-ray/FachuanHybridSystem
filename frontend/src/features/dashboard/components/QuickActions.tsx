import { useNavigate } from 'react-router'
import { Briefcase, FileText, Users, Bot } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { PATHS } from '@/routes/paths'

const ACTIONS = [
  { label: '新建案件', icon: Briefcase, path: PATHS.ADMIN_CASES },
  { label: '新建合同', icon: FileText, path: PATHS.ADMIN_CONTRACTS },
  { label: '新建当事人', icon: Users, path: PATHS.ADMIN_CLIENTS },
  { label: 'AI 工作台', icon: Bot, path: PATHS.ADMIN_WORKBENCH },
]

export function QuickActions() {
  const navigate = useNavigate()

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-sm font-medium">快捷操作</CardTitle>
      </CardHeader>
      <CardContent className="pt-0 grid grid-cols-2 gap-2">
        {ACTIONS.map((action) => (
          <button
            key={action.label}
            type="button"
            onClick={() => navigate(action.path)}
            className="flex items-center gap-2.5 rounded-lg border border-border/60 px-3 py-2.5 text-xs font-medium hover:bg-muted/50 hover:border-border transition-colors text-left"
          >
            <action.icon className="size-4 text-muted-foreground" />
            <span>{action.label}</span>
          </button>
        ))}
      </CardContent>
    </Card>
  )
}
