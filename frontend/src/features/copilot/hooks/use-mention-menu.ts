/**
 * `@` 引用菜单的整条交互管线：识别 token → 并发拉各源 → 共享高亮 → 键盘裁决。
 *
 * 照 deepseek-harness `ui-input-trigger`（`core/menu.ts` 的 generation 门控 reducer
 * + `client/controller.ts:265` 的 `arbitrate`）的机制实现，原因写在对应位置，
 * **不要「优化」掉**：
 *
 * 1. **一次查询一个 AbortController + 一个 generation 号**：查询词一变就 abort
 *    上一轮、generation +1，迟到结果按 generation 丢弃。没有这层，「@起」的慢
 *    响应会盖掉「@起诉状」的结果——菜单显示的是别的查询的行，律师按 Enter 就引用错对象。
 * 2. **一个源失败只静默掉这一组**（console 一次，不弹错、不关菜单）。四类对象
 *    四个源，某一类 500 不该把另外三类一起带走——那看起来就是「@ 坏了」。
 * 3. **组还 pending 时 Enter 显式空转**（返回 'consumed'）：绝不选陈旧行，也绝不
 *    让 Enter 落到「发送」上（半截查询发出去比没反应更糟）。
 * 4. **IME 合成期间一律 pass**：复用 `use-ime-enter-guard`（PIT-006），不另写一套
 *    判定、也不碰 composition 事件——合成态生命周期只能有一处（Composer）。
 *
 * 本 hook 只回答「这个按键归不归我」（'consumed' | 'pass'）；改草稿由调用方拿
 * `onPick(insert, token)` 自己做（`applyMention` 是纯函数），本 hook 不碰草稿、
 * 不碰 store——store 写入是 `addMention` 的事。
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { globalSearch, loadScopeFolderRows } from '../api'
import type { ScopeFolderRows } from '../api'
import {
  detectMentionToken,
  filterMentionCandidates,
  flattenMentionOptions,
  makeMentionInsert,
  moveMentionHighlight,
  type MentionCandidate,
  type MentionGroupLike,
  type MentionHighlight,
  type MentionInsert,
  type MentionSource,
  type MentionToken,
} from '../domain'
import type { CopilotScope } from '../types'
import { useImeEnterGuard } from './use-ime-enter-guard'

/** 每个源最多几行（一屏；再多键盘也翻不完，还会把别的组挤出视野） */
const SOURCE_LIMIT = 12

/** 菜单组：源的结果 + 该组自己的状态（失败时整组消失） */
export interface MentionGroup extends MentionGroupLike {
  title: string
  status: 'pending' | 'ready'
  items: MentionCandidate[]
}

/** 键盘裁决结果：'consumed' = 菜单吃掉了这个键，调用方必须短路发送逻辑 */
export type MentionKeyResult = 'consumed' | 'pass'

/** 复用 Composer 已挂好的 IME 守卫（同一实例，不另建 composition 生命周期） */
type ImeComposingCheck = Pick<ReturnType<typeof useImeEnterGuard>, 'isComposing'>

export interface UseMentionMenuOptions {
  /** 草稿全文 */
  text: string
  /** 光标位置（textarea 的 selectionStart） */
  caret: number
  /** 当前业务范围（决定文书/目录源取哪个绑定文件夹；缺省 = 通用对话，那两组为空） */
  scope?: CopilotScope
  /** 数据源；缺省按 scope 构建四类（测试注入用） */
  sources?: MentionSource[]
  /** IME 守卫（Composer 传入 useComposerSubmit 返回的同一实例） */
  ime?: ImeComposingCheck
  /** 选中：调用方负责 applyMention + addMention */
  onPick: (insert: MentionInsert, token: MentionToken) => void
}

/** 同一份告警只打一次：源失败/无范围是「每敲一个字都重复」的场景，刷屏会淹掉真错误 */
const warned = new Set<string>()

function warnOnce(key: string, message: string, detail?: unknown): void {
  if (warned.has(key)) return
  warned.add(key)
  console.warn(message, detail ?? '')
}

/** 测试用：清掉告警去重表（否则跨用例只打一次） */
export function resetMentionWarnings(): void {
  warned.clear()
}

/** subpath 的父目录（`1-一审/起诉状.pdf` → `1-一审`；根层文件 → 绑定文件夹） */
function parentDir(subpath: string): string {
  return subpath.split('/').filter(Boolean).slice(0, -1).join('/') || '绑定文件夹'
}

/**
 * 同名文件消歧：`store/mentions.ts` 的去重键是 (kind, refId, label)，文书没有业务
 * id，两份不同目录下的同名文件会被当成同一条，第二次选中就静默丢失。有重名时给
 * label 补上级目录（只补重名的那几条，其余保持原样好读）。
 */
function disambiguateLabels(items: MentionCandidate[]): MentionCandidate[] {
  const counts = new Map<string, number>()
  for (const item of items) counts.set(item.label, (counts.get(item.label) ?? 0) + 1)
  return items.map((item) =>
    (counts.get(item.label) ?? 0) > 1 && item.subpath
      ? { ...item, label: `${parentDir(item.subpath)}/${item.label}` }
      : item,
  )
}

