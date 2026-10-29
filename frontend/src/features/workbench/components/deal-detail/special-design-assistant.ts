/**
 * 「AI 设计阶段」的多轮对话替身：确定性规则引擎（54 号原型 design-chat.js 的 RULES 直译）。
 *
 * **为什么设计成多轮对话而不是「AI 给一版，你接受或不要」**：律师的真实台词是连续的
 * ——「职工安置单独拆一步」→「第 3 步再拆细」→「验收标准别写死天数」。每一轮 AI 都
 * 要**改草稿**，而不是重新给一份。左栏草稿随每轮实时变化，右栏对话可回看。
 *
 * **接口**：`PhaseDesignAssistant.suggest(input) → turn`。将来接 copilot 时，把
 * `createRuleAssistant` 换成「发一句话给 LLM + 让它调用阶段草稿工具」的实现即可
 * ——渲染层只消费 `DesignTurn`，不知道背后是规则还是模型。接真实 LLM 的位置：
 * `createRuleAssistant` 下方 `createCopilotAssistant` 的注释处（copilot/store 的
 * 流式对话 + 一个能改阶段草稿的工具，形如 rewrite_folder_file，但作用于阶段草稿）。
 *
 * 规则不是关键词玩具：每条规则都是一次真实的阶段性编辑，作用在草稿上，并把
 * 「改了哪几处」如实回报；一条都没命中时**明确说没找到**，不假装改了。
 */

import {
  appendPhase,
  blankPhase,
  findByKey,
  flattenTree,
  insertAfter,
  newDeliverableId,
  removePhase,
  type PhaseNode,
} from './special-phase-tree'

export interface DesignTurn {
  /** AI 这一轮说了什么（纯文本，`\n` 换行） */
  reply: string
  /** 这一轮**实际**改动了哪几处（逐条给律师看，空数组 = 没改） */
  changes: string[]
  /** 改完后的草稿 */
  draft: PhaseNode[]
  /** 没找到可执行的改动（渲染成虚线气泡，且不宣称改动） */
  unchanged: boolean
}

export interface AssistantInput {
  /** 律师这句话 */
  text: string
  /** 当前草稿（规则的输入） */
  draft: PhaseNode[]
  /** 设计器右栏选中的阶段 key（「补交付物」这类无主语指令的落点） */
  selectedKey: string | null
}

/** 可注入的设计建议器：默认实现是确定性规则，将来换成 LLM 工具调用 */
export interface PhaseDesignAssistant {
  /** 给律师的引导语（每条规则对应一句可照抄的指令） */
  hints(): string[]
  suggest(input: AssistantInput): DesignTurn
}

/* ---------------- 工具 ---------------- */

const CN_NUM: Record<string, number> = {
  一: 1, 二: 2, 两: 2, 三: 3, 四: 4, 五: 5, 六: 6, 七: 7, 八: 8, 九: 9, 十: 10,
}

function cnNum(s: string): number {
  if (/^\d+$/.test(s)) return Number(s)
  return CN_NUM[s] ?? 0
}

/** 计划项（无文件、待起草） */
function planned(name: string) {
  return {
    id: newDeliverableId(),
    date: '',
    name,
    version: '',
    state: 'todo' as const,
    planned: true,
  }
}

/** 名字按**包含**匹配：子阶段常叫「职工安置文书」，与「职工安置」是同一类工作 */
function matchByName(tree: PhaseNode[], needle: string): { key: string; name: string } | null {
  const flat = flattenTree(tree)
  const exact = flat.find((x) => x.node.name === needle)
  const loose = flat.find((x) => x.node.name.includes(needle) || needle.includes(x.node.name))
  const hit = exact ?? loose
  return hit ? { key: hit.node.key, name: hit.node.name } : null
}

/**
 * 每个阶段名 → 该阶段真正会分成哪两步（不是「（第一轮）」这种编号占位名）。
 * 拆细时必须给出**有意义的子步骤**，否则律师拿到的是两份没法验收的空壳。
 */
