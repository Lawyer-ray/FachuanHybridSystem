import { useState, useCallback } from 'react'
import { FolderDown, FileText, Loader2, Lock, Unlock, Search } from 'lucide-react'
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

function handleDownloadResponse(res: Response, filename: string) {
  const ct = res.headers.get('content-type')
  if (ct && ct.includes('application/json')) {
    return res.json().then((data: { message?: string }) => {
      toast.success(data.message || '已生成并保存')
    })
  }
  return res.blob().then(blob => {
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    a.click()
    URL.revokeObjectURL(url)
    toast.success(`${filename} 生成成功，已开始下载`)
  })
}

export function DocumentsTab({ contract: c }: { contract: Contract }) {
  const [generating, setGenerating] = useState(false)
  const [generatingType, setGeneratingType] = useState<string | null>(null)
  const [folderUnlocked, setFolderUnlocked] = useState(false)
  const [selectedAgreementId, setSelectedAgreementId] = useState<number | null>(null)
  const [showAgreementDialog, setShowAgreementDialog] = useState(false)

  const handleGenerateContract = useCallback(async () => {
    if (generating) return
    setGenerating(true)
    setGeneratingType('contract')
    try {
      const res = await contractApi.generateContract(c.id)
      await handleDownloadResponse(res, `合同_${c.name}.docx`)
    } catch { toast.error('生成合同失败') }
    setGenerating(false)
    setGeneratingType(null)
  }, [generating, c.id, c.name])

  const handleGenerateAgreement = useCallback(async (agreementId: number) => {
    if (generating) return
    setGenerating(true)
    setGeneratingType('agreement')
    setShowAgreementDialog(false)
    try {
      const res = await contractApi.generateSupplementaryAgreement(c.id, agreementId)
      await handleDownloadResponse(res, '补充协议.docx')
    } catch { toast.error('生成补充协议失败') }
    setGenerating(false)
    setGeneratingType(null)
    setSelectedAgreementId(null)
  }, [generating, c.id])

  const handleGenerateFolder = useCallback(async () => {
    if (generating || !folderUnlocked) return
    setGenerating(true)
    setGeneratingType('folder')
    try {
      const blob = await contractApi.generateFolder(c.id)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = '文件夹.zip'
      a.click()
      URL.revokeObjectURL(url)
      toast.success('文件夹生成成功，已开始下载')
    } catch { toast.error('生成文件夹失败') }
    setGenerating(false)
    setGeneratingType(null)
    setFolderUnlocked(false)
  }, [generating, folderUnlocked, c.id])

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
        <SupplementaryAgreementList contractId={c.id} agreements={c.supplementary_agreements} compact />
      </div>

      {/* Important Date Reminders */}
      <DetailCard title="重要日期提醒">
        {c.reminders.length === 0 ? (
          <p className="text-muted-foreground text-[13px]">暂无提醒</p>
        ) : (
          <div className="flex flex-col gap-2">
            {c.reminders.map(r => {
              const today = new Date()
              const dueDate = r.due_at ? new Date(r.due_at) : null
              const isOverdue = dueDate ? dueDate < today : false
              const isSoon = dueDate ? !isOverdue && (dueDate.getTime() - today.getTime()) < 7 * 24 * 60 * 60 * 1000 : false

              return (
                <div
                  key={r.id}
                  className="flex items-center gap-3 rounded-md border border-border/60 bg-muted/30 px-3 py-2.5 text-[13px]"
                >
                  <Badge variant="outline" className="text-[11px] px-2 py-0.5">{r.reminder_type_label || r.content}</Badge>
                  <span className="flex-1 text-muted-foreground text-xs">{r.content}</span>
                  {isOverdue && (
                    <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-medium bg-red-50 text-red-700">已过期</span>
                  )}
                  {isSoon && (
                    <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-medium bg-amber-50 text-amber-700">即将到期</span>
                  )}
                  <span className="text-muted-foreground text-xs font-mono">{r.due_at?.slice(0, 10) || ''}</span>
                </div>
              )
            })}
          </div>
        )}
      </DetailCard>

      {/* Document Generation */}
      <DetailCard title="文档生成">
        <div className="flex flex-col gap-3">
          {/* Generate Contract */}
          <div className="flex items-center gap-2">
            <Button
              variant="outline" size="sm" className="h-8"
              onClick={handleGenerateContract}
              disabled={!c.matched_document_template || generating}
              title={!c.matched_document_template ? '无匹配的合同模板' : undefined}
            >
              {generatingType === 'contract' ? (
                <Loader2 className="mr-1.5 size-3.5 animate-spin" />
              ) : (
                <FileText className="mr-1.5 size-3.5" />
              )}
              生成合同
            </Button>
            <Button
              variant="ghost" size="sm" className="h-8 px-2"
              onClick={handleGenerateContract}
              disabled={!c.matched_document_template || generating}
              title="预览替换词"
            >
              <Search className="size-3.5" />
            </Button>
          </div>

          {/* Generate Supplementary Agreement */}
          {c.supplementary_agreements.length > 0 ? (
            <div className="flex items-center gap-2">
              {c.supplementary_agreements.length === 1 ? (
                <Button
                  variant="outline" size="sm" className="h-8"
                  onClick={() => handleGenerateAgreement(c.supplementary_agreements[0].id)}
                  disabled={generating}
                >
                  {generatingType === 'agreement' ? (
                    <Loader2 className="mr-1.5 size-3.5 animate-spin" />
                  ) : (
                    <FileText className="mr-1.5 size-3.5" />
                  )}
                  生成补充协议
                </Button>
              ) : (
                <>
                  <Button
                    variant="outline" size="sm" className="h-8"
                    onClick={() => setShowAgreementDialog(true)}
                    disabled={generating}
                  >
                    {generatingType === 'agreement' ? (
                      <Loader2 className="mr-1.5 size-3.5 animate-spin" />
                    ) : (
                      <FileText className="mr-1.5 size-3.5" />
                    )}
                    生成补充协议
                  </Button>
                </>
              )}
            </div>
          ) : (
            <Button variant="outline" size="sm" className="h-8" disabled title="暂无补充协议">
              <FileText className="mr-1.5 size-3.5" />
              生成补充协议
            </Button>
          )}

          {/* Generate Folder */}
          <div className="flex items-center gap-0">
            <Button
              variant="outline" size="sm" className="h-8 rounded-r-none"
              onClick={handleGenerateFolder}
              disabled={!c.matched_folder_templates || !folderUnlocked || generating}
              title={!c.matched_folder_templates ? '无匹配的文件夹模板' : !folderUnlocked ? '点击解锁后才能生成' : undefined}
            >
              {generatingType === 'folder' ? (
                <Loader2 className="mr-1.5 size-3.5 animate-spin" />
              ) : (
                <FolderDown className="mr-1.5 size-3.5" />
              )}
              生成文件夹
            </Button>
            <Button
              variant={folderUnlocked ? 'default' : 'secondary'}
              size="sm"
              className="h-8 rounded-l-none px-2"
              onClick={() => setFolderUnlocked(prev => !prev)}
              title={folderUnlocked ? '点击锁定' : '点击解锁后才能生成'}
            >
              {folderUnlocked ? <Unlock className="size-3.5" /> : <Lock className="size-3.5" />}
            </Button>
          </div>
        </div>
      </DetailCard>

      {/* Supplementary Agreement Selection Dialog */}
      {showAgreementDialog && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={() => setShowAgreementDialog(false)}>
          <div className="bg-background rounded-lg shadow-lg p-6 w-[400px] max-h-[70vh] overflow-y-auto" onClick={e => e.stopPropagation()}>
            <h3 className="text-sm font-semibold mb-4">选择补充协议</h3>
            <div className="flex flex-col gap-2 mb-4">
              {c.supplementary_agreements.map(sa => (
                <button
                  key={sa.id}
                  className={`text-left px-3 py-2 rounded-md border text-sm transition-colors ${selectedAgreementId === sa.id ? 'border-primary bg-primary/5' : 'border-border hover:bg-muted'}`}
                  onClick={() => setSelectedAgreementId(sa.id)}
                >
                  {sa.name || `未命名补充协议 #${sa.id}`}
                </button>
              ))}
            </div>
            <div className="flex justify-end gap-2">
              <Button variant="outline" size="sm" onClick={() => setShowAgreementDialog(false)}>取消</Button>
              <Button size="sm" disabled={!selectedAgreementId || generating} onClick={() => selectedAgreementId && handleGenerateAgreement(selectedAgreementId)}>
                确定生成
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Folder Binding */}
      <div className="rounded-lg border border-border/60 p-[18px] mb-4 bg-card">
        <FolderBindingManager contractId={c.id} />
      </div>
    </div>
  )
}
