import { useState } from 'react'
import { FileText } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { toast } from 'sonner'

import { convertDocument, listConvertTemplates } from '../../api'
import { TOOL_ENDPOINT } from '../../constants'
import { BTN_PRIMARY, FIELD } from '../../ui'
import { Spinner, ToolShell } from './shared'
import { errMessage } from '../../errors'

/** 要素式转换：POST /doc-convert/convert（multipart：file + mbid），成功后直接下载 */
export function DocConvertCard() {
  const [mbid, setMbid] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [busy, setBusy] = useState(false)

  const { data: groups = [], isLoading } = useQuery({
    queryKey: ['doc-convert-templates'],
    queryFn: listConvertTemplates,
    staleTime: 5 * 60_000,
  })

  const submit = async () => {
    if (!mbid) {
      toast.info('先选文书类型')
      return
    }
    if (!file) {
      toast.info('先选择要转换的文书')
      return
    }
    setBusy(true)
    try {
      const res = await convertDocument(mbid, file)
      const a = document.createElement('a')
      a.href = res.downloadUrl
      a.download = res.filename
      document.body.appendChild(a)
      a.click()
      a.remove()
      toast.success(`转换完成，已下载「${res.filename}」`)
    } catch (e) {
      toast.error(errMessage(e, '要素式转换失败，请检查文件格式'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <ToolShell icon={<FileText className="h-3.5 w-3.5" />} title="要素式转换" endpoint={TOOL_ENDPOINT.docConvert}>
      <div className="flex flex-1 flex-col gap-[7px]">
        <select className={FIELD} value={mbid} onChange={(e) => setMbid(e.target.value)} disabled={isLoading}>
          <option value="">{isLoading ? '正在加载文书模板…' : '选择文书类型…'}</option>
          {groups.map((g) => (
            <optgroup key={g.category} label={g.category}>
              {g.items.map((it) => (
                <option key={it.mbid} value={it.mbid}>
                  {it.name}
                </option>
              ))}
            </optgroup>
          ))}
        </select>

        <label className="flex cursor-pointer items-center gap-2 rounded-[8px] border border-dashed border-input bg-secondary/30 px-[9px] py-[6px] transition-colors hover:border-ring/40 hover:bg-card">
          <input type="file" accept=".doc,.docx,.pdf" className="hidden" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
          <span className="text-[11px] font-medium whitespace-nowrap text-secondary-foreground">选择文书</span>
          <span className="truncate text-[10.5px] text-muted-foreground">{file ? file.name : '.doc / .docx / .pdf ≤ 20MB'}</span>
        </label>

        <div className="mt-auto flex items-center gap-2">
          <button type="button" className={BTN_PRIMARY} onClick={submit} disabled={busy}>
            {busy && <Spinner />}
            转换
          </button>
          <span className="flex-1 truncate text-right text-[10.5px] text-muted-foreground">→ 要素式文书</span>
        </div>
      </div>
    </ToolShell>
  )
}
