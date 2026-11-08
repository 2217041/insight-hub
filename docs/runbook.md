# 运行手册（Runbook）

> 这份文档回答一个问题：**从关机的电脑，到览览器里看到项目，需要几步。**
> 出问题时先看这里，不要凭记忆瞎试。

---

## 0. 先理解架构：本项目运行时是「三个进程」

```
┌─────────────────────┐   ┌──────────────────┐   ┌──────────────────────┐
│  Windows 览览器      │──▶│  Next.js :3000   │──▶│  FastAPI :8000       │
│  localhost:3000     │   │  (npm run dev)   │   │  (uvicorn)           │
└─────────────────────┘   └──────────────────┘   └──────────┬───────────┘
                                                             │
                                              ┌──────────────┴────────────┐
                                              ▼                           ▼
                                   ┌────────────────────┐    ┌────────────────────┐
                                   │ PostgreSQL :5432   │    │ Redis :6379        │
                                   │ (WSL2 Ubuntu 24.04)│    │ (WSL2 Ubuntu 24.04)│
                                   └────────────────────┘    └────────────────────┘
```

- 前两个跑在 **Windows** 上，需要你手动起（或者用脚本）；
- 后两个跑在 **WSL2 的 Ubuntu** 里，登录系统后由**计划任务自动启动**。

---

## 1. 日常启动（一条命令）

```powershell
cd D:\aistudy\insight-hub
.\scripts\dev.ps1
```

它会依次做四件事：

1. 检查/启动 WSL 里的 PostgreSQL 和 Redis；
2. 开一个新窗口起 FastAPI（标题 `Insight Hub API`）；
3. 开一个新窗口起 Next.js（标题 `Insight Hub Web`）；
4. 轮询等两个服务就绪，打印健康检查结果，并打开 http://localhost:3000 。

常用参数：

| 命令 | 作用 |
|---|---|
| `.\scripts\dev.ps1` | 全量启动 + 开览览器 |
| `.\scripts\dev.ps1 -NoBrowser` | 不开览览器 |
| `.\scripts\dev.ps1 -SkipServices` | 跳过 WSL 检查（服务已在跑时更快） |

> **停止**：关掉那两个 PowerShell 窗口即可。
> 数据库会继续在后台跑（下次启动更快），要停就执行第 5 节。

---

## 2. 手动启动（脚本出问题时逐步排查）

### 2.1 数据库与缓存

```powershell
wsl -d Ubuntu-24.04 -u root -- /usr/local/bin/start-services.sh
```

期望输出：

```
postgres: /var/run/postgresql:5432 - accepting connections
redis   : PONG
```

### 2.2 后端

```powershell
cd D:\aistudy\insight-hub\apps\api
.\.venv\Scripts\python.exe -m uvicorn main:app --reload --port 8000
```

> 不要用 `uv run uvicorn`：`uv run` 需要 `pyproject.toml`，本项目用的是 `requirements.txt`。
> 也不要 `activate` 虚拟环境：PowerShell 的脚本执行策略可能拦 `Activate.ps1`，直接调 venv 里的 python 最稳。

### 2.3 前端

```powershell
cd D:\aistudy\insight-hub\apps\web
npm.cmd run dev
```

> 用 `npm.cmd` 而不是 `npm`：`npm.ps1` 会被执行策略拦。

---

## 3. 验证（做完上面，逐条打勾）

```powershell
# 1) 端口都在听
foreach ($p in 5432,6379,8000,3000) {
  "$p -> " + (Test-NetConnection 127.0.0.1 -Port $p -WarningAction SilentlyContinue).TcpTestSucceeded
}

# 2) 后端三项全绿
(Invoke-WebRequest http://127.0.0.1:8000/api/health -UseBasicParsing).Content

# 3) 前端能开
(Invoke-WebRequest http://localhost:3000 -UseBasicParsing).StatusCode
```

全绿时后端返回：

```json
{"status":"ok","db":"ok","db_detail":"pg 16.15 ... + pgvector / 3 ms",
 "redis":"ok","redis_detail":"127.0.0.1 / 0 ms","version":"0.1.0"}
```