/** 行 → 候选（文书/目录共用：owner 决定出站块里的 id 键名） */
function toCandidates(rows: ScopeFolderRows, scope: CopilotScope): { files: MentionCandidate[]; folders: MentionCandidate[] } {
  const owner = { kind: scope.origin, id: scope.refId } as const
  return {
    files: disambiguateLabels(
      rows.files.map((file) => ({
        kind: 'document',
        label: file.name,
        sublabel: `${parentDir(file.subpath)} · ${Math.max(1, Math.round(file.size / 1024))}KB`,
        subpath: file.subpath,
        owner,
      })),
    ),
    folders: rows.folders.map((folder) => ({
      kind: 'folder',
      label: folder.name,
      sublabel: `目录 · ${folder.subpath}`,
      subpath: folder.subpath,
      owner,
    })),
  }
}

/** 案件 / 合同：全局搜索的两类结果（同一端点，各自挑自己那组） */
function searchSource(kind: 'case' | 'contract'): MentionSource {
  return {
    key: kind,
    trigger: '@',
    title: kind === 'case' ? '案件' : '合同',
    load: async ({ query, signal }) => {
      const q = query.trim()
      // 空查询不打网络（后端对空 q 也是早退回空）：按下 `@` 那一瞬想看「这里有什么」，
      // 那由文书/目录两组回答，不是靠搜一个空串
      if (!q) return []
      const result = await globalSearch(q, SOURCE_LIMIT, signal)
      const rows = kind === 'case' ? result.cases : result.contracts
      return rows.map((row) => ({
        kind,
        refId: row.id,
        label: row.title,
        // 案件带案由、合同带委托人（case 行还可能带所属项目名），只做副标题展示
        sublabel: row.subtitle || row.contract_name || '',
        // 整案/整份合同 = 它的整棵绑定文件夹。'.' 经后端
        // `bound_folder_browse.normalize_subpath` 归一成 ''（绑定根）——不能写空串，
        // `SENT_REF_RE` 要求 subpath 至少一个字符，空串会让历史回放认不出这条引用
        subpath: '.',
        owner: { kind, id: row.id },
      }))
    },
    toInsert: makeMentionInsert,
  }
}

/** 绑定文件夹里的文书/子目录：按名字本地过滤（后端没有目录内检索端点） */
function scopeSource(kind: 'document' | 'folder', scope: CopilotScope | undefined): MentionSource {
  return {
    key: kind,
    trigger: '@',
    title: kind === 'document' ? '文书' : '文件夹',
    load: async ({ query }) => {
      if (!scope) {
        warnOnce(`no-scope:${kind}`, `[copilot] @引用：通用对话没有业务范围，「${kind === 'document' ? '文书' : '文件夹'}」源为空（进案件/合同页再 @）`)
        return []
      }
      const rows = await loadScopeFolderRows(scope)
      if (!rows.browsable) {
        warnOnce(`unbound:${scope.origin}:${scope.refId}`, `[copilot] @引用：当前${scope.origin === 'case' ? '案件' : '合同'}没有可浏览的绑定文件夹，文书/目录两组为空`, rows.message ?? undefined)
        return []
      }
      const candidates = toCandidates(rows, scope)
      return filterMentionCandidates(kind === 'document' ? candidates.files : candidates.folders, query, SOURCE_LIMIT)
    },
    toInsert: makeMentionInsert,
  }
}

/** 四类源（顺序 = 菜单分组顺序：先业务对象，再它里面的文件/目录） */
export function buildMentionSources(scope?: CopilotScope): MentionSource[] {
  return [searchSource('case'), searchSource('contract'), scopeSource('document', scope), scopeSource('folder', scope)]
}

/**
 * `@` 引用菜单的交互状态。
 *
 * @returns `open` 是否展开、`groups` 分组视图、`highlight` 共享高亮、
 *   `onKeyDown` 键盘裁决（'consumed' | 'pass'）、`onHover` / `pick` 鼠标入口。
 */