const SPLIT: Record<string, { a: { name: string; acceptance: string; docs: string[] }; b: { name: string; acceptance: string; docs: string[] } }> = {
  职工安置: {
    a: { name: '职工沟通与经济补偿测算', acceptance: '职工名册与补偿测算表经客户确认', docs: ['《职工名册》', '《经济补偿测算表》'] },
    b: { name: '安置方案与协商签署', acceptance: '《职工安置方案》定稿、协商解除签署完成', docs: ['《职工安置方案》', '《协商解除协议》'] },
  },
  登记与注销: {
    a: { name: '清税与清算组备案', acceptance: '清税证明取得、清算组备案完成', docs: ['《清税申报表》', '《清算组备案材料》'] },
    b: { name: '注销登记', acceptance: '市场监管注销登记完成', docs: ['《注销登记材料》'] },
  },
  尽职调查: {
    a: { name: '资料收集与核查', acceptance: '资产、债务、职工底数核清', docs: ['《尽职调查清单》'] },
    b: { name: '出具尽调报告', acceptance: '《尽职调查报告》定稿', docs: ['《尽职调查报告》'] },
  },
  文件起草: {
    a: { name: '核心文书起草', acceptance: '核心文书初稿完成', docs: ['《债权债务清理方案》'] },
    b: { name: '股东决议与定稿', acceptance: '股东会决议通过、文书定稿', docs: ['《股东会决议（解散清算）》'] },
  },
}

/* ---------------- 规则 ---------------- */

interface Rule {
  /** 匹配律师这句话 */
  test: RegExp
  /** 作用在草稿上；返回改动说明（null = 这条规则没东西可改） */
  apply: (draft: PhaseNode[], m: RegExpMatchArray, selectedKey: string | null) => { draft: PhaseNode[]; note: string } | null
}

/**
 * 规则表顺序有意义：删除放最前（最容易被执行「交付物」的规则截胡），
 * 拆细放在「加阶段」之前（「第 3 步再拆细」里也有「阶段」二字）。
 */
const RULES: Rule[] = [
  {
    // ⓪ 删除阶段
    test: /(?:删掉|删除|去掉|不要)\s*[「"]?([^「」"，。\s]{2,12})[」"]?/,
    apply: (draft, m) => {
      const needle = (m[1] ?? '').replace(/\s*(这个|那个)?\s*阶段\s*$/, '').trim()
      if (!needle) return null
      const hit = matchByName(draft, needle)
      if (!hit) return null
      return { draft: removePhase(draft, hit.key), note: `删掉了「${hit.name}」这个阶段` }
    },
  },
  {
    // ① 拆出职工安置阶段
    test: /职工|安置|员工/,
    apply: (draft) => {
      // 只看**顶层**是否已有独立的「职工安置」：子层里叫「职工安置文书」是原有细项，不该阻止拆分
      if (draft.some((n) => n.name.includes('职工'))) return null
      const anchor = flattenTree(draft).find((x) => x.node.name.includes('文件起草'))
      const node: PhaseNode = {
        ...blankPhase('职工安置'),
        open: true,
        acceptance: '《职工安置方案》定稿，职工沟通记录归档',
        deliverables: [planned('《职工安置方案》'), planned('《职工沟通记录》')],
      }
      let next = anchor ? insertAfter(draft, anchor.node.key, node) : appendPhase(draft, node)
      // 从原阶段里摘掉重复的《职工安置方案》
      const from = flattenTree(next).find((x) => x.node.name.includes('文件起草') && !x.node.name.includes('职工'))
      if (from) {
        const keep = from.node.deliverables.filter((d) => !d.name.includes('职工'))
        next = next.map(function replace(n): PhaseNode {
          if (n.key !== from.node.key) return { ...n, folders: n.folders.map(replace) }
          return { ...n, deliverables: keep }
        })
      }
      return { draft: next, note: '在「文件起草」之后新增阶段「职工安置」，并把《职工安置方案》从原阶段移过来' }
    },
  },
  {
    // ② 第 N 步再拆细
    test: /第\s*([一二三四五六七八九十\d]+)\s*(步|阶段|个).*(拆|细|分)/,
    apply: (draft, m) => {
      const n = cnNum(m[1] ?? '')
      const flat = flattenTree(draft)
      const target = flat[n - 1]
      if (!target) return null
      const p = target.node
      const preset = SPLIT[p.name]
      const a = preset?.a ?? { name: `${p.name}·准备`, acceptance: '', docs: p.deliverables.slice(0, 1).map((d) => d.name) }
      const b = preset?.b ?? { name: `${p.name}·交付`, acceptance: p.acceptance, docs: p.deliverables.slice(1).map((d) => d.name) }
      const bNode: PhaseNode = {
        ...blankPhase(b.name),
        acceptance: b.acceptance,
        deliverables: b.docs.map(planned),
      }
      const t = insertAfter(draft, p.key, bNode)
      const next = t.map(function patch(node): PhaseNode {
        if (node.key !== p.key) return { ...node, folders: node.folders.map(patch) }
        return {
          ...node,
          name: a.name,
          acceptance: a.acceptance,
          deliverables: a.docs.map(planned),
          folders: node.folders.map(patch),
        }
      })
      return { draft: next, note: `把第 ${n} 阶段「${p.name}」拆成两步：「${a.name}」+「${b.name}」` }
    },
  },
  {
    // ③ 验收标准不写死天数
    test: /天数|日期|截止|不要写死|别写死|模糊|弹性/,
    apply: (draft) => {
      let count = 0
      const strip = (n: PhaseNode): PhaseNode => {
        let acceptance = n.acceptance
        if (/\d+\s*(天|日|周|个月)|前完成|截止/.test(acceptance)) {
          acceptance = acceptance.replace(/\d+\s*(天|个工作日|日|周|个月)[^，。；]*/g, '').replace(/，$/, '')
          count += 1
        }
        return { ...n, acceptance, folders: n.folders.map(strip) }
      }
      const next = draft.map(strip)
      return {
        draft: next,
        note: count ? `清掉 ${count} 处验收标准里的具体天数` : '验收标准里本来就没有写死天数，保持结果口径',
      }
    },
  },
  {
    // ④ 增加阶段
    test: /加(一个|个|一)?阶段|新增(一个)?阶段|补(一个)?阶段/,
    apply: (draft) => {
      const node: PhaseNode = {
        ...blankPhase('归档与复盘'),
        deliverables: [planned('《项目结项报告》')],
      }
      const next = appendPhase(draft, node)
      return { draft: next, note: `在末尾加了第 ${flattenTree(next).length} 阶段「归档与复盘」` }
    },
  },
  {
    // ⑤ 补交付物（无主语时落到右栏选中阶段，否则第一个阶段）
    test: /交付物|文书/,
    apply: (draft, _m, selectedKey) => {
      const flat = flattenTree(draft)
      if (flat.length === 0) return null
      const target = (selectedKey ? findByKey(draft, selectedKey) : null) ?? flat[0]
      if (!target) return null
      const key = target.node.key
      const name = target.node.name
      const doc = `《${name}工作底稿》`
      const exists = target.node.deliverables.some((d) => d.name === doc)
      if (exists) return { draft, note: `「${name}」已经有${doc}，没有重复添加` }
      const next = draft.map(function add(n): PhaseNode {
        if (n.key !== key) return { ...n, folders: n.folders.map(add) }
        return { ...n, deliverables: [...n.deliverables, planned(doc)] }
      })
      return { draft: next, note: `给「${name}」补了一份${doc}` }
    },
  },
]

