#!/bin/sh
# 大模型隐私复审（pre-commit）：正则看不见的孤立人名 / 无后缀机构名 / 门牌地址。
# 需要后端 Django 环境读 LLMProvider 表（模型配置唯一来源），所以用 backend/.venv 的 Python；
# 没有 venv 的机器（CI、新同事）直接放行——隐私正则闸门仍然生效。
PY="backend/.venv/bin/python"
if [ ! -x "$PY" ]; then
  echo "llm-privacy: 未找到 backend/.venv，跳过大模型隐私复审"
  exit 0
fi
exec "$PY" backend/devtools/security_guard.py --check llm-privacy --mode staged "$@"
