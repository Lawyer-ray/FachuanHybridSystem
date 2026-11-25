#!/bin/sh
# 大模型隐私复审（pre-commit）：正则看不见的孤立人名 / 无后缀机构名 / 门牌地址。
# 需要后端 Django 环境读 LLMProvider 表（模型配置唯一来源），所以用 backend/.venv 的 Python；
# 没有 venv 的机器（CI、新同事）直接放行——隐私正则闸门仍然生效。
#
# ## 这个包装脚本为什么还要盯着工作区
#
# pre-commit 判断「钩子有没有改文件」的方式是：跑钩子前后各做一次 git diff，
# 变了就算这个钩子改的。多个会话共用同一个 worktree 时（本仓库允许并行，见
# CLAUDE.md「每个 writer 独占一个 worktree」——不独占时就会撞上），另一个会话在
# 复审的这几秒里写文件，pre-commit 会把**别人的改动**算到本钩子头上，报
# 「files were modified by this hook」，紧接着 stash 回收冲突，提交被拒。
#
# 本脚本自己一行文件都不写（已实测：`--mode all` 跑完 `git status` 零变化）。
# 所以这里在前后各取一次工作区指纹，变化了就**明确说清不是隐私复审失败**，
# 免得下一个人去改一个没坏的钩子，或者干脆加 --no-verify 绕过门禁。
PY="backend/.venv/bin/python"
if [ ! -x "$PY" ]; then
  echo "llm-privacy: 未找到 backend/.venv，跳过大模型隐私复审"
  exit 0
fi

fingerprint() {
  git status --porcelain=v1 2>/dev/null | git hash-object --stdin 2>/dev/null
}

BEFORE=$(fingerprint)
"$PY" backend/devtools/security_guard.py --check llm-privacy --mode staged "$@"
STATUS=$?
AFTER=$(fingerprint)

if [ "$BEFORE" != "$AFTER" ]; then
  echo "llm-privacy: ⚠️ 复审期间工作区被其他进程改动（多半是另一个 AI 会话在写同一个 worktree）。"
  echo "             pre-commit 会把那次改动算到本钩子上并报「files were modified by this hook」，"
  echo "             与隐私审查无关。处置：等对方提交完再提交，或按 CLAUDE.md 各用各的 worktree。"
  echo "             不要用 --no-verify 绕过——隐私正则闸门同样会被跳过。"
fi

exit "$STATUS"
