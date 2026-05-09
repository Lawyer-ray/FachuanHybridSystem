/** 批量分析汇总：CSV + ZIP 下载按钮 */

import { useState } from 'react'
import { Download } from 'lucide-react'
import { cn } from '@/lib/utils'
import { API_BASE_URL } from '@/lib/api'
import { getAccessToken } from '@/lib/token'
import { downloadBlob } from '@/lib/download'
import { toast } from 'sonner'

export function BatchDownloadButton({ jobId }: { jobId: string }) {
  const [downloading, setDownloading] = useState<string | null>(null)

  const handleDownload = async (type: 'csv' | 'zip') => {
    setDownloading(type)
    try {
      const baseUrl = API_BASE_URL
      const token = getAccessToken()
      const endpoint = type === 'csv' ? 'download' : 'download-detail'
      const response = await fetch(`${baseUrl}/workbench/batch/${jobId}/${endpoint}`, {
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
    <div className="mt-2 flex gap-2">
      <button
        onClick={() => handleDownload('csv')}
        disabled={downloading !== null}
        className="inline-flex items-center gap-1.5 rounded-md bg-primary/10 px-3 py-1.5 text-xs font-medium text-primary hover:bg-primary/20 transition-colors disabled:opacity-50"
      >
        <Download className={cn('size-3.5', downloading === 'csv' && 'animate-spin')} />
        {downloading === 'csv' ? '下载中...' : '下载汇总 CSV'}
      </button>
      <button
        onClick={() => handleDownload('zip')}
        disabled={downloading !== null}
        className="inline-flex items-center gap-1.5 rounded-md bg-primary/10 px-3 py-1.5 text-xs font-medium text-primary hover:bg-primary/20 transition-colors disabled:opacity-50"
      >
        <Download className={cn('size-3.5', downloading === 'zip' && 'animate-spin')} />
        {downloading === 'zip' ? '下载中...' : '下载分析详情 ZIP'}
      </button>
    </div>
  )
}
