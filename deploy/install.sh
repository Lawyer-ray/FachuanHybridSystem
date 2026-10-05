#!/usr/bin/env bash
# 安装/更新公网栈 launchd 服务（gunicorn / qcluster / nginx）。
#
# 关键设计（macOS TCC）：launchd 后台进程读 ~/Downloads 一律 EPERM，
# 因此先构建「运行时目录」~/Library/Application Support/FachuanHybridSystem
# （不受 TCC 保护），launchd 进程读取的脚本/环境/nginx 配置/dist 副本
# 全部以该目录为准；本仓库 deploy/ 下的同名文件是源文件。
#
# 重复执行安全：先 bootout 旧实例再 bootstrap。
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNTIME="$HOME/Library/Application Support/FachuanHybridSystem"
UID_="$(id -u)"

mkdir -p "$RUNTIME/bin" "$RUNTIME/env" "$RUNTIME/nginx"

# 1) 同步运行时文件
cp "$REPO/deploy/bin/gunicorn.sh" "$RUNTIME/bin/"
cp "$REPO/deploy/bin/qcluster.sh" "$RUNTIME/bin/"
cp "$REPO/deploy/env/prod.env" "$RUNTIME/env/"
cp "$REPO/deploy/gunicorn.conf.py" "$RUNTIME/"
chmod +x "$RUNTIME/bin/"*.sh

# 2) nginx 配置模板替换 __RUNTIME__ 后落运行时目录，并先行校验
sed "s|__RUNTIME__|$RUNTIME|g" "$REPO/deploy/nginx/nginx.conf" > "$RUNTIME/nginx/nginx.conf"
cp "$REPO/deploy/nginx/django_proxy.inc" "$RUNTIME/nginx/"
/opt/homebrew/bin/nginx -t -c "$RUNTIME/nginx/nginx.conf" 1>&2

# 3) 清掉可能残留的旧实例/孤儿进程，再装载三个服务
pkill -f "nginx.*$RUNTIME/nginx/nginx.conf" 2>/dev/null || true
for svc in gunicorn qcluster nginx; do
  label="com.user.fachuan-$svc"
  src="$REPO/deploy/launchd/$label.plist"
  dst="$HOME/Library/LaunchAgents/$label.plist"
  cp "$src" "$dst"
  launchctl bootout "gui/$UID_/$label" 2>/dev/null || true
  launchctl bootstrap "gui/$UID_" "$dst"
  echo "✓ $label 已加载"
done

echo ""
echo "常用操作（详见 deploy/README.md）:"
echo "  看状态:  launchctl list | grep fachuan"
echo "  跟日志:  make prod-logs"
echo "  重启后端: make prod-restart"
