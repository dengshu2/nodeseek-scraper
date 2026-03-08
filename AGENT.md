# NodeSeek Scraper — AI Agent 上下文文档

> 本文件专为 AI 编程助手（Cursor、Claude、Gemini 等）设计，提供快速上下文，
> 避免跨对话重新理解项目结构。每次新对话开始时请先读本文。

---

## 一、项目定位

轻量级 NodeSeek 论坛数据聚合 CLI 工具，用户本地运行，无服务器部署。

```
uv run ns.py hot         # 热榜（直接 API，无需认证）
uv run ns.py post 637248 # 帖子详情+评论（需绕过 Cloudflare）
uv run ns.py user shaw-deng  # 用户评论（需绕过 Cloudflare）
uv run ns.py search claude   # 关键词搜索（第三方聚合 API）
```

---

## 二、目录结构

```
nodeseek-scraper/
├── ns.py                        # CLI 入口，argparse 分发到 cmd_* 函数
├── pyproject.toml               # uv 依赖管理，包名 = "nodeseek"
├── .env                         # NS_COOKIES（sync-cookies 自动写入）
│
├── nodeseek/                    # Python 包（核心库）
│   ├── __init__.py              # __version__ = "0.1.0"
│   ├── config.py                # 路径常量、BASE_URL、CF_WAIT_SECONDS
│   ├── browser.py               # ⭐ 浏览器/CDP 管理（见 §三）
│   ├── models.py                # PostDetail, Comment, UserProfile 数据类
│   │
│   ├── fetchers/
│   │   ├── hot.py               # httpx → 第三方 API（无 CF）
│   │   ├── post.py              # Playwright CDP → 帖子页 HTML 解析
│   │   ├── user.py              # Playwright CDP → /api/content/list-comments
│   │   └── search.py            # httpx → nodeseek.dengshu.ovh（自建聚合 API）
│   │
│   ├── parsers/
│   │   └── post_parser.py       # lxml + cssselect 解析帖子 HTML
│   │
│   └── exporters/
│       ├── json_exporter.py
│       ├── csv_exporter.py
│       ├── markdown_exporter.py
│       └── table_printer.py     # Rich 终端表格
│
├── .chrome-scraper-profile/     # CDP 专用 Chrome Profile（主路径）
├── .browser-profile/            # Playwright fallback profile（备用）
└── output/                      # 抓取结果（hot/posts/users/search）
```

---

## 三、核心机制：Cloudflare 绕过

### 3.1 为什么必须用 GUI Chrome（⚠️ 关键约束）

NodeSeek 对 `/post-*` 和用户 API 路径启用了**交互式 Cloudflare Turnstile**（Managed Challenge）。

| 模式 | CF 自动通过？ | 备注 |
|------|-------------|------|
| `headless=new` | ❌ 不能 | 指纹真实，但 Turnstile 需要人工点击 |
| GUI Chrome（有效 cf_clearance）| ✅ 自动通过 | Profile 中保存了 cf_clearance |
| GUI Chrome（首次/cf 过期）| 需人工点一次 | 之后自动常驻复用 |

**因此：**
- 必须使用真实 GUI Chrome（非 headless）
- 首次使用需人工完成一次 Turnstile 验证
- cf_clearance 有效期约 1-24 小时，过期后需重新验证一次

### 3.2 browser.py 工作流

```
运行 ns.py post/user
    ↓
_try_connect_cdp()  → 检测 9222 端口是否有 Chrome 已启动
    ↓ 有：直接 CDP 接管（零延迟）
    ↓ 无：
_auto_launch_cdp_chrome()
    → subprocess.Popen 启动 GUI Chrome
    → --window-position=-10000,-10000 --window-size=1,1 --window-state=minimized  ← 窗口踢至屏幕外+最小化（2026-03 优化）
    → Dock 里会有图标（正常现象，GUI 进程标志）
    → 轮询等待 CDP 就绪（最多 15 秒）
    ↓
persistent_browser() (asynccontextmanager)
    → get_all_cookies()：优先 .env NS_COOKIES，其次 browser-cookie3 读 Chrome
    → ctx.add_cookies()：注入 cf_clearance 等 cookies
    → yield ctx
    → browser.close()（仅断开 CDP，不终止 Chrome 进程）
```

