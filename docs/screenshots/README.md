# 截图存档

> 目的：把每个里程碑的**可验证证据**留档。简历、答辩、面试投屏、复盘全靠它。
> 事后补是补不出来的——W1 就养成习惯。

## 1. 目录与命名

```
docs/screenshots/
├─ w1/                    # 按里程碑分目录
│  ├─ 01-home-health.png  # 序号-内容，两位数字，便于排序
│  ├─ 02-api-docs.png
│  └─ 03-start-services.png
├─ w13/                   # RAG 达标时的评测报告、检索对比
├─ w17/                   # Agent 轨迹
└─ w20/                   # 压测曲线、成本看板
```

命名规则：`NN-用途.png`（小写、短横线分隔、不要中文名——避免跨平台路径问题）。
**图里必须能看出"是什么时候、什么状态"**，最好带上时间戳或版本号。

## 2. 三种获取方式

### 方式 A：网页截图（推荐，可重复、尺寸统一）

```powershell
# 首页
.\scripts\shot.ps1 -Url http://localhost:3000 -Out docs/screenshots/w1/01-home-health.png -Width 1100 -Height 760

# API 文档
.\scripts\shot.ps1 -Url http://127.0.0.1:8000/docs -Out docs/screenshots/w1/02-api-docs.png -Height 1000
```

原理是用无头 Chrome 渲染后截图，**适合做版本对比**（每次改动都跑一遍同名脚本，尺寸一致便于贴到报告里）。

> 前提：页面能访问。若脚本报"文件未生成"，先确认服务在跑。

### 方式 B：手动截图（终端、弹窗、交互过程）

| 快捷键 | 作用 | 说明 |
|---|---|---|
| `Win + Shift + S` | 区域截图 | 最常用，截完进剪贴板，再粘贴保存 |
| `Win + PrtScn` | 全屏存文件 | 自动存到 `图片\屏幕截图` |
| `Alt + PrtScn` | 当前窗口 | 截终端/对话框很方便 |

保存到对应目录后统一改名。

### 方式 C：终端输出——别截图，存文本

终端里的文字**复制成文本文档更好**：可搜索、可 diff、不糊。

```powershell
mkdir docs\logs -Force
wsl -d Ubuntu-24.04 -u root -- /usr/local/bin/start-services.sh *> docs\logs\w1-start-services.txt
```

确实需要图（比如要给非技术的人看）再截。

## 3. 动图与录屏

演示类内容（Agent 多步执行、流式输出）截图说不清楚，用 GIF：

- **ScreenToGif**（免费、Windows 原生、可逐帧编辑）：录 10 秒左右，压到 2 MB 以内。
- 超过 30 秒的流程，录 mp4 放 `docs/demo/`，**不要塞进 git**（大文件），只提交 GIF 或链接。

## 4. 体积与隐私

- 单张 PNG 控制在 300 KB 以内；截图前把浏览器缩放调到 100%，别截 4K 全屏。
- **提交前检查一遍**：不能出现 API Key、数据库密码、内网 IP、同事姓名、客户名。
- `.gitignore` 已排除 `*.log`，但 `docs/logs/*.txt` 是有意提交的，注意内容。

## 5. 这些图用在哪

1. `README.md` 顶部放一张主界面图 + 一张评测曲线（访客 3 秒判断你做没做过真东西）；
2. 简历附件 / 作品集页面；
3. 面试投屏时讲"这一版还只有健康检查，这一版已经有评测看板"——**成长叙事需要两个时间点的对比图**。

## 6. W1 需要留的三张

| 文件 | 内容 | 怎么来 |
|---|---|---|
| `01-home-health.png` | 首页三项全绿 | 方式 A |
| `02-api-docs.png` | FastAPI Swagger 文档页 | 方式 A |
| `03-start-services.png` | 终端里 `accepting connections` + `PONG` | 方式 B + 方式 C 各存一份 |