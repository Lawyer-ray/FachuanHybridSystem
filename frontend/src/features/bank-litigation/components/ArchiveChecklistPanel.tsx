/**
 * OA 归档 · 归档检查清单
 *
 * ═══ 口径来源 ═══
 * 结构与条目**照搬后端 Django admin 的合同归档**
 * （`contracts/templates/admin/contracts/contract/partials/finalized_materials.html`
 * 的「归档检查清单」区块 + `services/archive/constants.py` 的 LITIGATION_CHECKLIST）。
 *
 * 为什么必须照搬而不是自创：归档清单是**律师协会/司法局的执业规范**，
 * 20 项诉讼归档材料、哪些必需、哪些由模板生成，都是既定项。
 * 前端自拟一套会让律师在 admin 和前端看到两份不同的清单，
 * 归档时不知道该按哪个补。
 *
 * ═══ 与 admin 的差异（有意为之） ═══
 * admin 是 Alpine.js 全功能页（拖拽排序、上传、从案件材料同步、学习分类规则…），
 * 这里只做**只读呈现 + 生成归档文件夹**这一个动作：
 * 前端这一页的定位是「看还差什么、一键生成」，重管理动作仍在 admin。
 * 所以界面保留清单结构、进度、必需项标记，去掉编辑能力。
 */

import { useMemo, useState } from 'react'
import { AlertTriangle, Check, Circle, FileText, FolderOpen } from 'lucide-react'

import { cn } from '@/lib/utils'

import { ActionButton, InsetBlock, Pill, RailSection, SectionTitle, StatTile, WorkCard } from './ui'
import {
  DEMO_ARCHIVE_CATEGORIES,
  DEMO_ARCHIVE_LOG,
  DEMO_ARCHIVE_MATERIALS,
} from './demo-data'

/** 归档清单项（与后端 ChecklistItem 同构，省略前端用不到的字段） */
interface ArchiveItem {
  code: string
  name: string
  /** 是否必需项（缺了无法归档） */
  required: boolean
  /** 材料从哪来：模板生成 / 合同文件夹 / 案件材料 / 手工上传 */
  source: 'template' | 'contract' | 'case' | 'manual'
  /** 是否已就位 */
  done: boolean
  /** 已就位的文件名（展示用） */
  file?: string
}

/**
 * 诉讼类归档清单（20 项）。
 *
 * 顺序与名称严格对齐 `apps/contracts/services/archive/constants.py`
 * 的 `LITIGATION_CHECKLIST`。这份常量在前端留一份只读副本是**有代价的**
 * （后端改动要同步），但比让前端猜「有哪些项」要好：
 * 清单是执业规范，变更频率极低，而猜错会导致归档缺项。
 */
const LITIGATION_CHECKLIST: Omit<ArchiveItem, 'done' | 'file'>[] = [
  { code: 'lt_1', name: '案卷封面', required: true, source: 'template' },
  { code: 'lt_2', name: '结案归档登记表', required: true, source: 'template' },
  { code: 'lt_3', name: '案卷目录', required: true, source: 'template' },
  { code: 'lt_4', name: '委托合同、风险告知书', required: true, source: 'contract' },
  { code: 'lt_5', name: '收费凭证', required: false, source: 'contract' },
  { code: 'lt_6', name: '律师办案工作日记', required: true, source: 'template' },
  { code: 'lt_7', name: '起诉书、上诉书或答辩书', required: true, source: 'case' },
  { code: 'lt_8', name: '阅卷笔录', required: false, source: 'case' },
  { code: 'lt_9', name: '会见当事人谈话笔录', required: false, source: 'case' },
  { code: 'lt_10', name: '调查材料等案件关联材料', required: false, source: 'case' },
  { code: 'lt_11', name: '诉讼保全申请书、证据保全申请书、先行给付申请书和法院裁定书', required: false, source: 'case' },
  { code: 'lt_12', name: '承办律师代理意见', required: false, source: 'case' },
  { code: 'lt_13', name: '集体讨论记录', required: false, source: 'case' },
  { code: 'lt_14', name: '出庭通知书', required: false, source: 'case' },
  { code: 'lt_15', name: '代理词', required: false, source: 'case' },
  { code: 'lt_16', name: '庭审笔录', required: false, source: 'case' },
  { code: 'lt_17', name: '判决书、裁定书、调解书、上诉书', required: true, source: 'case' },
  { code: 'lt_18', name: '办案服务质量监督卡', required: true, source: 'template' },
  { code: 'lt_19', name: '办案小结', required: true, source: 'template' },
  { code: 'lt_20', name: '授权委托证明材料', required: true, source: 'contract' },
]

