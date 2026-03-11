# NodeSeek Scraper — AI Agent 上下文文档

> 本文件专为 AI 编程助手（Cursor、Claude、Gemini 等）设计，提供快速上下文，
> **⚠️ 项目支持 Windows / macOS / Linux 三平台**。
> 避免跨对话重新理解项目结构。每次新对话开始时请先读本文。

---

## 一、项目定位

轻量级 NodeSeek 论坛数据聚合 CLI 工具，用户本地运行，无服务器部署。

```
uv run ns.py hot         # 热榜（直接 API，无需认证）
uv run ns.py post 637248 # 帖子详情+评论（需绕过 Cloudflare）
uv run ns.py user shaw-deng  # 用户评论（需绕过 Cloudflare）
uv run ns.py user tmall wjgppx yeling  # ⚡ 批量用户评论（共享浏览器，只启动一次）
uv run ns.py profile shaw-deng  # 用户基本资料（需绕过 Cloudflare）
uv run ns.py profile tmall wjgppx yeling  # ⚡ 批量用户资料（共享浏览器，只启动一次）
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
│   ├── browser.py               # ⭐ Camoufox 浏览器管理（见 §三）
│   ├── models.py                # PostDetail, Comment, UserProfile 数据类
│   │
│   ├── fetchers/
│   │   ├── hot.py               # httpx → 第三方 API（无 CF）
│   │   ├── post.py              # Camoufox headless → 帖子页 HTML 解析
│   │   ├── user.py              # Camoufox headless → /api/content/list-comments
│   │   ├── profile.py           # Camoufox headless → /api/account/getInfo/{uid}
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
└── output/                      # 抓取结果（hot/posts/users/search）
```

---

## 三、核心机制：Cloudflare 绕过（Camoufox）

### 3.1 方案概述

NodeSeek 对 `/post-*` 和用户 API 路径启用了**交互式 Cloudflare Turnstile**（Managed Challenge）。

本项目使用 **Camoufox**（定制 Firefox 引擎）自动绕过 CF，**完全 headless，零人工干预**：

| 模式 | CF 自动通过？ | 备注 |
|------|-------------|------|
| Playwright headless Chrome | ❌ | 指纹被 CF 检测 |
| GUI Chrome + CDP（旧方案） | ⚠️ 需首次人工 | 依赖 cf_clearance + 常驻进程 |
| **Camoufox headless（当前方案）** | **✅ 自动** | **C++ 级反指纹，无需人工** |

### 3.2 Camoufox 技术原理

- 基于定制 Firefox 引擎，在 C++ 层面拦截指纹检测
- 修改 navigator、screen、WebGL、fonts 等属性，避免 JS 注入被反爬系统发现
- 内置类人行为模拟（`humanize=True`）：鼠标移动、打字延迟
- 完全兼容 Playwright API（page.goto / page.content / page.evaluate 等）

### 3.3 browser.py 工作流

```
运行 ns.py post/user/profile
    ↓
persistent_browser() (asynccontextmanager)
    → AsyncCamoufox(headless=True, humanize=True)
    → 启动定制 Firefox 实例（约 3-4 秒）
    → yield BrowserContext（Playwright 兼容）
    → 命令结束后自动关闭浏览器，无常驻进程
```

### 3.4 注意事项

- **无需安装 Chrome**：Camoufox 自带定制 Firefox，首次使用自动下载（~960MB）
- **无常驻进程**：每次命令启动独立浏览器实例，用完即释放
- **无需 cookie 管理**：CF 绕过在引擎层面实现，不依赖 cf_clearance

---

## 四、数据流

| 命令 | 数据源 | CF 保护 | 技术 |
|------|--------|---------|------|
| `hot` | api.bimg.eu.org | ❌ 无 | httpx |
| `post` | nodeseek.com 页面 | ✅ Camoufox 自动绕过 | Camoufox + lxml |
| `user` | /api/content/list-comments | ✅ Camoufox 自动绕过 | Camoufox + JSON |
| `profile` | /api/account/getInfo/{uid} | ✅ Camoufox 自动绕过 | Camoufox + JSON |
| `search` | nodeseek.dengshu.ovh | ❌ 无 | httpx |

**search API 限制**：`nodeseek.dengshu.ovh` 是站长（dengshu）部署的第三方聚合服务，数据来自 NodeSeek RSS，存在延迟，不是实时爬取。

**user API 限制**：NodeSeek 服务端最多翻约 34 页（≈ 510 条评论），超出部分无法获取，这是服务端硬限制。

---

## 五、依赖说明

