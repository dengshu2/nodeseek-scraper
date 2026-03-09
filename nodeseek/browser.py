"""
browser.py — 浏览器 context 管理

## 工作原理

完全依赖 **CDP（Chrome DevTools Protocol）接管真实 Chrome 进程**，不再使用 cookie 注入：

  1. 检测 9222 端口 → 已有 Chrome 直连（零延迟，最常见路径）
  2. 未检测到    → 自动启动专用 GUI Chrome（--remote-debugging-port=9222）
                   首次启动后常驻后台，后续команд令直接复用

## 为什么不用 headless（及为什么不需要 cookie）

NodeSeek 对 /post-* 路径启用了交互式 Turnstile（Managed Challenge）。
GUI Chrome 使用真实 profile 目录，cf_clearance 由 Chrome 自动管理，
只需首次访问帖子页完成一次人工点击，此后 profile 永久持有信任凭证，
完全无需外部 cookie 管理。

## 使用方式

  async with persistent_browser() as ctx:
      page = ctx.pages[0] if ctx.pages else await ctx.new_page()
      await page.goto(url)
"""
import asyncio
import subprocess
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from rich.console import Console

from nodeseek import config

console = Console()

CDP_PORT = 9222


# ──────────────────────────────────────────────────────
# Chrome 二进制自动探测
# ──────────────────────────────────────────────────────

def _find_chrome_binary() -> Optional[str]:
    """
    自动探测 Chrome / Chromium 可执行文件路径（Windows + macOS + Linux）。
    按优先级逐一检查候选路径，返回第一个存在的路径。
    """
    import os
    import platform

    candidates: list[str] = []
    system = platform.system()

    if system == "Windows":
        # Windows — 常见安装路径（通过环境变量定位）
        for env_var in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
            base = os.environ.get(env_var, "")
            if base:
                candidates.append(os.path.join(base, r"Google\Chrome\Application\chrome.exe"))
        # 用户级 AppData 安装
        appdata = os.environ.get("LOCALAPPDATA", "")
        if appdata:
            candidates.append(os.path.join(appdata, r"Chromium\Application\chrome.exe"))
    elif system == "Darwin":
        # macOS — 系统级安装
        candidates.append("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
        # macOS — 用户级安装
        candidates.append(str(Path.home() / "Applications/Google Chrome.app/Contents/MacOS/Google Chrome"))
        # macOS — Chromium
        candidates.append("/Applications/Chromium.app/Contents/MacOS/Chromium")
    else:
        # Linux
        candidates.extend([
            "/usr/bin/google-chrome",
            "/usr/bin/google-chrome-stable",
            "/usr/bin/chromium-browser",
            "/usr/bin/chromium",
        ])

    for path in candidates:
        if Path(path).exists():
            return path
    return None


# ──────────────────────────────────────────────────────
# CDP 连接
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


async def _launch_and_connect(pw) -> Optional[object]:
    """
    自动启动专用 GUI Chrome（CDP 模式），连接后返回 browser。

    Chrome 进程以 --window-position=-10000,-10000 启动，视觉上隐藏但非 headless，
    保证 Cloudflare 指纹检测通过。进程常驻后台，后续命令直接复用。
    """
    chrome_bin = _find_chrome_binary()
    if not chrome_bin:
        return None

    profile_dir = str(config.SCRAPER_CDP_PROFILE_DIR)
    Path(profile_dir).mkdir(parents=True, exist_ok=True)

    console.print(
        "[cyan]→ 自动启动专用 Chrome（CDP 模式）...[/cyan]\n"
        "[dim]  首次运行需完成一次 Cloudflare 验证（点击帖子页的 Turnstile），后续自动通过。[/dim]"
    )

    import platform

    chrome_args = [
        chrome_bin,
        f"--remote-debugging-port={CDP_PORT}",
        f"--user-data-dir={profile_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-extensions",
        "--disable-default-apps",
        "--disable-sync",
        # 视觉隐藏（非 headless，CF 指纹不受影响）
        "--window-position=-10000,-10000",
        "--window-size=1,1",
    ]

    popen_kwargs: dict = {
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }

    if platform.system() == "Windows":
        # Windows: --window-state=minimized 不生效，改用 STARTUPINFO
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = 7  # SW_SHOWMINIMIZED
        popen_kwargs["startupinfo"] = si
        # 让 Chrome 进程独立于父进程，避免脚本退出时 Chrome 跟着退出
        popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        chrome_args.append("--window-state=minimized")

    subprocess.Popen(chrome_args, **popen_kwargs)

    # 轮询等待 CDP 就绪（最多 15 秒）
    for _ in range(15):
        await asyncio.sleep(1)
        browser = await _try_connect_cdp(pw)
        if browser:
            console.print(
                "[green]✓ Chrome 已就绪（CDP），后续命令将自动复用此进程[/green]"
            )
            return browser

    console.print("[red]✗ Chrome 启动超时（15s），请检查 Chrome 是否正常安装[/red]")
    return None


# ──────────────────────────────────────────────────────
# Playwright Context 工厂
# ──────────────────────────────────────────────────────

@asynccontextmanager
async def persistent_browser(headless: bool = True, verbose: bool = False):
    """
    异步上下文管理器，返回可用的 BrowserContext。

    优先级：
      1. 已有 CDP Chrome（port 9222）→ 直连（零延迟）
      2. 自动启动专用 GUI Chrome   → CDP 连接（首次约 3-5 秒，后续零延迟）
      3. 无 Chrome 可执行文件      → 抛出 RuntimeError，提示安装 Chrome

    示例：
        async with persistent_browser() as ctx:
            page = ctx.pages[0] if ctx.pages else await ctx.new_page()
            await page.goto(url)
    """
    from playwright.async_api import async_playwright

    async with async_playwright() as pw:
        # ── 1. 尝试接管已有 Chrome ──────────────────────────
        browser = await _try_connect_cdp(pw)

        # ── 2. 自动启动新 Chrome ────────────────────────────
        if not browser:
            browser = await _launch_and_connect(pw)

        # ── 3. 无 Chrome → 报错 ─────────────────────────────
        if not browser:
            raise RuntimeError(
                "未找到可用的 Chrome 浏览器。\n"
                "请安装 Google Chrome：https://www.google.com/chrome/\n"
                "安装后重新运行命令，工具将自动启动并接管 Chrome。"
            )

        ctx = browser.contexts[0] if browser.contexts else await browser.new_context()

        if verbose:
            console.print(f"[dim]→ 使用 BrowserContext（已有 pages: {len(ctx.pages)}）[/dim]")

        try:
            yield ctx
        finally:
            # 仅断开 CDP 连接，不终止 Chrome 进程（保留常驻复用能力）
            await browser.close()
