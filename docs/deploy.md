# 部署指南（W6）

> 目标：在一台干净的 Linux 服务器上，用 `docker compose` 把整套服务跑起来。

---

## 一、架构

```
                 ┌──────────────┐
   公网 :80  ───▶│    nginx     │
                 └──┬────────┬──┘
          /api/*    │        │    /*
                    ▼        ▼
              ┌─────────┐  ┌─────────┐
              │   api   │  │   web   │   (Next.js, 仅内网)
              │ :8000   │  │ :3000   │
              └────┬────┘  └─────────┘
                   │
        ┌──────────┴──────────┐
        ▼                     ▼
   ┌─────────┐          ┌──────────┐
   │   db    │          │  redis   │
   │pgvector │          │          │
   └─────────┘          └────┬─────┘
                             ▲
                       ┌─────┴─────┐
                       │  worker   │  (复用 api 镜像，换 command)
                       └───────────┘
```

**只有 nginx 暴露端口**，db/redis/api/web 都在 compose 内网里。

---

## 二、服务器准备

| 项 | 建议 |
|---|---|
| 规格 | 2 核 4 G（学生机/轻量应用服务器，¥10–30/月） |
| 系统 | Ubuntu 24.04 LTS |
| 安全组 | 放行 22（改端口更安全）、80；**5432 / 6379 绝不开公网** |
| 登录 | 只用 SSH 密钥，禁用密码登录 |

```bash
# 装 Docker + compose 插件
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER    # 重新登录生效
docker compose version
```

> 国内服务器拉镜像慢时，可配镜像加速器（阿里云/腾讯云控制台可拿专属地址），
> 写进 `/etc/docker/daemon.json` 的 `registry-mirrors`。

---

## 三、部署

```bash
git clone <你的仓库地址> insight-hub && cd insight-hub

# 1. 配置环境变量（JWT_SECRET 必须换）
cp .env.example .env
sed -i "s/^JWT_SECRET=$/JWT_SECRET=$(openssl rand -hex 32)/" .env
cat .env

# 2. 起服务（首次会构建镜像，约 5–10 分钟）
docker compose up -d --build

# 3. 看状态
docker compose ps
docker compose logs -f api
```

**迁移是自动的**：`api` 容器的启动命令是 `alembic upgrade head && uvicorn ...`，
保证表结构永远先于服务就绪。Alembic 升级幂等，重复执行安全。

验证：

```bash
curl -s http://127.0.0.1/api/health
# {"status":"ok","db":"ok","redis":"ok","version":"0.5.0"}
```

浏览器打开 `http://<服务器IP>/` 应该看到登录页。

---

## 四、日常运维

| 操作 | 命令 |
|---|---|
| 看日志 | `docker compose logs -f api` / `-f worker` |
| 重启单个服务 | `docker compose restart api` |
| 更新代码 | `git pull && docker compose up -d --build` |
| 停服务 | `docker compose down`（保留数据卷） |
| **清库重来** | `docker compose down -v`（**数据全丢**） |
| 备份数据库 | `docker compose exec db pg_dump -U insight insight > backup.sql` |
| 恢复 | `cat backup.sql \| docker compose exec -T db psql -U insight insight` |
| 进容器 | `docker compose exec api bash` |

---

## 五、上线检查清单

- [ ] `.env` 里的 `JWT_SECRET` 是随机生成的，不是默认值
- [ ] `POSTGRES_PASSWORD` 改过，且 5432 没有映射到宿主机
- [ ] `curl /api/health` 返回 `ok`
- [ ] 注册 → 登录 → 发消息 → 刷新页面，历史还在
- [ ] 上传一个 .md，进度从 pending 走到 ready
- [ ] **SSE 是逐段输出**（如果变成一次性蹦出来，是 Nginx 缓冲没关）
- [ ] 重启容器后数据还在（数据卷挂对了）
- [ ] `docker compose down && up -d` 后服务能自动恢复

---

## 六、踩过的坑（都在这周真实发生过）

| 坑 | 现象 | 解决 |
|---|---|---|
| **迁移没建 pgvector 扩展** | 全新库上 `type "vector" does not exist`，api 容器无限重启 | 迁移开头加 `CREATE EXTENSION IF NOT EXISTS vector` |
| 依赖没进 requirements | 重建环境后 `alembic` 找不到 | 手动装过的包必须回写依赖清单 |
| 前端请求地址写死 | 容器里 `localhost:8000` 指向容器自己 | `NEXT_PUBLIC_API_BASE=""` + Nginx 反代同源 `/api` |
| SSE 被缓冲 | 流式变一次性输出 | `proxy_buffering off` + `X-Accel-Buffering: no` |
| 裸 `depends_on` | api 先于 db 就绪，迁移连接失败 | `condition: service_healthy` |

---

## 七、HTTPS（可选）

有域名的话，用 certbot 申请证书：

```bash
sudo apt install -y certbot
sudo certbot certonly --standalone -d your-domain.com
```

然后把证书挂进 nginx 容器，并在 `docker/nginx.conf` 加 443 的 server 块（80 段加 301 跳转）。

**没有域名也能用**：直接用 `http://<IP>/`，只是没有 HTTPS。
ICP 备案要求只针对域名，IP 访问不需要——所以先用 IP 验证功能是可行的。