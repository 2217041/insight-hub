#!/usr/bin/env bash
# 服务器侧部署：加载预构建镜像 + 起服务（不在服务器上构建）
#
# 为什么不在服务器构建：
#   这台机器只有 1 GB 内存，`next build` 会吃 1.5 GB+，
#   实测直接把它拖到 SSH 都连不上（swap 抖动）。
#
# 用法：
#   bash deploy-images.sh /tmp/images.tar.gz

set -euo pipefail

APP_DIR="${APP_DIR:-/opt/insight-hub}"
IMAGES="${1:-/tmp/images.tar.gz}"

echo "==> 1/6 检查"
cd "$APP_DIR"
[ -f .env ] || { echo ".env 不存在，先创建"; exit 1; }
echo "    仓库：$(git log --oneline -1)"

echo "==> 2/6 加载镜像"
if [ -f "$IMAGES" ]; then
  gunzip -c "$IMAGES" | docker load
else
  echo "    没有找到 $IMAGES，假设镜像已在本地"
fi
docker images --format '{{.Repository}}:{{.Tag}} {{.Size}}' | grep insight-hub || true

echo "==> 3/6 拉取基础镜像（db / redis / nginx）"
docker compose pull db redis nginx

echo "==> 4/6 启动（--no-build，绝不触发构建）"
docker compose up -d --no-build

echo "==> 5/6 等待就绪"
for i in $(seq 1 60); do
  if curl -fsS -m 3 http://127.0.0.1/api/health >/tmp/health.json 2>/dev/null; then
    echo "    $(cat /tmp/health.json)"
    break
  fi
  sleep 3
  [ "$i" -eq 60 ] && { echo "    ⚠️ 超时"; docker compose ps; docker compose logs --tail 20 api; exit 1; }
done

echo "==> 6/6 状态"
docker compose ps
echo
echo "    内网：http://127.0.0.1/"
echo "    公网：http://<公网IP>/"