/**
 * 另存为的默认文件名：`原名[修订版]V1_<今天>.docx`。
 *
 * 与审查流水线 `generate_output_filename` 同一套命名约定，律师在文件夹里
 * 一眼能分出「我手改的版本」和「客户来稿」。已带 `[修订版]` 的不再叠加，
 * 已带 `_YYYYMMDD` 的旧日期先剥掉（否则反复另存会叠成 _20260101_20261025）。
 */
export function defaultSaveAsName(name: string, today = new Date()): string {
  const ext = (name.match(/\.[^.]+$/) || ['.docx'])[0]
  let stem = name.slice(0, name.length - ext.length)
  stem = stem.replace(/_\d{8}$/, '')
  const base = stem.includes('[修订版]') ? stem : `${stem}[修订版]V1`
  const y = today.getFullYear()
  const m = String(today.getMonth() + 1).padStart(2, '0')
  const d = String(today.getDate()).padStart(2, '0')
  return `${base}_${y}${m}${d}${ext}`
}
