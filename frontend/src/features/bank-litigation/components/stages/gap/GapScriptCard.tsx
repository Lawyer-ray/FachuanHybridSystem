/**
 * ③ 缺件 —— 通知模板卡（话术可编辑，按缺件等级自动选）。
 *
 * 话术按 id 覆盖默认正文，改过就标「已改过」并给「恢复默认」。
 * 编辑态与草稿是这一块自己的局部状态：一次只编辑一条，未保存前不影响卡片正文。
 */
import { Pencil } from 'lucide-react'
import { useState } from 'react'

import { DEMO_X2_GAP_SCRIPTS } from '../../demo-data'
import { ActionButton, Pill, SectionTitle, WorkCard } from '../../ui'

/** 通知模板：话术可编辑 */
export function GapScriptCard() {
  /** 可编辑的通知话术（按 id 覆盖默认正文） */
  const [scripts, setScripts] = useState<Record<string, string>>({})
  /** 正在编辑的话术模板 */
  const [editing, setEditing] = useState<string | null>(null)
  /** 编辑中的草稿 */
  const [draft, setDraft] = useState('')

  return (
    <WorkCard padded={false}>
      <div className="flex items-center gap-2 border-b border-border-light px-5 py-3">
        <SectionTitle title="通知模板" hint="按缺件等级自动选话术 · 可编辑" className="w-full" />
      </div>
      <ul className="divide-y divide-border-light">
        {DEMO_X2_GAP_SCRIPTS.map((t) => {
          const body = scripts[t.id] ?? t.body
          const isEditing = editing === t.id
          return (
            <li key={t.id} className="px-5 py-2.5">
              <div className="flex items-center gap-2">
                <Pill tone={t.severity === '硬阻塞' ? 'red' : t.severity === '催办' ? 'yellow' : 'blue'}>
                  {t.severity}
                </Pill>
                <span className="text-[12px] font-medium">{t.title}</span>
                {scripts[t.id] !== undefined ? (
                  <span className="rounded-[4px] border border-status-blue/40 bg-status-blue-bg px-1 text-[9.5px] text-status-blue">
                    已改过
                  </span>
                ) : null}
                <div className="ml-auto flex items-center gap-1.5">
                  {isEditing ? (
                    <>
                      <ActionButton
                        sm
                        dark
                        onClick={() => {
                          setScripts((prev) => ({ ...prev, [t.id]: draft }))
                          setEditing(null)
                        }}
                      >
                        保存
                      </ActionButton>
                      <ActionButton sm onClick={() => setEditing(null)}>
                        取消
                      </ActionButton>
                    </>
                  ) : (
                    <ActionButton
                      sm
                      title="改这段话术，之后发送用新版本"
                      onClick={() => {
                        setEditing(t.id)
                        setDraft(body)
                      }}
                    >
                      <Pencil className="size-3" />
                      编辑话术
                    </ActionButton>
                  )}
                </div>
              </div>
              {isEditing ? (
                <textarea
                  aria-label={`编辑「${t.title}」话术`}
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  rows={4}
                  className="mt-1.5 w-full resize-y rounded-[8px] border border-border bg-background px-2.5 py-2 text-[11px] leading-[1.7] text-secondary-foreground outline-none focus:border-foreground"
                />
              ) : (
                <div className="mt-0.5 text-[10.5px] leading-[1.7] text-muted-foreground">{body}</div>
              )}
              <div className="mt-1 flex items-center gap-2 text-[10px] text-muted-foreground">
                <span>占位符 {'{n}'} {'{list}'} {'{days}'} {'{link}'} 发送时自动替换</span>
                {scripts[t.id] !== undefined ? (
                  <button
                    type="button"
                    onClick={() =>
                      setScripts((prev) => {
                        const next = { ...prev }
                        delete next[t.id]
                        return next
                      })
                    }
                    className="ml-auto text-status-blue hover:underline"
                  >
                    恢复默认
                  </button>
                ) : null}
              </div>
            </li>
          )
        })}
      </ul>
    </WorkCard>
  )
}
