/**
 * AuthoritySection - 主管机关列表区块
 *
 * Requirements: 3.10, 5.9
 */

import { Landmark, Clock, Info } from 'lucide-react'
import { format } from 'date-fns'

import { Card, CardHeader } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import type { SupervisingAuthority } from '../types'

export interface AuthoritySectionProps {
  authorities: SupervisingAuthority[]
  editable?: boolean
  caseId?: number
}

function formatDate(dateStr: string | null | undefined): string {
  if (!dateStr) return '-'
  try {
    return format(new Date(dateStr), 'yyyy-MM-dd')
  } catch {
    return dateStr
  }
}

function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center py-8">
      <div className="bg-muted flex size-10 items-center justify-center rounded-full">
        <Landmark className="text-muted-foreground size-5" />
      </div>
      <p className="text-muted-foreground mt-3 text-sm">暂无主管机关</p>
    </div>
  )
}

export function AuthoritySection({ authorities, editable }: AuthoritySectionProps) {
  return (
    <div className="space-y-3">
      {editable && (
        <div className="bg-muted/50 flex items-center gap-2 rounded-md border px-3 py-2">
          <Info className="text-muted-foreground size-4 shrink-0" />
          <p className="text-muted-foreground text-xs">主管机关通过新建案件时添加</p>
        </div>
      )}

      {authorities.length === 0 ? (
        <EmptyState />
      ) : (
        authorities.map((auth) => (
          <Card key={auth.id} className="gap-0 py-0">
            <CardHeader className="py-4">
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2 min-w-0">
                  <Landmark className="text-muted-foreground size-4 shrink-0" />
                  <span className="text-sm font-medium truncate">
                    {auth.name || '未命名机关'}
                  </span>
                  {auth.authority_type_display && (
                    <Badge variant="outline" className="shrink-0 text-xs">
                      {auth.authority_type_display}
                    </Badge>
                  )}
                </div>
                <div className="flex items-center gap-1 text-muted-foreground shrink-0">
                  <Clock className="size-3" />
                  <span className="text-xs">{formatDate(auth.created_at)}</span>
                </div>
              </div>
            </CardHeader>
          </Card>
        ))
      )}
    </div>
  )
}

export default AuthoritySection