### 3.3 重要：Chrome 进程常驻

**工具结束后 Chrome 进程不会退出**，下次调用直接 CDP 复用，启动延迟只在第一次发生。
这是**故意设计**，不是 bug。`browser.close()` 只断开 Playwright 连接，不 kill 进程。

### 3.4 Cookie 同步命令

```bash
uv run ns.py sync-cookies   # 从已登录的真实 Chrome 读取 cookies 写入 .env
```

---

## 四、数据流

| 命令 | 数据源 | CF 保护 | 技术 |
|------|--------|---------|------|
| `hot` | api.bimg.eu.org | ❌ 无 | httpx |
| `post` | nodeseek.com 页面 | ✅ GUI CDP | Playwright + lxml |
| `user` | /api/content/list-comments | ✅ GUI CDP | Playwright + JSON |
| `search` | nodeseek.dengshu.ovh | ❌ 无 | httpx |

**search API 限制**：`nodeseek.dengshu.ovh` 是站长（dengshu）部署的第三方聚合服务，数据来自 NodeSeek RSS，存在延迟，不是实时爬取。

**user API 限制**：NodeSeek 服务端最多翻约 34 页（≈ 510 条评论），超出部分无法获取，这是服务端硬限制。

---

## 五、依赖说明

```toml
httpx      # hot/search 的 HTTP 客户端
playwright # 浏览器自动化（CDP + fallback 两种模式）
lxml + cssselect  # 帖子 HTML 解析
rich       # 终端 UI（表格、进度条、颜色）
browser-cookie3   # sync-cookies 命令读取真实 Chrome cookies
python-dotenv     # 读写 .env 中的 NS_COOKIES
```

运行环境：`uv run ns.py ...`（无需手动激活 venv）

---

## 六、已知问题 & 当前状态（2026-03）

### 已实现
- [x] 热榜/日榜/周榜（多格式输出：json/csv/table）
- [x] 帖子详情+评论（自动翻页，多格式：json/md）
- [x] 用户评论（多格式：json/csv/md）
- [x] 关键词搜索（多格式，支持 --output 保存文件）
- [x] Cloudflare 自动绕过（CDP 常驻模式）
- [x] Chrome 窗口踢至屏幕外 + 最小化（防弹窗，2026-03-08）
- [x] CDP context 复用已有 page（减少 new_page 触发窗口弹出，2026-03-08）

### 已知约束
- CF Turnstile 首次/过期需人工验证一次，无法完全自动化
- search 依赖第三方 API，数据非实时
- user 评论上限 510 条
- Chrome 常驻进程占用约 150-200MB 内存

### 潜在优化方向（未实现）
- **Step 2（CF 优化）**：检测 Profile 中 cf_clearance 有效期，未过期时改用 `headless=new` 彻底无弹窗
- MCP Server wrapper（让 AI 直接调用抓取能力）
- 定时任务 / 增量更新

---

## 七、修改时注意事项

1. **不要改 browser.py 的 GUI 模式为 headless**，除非同时解决 CF Turnstile 问题（见 §三）
2. **ns.py 是脚本文件**，通过 `uv run ns.py` 执行，不是通过 `uv run ns`（pyproject.toml 的 scripts 入口需安装后才生效）
3. **输出目录约定**：`output/hot/`、`output/posts/`、`output/users/`、`output/search/`
4. **格式约定**：hot 支持 json/csv/table；post/user 支持 json/md/csv；**search 支持 json/md/table**，其中 json/md 格式会写入文件（支持 `--output` 自定义目录）
5. **数据模型统一在 `models.py`**：包括 `HotPost`、`PostDetail`、`Comment`、`UserComment`、`UserProfile`、`SearchResult`、`SearchResponse`
6. **exporter 公共工具**：`make_output_dir()` 和 `make_timestamp()` 定义在 `nodeseek/exporters/utils.py`，三个 exporter 统一 import，不要各自重复定义
