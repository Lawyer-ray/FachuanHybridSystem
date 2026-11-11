/**
 * 回扫 —— 邮箱扫描设置弹窗（轮询间隔 / 监听文件夹 / 发件人白名单）。
 *
 * 表单值只在弹窗里活着，保存时才冒泡成一条配置，所以草稿状态收在
 * `MailboxConfigForm` 里；`MailboxConfigDrawer` 只负责按地址取默认值，
 * 并用 `key` 让每次打开都是干净草稿（换邮箱不残留上一份的输入）。
 */
import { useState } from 'react'

import { DEMO_X2_SCAN_INTERVALS, DEMO_X2_SCAN_MAILBOXES, type ScanMailboxConfig } from '../../demo-data'
import { ActionButton, InsetBlock, Pill } from '../../ui'
import { DetailDrawer } from '../DetailDrawer'

/** 邮箱配置弹窗：轮询间隔 / 文件夹 / 发件人白名单 */
export function MailboxConfigDrawer({
  addr,
  onClose,
  onSave,
  saved,
}: {
  addr: string | null
  onClose: () => void
  onSave: (cfg: ScanMailboxConfig) => void
  /** 已保存过的配置（优先于演示默认值） */
  saved: Record<string, ScanMailboxConfig>
}) {
  const base = addr ? (saved[addr] ?? DEMO_X2_SCAN_MAILBOXES.find((m) => m.addr === addr)) ?? null : null
  return (
    <MailboxConfigForm key={base?.addr ?? 'none'} base={base} onClose={onClose} onSave={onSave} />
  )
}

/** 邮箱配置表单本体：草稿值在这里，保存后由面板覆盖默认值 */
function MailboxConfigForm({
  base,
  onClose,
  onSave,
}: {
  base: ScanMailboxConfig | null
  onClose: () => void
  onSave: (cfg: ScanMailboxConfig) => void
}) {
  const [interval, setInterval] = useState(base?.interval ?? '')
  const [folder, setFolder] = useState(base?.folder ?? '')
  const [whitelist, setWhitelist] = useState(base?.whitelist ?? '')

  return (
    <DetailDrawer
      open={base != null}
      onClose={onClose}
      title="邮箱扫描设置"
      subtitle={base?.addr}
      badge={<Pill tone="green">监听中</Pill>}
      width={460}
      footer={
        base ? (
          <>
            <ActionButton
              dark
              onClick={() => onSave({ ...base, interval, folder, whitelist })}
            >
              保存配置
            </ActionButton>
            <ActionButton onClick={onClose}>取消</ActionButton>
          </>
        ) : null
      }
    >
      {base ? (
        <div className="flex flex-col gap-3">
          <div>
            <label className="text-[10px] text-muted-foreground" htmlFor="x2-interval">
              轮询间隔
            </label>
            <select
              id="x2-interval"
              value={interval}
              onChange={(e) => setInterval(e.target.value)}
              className="mt-1 w-full rounded-[8px] border border-border bg-background px-2.5 py-1.5 text-[12px] outline-none focus:border-foreground"
            >
              {DEMO_X2_SCAN_INTERVALS.map((i) => (
                <option key={i} value={i}>
                  每 {i}
                </option>
              ))}
            </select>
            <p className="mt-1 text-[10px] text-muted-foreground">法院送达邮箱建议 1 分钟，其他 5 分钟足够。</p>
          </div>

          <div>
            <label className="text-[10px] text-muted-foreground" htmlFor="x2-folder">
              监听文件夹
            </label>
            <input
              id="x2-folder"
              value={folder}
              onChange={(e) => setFolder(e.target.value)}
              className="mt-1 w-full rounded-[8px] border border-border bg-background px-2.5 py-1.5 text-[12px] outline-none focus:border-foreground"
            />
            <p className="mt-1 text-[10px] text-muted-foreground">多个用 / 分隔，如 INBOX / 送达文书。</p>
          </div>

          <div>
            <label className="text-[10px] text-muted-foreground" htmlFor="x2-whitelist">
              发件人白名单
            </label>
            <textarea
              id="x2-whitelist"
              rows={3}
              value={whitelist}
              onChange={(e) => setWhitelist(e.target.value)}
              className="mt-1 w-full resize-y rounded-[8px] border border-border bg-background px-2.5 py-1.5 text-[11px] leading-[1.7] outline-none focus:border-foreground"
            />
            <p className="mt-1 text-[10px] text-muted-foreground">
              只处理白名单里的发件人；其余邮件仍会留档，但不自动归案。
            </p>
          </div>

          <InsetBlock className="bg-secondary/25">
            <div className="text-[10px] text-muted-foreground">当前账号</div>
            <p className="mt-1 text-[11px] leading-[1.7] text-secondary-foreground">
              {base.note} · 本月已扫 {base.count} 封
            </p>
          </InsetBlock>
        </div>
      ) : null}
    </DetailDrawer>
  )
}