const HINTS = [
  '「职工安置单独拆一步」',
  '「第 3 步再拆细」',
  '「验收标准别写死天数」',
  '「加一个阶段」/「删掉交接阶段」',
]

/** 默认建议器：确定性规则（同一句话永远得到同一处改动，便于单测与自检） */
export function createRuleAssistant(): PhaseDesignAssistant {
  return {
    hints: () => HINTS.slice(),
    suggest: ({ text, draft, selectedKey }) => {
      const input = text.trim()
      const changes: string[] = []
      let next = draft
      for (const rule of RULES) {
        const m = input.match(rule.test)
        if (!m) continue
        const result = rule.apply(next, m, selectedKey)
        // 规则命中但无可改动（如本来就拆过）时同样计入 changes——它也是一句真实说明
        if (result) {
          next = result.draft
          changes.push(result.note)
        }
      }
      if (changes.length === 0) {
        return {
          draft,
          changes: [],
          unchanged: true,
          reply: ['这句我没找到可执行的改动。可以直接指出来，比如：', ...HINTS.map((h) => `· ${h}`)].join('\n'),
        }
      }
      return { draft: next, changes, unchanged: false, reply: '改好了，左边草稿已更新：' }
    },
  }
}

/*
 * 将来接 copilot 的位置：把本文件的默认建议器换成
 *
 *   createCopilotAssistant(contractId): PhaseDesignAssistant
 *     · suggest() 把 (text, draft 摘要, selectedKey) 发进 copilot 会话（流式）；
 *     · 模型通过工具调用（如 rewrite_phase_draft）返回改动后的草稿 + 逐条 changes；
 *     · 渲染层不变——PhaseDesignDialog 只消费 DesignTurn。
 *
 * 目前不接真 LLM：本轮的验收目标是「草稿随对话变、回复列出改动、未命中明说」，
 * 规则引擎可以确定性地证明这三条，而接模型会把这些断言变成不稳定测试。
 */

/** 对话开场白（首轮，agent 与页签无关——切页签不该清空记录） */
export const DESIGN_GREETING =
  '这是这家厂（专项服务 · 关厂清盘 · 固定收费）关厂清盘的常见骨架，已经按现有阶段落在左边。' +
  '你可以直接说哪里不对——比如「职工安置单独拆一步」「第 3 步再细一点」，我改左边这份草稿。'