/** 材料来源 → 展示名 */
const SOURCE_LABEL: Record<ArchiveItem['source'], string> = {
  template: '模板生成',
  contract: '合同文件夹',
  case: '案件材料',
  manual: '手工上传',
}

/**
 * 演示态：已就位的前 9 项。
 *
 * ⚠️ 真实实现应来自后端 `build_archive_checklist_service()` 的结果；
 * 这里先按「模板类 + 合同类 + 部分案件材料已齐」造一份，等后端提供
 * 只读清单接口后替换这一处即可（结构已按后端 ChecklistItem 对齐）。
 */
const DEMO_DONE: Record<string, string> = {
  lt_1: '案卷封面.pdf',
  lt_2: '结案归档登记表.pdf',
  lt_3: '案卷目录.pdf',
  lt_4: '委托代理合同（扫描件）.pdf',
  lt_6: '律师办案工作日记.pdf',
  lt_7: '民事起诉状（定稿）.pdf',
  lt_17: '（20XX）粤0606民初XXXX号 民事判决书.pdf',
  lt_18: '办案服务质量监督卡.pdf',
  lt_19: '办案小结.pdf',
  lt_20: '授权委托书（扫描件）.pdf',
}

export function OAArchivePanel() {
  const [showOnlyMissing, setShowOnlyMissing] = useState(false)

  const items = useMemo<ArchiveItem[]>(
    () => LITIGATION_CHECKLIST.map((it) => ({ ...it, done: Boolean(DEMO_DONE[it.code]), file: DEMO_DONE[it.code] })),
    [],
  )

  const doneCount = items.filter((i) => i.done).length
  const total = items.length
  const requiredItems = items.filter((i) => i.required)
  const requiredDone = requiredItems.filter((i) => i.done).length
  const missingRequired = requiredItems.filter((i) => !i.done).length
  const pct = Math.round((doneCount / total) * 100)
  const visible = showOnlyMissing ? items.filter((i) => !i.done) : items
  /** 已入卷材料的总页数：律师交卷前会核对纸质卷宗厚度，页数是最快的对账方式 */
  const donePages = items.reduce((s, i) => (i.done ? s + (DEMO_ARCHIVE_MATERIALS[i.code]?.pages ?? 0) : s), 0)
  const failedLogs = DEMO_ARCHIVE_LOG.filter((l) => !l.ok).length

  return (
    <div className="flex flex-col gap-3.5">
      {/* ══ 顶部统计 ══ */}
      <div className="grid grid-cols-2 gap-3 min-[900px]:grid-cols-4">
        <StatTile label="归档进度" value={`${doneCount}/${total}`} tone={missingRequired ? 'yellow' : 'green'} />
        <StatTile
          label="必需项"
          value={`${requiredDone}/${requiredItems.length}`}
          tone={missingRequired ? 'red' : 'green'}
          hint={missingRequired ? `还差 ${missingRequired} 项` : '已齐'}
        />
        <StatTile label="归档类别" value="诉讼" hint="20 项检查清单" />
        <StatTile label="编写进度" value={`${pct}%`} hint={`已入卷 ${donePages} 页`} />
      </div>

      {/* ══ 进度条 + 动作 ══ */}
      <WorkCard>
        <div className="flex flex-wrap items-center gap-3">
          <div className="min-w-0 flex-1">
            <div className="flex items-baseline gap-2">
              <span className="text-[13px] font-[620]">归档检查清单</span>
              <Pill tone="blue">诉讼 · 20 项</Pill>
            </div>
            <div className="mt-2 flex items-center gap-2.5">
              <div className="h-[6px] min-w-0 flex-1 overflow-hidden rounded-full bg-secondary">
                <div
                  className={cn(
                    'h-full rounded-full transition-[width] duration-500',
                    missingRequired ? 'bg-status-yellow' : 'bg-status-green',
                  )}
                  style={{ width: `${pct}%` }}
                />
              </div>
              <span className="flex-none text-[11.5px] tabular-nums text-muted-foreground">
                {doneCount}/{total}
                {missingRequired ? (
                  <span className="ml-1.5 text-status-red">必需 缺 {missingRequired}</span>
                ) : null}
              </span>
            </div>
          </div>

          <div className="flex flex-none items-center gap-2">
            <ActionButton
              sm
              title={missingRequired ? `还有 ${missingRequired} 项必需材料未齐` : '在合同绑定文件夹下生成'}
              disabled={missingRequired > 0}
            >
              <FolderOpen className="size-3.5" /> 生成归档文件夹
            </ActionButton>
            <ActionButton sm onClick={() => setShowOnlyMissing((v) => !v)}>
              {showOnlyMissing ? '显示全部' : '只看缺项'}
            </ActionButton>
          </div>
        </div>
      </WorkCard>

      {/* ══ 清单 ══ */}
      <WorkCard padded={false}>
        <div className="flex items-center gap-2 border-b border-border px-5 py-3">
          <SectionTitle
            title="归档材料"
            hint={showOnlyMissing ? `只看缺项 · ${visible.length} 项` : '按执业规范顺序排列'}
            className="w-full"
          />
        </div>

        <ul className="divide-y divide-border/60">
          {visible.map((it) => {
            const meta = DEMO_ARCHIVE_MATERIALS[it.code]
            return (
              <li key={it.code} className="flex items-start gap-3 px-5 py-2.5">
                {/* 状态点：已就位=绿勾，缺=空心圈 */}
                {it.done ? (
                  <span className="mt-[3px] grid size-4 flex-none place-items-center rounded-full bg-status-green">
                    <Check className="size-2.5 text-white" strokeWidth={3.5} />
                  </span>
                ) : it.required ? (
                  <span className="mt-[3px] grid size-4 flex-none place-items-center rounded-full border border-status-red/50">
                    <span className="size-1.5 rounded-full bg-status-red/70" />
                  </span>
                ) : (
                  <Circle className="mt-[3px] size-4 flex-none text-border" strokeWidth={1.5} />
                )}

                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
                    <span
                      className={cn(
                        'text-[12.5px] leading-[1.5]',
                        it.done ? 'text-foreground' : it.required ? 'font-medium text-foreground' : 'text-secondary-foreground',
                      )}
                    >
                      {it.name}
                    </span>
                    {it.required ? (
                      <span className="text-[9.5px] font-semibold text-status-red">必需</span>
                    ) : null}
                  </div>
                  <div className="mt-0.5 flex items-center gap-1.5 text-[10.5px] text-muted-foreground">
                    <span className="rounded-[3px] bg-secondary px-1 py-[1px]">{SOURCE_LABEL[it.source]}</span>
                    {it.done && it.file ? (
                      <span className="flex min-w-0 items-center gap-1">
                        <FileText className="size-2.5 flex-none" />
                        <span className="truncate" title={it.file}>
                          {it.file}
                        </span>
                      </span>
                    ) : (
                      <span className={it.required ? 'text-status-red' : ''}>
                        {it.required ? '缺失，归档前必须补齐' : '未归档（非必需）'}
                      </span>
                    )}
                  </div>
                </div>

                {/* 材料台账：页数 / 上传时间 / 来源文件 —— 律师核对纸质卷宗时按这三列对 */}
                <div className="hidden w-[300px] flex-none items-center gap-2 text-[10.5px] text-muted-foreground min-[1100px]:flex">
                  <span className="w-[44px] flex-none text-right tabular-nums">{meta ? `${meta.pages} 页` : '—'}</span>
                  <span className="w-[68px] flex-none text-right tabular-nums">{meta ? meta.at : '未上传'}</span>
                  <span className="min-w-0 flex-1 truncate" title={meta?.source ?? ''}>
                    {meta ? meta.source : '—'}
                  </span>
                </div>

                <div className="flex-none">
                  <Pill tone={it.done ? 'green' : it.required ? 'red' : 'neutral'}>
                    {it.done ? '已归档' : it.required ? '缺件' : '待补'}
                  </Pill>
                </div>
              </li>
            )
          })}
        </ul>

        {visible.length === 0 ? (
          <div className="px-5 py-10 text-center text-[12px] text-muted-foreground">
            全部 {total} 项已归档，可以生成归档文件夹。
          </div>
        ) : null}
      </WorkCard>

      {/* ══ 阻断说明 ══ */}
      {missingRequired > 0 ? (
        <WorkCard className="border-status-yellow/40 bg-status-yellow-bg/40">
          <div className="flex items-start gap-2.5">
            <AlertTriangle className="mt-[1px] size-3.5 flex-none text-status-yellow" />
            <div className="min-w-0">
              <div className="text-[12px] font-medium">还有 {missingRequired} 项必需材料未齐</div>
              <p className="mt-1 text-[11px] leading-[1.65] text-muted-foreground">
                必需项缺件时无法生成归档文件夹 —— 归档卷宗会被律协/司法局检查，
                缺项属于执业规范问题，不是可选优化。非必需项可以先归档后补。
              </p>
            </div>
          </div>
        </WorkCard>
      ) : null}

      {/* ══ 归档操作日志 ══ */}
      <WorkCard padded={false}>
        <div className="border-b border-border-light px-5 py-3">
          <SectionTitle
            title="归档操作日志"
            hint={`最近 ${DEMO_ARCHIVE_LOG.length} 次 · 其中 ${failedLogs} 次未成功`}
          />
        </div>
        <div className="grid grid-cols-[74px_88px_minmax(0,1fr)_56px_64px] gap-2 border-b border-border-light px-5 py-1.5 text-[10px] text-muted-foreground">
          <span>时间</span>
          <span>动作</span>
          <span>对象</span>
          <span>操作人</span>
          <span className="text-right">结果</span>
        </div>
        <ul className="divide-y divide-border-light">
          {DEMO_ARCHIVE_LOG.map((l) => (
            <li
              key={`${l.at}-${l.action}`}
              className="grid grid-cols-[74px_88px_minmax(0,1fr)_56px_64px] items-center gap-2 px-5 py-[7px] text-[11px]"
            >
              <span className="tabular-nums text-muted-foreground">{l.at}</span>
              <span className="text-secondary-foreground">{l.action}</span>
              <span className="min-w-0">
                <span className="block truncate" title={l.target}>
                  {l.target}
                </span>
                {!l.ok ? (
                  <span className="block truncate text-[10px] text-status-red" title={l.note}>
                    {l.note}
                  </span>
                ) : null}
              </span>
              <span className="text-muted-foreground">{l.by}</span>
              <span className="text-right">
                <Pill tone={l.ok ? 'green' : 'red'}>{l.ok ? '成功' : '失败'}</Pill>
              </span>
            </li>
          ))}
        </ul>
      </WorkCard>

      {/* ══ 类别对比 + 归档口径说明：一卡两段 ══ */}
      <WorkCard padded={false}>
        <RailSection
          title="归档类别对比"
          action={<span className="text-[10.5px] text-muted-foreground">清单项数随类别变，别混用</span>}
        >
          <div className="grid grid-cols-[56px_64px_64px_64px_minmax(0,1fr)] gap-2 border-b border-border-light pb-1 text-[10px] text-muted-foreground">
            <span>类别</span>
            <span className="text-right">清单项</span>
            <span className="text-right">必需项</span>
            <span className="text-right">已归档</span>
            <span>该类特有材料</span>
          </div>
          <ul className="divide-y divide-border-light">
            {DEMO_ARCHIVE_CATEGORIES.map((c) => (
              <li
                key={c.category}
                className="grid grid-cols-[56px_64px_64px_64px_minmax(0,1fr)] items-center gap-2 py-[7px] text-[11.5px]"
              >
                <span className="flex items-center gap-1.5">
                  <span className={cn('size-1.5 rounded-full', c.category === '诉讼' ? 'bg-status-blue' : 'bg-border')} />
                  {c.category}
                </span>
                <span className="text-right tabular-nums">{c.items} 项</span>
                <span className="text-right tabular-nums text-status-red">{c.required} 项</span>
                <span className="text-right tabular-nums text-muted-foreground">{c.archived} 卷</span>
                <span className="min-w-0 truncate text-[11px] text-muted-foreground" title={c.only}>
                  {c.only}
                </span>
              </li>
            ))}
          </ul>
        </RailSection>

        <RailSection title="归档口径">
          <InsetBlock>
            <p className="text-[11px] leading-[1.7] text-secondary-foreground">
              类别决定清单：诉讼按 20 项执业规范清单，非诉 12 项、刑事 18 项各有独立清单，
              <b className="font-medium">不能拿诉讼清单去归档非诉卷</b>，否则检查时会被认定缺项。
              清单项数与后端 `services/archive/constants.py` 保持一致，前端只读呈现。
            </p>
          </InsetBlock>
          <div className="mt-2 flex flex-wrap items-center gap-1.5 text-[10.5px] text-muted-foreground">
            <span>本卷已入卷 {donePages} 页</span>
            <span className="text-border">·</span>
            <span>材料来源：模板生成 {items.filter((i) => i.source === 'template').length} 项</span>
            <span className="text-border">·</span>
            <span>合同文件夹 {items.filter((i) => i.source === 'contract').length} 项</span>
            <span className="text-border">·</span>
            <span>案件材料 {items.filter((i) => i.source === 'case').length} 项</span>
          </div>
        </RailSection>
      </WorkCard>
    </div>
  )
}
