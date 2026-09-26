import { useState } from 'react'
import { MessageSquare } from 'lucide-react'
import { toast } from 'sonner'

import { submitCourtSms } from '../../api'
import { TOOL_ENDPOINT } from '../../constants'
import { BTN_PRIMARY, FIELD } from '../../ui'
import { Spinner, ToolShell } from './shared'
import { errMessage } from '../../errors'

/** 收法院短信：POST /automation/court-sms（提交后由后端异步解析） */
export function CourtSmsCard() {
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)

  const submit = async () => {
    const v = text.trim()
    if (!v) {
      toast.info('先粘贴一条法院短信')
      return
    }
    setBusy(true)
    try {
      await submitCourtSms(v)
      setText('')
      toast.success('短信已提交，正在解析处理——完成后会出现在「待处理」里')
    } catch (e) {
      toast.error(errMessage(e, '短信提交失败，请稍后重试'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <ToolShell icon={<MessageSquare className="h-3.5 w-3.5" />} title="收法院短信" endpoint={TOOL_ENDPOINT.courtSms}>
      <div className="flex flex-1 flex-col gap-[7px]">
        <textarea
          className={FIELD + ' resize-none leading-[1.5]'}
          rows={3}
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="粘贴短信全文，如：某某区人民法院：张某诉李某民间借贷纠纷案定于9月29日9时30分开庭…"
        />
        <div className="mt-auto flex items-center gap-2">
          <button type="button" className={BTN_PRIMARY} onClick={submit} disabled={busy}>
            {busy && <Spinner />}
            提交短信
          </button>
          <span className="flex-1 truncate text-right text-[10.5px] text-muted-foreground">提交后自动解析处理</span>
        </div>
      </div>
    </ToolShell>
  )
}