```toml
httpx          # hot/search 的 HTTP 客户端
camoufox       # 反指纹 Firefox 引擎（自动绕过 CF）
playwright     # 浏览器自动化 API（由 camoufox 封装使用）
lxml + cssselect  # 帖子 HTML 解析
rich           # 终端 UI（表格、进度条、颜色）
```

运行环境：`uv run ns.py ...`（无需手动激活 venv）

---

## 六、已知问题 & 当前状态（2026-03）

### 已实现
- [x] 热榜/日榜/周榜（多格式输出：json/csv/table）
- [x] 帖子详情+评论（自动翻页，多格式：json/md）
- [x] 用户评论（多格式：json/csv/md）
- [x] 用户基本资料查询（profile 命令）
- [x] 关键词搜索（多格式，支持 --output 保存文件）
- [x] Cloudflare 自动绕过（Camoufox headless 模式，零人工干预，2026-03-09）
- [x] Windows / macOS / Linux 全平台支持
- [x] 进程级文件锁（`/tmp/ns_camoufox.lock`），防止多个 ns.py 并行启动时浏览器冲突（2026-03-11）

### 已知约束
- search 依赖第三方 API，数据非实时
- user 评论上限 510 条
- Camoufox 定制 Firefox 二进制约 960MB 磁盘占用
- 每次命令启动独立浏览器实例（约 3-4 秒启动开销）

### ⚠️ macOS arm64 Camoufox 版本锁定（2026-03-09）

**当前锁定版本：`135.0.1-beta.24`（macOS arm64 专用）**

- **问题**：Camoufox `146.0.1-beta.25`（最新版）在 macOS arm64 上存在严重 bug：
  访问 NodeSeek 帖子页时，Firefox 内核抛出 `NS_ERROR_FAILURE (nsIStreamListener.onDataAvailable)`，
  导致 `page.content()` 返回乱码二进制，页面 DOM 无法正常解析。
- **影响范围**：仅 macOS arm64（Apple Silicon）。Windows x86_64 / Linux 不受影响。
- **上游 issue**：https://github.com/daijro/camoufox/issues（CloverLabs 团队正在修复）
- **已验证可用版本**：`135.0.1-beta.24`
- **⛔ 禁止运行** `uv run camoufox fetch`，否则会升级到 beta.25 导致功能失效
- **升级前请确认**：在 GitHub Releases 确认新版已修复该 bug 后，再手动运行恢复脚本：
  ```bash
  # 恢复脚本（macOS arm64）
  scripts/fix-camoufox-macos.sh
  ```

### 潜在优化方向（未实现）
- MCP Server wrapper（让 AI 直接调用抓取能力）
- 定时任务 / 增量更新
- 浏览器实例复用（减少批量场景的启动开销）

---

## 七、修改时注意事项

1. **browser.py 使用 Camoufox headless 模式**，已自动绕过 CF Turnstile，无需手动验证（见 §三）
2. **Camoufox 返回 Playwright 兼容的 BrowserContext**，所有 fetcher 使用标准 Playwright API（page.goto / page.content / page.evaluate）
3. **ns.py 是脚本文件**，通过 `uv run ns.py` 执行，不是通过 `uv run ns`（pyproject.toml 的 scripts 入口需安装后才生效）
4. **输出目录约定**：`output/hot/`、`output/posts/`、`output/users/`、`output/search/`
5. **格式约定**：hot 支持 json/csv/table；post/user 支持 json/md/csv；**search 支持 json/md/table**，其中 json/md 格式会写入文件（支持 `--output` 自定义目录）
6. **数据模型统一在 `models.py`**：包括 `HotPost`、`PostDetail`、`Comment`、`UserBasicInfo`、`UserComment`、`UserProfile`、`SearchResult`、`SearchResponse`
7. **exporter 公共工具**：`make_output_dir()` 和 `make_timestamp()` 定义在 `nodeseek/exporters/utils.py`，三个 exporter 统一 import，不要各自重复定义
8. **⚠️ macOS arm64 不可升级 Camoufox 浏览器二进制**：见 §六「版本锁定」说明，`camoufox fetch` 命令会破坏 macOS 上的抓取功能
9. **⚠️ 不要并行运行多个 post/user/profile 命令**：Camoufox 不支持多实例并行（macOS 进程间冲突）。browser.py 已加入文件锁（`/tmp/ns_camoufox.lock`）自动排队，但 AI 调用时仍应尽量将帖子 ID 合并到一次命令中（如 `uv run ns.py post 1 2 3 4 5 6`）以节省总耗时，而非拆成多组并行。
