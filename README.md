# NodeSeek 数据工具

> 轻量级 NodeSeek 论坛数据聚合工具 — 热榜 / 帖子详情 / 用户评论

## 快速开始

```bash
# 安装依赖（仅需一次）
uv sync
uv run playwright install chromium

# 热榜
uv run ns.py hot                      # 实时热榜 → output/hot/hot_*.json
uv run ns.py hot --type daily         # 日榜
uv run ns.py hot --type weekly        # 周榜
uv run ns.py hot --type all           # 三榜全拉
uv run ns.py hot --format table       # 终端表格预览
uv run ns.py hot --top 20             # 只取前20条

# 用户评论
uv run ns.py user shaw-deng           # 全部评论 → output/users/shaw-deng.json
uv run ns.py user --uid 36700         # 按 UID 直接查
uv run ns.py user shaw-deng --pages 3 # 限制3页（每页15条）
uv run ns.py user shaw-deng --format md   # Markdown 格式（适合 AI 分析）
uv run ns.py user shaw-deng --format csv  # CSV 格式

# 帖子详情
uv run ns.py post 637248              # 单个帖子 → output/posts/post_637248.json
uv run ns.py post 637248 637250       # 多个帖子
uv run ns.py post 637248 --no-comments  # 只要正文
uv run ns.py post 637248 --format md  # Markdown 格式
```

## 数据源

| 功能 | 数据源 | CF 保护 | 依赖 |
|------|--------|---------|------|
| 热榜/日榜/周榜 | 第三方 API (api.bimg.eu.org) | ❌ 无 | httpx |
| 帖子详情+评论 | nodeseek.com 页面渲染 | ✅ 需要 | Playwright |
| 用户评论 | nodeseek.com 内部 API | ✅ 需要 | Playwright |

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
│   │
│   ├── fetchers/
│   │   ├── hot.py               # 热榜 (httpx)
│   │   ├── post.py              # 帖子详情 (Playwright)
│   │   └── user.py              # 用户评论 (Playwright + 内部 API)
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
└── output/
    ├── hot/                     # 热榜 JSON/CSV
    ├── posts/                   # 帖子详情
    └── users/                   # 用户评论
```

## 输出文件

```
output/
├── hot/
│   ├── hot_20260304_220000.json     # 热榜，含全部字段
│   ├── daily_20260304_220000.json   # 日榜
│   └── weekly_20260304_220000.json  # 周榜（最多100条）
├── posts/
│   ├── post_637248.json             # 帖子详情+评论
│   └── post_637248.md               # Markdown 版
└── users/
    ├── shaw-deng.json               # 用户全部评论
    └── shaw-deng.md                 # Markdown 版（适合 AI 分析）
```

## 依赖

- **Python ≥ 3.11**
- **uv** — 依赖管理 (`brew install uv`)
- **httpx** — 热榜 HTTP 客户端
- **playwright + chromium** — Cloudflare 验证 + 页面渲染
- **lxml + cssselect** — HTML 解析
- **rich** — 终端美化输出

## 注意事项

- 帖子和用户评论功能需要 Playwright 通过 Cloudflare 验证，首次运行约需 5-10 秒额外等待
- 热榜功能无需浏览器，速度极快（< 1s）

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

这是 NodeSeek 服务端的硬性限制，与爬虫无关。若用户评论数超过 510 条，只能获取最近的 510 条历史记录。

### uv 环境说明

本项目使用 uv 管理依赖，虚拟环境位于 `.venv/`。

```bash
# ✅ 正确用法（新终端直接运行）
uv run ns.py hot

# ❌ 不要手动激活 .venv，也不要使用旧的 venv/
# source .venv/bin/activate  ← 不需要
```

如遇到 `VIRTUAL_ENV` 相关警告或命令卡住，通常是旧 venv 的环境变量残留，重开终端即可解决。
