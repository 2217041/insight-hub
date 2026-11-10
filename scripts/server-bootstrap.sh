#!/usr/bin/env bash
# 服务器一键初始化：装 Docker、拉代码、配置环境、启动服务
#
# 用法（在服务器上以 root 执行）：
#   curl -fsSL https://raw.githubusercontent.com/2217041/insight-hub/main/scripts/server-bootstrap.sh -o bootstrap.sh
#   bash bootstrap.sh
#
# 或者仓库已经在服务器上：
#   sudo bash scripts/server-bootstrap.sh

set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/2217041/insight-hub.git}"
TARGET_DIR="${TARGET_DIR:-/opt/insight-hub}"

echo "==> 1/6 系统检查"
if [ "$(id -u)" -ne 0 ]; then
  echo "请用 root 或 sudo 运行"
  exit 1
fi
. /etc/os-release
echo "    $PRETTY_NAME"

echo "==> 2/6 安装 Docker 与 compose 插件"
if ! command -v docker >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com | sh
else
  echo "    Docker 已安装：$(docker --version)"
fi
apt-get install -y -qq docker-compose-v2 >/dev/null 2>&1 || true
docker compose version

echo "==> 3/6 拉取代码到 $TARGET_DIR"
if [ -d "$TARGET_DIR/.git" ]; then
  cd "$TARGET_DIR" && git pull --ff-only
else
  git clone --depth 1 "$REPO_URL" "$TARGET_DIR"
  cd "$TARGET_DIR"
fi

echo "==> 4/6 生成 .env（JWT_SECRET 随机 64 位）"
if [ ! -f .env ]; then
  PG_PASS="$(openssl rand -hex 12)"
  cat > .env <<EOF
POSTGRES_USER=insight
POSTGRES_PASSWORD=${PG_PASS}
POSTGRES_DB=insight
JWT_SECRET=$(openssl rand -hex 32)
EOF
  chmod 600 .env
  echo "    已生成 .env（数据库密码与 JWT 密钥均为随机值）"
else
  echo "    .env 已存在，跳过"
fi

echo "==> 5/6 构建并启动（首次约 5–10 分钟）"
# 2 核 4 G 的机器在 next build 时容易 OOM，先确保有 swap
if [ ! -f /swapfile ]; then
  fallocate -l 2G /swapfile 2>/dev/null || dd if=/dev/zero of=/swapfile bs=1M count=2048
  chmod 600 /swapfile && mkswap /swapfile >/dev/null && swapon /swapfile
  echo "    已创建 2G swap"
fi
docker compose up -d --build

echo "==> 6/6 等待就绪"
for i in $(seq 1 40); do
  if curl -fsS http://127.0.0.1/api/health >/tmp/health.json 2>/dev/null; then
    echo "    健康检查通过：$(cat /tmp/health.json)"
    break
  fi
  sleep 3
  [ "$i" -eq 40 ] && { echo "    ⚠️  超时，请查看：docker compose logs api"; exit 1; }
done

echo
echo "==> 完成"
echo "    本机访问：http://127.0.0.1/"
echo "    公网访问：http://<服务器公网IP>/   （需要在云控制台放行 80 端口）"
echo "    查看日志：cd $TARGET_DIR && docker compose logs -f api"
echo "    运维命令：见 docs/deploy.md"