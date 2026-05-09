/** 法律文本渲染 — 将案号、法条引用、金额高亮显示 */

import React, { useMemo } from 'react'
import { Hash } from 'lucide-react'
import { findLegalReferences, getCaseNumberInfo, getLawArticleInfo } from '../utils/legal-text'

export function LegalText({ text }: { text: string }) {
  const matches = useMemo(() => findLegalReferences(text), [text])
  if (matches.length === 0) return <>{text}</>

  const parts: React.ReactNode[] = []
  let lastIndex = 0

  for (const match of matches) {
    if (match.index > lastIndex) {
      parts.push(text.slice(lastIndex, match.index))
    }

    if (match.type === 'case_number') {
      const info = getCaseNumberInfo(match.text)
      parts.push(
        <span
          key={match.index}
          className="inline-flex items-center gap-0.5 rounded bg-blue-50 px-1 py-0.5 text-[11px] font-medium text-blue-700 dark:bg-blue-950/40 dark:text-blue-300 cursor-default"
          title={`${info.year}年 ${info.court} ${info.number}`}
        >
          <Hash className="size-2.5 inline" />
          {match.text}
        </span>,
      )
    } else if (match.type === 'law_article') {
      const info = getLawArticleInfo(match.text)
      parts.push(
        <span
          key={match.index}
          className="inline-flex items-center gap-0.5 rounded bg-amber-50 px-1 py-0.5 text-[11px] font-medium text-amber-700 dark:bg-amber-950/40 dark:text-amber-300 cursor-default"
          title={`${info.lawName} · ${info.article}`}
        >
          {match.text}
        </span>,
      )
    } else if (match.type === 'money') {
      parts.push(
        <span
          key={match.index}
          className="inline font-medium text-emerald-700 dark:text-emerald-400"
        >
          {match.text}
        </span>,
      )
    }

    lastIndex = match.index + match.length
  }

  if (lastIndex < text.length) {
    parts.push(text.slice(lastIndex))
  }

  return <>{parts}</>
}
