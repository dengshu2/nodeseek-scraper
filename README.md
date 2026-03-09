# NodeSeek 数据工具

> 轻量级 NodeSeek 论坛数据聚合工具 — 热榜 / 帖子详情 / 用户评论
>
> **支持 Windows / macOS / Linux**

## 快速开始

```bash
# 安装依赖（仅需一次，Camoufox 首次运行会自动下载定制 Firefox）
uv sync

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
uv run ns.py user shaw-deng --no-profile  # 仅拉取评论，不获取用户资料

# 用户基本资料（自动处理 Cloudflare）
uv run ns.py profile shaw-deng        # 终端资料卡片展示
uv run ns.py profile --uid 36700      # 按 UID 查
uv run ns.py profile shaw-deng -f json  # JSON 输出 → output/users/shaw-deng_profile.json

# 帖子详情（自动处理 Cloudflare）
uv run ns.py post 637248              # 单个帖子 → output/posts/post_637248.json
uv run ns.py post 637248 637250       # 多个帖子
uv run ns.py post 637248 --no-comments  # 只要正文
uv run ns.py post 637248 --format md  # Markdown 格式

# 关键词搜索（调用聚合 API，无需认证）
uv run ns.py search claude            # 搜索含 "claude" 的帖子（表格输出）
uv run ns.py search vps --category trade --limit 30  # 交易区 VPS 相关
uv run ns.py search --author shaw-deng               # 按作者搜索
uv run ns.py search claude --format json             # JSON 输出 → output/search/
uv run ns.py search claude --format md               # Markdown 输出（适合 AI 分析）
uv run ns.py search claude --format json --output /tmp/result/  # 保存到指定目录
```

## Cloudflare 处理机制

`post`、`user`、`profile` 命令需要绕过 NodeSeek 的 Cloudflare 保护。工具使用 **Camoufox**（定制 Firefox 引擎）**全自动处理**，无需任何手动操作：

```
运行 ns.py post/user/profile
    ↓
Camoufox 启动定制 Firefox（headless，约 3-4 秒）
    ↓
C++ 级反指纹伪装 + 类人行为模拟 → 自动通过 Cloudflare Turnstile
    ↓
抓取完成后自动关闭浏览器，无常驻进程
```

- **零配置**：无需安装 Chrome，Camoufox 首次运行自动下载定制 Firefox（~960MB）
- **零人工**：headless 模式自动绕过 CF，无需点击验证或管理 cookie
- **无常驻进程**：每次命令独立启动浏览器实例，用完即释放

## 数据源

| 功能 | 数据源 | CF 保护 | 依赖 |
|------|--------|---------|------|
| 热榜/日榜/周榜 | 第三方 API (api.bimg.eu.org) | ❌ 无 | httpx |
| 帖子详情+评论 | nodeseek.com 页面渲染 | ✅ Camoufox 自动绕过 | Camoufox + lxml |
| 用户评论 | nodeseek.com 内部 API | ✅ Camoufox 自动绕过 | Camoufox + JSON |
| 用户资料 | /api/account/getInfo/{uid} | ✅ Camoufox 自动绕过 | Camoufox + JSON |
| 关键词搜索 | 自建聚合 API (nodeseek.dengshu.ovh) | ❌ 无 | httpx |

热榜 API 更新频率：实时热榜每分钟、日榜每5分钟、周榜每60分钟。

## 项目结构

```
nodeseek-scraper/
├── ns.py                        # CLI 入口 (uv run ns.py ...)
├── pyproject.toml               # uv 依赖管理
│
├── nodeseek/                    # 核心库
│   ├── models.py                # 数据模型 (dataclass)
│   ├── config.py                # 全局配置
│   ├── browser.py               # Camoufox 浏览器管理（反指纹 headless Firefox）
│   │
│   ├── fetchers/
│   │   ├── hot.py               # 热榜 (httpx)
│   │   ├── post.py              # 帖子详情 (Camoufox headless)
│   │   ├── user.py              # 用户评论 (Camoufox headless)
│   │   ├── profile.py           # 用户资料 (Camoufox headless)
│   │   └── search.py            # 关键词搜索 (httpx → 自建 API)
│   │
│   ├── parsers/
│   │   └── post_parser.py       # HTML → PostDetail (lxml)
│   │
│   └── exporters/
│       ├── json_exporter.py
│       ├── csv_exporter.py
│       ├── markdown_exporter.py
│       ├── search_exporter.py
│       ├── table_printer.py     # Rich 终端表格
│       └── utils.py             # 公共工具函数
│
└── output/                      # 抓取结果 (hot/posts/users/search)
```

## 依赖

- **Python ≥ 3.11**
- **uv** — 依赖管理
  - macOS / Linux: `curl -LsSf https://astral.sh/uv/install.sh | sh`（或 `brew install uv`）
  - Windows: `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`
- **camoufox** — 定制 Firefox 引擎，自动绕过 Cloudflare（首次运行自动下载 ~960MB 二进制）
- **httpx** — 热榜 / 搜索 HTTP 客户端
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
# ✅ 正确用法（所有平台通用）
uv run ns.py hot

# ❌ 不要手动激活 .venv
# macOS/Linux: source .venv/bin/activate  ← 不需要
# Windows:     .venv\Scripts\activate     ← 也不需要
```

如遇到 `VIRTUAL_ENV` 相关警告，重开终端即可解决。
