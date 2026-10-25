/**
 * 从合同文件夹里认出「服务事项」。
 *
 * **为什么从文件夹认，而不是另建一张表**：常法项目的目录结构本身就是数据——
 * 律师每天就在 `3-办案/2026.04.27-草拟付款确认书/` 里干活，事项名与发生日
 * 都写在文件夹名上。再让他在系统里录一遍「服务事项」，是同一件事做两次；
 * 而且两边一旦不同步，律师就不知道该信哪个。
 *
 * 命名约定（实测于 300-常法 下的真实目录）：
 *
 * ```
 * <合同根>/
 *   1-合同发票/
 *   2-邮寄/
 *   3-办案/2026.04.27-草拟付款确认书/      ← 事项 = 目录名
 *   3-日常办案/2026.08.19-发送律师函/      ← 「办案」也可能叫「日常办案」
 *   3-办案/2026.04.14-给某某公司发律师函/文件.docx
 * ```
 *
 * 识别策略是**宽松匹配**而不是写死 `3-办案`：目录前缀数字是排序用的，各人
 * 习惯不同（2-/3-），「办案」「日常办案」「非诉」都可能出现。所以只要目录名
 * 含「办案」，或它下面全是 `日期-事项` 形态的子目录，就认作事项来源。
 */

export interface ParsedItem {
  /** 目录名（事项名去掉日期前缀后的原样文字） */
  title: string
  /** 从目录名解析出的日期 yyyy-mm-dd；解析不出为 '' */
  date: string
  /** 相对合同根的路径（可直接交给文件夹树/下载接口） */
  subpath: string
  /** 目录原名（含编号与日期，用于展示或排查） */
  rawName: string
}

/**
 * 去掉排序序号前缀：`3-办案` → `办案`。
 *
 * **不能宽泛匹配 `数字 + 分隔符**`：`2026.04.27-草拟付款确认书` 会把 `2026.`
 * 当成序号吃掉，剩 `04.27-...`，后续日期解析全错。所以只认**短序号**
 * （1–2 位，跟真实排序习惯 `1-` `2-` `3-` 对应）。
 */
export function stripOrderPrefix(name: string): string {
  return name.replace(/^\s*\d{1,2}\s*[-.、_]\s*/, '').trim()
}

/**
 * 从 `2026.04.27-草拟付款确认书` 解析出日期与事项名。
 *
 * 支持 `2026.04.27` / `2026-04-27` / `2026年4月27日` 三种分隔（律师的文件夹
 * 三种都见过）。解析不出日期时返回 `date: ''`，事项名仍是整个目录名——
 * 宁可少一个日期，也不要因为格式不合就整条丢掉。
 */
export function parseDatedFolder(name: string): { date: string; title: string } {
  const m = name.match(/^\s*(\d{4})[.\-年]\s*(\d{1,2})[.\-月]\s*(\d{1,2})\s*日?\s*[-_.、\s]*\s*(.*)$/)
  if (!m) return { date: '', title: name.trim() }
  const [, y, mo, d, rest] = m
  const date = `${y}-${String(Number(mo)).padStart(2, '0')}-${String(Number(d)).padStart(2, '0')}`
  return { date, title: (rest || '').trim() || name.trim() }
}

/** 该目录名是否像「办案事项目录」（含办案/日常办案 等） */
export function looksLikeCaseFolder(name: string): boolean {
  return /办案|法律服务|日常事务/.test(stripOrderPrefix(name))
}

/** 条目来自文件夹扫描的最小形状（与后端 folder-entries 对齐，只要这两列） */
export interface FolderEntry {
  name: string
  subpath: string
}

/**
 * 在合同根的一层目录里找出「事项源目录」，并把它下面的子目录转成服务事项。
 *
 * 两步：先挑出事项源目录（名字含「办案」）；若一个都没有，退化为「哪个目录
 * 下面的子目录最像 `日期-事项`」——这样客户把事项放在 `2-办案` 甚至
 * `案件记录` 里也能认出来。
 *
 * 只下探两层（根 → 事项源 → 事项），不递归：更深的层是事项自己的附件。
 */
export function pickServiceItems(roots: FolderEntry[], childrenOf: (subpath: string) => FolderEntry[]): ParsedItem[] {
  const folders = roots.filter((e) => !/\.[a-z0-9]{1,5}$/i.test(e.name))

  // 1) 名字里带「办案」的优先
  let sources = folders.filter((f) => looksLikeCaseFolder(f.name))

  // 2) 没有显式命名的：挑「子目录里带日期的比例最高」的那个目录
  if (sources.length === 0) {
    let best: { entry: FolderEntry; hits: number } | null = null
    for (const f of folders) {
      const kids = childrenOf(f.subpath)
      const hits = kids.filter((k) => parseDatedFolder(k.name).date !== '').length
      if (hits > 0 && (!best || hits > best.hits)) best = { entry: f, hits }
    }
    if (best) sources = [best.entry]
  }

  const out: ParsedItem[] = []
  for (const src of sources) {
    for (const kid of childrenOf(src.subpath)) {
      if (/\.[a-z0-9]{1,5}$/i.test(kid.name)) continue // 事项层的散文件不算事项
      const { date, title } = parseDatedFolder(kid.name)
      out.push({ title, date, subpath: kid.subpath, rawName: kid.name })
    }
  }

  // 有日期的按日期倒序（最近的在前），无日期的沉底按名字排
  return out.sort((a, b) => {
    if (a.date && b.date) return b.date.localeCompare(a.date)
    if (a.date) return -1
    if (b.date) return 1
    return a.title.localeCompare(b.title, 'zh')
  })
}
