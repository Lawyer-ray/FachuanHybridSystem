/**
 * 发票自动归属到收款的纯决策逻辑（组件只管调接口与提示）。
 *
 * 背景：律师的真实诉求是「这笔钱收到了、票也开好了，两件事本来就是一件事」。
 * 合同只有一笔收款时（本案绝大多数情况），让他在弹窗里对着一张票再点一次
 * 「关联」是多余的——直接挂进去，开票金额当场就对上了。
 *
 * 边界（守住「不可错挂」）：
 * - **只有一笔收款**才自动挂：多笔收款时哪张票算哪笔是业务判断，不猜；
 * - **票必须是待归属状态**（`payment_id == null`）且属于同一合同，后端也再校验一次；
 * - 一张票挂错要能救回来 —— 见 `groupsForReview`（按收款呈现，可解绑重挂）。
 */

/** 自动归属判定所需的最小发票形状（与 `PaymentInvoice` 结构兼容） */
export interface PoolInvoice {
  id: number
  payment_id: number | null
  total_amount: string | null
}

/** 自动归属判定所需的最小收款形状 */
export interface PaymentTarget {
  id: number
  amount: string
}

/** 金额串 → number（容忍千分位、¥ 前缀、空白；识别不出返 null） */
export function amountOf(raw: string | null | undefined): number | null {
  if (raw == null) return null
  const cleaned = String(raw).replace(/[¥￥,\s，]/g, '')
  if (!cleaned) return null
  const n = Number(cleaned)
  return Number.isFinite(n) ? n : null
}

/**
 * 记收款保存后，哪些待归属的票应当直接挂到这笔新收款？
 *
 * 只做一件事：合同下**唯一一笔**收款时，把池里所有待归属的票挂给它。
 * （新建的收款成为唯一一笔，说明此前合同下没有别的收款；反过来如果发现
 * 支付列表里不止一笔，就整批交还给人点。）
 */
export function autoAttachTarget(payments: PaymentTarget[], pool: PoolInvoice[]): number | null {
  const pending = pool.filter((inv) => inv.payment_id == null)
  if (pending.length === 0) return null
  const ids = [...new Set(payments.map((p) => p.id))]
  if (ids.length !== 1) return null
  return ids[0] ?? null
}

/** 归属结果：金额吻合自动挂 vs 金额不同的（可能还有别的收款要收） */
export interface AttachOutcome {
  attached: PoolInvoice[]
  amountMismatch: PoolInvoice[]
}

/**
 * 拆分归属结果，供提示文案用。
 * 金额吻合 → 「已自动关联」；金额不同 → 「也一起挂给这笔」，律师自己看得见能改。
 */
export function splitByAmountMatch(attached: PoolInvoice[], paymentAmount: number | null): AttachOutcome {
  if (paymentAmount == null) return { attached, amountMismatch: [] }
  const same: PoolInvoice[] = []
  const diff: PoolInvoice[] = []
  for (const inv of attached) {
    const amt = amountOf(inv.total_amount)
    if (amt != null && Math.abs(amt - paymentAmount) < 0.005) same.push(inv)
    else diff.push(inv)
  }
  return { attached: same, amountMismatch: diff }
}

/** 一张票在「按收款分组」视图里的归属描述 */
export interface InvoiceGroup {
  /** 收款 id；null = 还没归属任何收款 */
  paymentId: number | null
  invoices: PoolInvoice[]
}

/**
 * 把合同发票按收款分组（金额最大的那笔在最前，未归属的单独一组放最后）。
 *
 * 用途：归属挂错时律师要能看见「这张票挂在哪笔钱下面」，并且当场解绑重挂。
 * 未归属组放在最后是因为它是「待处理」，不是「已完成」。
 */
export function groupsForReview(invoices: PoolInvoice[], payments: PaymentTarget[]): InvoiceGroup[] {
  const byPayment = new Map<number, PoolInvoice[]>()
  const unlinked: PoolInvoice[] = []
  for (const inv of invoices) {
    if (inv.payment_id == null) {
      unlinked.push(inv)
      continue
    }
    const bucket = byPayment.get(inv.payment_id)
    if (bucket) bucket.push(inv)
    else byPayment.set(inv.payment_id, [inv])
  }

  const groups: InvoiceGroup[] = [...byPayment.entries()]
    .map(([paymentId, list]) => ({ paymentId, invoices: list }))
    .sort((a, b) => {
      const aAmt = amountOf(payments.find((p) => p.id === a.paymentId)?.amount)
      const bAmt = amountOf(payments.find((p) => p.id === b.paymentId)?.amount)
      return (bAmt ?? 0) - (aAmt ?? 0)
    })

  if (unlinked.length) groups.push({ paymentId: null, invoices: unlinked })
  return groups
}
