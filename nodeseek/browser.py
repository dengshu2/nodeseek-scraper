"""
browser.py — 浏览器 context 管理

核心策略（按优先级）：
  1. CDP 接管（推荐）：
     a. 检测 9222 端口 → 已有 Chrome（用户手动启动或上次自动启动的残留）直接连
     b. 未检测到 → 自动启动专用 headless Chrome（--headless=new），后台常驻

  2. Cookie 注入（fallback）：仅在找不到任何 Chrome 可执行文件时使用

--headless=new 说明：
  Chrome 112+ 引入的新 headless 模式与 GUI 模式共享同一套渲染引擎，
  Canvas、WebGL、音频指纹与真实 Chrome 完全一致，Cloudflare Bot 无法区分。
  相比完整 GUI Chrome，无弹窗、资源占用极低（专用 profile，无历史标签页）。

常规使用无需任何手动操作，首次运行会自动在后台启动 headless Chrome。
"""
import asyncio
import os
import subprocess
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from rich.console import Console

from nodeseek import config

console = Console()

# Chrome 远程调试端口（CDP）
CDP_PORT = 9222


# ──────────────────────────────────────────────────────
# Chrome 二进制自动探测
# ──────────────────────────────────────────────────────

def _find_chrome_binary() -> Optional[str]:
    """
    自动探测 Chrome / Chromium 可执行文件路径（macOS + Linux）。
    按优先级逐一检查候选路径，返回第一个存在的路径。
    """
    candidates = [
        # macOS — 系统级安装
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        # macOS — 用户级安装
        str(Path.home() / "Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
        # macOS — Chromium
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        # Linux — 常见路径
        "/usr/bin/google-chrome",
        "/usr/bin/google-chrome-stable",
        "/usr/bin/chromium-browser",
        "/usr/bin/chromium",
    ]
    for path in candidates:
        if Path(path).exists():
            return path
    return None


# ──────────────────────────────────────────────────────
# CDP 连接逻辑
# ──────────────────────────────────────────────────────

async def _try_connect_cdp(pw) -> Optional[object]:
    """
    尝试连接到已运行在 :9222 的 Chrome。
    先请求 /json/version 获取真实 WebSocket URL，再通过 CDP 建立连接。
    成功返回 browser 对象，失败返回 None。
    """
    import urllib.request
    import json as _json

    try:
        info = _json.loads(
            urllib.request.urlopen(
                f"http://localhost:{CDP_PORT}/json/version", timeout=2
            ).read()
        )
        ws_url = info.get("webSocketDebuggerUrl")
        if not ws_url:
            return None

        browser = await pw.chromium.connect_over_cdp(ws_url)
        console.print(
            f"[green]✓ 已通过 CDP 接管 Chrome（{info.get('Browser', '')}）[/green]"
        )
        return browser
    except Exception:
        return None


async def _auto_launch_cdp_chrome(pw) -> Optional[object]:
    """
    自动启动专用 GUI Chrome（CDP 模式），连接后返回 browser。

    为什么必须是 GUI（非 headless）：
      NodeSeek 对 /post-* 路径启用了交互式 Turnstile（Managed Challenge），
      headless=new 虽然指纹真实，但无法自动完成点击验证。
      GUI Chrome 首次访问帖子页时会弹出 Turnstile，用户点一次后
      cf_clearance 写入 profile，后续所有请求均自动通过。

    Chrome 进程启动后常驻后台，下次调用时直接复用（_try_connect_cdp 命中），
    启动延迟仅在第一次产生。
    """
    chrome_bin = _find_chrome_binary()
    if not chrome_bin:
        console.print(
            "[yellow]⚠️  未找到 Chrome 可执行文件，将降级为 cookie 注入模式\n"
            "[dim]   安装 Google Chrome 后可获得最佳效果[/dim][/yellow]"
        )
        return None

    profile_dir = str(config.SCRAPER_CDP_PROFILE_DIR)
    Path(profile_dir).mkdir(parents=True, exist_ok=True)

    console.print(
        "[cyan]→ 自动启动专用 Chrome（CDP 模式）...[/cyan]\n"
        "[dim]  首次运行需要完成一次 Cloudflare 验证，后续自动通过。[/dim]"
    )

    subprocess.Popen(
        [
            chrome_bin,
            f"--remote-debugging-port={CDP_PORT}",
            f"--user-data-dir={profile_dir}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-extensions",
            "--disable-default-apps",
            "--disable-sync",
            "--start-minimized",        # 最小化启动，减少视觉干扰
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    # 轮询等待 CDP 就绪（最多 15 秒）
    for _ in range(15):
        await asyncio.sleep(1)
        browser = await _try_connect_cdp(pw)
        if browser:
            console.print(
                "[green]✓ Chrome 已就绪（CDP），后续命令将自动复用此进程[/green]"
            )
            return browser

    console.print(
        "[red]✗ Chrome 启动超时（15s），请检查 Chrome 安装是否正常[/red]"
    )
    return None


async def _warmup_cloudflare(ctx, verbose: bool = False) -> None:
    """
    CF 预热握手：让 headless Chrome 主动访问 NodeSeek 首页 + 一个帖子页，
    使 CF 给当前 profile 颁发适用于 /post-* 路径的 cf_clearance。

    设计要点：
    - 先访问首页获取 cf_clearance（大多数情况 <5s）
    - 再访问一个公开帖子页，让 CF 将 /post-* 路径也加入信任
    - headless=new 能通过 CF 自动挑战（非交互式 Turnstile），无需人工介入
    - 超时时仅输出警告，不阻塞主流程
    """
    page = await ctx.new_page()
    try:
        # ── Step 1: 首页获取 cf_clearance ──────────────────────
        if verbose:
            console.print(f"[dim]→ CF 预热 Step1：访问首页 {config.BASE_URL}[/dim]")

        await page.goto(config.BASE_URL, timeout=30_000, wait_until="domcontentloaded")

        cf_obtained = False
        for i in range(15):
            await asyncio.sleep(1)
            current_cookies = await ctx.cookies()
            cf_cookie = next(
                (c for c in current_cookies if c["name"] == "cf_clearance"), None
            )
            if cf_cookie:
                _update_env_cf_clearance(cf_cookie["value"])
                cf_obtained = True
                if verbose:
                    console.print(f"[dim]  ✓ 首页 CF 通过（{i + 1}s），cf_clearance 已获取[/dim]")
                break

        if not cf_obtained:
            if verbose:
                console.print("[dim]⚠️  首页未获取到 cf_clearance，跳过帖子路径预热[/dim]")
            return

        # ── Step 2: 访问帖子路径建立 /post-* 信任 ───────────────
        # 使用 NodeSeek 首页排行榜第一名附近的帖子或已知公开 ID
        WARMUP_POST_URL = f"{config.BASE_URL}/post-633350-1"
        if verbose:
            console.print(f"[dim]→ CF 预热 Step2：访问帖子路径 {WARMUP_POST_URL}[/dim]")

        await page.goto(WARMUP_POST_URL, timeout=30_000, wait_until="domcontentloaded")

        # 等待 CF 对帖子路径完成验证（检测到 .content-item 即通过）
        for i in range(20):
            await asyncio.sleep(1)
            try:
                el = await page.query_selector(".content-item")
                if el:
                    if verbose:
                        console.print(
                            f"[dim]  ✓ 帖子路径 CF 通过（{i + 1}s），profile 信任已建立[/dim]"
                        )
                    # 回写最新 cf_clearance
                    final_cookies = await ctx.cookies()
                    cf = next((c for c in final_cookies if c["name"] == "cf_clearance"), None)
                    if cf:
                        _update_env_cf_clearance(cf["value"])
                    return
            except Exception:
                pass

        if verbose:
            console.print(
                "[yellow]⚠️  帖子路径预热超时（20s），CF 可能对 /post-* 施加额外保护[/yellow]"
            )

    except Exception as e:
        if verbose:
            console.print(f"[dim]⚠️  CF 预热异常: {e}[/dim]")
    finally:
        await page.close()


def _update_env_cf_clearance(value: str) -> None:
    """将新的 cf_clearance 值更新到 .env 的 NS_COOKIES 中"""
    try:
        from dotenv import load_dotenv
        env_path = config.ROOT_DIR / ".env"
        load_dotenv(env_path)
        cookie_str = os.getenv("NS_COOKIES", "").strip("\"'")

        if not cookie_str:
            return

        # 替换 cf_clearance 的值
        parts = []
        for part in cookie_str.split(";"):
            part = part.strip()
            if part.startswith("cf_clearance="):
                parts.append(f"cf_clearance={value}")
            elif part:
                parts.append(part)

        new_cookie_str = "; ".join(parts)
        existing_lines = []
        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8").splitlines():
                if not line.strip().startswith("NS_COOKIES="):
                    existing_lines.append(line)
        existing_lines.append(f'NS_COOKIES="{new_cookie_str}"')
        env_path.write_text("\n".join(existing_lines) + "\n", encoding="utf-8")
    except Exception:
        pass  # 回写失败不影响主流程


# ──────────────────────────────────────────────────────
# Cookie 管理
# ──────────────────────────────────────────────────────

def load_cookies_from_chrome() -> list[dict]:
    """从真实 Chrome（macOS）读取 nodeseek.com 的所有 cookies"""
    try:
        import browser_cookie3
    except ImportError:
        console.print("[red]缺少依赖 browser-cookie3，请运行: uv sync[/red]")
        return []

    try:
        jar = browser_cookie3.chrome(domain_name="nodeseek.com")
        return _cookiejar_to_list(jar)
    except Exception as e:
        console.print(f"[yellow]⚠️  读取 Chrome cookies 失败: {e}[/yellow]")
        return []


def load_cookies_from_env() -> list[dict]:
    """从 .env 的 NS_COOKIES 变量加载 cookies"""
    from dotenv import load_dotenv

    env_path = config.ROOT_DIR / ".env"
    load_dotenv(env_path)
    cookie_str = os.getenv("NS_COOKIES", "").strip("\"'")

    if not cookie_str:
        return []

    cookies = []
    for part in cookie_str.split(";"):
        part = part.strip()
        if "=" in part:
            name, _, value = part.partition("=")
            if name.strip():
                cookies.append({
                    "name": name.strip(),
                    "value": value.strip(),
                    "domain": ".nodeseek.com",
                    "path": "/",
                    "sameSite": "Lax",
                })
    return cookies


def _cookiejar_to_list(jar) -> list[dict]:
    """将 http.cookiejar 格式转换为 Playwright add_cookies 格式"""
    result = []
    for c in jar:
        entry: dict = {
            "name": c.name,
            "value": c.value,
            "domain": c.domain if c.domain.startswith(".") else f".{c.domain}",
            "path": c.path or "/",
            "sameSite": "Lax",
        }
        if c.expires and c.expires > 0:
            entry["expires"] = float(c.expires)
        if c.secure:
            entry["secure"] = True
        result.append(entry)
    return result


def get_all_cookies(verbose: bool = False) -> list[dict]:
    """获取可用的 cookies（.env 优先，否则从 Chrome 读取）"""
    cookies = load_cookies_from_env()
    if cookies:
        if verbose:
            console.print(f"[dim]→ 从 .env 加载 {len(cookies)} 条 cookies[/dim]")
        return cookies

    if verbose:
        console.print("[dim]→ .env 未配置，尝试从 Chrome 读取...[/dim]")
    cookies = load_cookies_from_chrome()
    if cookies and verbose:
        console.print(f"[dim]→ 从 Chrome 读取 {len(cookies)} 条 cookies[/dim]")
    return cookies


def save_cookies_to_env(cookies: list[dict]) -> Path:
    """将 cookie 列表保存到 .env 的 NS_COOKIES 变量"""
    cookie_str = "; ".join(f"{c['name']}={c['value']}" for c in cookies)
    env_path = config.ROOT_DIR / ".env"
    existing_lines = []

    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if not line.strip().startswith("NS_COOKIES="):
                existing_lines.append(line)

    existing_lines.append(f'NS_COOKIES="{cookie_str}"')
    env_path.write_text("\n".join(existing_lines) + "\n", encoding="utf-8")
    return env_path


# ──────────────────────────────────────────────────────
# Playwright Context 工厂
# ──────────────────────────────────────────────────────

@asynccontextmanager
async def persistent_browser(headless: bool = True, verbose: bool = False):
    """
    异步上下文管理器，返回可用的 BrowserContext。

    优先级：
      1. 已有 CDP Chrome（port 9222）→ 直接连（零延迟）
      2. 自动启动专用 headless Chrome → 通过 CDP 连（首次约 3-5 秒，后续零延迟）
      3. Fallback：cookie 注入（仅在找不到 Chrome 时）

    用法：
        async with persistent_browser() as ctx:
            page = await ctx.new_page()
            await page.goto(...)
    """
    from playwright.async_api import async_playwright

    async with async_playwright() as pw:
        # ── 1. 尝试连接已有 CDP Chrome ───────────────────────
        browser = await _try_connect_cdp(pw)

        # ── 2. 自动启动 GUI Chrome（首次）──────────────────────
        if not browser:
            browser = await _auto_launch_cdp_chrome(pw)

        # ── CDP 路径：连接成功 ───────────────────────────────
        if browser:
            ctx = browser.contexts[0] if browser.contexts else await browser.new_context()

            # 将 .env / Chrome 中的 cookies 注入到 CDP context
            # 对于常驻 headless profile（空白 profile），这是获得 cf_clearance 的关键
            cookies = get_all_cookies(verbose=verbose)
            if cookies:
                try:
                    await ctx.add_cookies(cookies)
                    if verbose:
                        key_names = {"cf_clearance", "memberInfo", "__cf_bm"}
                        found = [c["name"] for c in cookies if c["name"] in key_names]
                        console.print(f"[dim]→ 已注入 cookies，关键: {', '.join(found) or '无'}[/dim]")
                except Exception as e:
                    if verbose:
                        console.print(f"[dim]⚠️  cookie 注入跳过: {e}[/dim]")
            elif verbose:
                console.print("[dim]→ 未找到可注入的 cookies，将依赖 profile 已有 session[/dim]")

            try:
                yield ctx
            finally:
                # 仅断开 CDP 连接，不终止 Chrome 进程（保留常驻复用能力）
                await browser.close()
            return

        # ── 3. Fallback：cookie 注入 ─────────────────────────
        console.print(
            "[yellow]⚠️  未找到可用 Chrome，降级为 cookie 注入模式（可能被 CF 拦截）\n"
            "[dim]   安装 Google Chrome 后将自动切换为 CDP 模式[/dim][/yellow]"
        )

        profile_dir = str(config.BROWSER_PROFILE_DIR)
        Path(profile_dir).mkdir(parents=True, exist_ok=True)

        cookies = get_all_cookies(verbose=verbose)
        if not cookies:
            console.print(
                "[yellow]⚠️  未找到 cookies，CF 可能拦截请求\n"
                "[dim]   建议先运行 uv run ns.py sync-cookies[/dim][/yellow]"
            )

        ctx = await pw.chromium.launch_persistent_context(
            user_data_dir=profile_dir,
            headless=headless,
            user_agent=config.USER_AGENT,
            viewport={"width": 1280, "height": 800},
            args=["--disable-blink-features=AutomationControlled"],
        )

        if cookies:
            await ctx.add_cookies(cookies)
            if verbose:
                key_names = {"cf_clearance", "memberInfo", "__cf_bm"}
                for c in cookies:
                    if c["name"] in key_names:
                        val = c["value"][:16] + "..."
                        console.print(f"[dim]  cookie: {c['name']}={val}[/dim]")

        try:
            yield ctx
        finally:
            await ctx.close()
