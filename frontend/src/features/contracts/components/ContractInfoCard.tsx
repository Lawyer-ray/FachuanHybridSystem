import { Calendar, Scale, User, Users, Briefcase, FileText, DollarSign, Tag } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Separator } from '@/components/ui/separator'
import type { Contract } from '../types'
import { FEE_MODE_LABELS, type FeeMode } from '../types'

function Info({ icon: Icon, label, children }: { icon: React.ElementType; label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1">
      <div className="text-muted-foreground flex items-center gap-1.5 text-xs"><Icon className="size-3.5" />{label}</div>
      <div className="text-sm">{children}</div>
    </div>
  )
}

export function ContractInfoCard({ contract: c }: { contract: Contract }) {
  const feeLabel = FEE_MODE_LABELS[c.fee_mode as FeeMode] ?? c.fee_mode
  return (
    <div className="grid gap-4 md:grid-cols-2">
      <Card>
        <CardHeader className="pb-3"><CardTitle className="text-base">基本信息</CardTitle></CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-2">
          <Info icon={FileText} label="合同名称">{c.name}</Info>
          <Info icon={Tag} label="类型 / 状态">
            <div className="flex gap-2">
              <Badge variant="outline">{c.case_type_label}</Badge>
              <Badge variant={c.status === 'active' ? 'default' : c.status === 'archived' ? 'secondary' : 'outline'}>{c.status_label}</Badge>
              {c.is_filed && <Badge variant="secondary">已建档</Badge>}
            </div>
          </Info>
          <Info icon={Calendar} label="指定日期">{c.specified_date || '-'}</Info>
          <Info icon={Calendar} label="合同期限">{c.start_date || '-'} ~ {c.end_date || '-'}</Info>
          {c.representation_stages.length > 0 && (
            <div className="sm:col-span-2">
              <Info icon={Scale} label="代理阶段">
                <div className="flex flex-wrap gap-1">
                  {c.representation_stages.map((s) => <Badge key={s} variant="outline" className="text-xs">{s}</Badge>)}
                </div>
              </Info>
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-3"><CardTitle className="text-base">收费信息</CardTitle></CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-2">
          <Info icon={DollarSign} label="收费模式">{feeLabel}</Info>
          {c.fixed_amount != null && <Info icon={DollarSign} label="固定/前期金额">¥{c.fixed_amount.toLocaleString()}</Info>}
          {c.risk_rate != null && <Info icon={DollarSign} label="风险比例">{c.risk_rate}%</Info>}
          {c.custom_terms && <div className="sm:col-span-2"><Info icon={FileText} label="自定义条款">{c.custom_terms}</Info></div>}
          <Separator className="sm:col-span-2" />
          <Info icon={DollarSign} label="已收款">¥{c.total_received.toLocaleString()}</Info>
          <Info icon={DollarSign} label="已开票">¥{c.total_invoiced.toLocaleString()}</Info>
          {c.unpaid_amount != null && <Info icon={DollarSign} label="未收款">¥{c.unpaid_amount.toLocaleString()}</Info>}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-3"><CardTitle className="text-base">律师指派</CardTitle></CardHeader>
        <CardContent>
          {c.assignments.length === 0 ? <p className="text-muted-foreground text-sm">未指派</p> : (
            <div className="space-y-2">
              {c.assignments.map((a) => (
                <div key={a.id} className="flex items-center gap-2">
                  <User className="text-muted-foreground size-4" />
                  <span className="text-sm">{a.lawyer_name}</span>
                  {a.is_primary && <Badge className="text-xs">主办</Badge>}
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-3"><CardTitle className="text-base">当事人</CardTitle></CardHeader>
        <CardContent>
          {c.contract_parties.length === 0 ? <p className="text-muted-foreground text-sm">未添加</p> : (
            <div className="space-y-2">
              {c.contract_parties.map((p) => (
                <div key={p.id} className="flex items-center gap-2">
                  <Users className="text-muted-foreground size-4" />
                  <span className="text-sm">{p.client_detail.name}</span>
                  <Badge variant="outline" className="text-xs">{p.role_label}</Badge>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {c.cases.length > 0 && (
        <Card className="md:col-span-2">
          <CardHeader className="pb-3"><CardTitle className="text-base">关联案件</CardTitle></CardHeader>
          <CardContent>
            <div className="space-y-2">
              {c.cases.map((cs) => (
                <div key={cs.id} className="flex items-center justify-between rounded-md border p-2">
                  <div className="flex items-center gap-2">
                    <Briefcase className="text-muted-foreground size-4" />
                    <span className="text-sm font-medium">{cs.name}</span>
                    {cs.status_label && <Badge variant="outline" className="text-xs">{cs.status_label}</Badge>}
                  </div>
                  {cs.target_amount != null && <span className="text-muted-foreground text-sm">¥{cs.target_amount.toLocaleString()}</span>}
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
