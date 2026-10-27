/**
 * 新增记忆表单：手动录入个人记忆（「让助手记住一件事」）。
 *
 * 从 MemoryDrawer 拆出（后者超软红线）。草稿与类型是本地 state——用户正在打字的
 * 内容不该被全局状态覆盖；提交成功后由父层清空（`draft` 受控，父层置空即生效）。
 *
 * 操作指引（playbook）走另一条上限：它不进每轮注入，只在记忆里留一行索引，
 * 适合写成多步骤规范，所以给更大输入框与更高上限。
 */

import { Plus } from 'lucide-react'

import type { MemoryKind } from '../../memory-api'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { KIND_LABEL, MAX_CONTENT, MAX_PLAYBOOK } from './labels'

/** 可手动录入的类型（顺序即下拉顺序：常用在前，纠正/指引在后） */
const KIND_OPTIONS: MemoryKind[] = ['preference', 'procedure', 'fact', 'correction', 'playbook']

export function MemoryComposer({
  draft,
  onDraftChange,
  kind,
  onKindChange,
  creating,
  error,
  onSubmit,
}: {
  draft: string
  onDraftChange: (text: string) => void
  kind: MemoryKind
  onKindChange: (kind: MemoryKind) => void
  /** 创建请求在途 */
  creating: boolean
  /** 创建失败的原因（父层 mutation 的 error.message） */
  error: string | null
  onSubmit: () => void
}) {
  const draftTrimmed = draft.trim()
  const isPlaybook = kind === 'playbook'
  const draftLimit = isPlaybook ? MAX_PLAYBOOK : MAX_CONTENT
  const draftTooLong = draftTrimmed.length > draftLimit

  return (
    <section className="mb-5" aria-label="新增记忆">
      <label htmlFor="memory-draft" className="mb-1.5 block text-[12px] font-[650] text-foreground">
        让助手记住一件事
      </label>
      <Textarea
        id="memory-draft"
        value={draft}
        onChange={(e) => onDraftChange(e.target.value)}
        placeholder={
          isPlaybook
            ? '多步骤操作规范，可分段，例如：\n1. 阅卷前先调 get_case 确认承办阶段\n2. 卷宗按「程序性文书→证据→笔录」排序\n3. 每份材料在页脚标注来源与页码'
            : '例如：文书先给结论，再给理由；引用法条时附条文原文'
        }
        rows={isPlaybook ? 6 : 2}
        className="resize-y text-[13px]"
      />
      {isPlaybook && (
        <p className="mt-1 text-[10px] leading-relaxed text-muted-foreground">
          操作指引不会每轮注入，只在记忆里留一行索引；需要时助手会自己取全文。适合写成多步骤规范。
        </p>
      )}
      <div className="mt-2 flex items-center gap-2">
        <select
          aria-label="记忆类型"
          value={kind}
          onChange={(e) => onKindChange(e.target.value as MemoryKind)}
          className="h-7 rounded-[7px] border border-border bg-card px-2 text-[11px] text-foreground"
        >
          {KIND_OPTIONS.map((option) => (
            <option key={option} value={option}>
              {KIND_LABEL[option]}
            </option>
          ))}
        </select>
        {draftTrimmed.length > 0 && (
          <span className={`text-[10px] ${draftTooLong ? 'text-destructive' : 'text-muted-foreground/70'}`}>
            {draftTrimmed.length}/{draftLimit}
          </span>
        )}
        <Button
          size="sm"
          className="ml-auto h-7 gap-1 px-2.5 text-[11px]"
          disabled={!draftTrimmed || draftTooLong || creating}
          onClick={onSubmit}
        >
          <Plus className="h-3 w-3" />
          记住
        </Button>
      </div>
      {error && <p className="mt-1.5 text-[11px] text-destructive">保存失败：{error}</p>}
    </section>
  )
}
