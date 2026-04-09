/**
 * 将当事人信息格式化为可复制的纯文本
 */

import type { Client } from '../types'

function getGenderFromIdNumber(idNumber: string | null): string | null {
  if (!idNumber || idNumber.length !== 18) return null
  const genderDigit = parseInt(idNumber[16], 10)
  if (isNaN(genderDigit)) return null
  return genderDigit % 2 === 1 ? '男' : '女'
}

export function formatClientText(client: Client): string {
  const isNatural = client.client_type === 'natural'
  const lines: string[] = []

  if (isNatural) {
    const gender = getGenderFromIdNumber(client.id_number)
    lines.push(`姓名：${client.name}${gender ? `，${gender}` : ''}`)
  } else {
    lines.push(`名称：${client.name}`)
  }

  if (client.id_number) {
    const label = isNatural ? '身份证号' : '统一社会信用代码'
    lines.push(`${label}：${client.id_number}`)
  }
  if (client.phone) lines.push(`手机号：${client.phone}`)
  if (client.address) lines.push(`地址：${client.address}`)
  if (!isNatural && client.legal_representative) {
    const label = client.client_type === 'non_legal_org' ? '负责人' : '法定代表人'
    lines.push(`${label}：${client.legal_representative}`)
  }
  return lines.join('\n')
}
