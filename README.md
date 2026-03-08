# NodeSeek 数据工具

> 轻量级 NodeSeek 论坛数据聚合工具 — 热榜 / 帖子详情 / 用户评论

## 快速开始

```bash
# 安装依赖（仅需一次）
uv sync
uv run playwright install chromium

# 热榜（无需任何认证，极速）
uv run ns.py hot                      # 实时热榜 → output/hot/hot_*.json
uv run ns.py hot --type daily         # 日榜
uv run ns.py hot --type weekly        # 周榜
uv run ns.py hot --type all           # 三榜全拉
uv run ns.py hot --format table       # 终端表格预览
uv run ns.py hot --top 20             # 只取前20条

# 用户评论（自动处理 Cloudflare）
uv run ns.py user shaw-deng           # 全部评论 → output/users/shaw-deng.json
uv run ns.py user --uid 36700         # 按 UID 直接查
uv run ns.py user shaw-deng --pages 3 # 限制3页（每页15条）
uv run ns.py user shaw-deng --format md   # Markdown 格式（适合 AI 分析）
uv run ns.py user shaw-deng --format csv  # CSV 格式

# 帖子详情（自动处理 Cloudflare）
uv run ns.py post 637248              # 单个帖子 → output/posts/post_637248.json
uv run ns.py post 637248 637250       # 多个帖子
uv run ns.py post 637248 --no-comments  # 只要正文
uv run ns.py post 637248 --format md  # Markdown 格式

# 关键词搜索（调用聚合 API，无需认证）
uv run ns.py search claude            # 搜索含 "claude" 的帖子（表格输出）
uv run ns.py search vps --category trade --limit 30  # 交易区 VPS 相关
uv run ns.py search --author shaw-deng               # 按作者搜索
uv run ns.py search claude --format json             # JSON 输出
uv run ns.py search claude --format md               # Markdown 输出（适合 AI 分析）
```

## Cloudflare 处理机制

`post` 和 `user` 命令需要绕过 NodeSeek 的 Cloudflare 保护。工具会**全自动处理**，无需手动操作：

```
运行 ns.py post/user
    ↓
检测 9222 端口是否有 Chrome → 有：直接接管（零延迟）
    ↓ 没有
自动启动专用 Chrome（--start-minimized，最小化到任务栏）
    ↓
连接 CDP，注入已有 cookies，开始抓取
```

### 首次使用（一次性操作）

专用 Chrome Profile（`.chrome-scraper-profile/`）是全新空白的，**第一次访问帖子页时 Cloudflare 会要求点击 Turnstile 验证**：

1. 运行任意 `post` 或 `user` 命令，Chrome 会自动最小化启动
2. 打开任务栏中的 Chrome，手动访问 `https://www.nodeseek.com` 并点击完成验证
3. 验证成功后，`cf_clearance` 写入专用 Profile，**后续永久免验证**

> 如果 cf_clearance 过期（通常 1-24 小时），重新访问一次 NodeSeek 即可，工具会自动检测并复用新 token。

### Cookie 同步（可选辅助）

如果自动流程遇到问题，可以手动从真实 Chrome 同步 cookies：

```bash
uv run ns.py sync-cookies   # 从已登录的 Chrome 读取并写入 .env
```

## 数据源

| 功能 | 数据源 | CF 保护 | 依赖 |
|------|--------|---------|------|
| 热榜/日榜/周榜 | 第三方 API (api.bimg.eu.org) | ❌ 无 | httpx |
| 帖子详情+评论 | nodeseek.com 页面渲染 | ✅ 自动处理 | Chrome CDP |
| 用户评论 | nodeseek.com 内部 API | ✅ 自动处理 | Chrome CDP |
| 关键词搜索 | 自建聚合 API (nodeseek.dengshu.ovh) | ❌ 无 | httpx |

热榜 API 更新频率：实时热榜每分钟、日榜每5分钟、周榜每60分钟。

## 项目结构

```
nodeseek-scraper/
├── ns.py                        # CLI 入口 (uv run ns.py ...)
├── pyproject.toml               # uv 依赖管理
├── .env                         # 同步 cookies 存储（NS_COOKIES）
│
├── nodeseek/                    # 核心库
│   ├── models.py                # 数据模型 (dataclass)
│   ├── config.py                # 全局配置
│   ├── browser.py               # Chrome CDP 管理（自动启动/接管/cookie 注入）
│   │
│   ├── fetchers/
│   │   ├── hot.py               # 热榜 (httpx)
│   │   ├── post.py              # 帖子详情 (Chrome CDP)
│   │   ├── user.py              # 用户评论 (Chrome CDP)
│   │   └── search.py            # 关键词搜索 (httpx → 自建 API)
│   │
│   ├── parsers/
│   │   └── post_parser.py       # HTML → PostDetail (lxml)
│   │
│   └── exporters/
│       ├── json_exporter.py
│       ├── csv_exporter.py
│       ├── markdown_exporter.py
│       └── table_printer.py     # Rich 终端表格
│
├── output/                      # 抓取结果
│   ├── hot/                     # 热榜 JSON/CSV
│   ├── posts/                   # 帖子详情
│   └── users/                   # 用户评论
│
├── .browser-profile/            # Playwright fallback profile（备用）
└── .chrome-scraper-profile/     # CDP 专用 Chrome Profile（主要）
```

## 依赖

- **Python ≥ 3.11**
- **uv** — 依赖管理 (`brew install uv`)
- **Google Chrome** — 自动启动用于 Cloudflare 绕过
- **httpx** — 热榜 / 搜索 HTTP 客户端
- **playwright + chromium** — fallback 模式（Chrome 不可用时）
- **lxml + cssselect** — HTML 解析
- **rich** — 终端美化输出

## 注意事项

### 帖子评论分页

NodeSeek 帖子评论每页显示 10 条，`post` 命令会**自动翻页**拉取全部评论：

| 页码 | URL | 内容 |
|------|-----|------|
| 第 1 页 | `/post-{id}-1` | 主帖正文 + 前 10 条评论 |
| 第 2 页 | `/post-{id}-2` | 第 11-20 条评论 |
| 第 N 页 | `/post-{id}-N` | 后续评论，直到 `pager-next` 消失 |

通过 `--no-comments` 可跳过评论仅抓取正文（只需 1 次页面请求）。

### ⚠️ 用户评论 API 限制

NodeSeek 内部 API `/api/content/list-comments` 存在**服务端翻页上限**：

| 限制项 | 数值 |
|--------|------|
| 最大可翻页数 | 约 34 页 |
| 最多可获取评论数 | **≈ 510 条**（最近的） |
| 超出部分 | 无法获取，服务端强制返回空数组 |

这是 NodeSeek 服务端的硬性限制，与爬虫无关。

### uv 环境说明

本项目使用 uv 管理依赖，虚拟环境位于 `.venv/`。

```bash
# ✅ 正确用法
uv run ns.py hot

# ❌ 不要手动激活 .venv
# source .venv/bin/activate  ← 不需要
```

如遇到 `VIRTUAL_ENV` 相关警告，重开终端即可解决。