export function useMentionMenu({ text, caret, scope, sources, ime, onPick }: UseMentionMenuOptions) {
  const ownIme = useImeEnterGuard()
  const guard = ime ?? ownIme
  const sourceList = useMemo(() => sources ?? buildMentionSources(scope), [sources, scope])

  // 只认 `@`：`/` 命令菜单自带一组「禁用项」语义（无会话时 compact 置灰），仍由
  // use-slash-menu 管；但两者共用同一个检测器、同一个按键仲裁入口（见 Composer）
  const token = useMemo(() => {
    const detected = detectMentionToken(text, caret)
    return detected?.trigger === '@' ? detected : null
  }, [text, caret])

  /** Esc 关闭时记住的 token 签名：同一 token（同起点同查询词）不再自动弹，改字才重开 */
  const signature = token ? `${token.start}:${token.query}` : null
  const [dismissed, setDismissed] = useState<string | null>(null)
  const open = token !== null && signature !== dismissed

  const [groups, setGroups] = useState<MentionGroup[]>([])
  const [highlight, setHighlight] = useState<MentionHighlight | null>(null)
  /** 第几代查询：迟到结果按它丢弃（机制 1） */
  const generationRef = useRef(0)
  const query = token?.query ?? null

  // 源列表走 ref 而不进 effect 依赖：调用方传字面量数组（`sources: [mySource]`）时
  // 每次渲染都是新引用，依赖它就会「拉取 → setState → 重渲染 → 再拉取」无限循环
  // （实测会把 jsdom 进程跑到 OOM）。源在会话期间本来就不变，首帧同步一次即可。
  const sourcesRef = useRef(sourceList)

  useEffect(() => {
    sourcesRef.current = sourceList
  }, [sourceList])

  useEffect(() => {
    if (!open || query === null) {
      // 关掉时清空：再次打开必须从 pending 开始，不能先闪一眼上次的行
      generationRef.current += 1
      setGroups([])
      setHighlight(null)
      return
    }
    const generation = generationRef.current + 1
    generationRef.current = generation
    const controller = new AbortController()
    const active = sourcesRef.current.filter((source) => source.trigger === '@')
    setGroups(active.map((source) => ({ key: source.key, title: source.title, status: 'pending', items: [] })))
    setHighlight(null)
    for (const source of active) {
      void source
        .load({ query, signal: controller.signal })
        .then((items) => {
          // 竞态闸门：这一轮已不是最新查询，结果直接丢弃（机制 1）
          if (generation !== generationRef.current) return
          setGroups((prev) => prev.map((g) => (g.key === source.key ? { ...g, status: 'ready', items } : g)))
        })
        .catch((error: unknown) => {
          if (generation !== generationRef.current) return
          // abort 是我们自己发起的（查询词变了 / 菜单关了），不是故障
          if (controller.signal.aborted) return
          // 机制 2：只静默掉这一组，其余组照常
          warnOnce(`source-failed:${source.key}`, `[copilot] @引用源「${source.title}」查询失败，已隐藏该组`, error)
          setGroups((prev) => prev.filter((g) => g.key !== source.key))
        })
    }
    return () => controller.abort()
  }, [open, query])

  const options = useMemo(() => flattenMentionOptions(groups), [groups])

  // 结果集变了：高亮失效就回到第一行（键盘永远有一个合法起点）
  useEffect(() => {
    if (options.length === 0) {
      if (highlight !== null) setHighlight(null)
      return
    }
    const stillThere = highlight !== null && options.some((o) => o.key === highlight.key && o.index === highlight.index)
    if (!stillThere) setHighlight({ key: options[0]!.key, index: options[0]!.index })
  }, [options, highlight])

  const pick = useCallback(
    (target?: MentionHighlight): boolean => {
      const position = target ?? highlight
      if (!position || !token) return false
      const group = groups.find((g) => g.key === position.key)
      // 机制 3：组没就绪绝不选（陈旧行会引用错对象）
      if (!group || group.status !== 'ready') return false
      const candidate = group.items[position.index]
      const source = sourceList.find((s) => s.key === position.key)
      if (!candidate || !source) return false
      onPick(source.toInsert(candidate), token)
      return true
    },
    [groups, highlight, onPick, sourceList, token],
  )

  const onHover = useCallback((key: string, index: number) => {
    setHighlight((prev) => (prev?.key === key && prev.index === index ? prev : { key, index }))
  }, [])

  const onKeyDown = useCallback(
    (event: React.KeyboardEvent): MentionKeyResult => {
      if (!open) return 'pass'
      // 机制 4：合成中的按键属于输入法（选词 Enter / 方向键），一律交回
      if (guard.isComposing(event)) return 'pass'
      // Shift+Enter 是换行，永远不是「选中项」（与 use-composer-submit 同口径）
      if (event.key === 'Enter' && event.shiftKey) return 'pass'
      if (event.key === 'Escape') {
        setDismissed(signature)
        return 'consumed'
      }
      switch (event.key) {
        case 'ArrowDown':
          setHighlight((prev) => moveMentionHighlight(options, prev, 1))
          return 'consumed'
        case 'ArrowUp':
          setHighlight((prev) => moveMentionHighlight(options, prev, -1))
          return 'consumed'
        case 'Enter':
        case 'Tab':
          // 菜单开着时 Enter/Tab 只有两种结局：选中，或显式空转（机制 3）。
          // 绝不放行成「发送」——那会把半截 `@起诉` 发出去
          pick()
          return 'consumed'
        default:
          return 'pass'
      }
    },
    [guard, open, options, pick, signature],
  )

  return {
    open,
    token,
    query,
    groups,
    options,
    highlight,
    onKeyDown,
    onHover,
    pick,
    /** 调用方没传 ime 时，用它把 composition 处理器挂到输入框上 */
    onCompositionStart: ownIme.onCompositionStart,
    onCompositionEnd: ownIme.onCompositionEnd,
  }
}
