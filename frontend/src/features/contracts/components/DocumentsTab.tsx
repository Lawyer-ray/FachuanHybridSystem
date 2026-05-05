import { useState, useCallback } from 'react'
import { Download, Loader2 } from 'lucide-react'
import { toast } from 'sonner'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { contractApi } from '../api'
import type { Contract } from '../types'
import { SupplementaryAgreementList } from './SupplementaryAgreementList'
import { FolderBindingManager } from './FolderBindingManager'

function DetailField({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div>
      <div className="text-muted-foreground mb-0.5 text-xs">{label}</div>
      <div className="text-[13px]">{value || '—'}</div>
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

export function DocumentsTab({ contract: c }: { contract: Contract }) {
  const [generatingId, setGeneratingId] = useState<number | null>(null)

  const handleGenerateAgreement = useCallback(async (agreementId: number) => {
    setGeneratingId(agreementId)
    try {
      await contractApi.generateSupplementaryAgreement(c.id, agreementId)
      toast.success('补充协议文档已生成')
    } catch { toast.error('生成失败') }
    setGeneratingId(null)
  }, [c.id])

  return (
    <div>
      {/* Matched Templates */}
      <DetailCard title="匹配的模板">
        <div className="grid gap-[14px] sm:grid-cols-2">
          <DetailField label="文件模板" value={
            c.matched_document_template
              ? <span>{c.matched_document_template}</span>
              : <span className="text-muted-foreground">合同自动生成时自动匹配</span>
          } />
          <DetailField label="文件夹模板" value={
            c.matched_folder_templates
              ? <span>{c.matched_folder_templates}</span>
              : <span className="text-muted-foreground">归档时自动匹配</span>
          } />
        </div>
        {c.has_matched_templates && (
          <div className="mt-3">
            <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium bg-green-50 text-green-700">已匹配模板</span>
          </div>
        )}
      </DetailCard>

      {/* Supplementary Agreements */}
      <div className="rounded-lg border border-border/60 p-[18px] mb-4 bg-card">
        <SupplementaryAgreementList contractId={c.id} agreements={c.supplementary_agreements} />
        {c.supplementary_agreements.length > 0 && (
          <div className="mt-3 pt-3 border-t border-border/40">
            <p className="text-xs text-muted-foreground mb-2">生成补充协议文档：</p>
            <div className="flex flex-wrap gap-2">
              {c.supplementary_agreements.map(sa => (
                <Button
                  key={sa.id}
                  variant="outline" size="sm" className="h-7 text-xs"
                  onClick={() => handleGenerateAgreement(sa.id)}
                  disabled={generatingId !== null}
                >
                  {generatingId === sa.id ? (
                    <Loader2 className="mr-1 size-3 animate-spin" />
                  ) : (
                    <Download className="mr-1 size-3" />
                  )}
                  {sa.name || `补充协议 #${sa.id}`}
                </Button>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Important Date Reminders */}
      <DetailCard title="重要日期提醒">
        {c.reminders.length === 0 ? (
          <p className="text-muted-foreground text-[13px]">暂无提醒</p>
        ) : (
          <div className="flex flex-col gap-2">
            {c.reminders.map(r => (
              <div
                key={r.id}
                className="flex items-center gap-3 rounded-md border border-border/60 bg-muted/30 px-3 py-2.5 text-[13px]"
              >
                <Badge variant="outline" className="text-[11px] px-2 py-0.5">{r.title}</Badge>
                <span className="flex-1" />
                <span className="text-muted-foreground text-xs font-mono">{r.due_date || ''}</span>
              </div>
            ))}
          </div>
        )}
      </DetailCard>

      {/* Folder Binding */}
      <div className="rounded-lg border border-border/60 p-[18px] mb-4 bg-card">
        <FolderBindingManager contractId={c.id} />
      </div>
    </div>
  )
}
