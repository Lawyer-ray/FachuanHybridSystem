/**
 * CaseAssignmentSection - 指派律师列表区块
 *
 * Requirements: 3.7
 */

import { UserCheck, Phone } from 'lucide-react'

import { Card, CardHeader } from '@/components/ui/card'
import type { CaseAssignment } from '../types'

export interface CaseAssignmentSectionProps {
  assignments: CaseAssignment[]
  editable?: boolean
}

function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center py-8">
      <div className="bg-muted flex size-10 items-center justify-center rounded-full">
        <UserCheck className="text-muted-foreground size-5" />
      </div>
      <p className="text-muted-foreground mt-3 text-sm">暂无指派律师</p>
    </div>
  )
}

export function CaseAssignmentSection({ assignments }: CaseAssignmentSectionProps) {
  return (
    <div className="space-y-3">
      {assignments.length === 0 ? (
        <EmptyState />
      ) : (
        assignments.map((a) => {
          const name = a.lawyer_detail?.real_name || a.lawyer_detail?.username || '未知律师'
          const phone = a.lawyer_detail?.phone

          return (
            <Card key={a.id} className="gap-0 py-0">
              <CardHeader className="py-4">
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2 min-w-0">
                    <UserCheck className="text-muted-foreground size-4 shrink-0" />
                    <span className="text-sm font-medium truncate">{name}</span>
                  </div>
                  {phone && (
                    <div className="flex items-center gap-1 text-muted-foreground shrink-0">
                      <Phone className="size-3" />
                      <span className="text-xs">{phone}</span>
                    </div>
                  )}
                </div>
              </CardHeader>
            </Card>
          )
        })
      )}
    </div>
  )
}

export default CaseAssignmentSection
