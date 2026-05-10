import { useState } from 'react'
import { Download, Loader2, FileText, Scale, Shield } from 'lucide-react'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { caseApi } from '../api'
import type { CaseParty } from '../types'

interface Props {
  caseId: number
  caseName: string
  parties: CaseParty[]
}

export function AuthorizationMaterialsSection({ caseId, caseName, parties }: Props) {
  const [loading, setLoading] = useState<string | null>(null)
  const [selectedClient, setSelectedClient] = useState<string>('')

  const ourParties = parties.filter(p => p.client_detail?.is_our_client)

  const run = async (key: string, fn: () => Promise<void>) => {
    setLoading(key)
    try {
      await fn()
      toast.success('下载成功')
    } catch {
      toast.error('下载失败')
    } finally {
      setLoading(null)
    }
  }

  return (
    <div className="space-y-4">
      {/* 全套 + 单项 */}
      <div>
        <div className="flex items-center gap-1.5 mb-2">
          <Shield className="text-muted-foreground size-3.5" />
          <span className="text-xs font-medium text-muted-foreground">授权委托材料</span>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button
            size="sm"
            variant="outline"
            className="h-7 text-xs"
            disabled={loading !== null || ourParties.length === 0}
            onClick={() => run('package', () => caseApi.downloadAuthorizationPackage(caseId, caseName))}
          >
            {loading === 'package' ? <Loader2 className="size-3 mr-1 animate-spin" /> : <Download className="size-3 mr-1" />}
            全套委托材料
          </Button>
          <Button
            size="sm"
            variant="outline"
            className="h-7 text-xs"
            disabled={loading !== null}
            onClick={() => run('letter', () => caseApi.downloadAuthorizationLetter(caseId, caseName))}
          >
            {loading === 'letter' ? <Loader2 className="size-3 mr-1 animate-spin" /> : <FileText className="size-3 mr-1" />}
            所函
          </Button>
          <Button
            size="sm"
            variant="outline"
            className="h-7 text-xs"
            disabled={loading !== null}
            onClick={() => run('combined-poa', () => caseApi.downloadCombinedPOA(caseId, caseName))}
          >
            {loading === 'combined-poa' ? <Loader2 className="size-3 mr-1 animate-spin" /> : <Scale className="size-3 mr-1" />}
            合并授权委托书
          </Button>
        </div>
      </div>

      {/* 按当事人 */}
      {ourParties.length > 0 && (
        <div>
          <div className="flex items-center gap-2 mb-2">
            <span className="text-xs font-medium text-muted-foreground">按当事人生成</span>
            <Select value={selectedClient} onValueChange={setSelectedClient}>
              <SelectTrigger className="w-[180px] h-6 text-xs">
                <SelectValue placeholder="选择当事人" />
              </SelectTrigger>
              <SelectContent>
                {ourParties.map(p => (
                  <SelectItem key={p.client} value={String(p.client)}>
                    {p.client_detail?.name ?? `#${p.client}`}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          {selectedClient && (
            <div className="flex flex-wrap gap-2">
              <Button
                size="sm"
                variant="outline"
                className="h-7 text-xs"
                disabled={loading !== null}
                onClick={() => run('legal-rep', () => caseApi.downloadLegalRepCertificate(caseId, Number(selectedClient)))}
              >
                {loading === 'legal-rep' ? <Loader2 className="size-3 mr-1 animate-spin" /> : <Download className="size-3 mr-1" />}
                法定代表人证明
              </Button>
              <Button
                size="sm"
                variant="outline"
                className="h-7 text-xs"
                disabled={loading !== null}
                onClick={() => run('poa', () => caseApi.downloadPowerOfAttorney(caseId, Number(selectedClient)))}
              >
                {loading === 'poa' ? <Loader2 className="size-3 mr-1 animate-spin" /> : <Download className="size-3 mr-1" />}
                授权委托书
              </Button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