浏览器打开 http://localhost:3000 ，点「+ 新对话」发一条消息，能看到**逐字流式回复**即全部就绪。

---

## 4. 数据库日常操作

**连接信息**（已写在 `.env.example`）：

| 项 | 值 |
|---|---|
| 连接串 | `postgresql+psycopg://insight:insight@127.0.0.1:5432/insight` |
| 用户 / 密码 | `insight` / `insight` |
| 超级用户 | `postgres` / `postgres` |
| 库名 | `insight`（已启用 pgvector 0.6.0） |

**进 psql**：

```powershell
wsl -d Ubuntu-24.04 -u root -- bash -c "PGPASSWORD=insight psql -h 127.0.0.1 -U insight -d insight"
```

**常用查询**：

```sql
\dt                                    -- 看表
SELECT * FROM pg_extension;            -- 确认 pgvector 在
SELECT version();                      -- 16.15
```

**备份 / 恢复**：

```powershell
# 备份到 D:\aistudy\backup.sql
wsl -d Ubuntu-24.04 -u root -- bash -c "PGPASSWORD=insight pg_dump -h 127.0.0.1 -U insight insight" > D:\aistudy\backup.sql

# 恢复
wsl -d Ubuntu-24.04 -u root -- bash -c "PGPASSWORD=insight psql -h 127.0.0.1 -U insight -d insight" < D:\aistudy\backup.sql
```

**Redis**：

```powershell
wsl -d Ubuntu-24.04 -u root -- redis-cli ping
wsl -d Ubuntu-24.04 -u root -- redis-cli keys '*'
wsl -d Ubuntu-24.04 -u root -- redis-cli flushdb   # 清空当前库（小心）
```

---

## 5. 停止服务

```powershell
# 只停数据库和缓存（WSL 里的）
wsl -d Ubuntu-24.04 -u root -- bash -c "service postgresql stop; service redis-server stop"

# 彻底关掉 WSL（释放内存）
wsl --shutdown
```

---

## 6. 登录自启是怎么配的

| 项 | 值 |
|---|---|
| 任务名 | `InsightHub-WSL-Services` |
| 触发 | 当前用户**登录时**，延迟 10 秒 |
| 动作 | `wscript.exe "D:\aistudy\start-wsl-services.vbs"` |
| VBS 做的事 | 再等 8 秒 → 隐藏窗口执行 `wsl ... start-services.sh` → 把返回码写进 `D:\aistudy\wsl-autostart.log` |

**为什么用 VBS 包一层**：直接用 `schtasks` 调 `wsl.exe` 会闪一个黑框；VBS 的 `Run(..., 0, True)` 可以完全隐藏窗口，同时还能等到返回码写日志。

**检查它是否正常**：

```powershell
Get-ScheduledTask -TaskName 'InsightHub-WSL-Services' | Select-Object State
Get-ScheduledTaskInfo -TaskName 'InsightHub-WSL-Services' | Select-Object LastRunTime, LastTaskResult
Get-Content D:\aistudy\wsl-autostart.log -Tail 3
```

> `LastTaskResult = 0` 且日志里 `rc=0` 才算成功。
> 注意：日志里有时间戳，**要确认那是最近一次开机的时间**，别被旧日志骗了。

**不想自启了**：

```powershell
Unregister-ScheduledTask -TaskName 'InsightHub-WSL-Services' -Confirm:$false
```

---

## 7. 换电脑 / 重装系统怎么恢复

