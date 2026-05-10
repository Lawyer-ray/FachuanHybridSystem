import { useState } from 'react'
import { Download, Loader2, FileText, Shield, Scale } from 'lucide-react'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { DetailCard } from '@/components/shared'
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
    <DetailCard title="授权材料快捷生成" extra={<Shield className="text-muted-foreground size-4" />}>
      <div className="space-y-4">
        {/* Full package */}
        <div className="rounded-md border border-border/60 bg-muted/30 px-4 py-3">
          <div className="flex items-center justify-between gap-3">
            <div>
              <p className="text-sm font-medium">全部授权材料包</p>
              <p className="text-xs text-muted-foreground mt-0.5">包含所函、法定代表人证明、授权委托书等全部材料</p>
            </div>
            <Button
              size="sm"
              variant="outline"
              disabled={loading !== null}
              onClick={() => run('package', () => caseApi.downloadAuthorizationPackage(caseId, caseName))}
            >
              {loading === 'package' ? <Loader2 className="size-3.5 mr-1 animate-spin" /> : <Download className="size-3.5 mr-1" />}
              下载 ZIP
            </Button>
          </div>
        </div>

        {/* Individual items */}
        <div className="grid gap-3 sm:grid-cols-2">
          <Card className="gap-0 py-0">
            <CardHeader className="py-3">
              <div className="flex items-center gap-2">
                <FileText className="text-muted-foreground size-4" />
                <span className="text-sm font-medium">所函</span>
              </div>
            </CardHeader>
            <CardContent className="pb-3 pt-0">
              <Button
                size="sm"
                variant="outline"
                className="w-full"
                disabled={loading !== null}
                onClick={() => run('letter', () => caseApi.downloadAuthorizationLetter(caseId, caseName))}
              >
                {loading === 'letter' ? <Loader2 className="size-3.5 mr-1 animate-spin" /> : <Download className="size-3.5 mr-1" />}
                下载
              </Button>
            </CardContent>
          </Card>

          <Card className="gap-0 py-0">
            <CardHeader className="py-3">
              <div className="flex items-center gap-2">
                <Scale className="text-muted-foreground size-4" />
                <span className="text-sm font-medium">合并授权委托书</span>
              </div>
            </CardHeader>
            <CardContent className="pb-3 pt-0">
              <Button
                size="sm"
                variant="outline"
                className="w-full"
                disabled={loading !== null}
                onClick={() => run('combined-poa', () => caseApi.downloadCombinedPOA(caseId, caseName))}
              >
                {loading === 'combined-poa' ? <Loader2 className="size-3.5 mr-1 animate-spin" /> : <Download className="size-3.5 mr-1" />}
                下载
              </Button>
            </CardContent>
          </Card>
        </div>

        {/* Per-client items */}
        {ourParties.length > 0 && (
          <div className="space-y-3">
            <p className="text-xs font-medium text-muted-foreground">按当事人生成</p>
            <div className="flex items-center gap-2">
              <Select value={selectedClient} onValueChange={setSelectedClient}>
                <SelectTrigger className="w-[200px] h-8">
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
              <div className="grid gap-3 sm:grid-cols-2">
                <Card className="gap-0 py-0">
                  <CardHeader className="py-3">
                    <span className="text-sm font-medium">法定代表人证明</span>
                  </CardHeader>
                  <CardContent className="pb-3 pt-0">
                    <Button
                      size="sm"
                      variant="outline"
                      className="w-full"
                      disabled={loading !== null}
                      onClick={() => run('legal-rep', () => caseApi.downloadLegalRepCertificate(caseId, Number(selectedClient)))}
                    >
                      {loading === 'legal-rep' ? <Loader2 className="size-3.5 mr-1 animate-spin" /> : <Download className="size-3.5 mr-1" />}
                      下载
                    </Button>
                  </CardContent>
                </Card>
                <Card className="gap-0 py-0">
                  <CardHeader className="py-3">
                    <span className="text-sm font-medium">授权委托书</span>
                  </CardHeader>
                  <CardContent className="pb-3 pt-0">
                    <Button
                      size="sm"
                      variant="outline"
                      className="w-full"
                      disabled={loading !== null}
                      onClick={() => run('poa', () => caseApi.downloadPowerOfAttorney(caseId, Number(selectedClient)))}
                    >
                      {loading === 'poa' ? <Loader2 className="size-3.5 mr-1 animate-spin" /> : <Download className="size-3.5 mr-1" />}
                      下载
                    </Button>
                  </CardContent>
                </Card>
              </div>
            )}
          </div>
        )}
      </div>
    </DetailCard>
  )
}
