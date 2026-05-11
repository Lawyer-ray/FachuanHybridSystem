/** 批量分析汇总：CSV + ZIP 下载按钮 */

import { useState } from 'react'
import { Download } from 'lucide-react'
import { cn } from '@/lib/utils'
import { API_BASE_URL } from '@/lib/api'
import { getAccessToken } from '@/lib/token'
import { downloadBlob } from '@/lib/download'
import { toast } from 'sonner'
import {
  AlertDialog, AlertDialogContent, AlertDialogHeader, AlertDialogTitle,
  AlertDialogFooter, AlertDialogCancel,
} from '@/components/ui/alert-dialog'
import { Button } from '@/components/ui/button'

type DownloadType = 'csv' | 'zip' | null

export function BatchDownloadButton({ jobId }: { jobId: string }) {
  const [downloading, setDownloading] = useState<string | null>(null)
  const [downloadType, setDownloadType] = useState<DownloadType>(null)

  const doDownload = async (type: 'csv' | 'zip', relevantOnly: boolean) => {
    setDownloadType(null)
    setDownloading(type)
    try {
      const baseUrl = API_BASE_URL
      const token = getAccessToken()
      const endpoint = type === 'csv' ? 'download' : 'download-detail'
      const params = new URLSearchParams()
      if (relevantOnly) params.set('relevant_only', 'true')
      const url = `${baseUrl}/workbench/batch/${jobId}/${endpoint}?${params.toString()}`
      const response = await fetch(url, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      })
      if (!response.ok) {
        if (response.status === 404) {
          toast.error(type === 'zip' ? '分析详情文件尚未生成' : '汇总文件不存在')
          return
        }
        throw new Error(`HTTP ${response.status}`)
      }
      const blob = await response.blob()
      const filename = type === 'csv'
        ? `案例分析汇总_${jobId.slice(0, 8)}.csv`
        : `案例分析详情_${jobId.slice(0, 8)}.zip`
      downloadBlob(blob, filename)
    } catch {
      toast.error('下载失败')
    } finally {
      setDownloading(null)
    }
  }

  return (
    <>
      <div className="mt-2 flex gap-2">
        <button
          onClick={() => setDownloadType('csv')}
          disabled={downloading !== null}
          className="inline-flex items-center gap-1.5 rounded-md bg-primary/10 px-3 py-1.5 text-xs font-medium text-primary hover:bg-primary/20 transition-colors disabled:opacity-50"
        >
          <Download className={cn('size-3.5', downloading === 'csv' && 'animate-spin')} />
          {downloading === 'csv' ? '下载中...' : '下载汇总 CSV'}
        </button>
        <button
          onClick={() => setDownloadType('zip')}
          disabled={downloading !== null}
          className="inline-flex items-center gap-1.5 rounded-md bg-primary/10 px-3 py-1.5 text-xs font-medium text-primary hover:bg-primary/20 transition-colors disabled:opacity-50"
        >
          <Download className={cn('size-3.5', downloading === 'zip' && 'animate-spin')} />
          {downloading === 'zip' ? '下载中...' : '下载分析详情 ZIP'}
        </button>
      </div>

      <AlertDialog open={downloadType !== null} onOpenChange={(open) => { if (!open) setDownloadType(null) }}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              下载{downloadType === 'csv' ? '汇总 CSV' : '分析详情 ZIP'}
            </AlertDialogTitle>
          </AlertDialogHeader>
          <p className="text-sm text-muted-foreground">
            选择下载范围：仅下载与研究问题相关的案例，或下载全部案例。
          </p>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <Button variant="outline" onClick={() => doDownload(downloadType!, true)}>
              仅相关案例
            </Button>
            <Button onClick={() => doDownload(downloadType!, false)}>
              全部案例
            </Button>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  )
}
