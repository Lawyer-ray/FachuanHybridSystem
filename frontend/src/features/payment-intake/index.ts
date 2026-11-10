/**
 * 到账待认领（Payment Intake）的对外出口。
 *
 * 其它 feature / app 层只从这里引，不穿透内部目录。
 * 首页（features/home）单向引用本出口的 PendingIntakeCard；
 * 本 feature 不得反向 import features/home 的内部文件。
 */
export { PendingIntakeCard } from './components/PendingIntakeCard'
export type { Intake, IntakeCandidate, SelectableContract, ExcludedHint } from './types'
export { INTAKE_PENDING_KEY, INTAKE_COUNT_KEY } from './api'
