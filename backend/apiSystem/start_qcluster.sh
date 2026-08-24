#!/bin/zsh
# 启动 Django-Q cluster (8 worker, dual MinerU key)
cd /Users/huangsong21/Downloads/Coding/AI/FachuanHybridSystem/backend/apiSystem
export PYTHONPATH=/Users/huangsong21/Downloads/Coding/AI/FachuanHybridSystem/backend
export DJANGO_Q_WORKERS=8
/Users/huangsong21/Downloads/Coding/AI/FachuanHybridSystem/backend/.venv/bin/python manage.py qcluster > /tmp/qcluster.log 2>&1 &
echo $! > /tmp/qcluster.pid
echo "Django-Q cluster started (PID $!)"