按顺序执行（脚本都在 `D:\aistudy\`）：

1. 装 Node 22 LTS、Python、Git、uv；
2. `wsl --install` 装内核（或下载 MSI），重启；
3. 导入 Ubuntu：`wsl --import Ubuntu-24.04 D:\wsl\Ubuntu-24.04 <rootfs.tar.gz> --version 2`；
4. 跑初始化脚本：`wsl -d Ubuntu-24.04 -u root -- bash /mnt/d/aistudy/wsl-setup.sh`；
5. `git clone` 仓库，`uv venv --python 3.12 .venv && uv pip install -r requirements.txt`，`npm install`；
6. 重建计划任务（见第 6 节）。

---

## 8. 故障速查

| 现象 | 最可能的原因 | 处理 |
|---|---|---|
| 页面一直转圈/提示"后端不可达" | 8000 没起 | 看 `Insight Hub API` 窗口的报错 |
| 后端返回 `"db":"error"` | WSL 里 PG 没起 | `wsl -d Ubuntu-24.04 -u root -- service postgresql status` |
| 后端返回 `"redis":"error"` | Redis 没起 | `wsl -d Ubuntu-24.04 -u root -- redis-cli ping` |
| `端口被占用` | 上次的进程没关 | `Get-NetTCPConnection -LocalPort 8000 -State Listen` → `Stop-Process -Id <PID>` |
| `npm : 无法加载文件 npm.ps1` | PowerShell 执行策略 | 用 `npm.cmd` |
| `uvicorn: command not found` | 没走 venv | 用 `.\.venv\Scripts\python.exe -m uvicorn` |
| 开机后数据库没起来 | 计划任务失败 | 看 `D:\aistudy\wsl-autostart.log` 的 `rc=` |
| WSL 内存占用越来越大 | 正常，WSL 不主动归还 | `wsl --shutdown` 后重新启动 |
| `Error parsing package.json file` | 文件带 UTF-8 BOM，Node 的 JSON.parse 不跳过 BOM | 去掉 BOM（见下方说明），再删 `.next` 重启 dev |
| 改了 `package.json` 后页面全 500 | Turbopack 缓存了旧文件 | 删 `apps/web/.next` 后重启 `npm run dev` |

---

## 8.1 关于 package.json 的 BOM 问题

**现象**：`npm run dev` 报 `Error parsing package.json file`，指向第 1 行第 1 列，
错误信息里的 `{` 前面有个看不见的字符（`﻿{`）。

**原因**：文件被保存成了 **UTF-8 带 BOM**。Node 读文件不剥 BOM，`JSON.parse` 遇到 `\uFEFF` 直接抛错。

**什么操作会产生 BOM**：
- Windows PowerShell 5.1 的 `Set-Content -Encoding UTF8`（它的 "UTF8" 其实是带 BOM 的）；
- `Out-File -Encoding utf8`、`ConvertTo-Json | Set-Content` 等管道写法；
- 某些编辑器"另存为 UTF-8 with BOM"。

**怎么检查**：

```powershell
$b = [System.IO.File]::ReadAllBytes("apps\web\package.json")[0..2]
($b | ForEach-Object { $_.ToString("X2") }) -join " "
# 正常应以 7B 0A 20 开头（'{' + 换行）；若以 EF BB BF 开头就是带 BOM
```

**怎么修**：用编辑器另存为 "UTF-8（无 BOM）"，或：

```powershell
$p = "apps\web\package.json"
$t = [System.IO.File]::ReadAllText($p, [System.Text.UTF8Encoding]::new($false))
[System.IO.File]::WriteAllText($p, $t, [System.Text.UTF8Encoding]::new($false))
```

**改完必须删 `.next` 再重启**，否则 Turbopack 还缓存着坏文件。

> 顺带记住：`.ps1` 脚本**恰恰相反**，必须带 BOM 才不会乱码（见 `scripts/shot.ps1` 的注释）。
> 同一个编码问题，两种文件要求相反。
## 9. 改代码时的注意点

| 文件 | 改完要做什么 |
|---|---|
| `apps/api/main.py` | 不用重启，`--reload` 会自动加载 |
| `apps/web/app/*.tsx` | 不用重启，热更新 |
| `apps/api/requirements.txt` | `uv pip install -r requirements.txt` |
| `apps/web/package.json` | `npm install` |
| `scripts/*.ps1` | 注意存成 **UTF-8 带 BOM**，否则 PowerShell 5.1 中文乱码报错 |