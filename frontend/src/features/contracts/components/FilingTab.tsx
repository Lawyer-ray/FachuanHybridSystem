import { ExternalLink, Briefcase } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import type { Contract } from '../types'
import { useNavigate } from 'react-router'

function DetailField({ label, value, mono }: { label: string; value: React.ReactNode; mono?: boolean }) {
  return (
    <div>
      <div className="text-muted-foreground mb-0.5 text-xs">{label}</div>
      <div className={`text-[13px] ${mono ? 'font-mono' : ''}`}>{value || '—'}</div>
    </div>
  )
}

function DetailCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-border/60 p-[18px] mb-4 bg-card">
      <h3 className="text-sm font-semibold text-foreground mb-3.5">{title}</h3>
      {children}
    </div>
  )
}

export function FilingTab({ contract: c }: { contract: Contract }) {
  const navigate = useNavigate()

  return (
    <div>
      {/* Law Firm OA */}
      {(c.law_firm_oa_url || c.law_firm_oa_case_number) && (
        <DetailCard title="律所 OA">
          <div className="grid gap-[14px] sm:grid-cols-2">
            <DetailField label="OA 链接" value={
              c.law_firm_oa_url ? (
                <a
                  href={c.law_firm_oa_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-primary inline-flex items-center gap-1 hover:underline text-[13px]"
                >
                  打开 OA <ExternalLink className="size-3" />
                </a>
              ) : '—'
            } />
            <DetailField label="OA 案件编号" value={c.law_firm_oa_case_number} mono />
          </div>
        </DetailCard>
      )}

      {/* Related Cases for Filing */}
      <DetailCard title="关联案件">
        {c.cases.length > 0 ? (
          <div className="flex flex-col gap-2">
            {c.cases.map(cs => (
              <div
                key={cs.id}
                className="flex items-center gap-3 rounded-md border border-border/60 bg-muted/30 px-3 py-2.5 text-[13px] cursor-pointer hover:bg-muted/60 transition-colors"
                onClick={() => navigate(`/admin/cases/${cs.id}`)}
              >
                <Briefcase className="size-3.5 text-muted-foreground shrink-0" />
                <span className="font-medium flex-1 truncate">{cs.name}</span>
                {cs.status_label && <Badge variant="outline" className="text-[10px] px-1.5 py-0 shrink-0">{cs.status_label}</Badge>}
                {cs.current_stage_label && <span className="text-muted-foreground text-xs">{cs.current_stage_label}</span>}
              </div>
            ))}
          </div>
        ) : (
          <p className="text-muted-foreground text-[13px]">暂无关联案件</p>
        )}
      </DetailCard>

      {/* OA System Filing */}
      <DetailCard title="OA 系统立案">
        <p className="text-muted-foreground text-[13px] mb-3">
          通过律所 OA 系统自动立案，系统将自动填写表单并同步至法院立案系统。
        </p>
        <Button variant="outline" size="sm" className="h-8 text-xs" disabled>
          开始立案
        </Button>
      </DetailCard>
    </div>
  )
}
