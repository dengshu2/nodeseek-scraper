"""
browser.py — 浏览器 context 管理 (Camoufox 反指纹引擎)

## 工作原理

使用 Camoufox（定制 Firefox 引擎）自动绕过 Cloudflare Turnstile：

  - C++ 级指纹伪装，引擎层面拦截指纹检测
  - headless=True  → 完全无头，无 GUI 弹窗，无常驻进程
  - humanize=True   → 内置类人行为模拟（鼠标移动、打字延迟）
  - 每次命令启动独立浏览器实例，用完即释放

## 与旧方案的对比

  旧方案（Chrome CDP）：需 GUI 模式 + 人工首次验证 Turnstile + 常驻进程
  新方案（Camoufox）：  headless 自动绕过，零人工干预，无常驻进程

## 使用方式

  async with persistent_browser() as ctx:
      page = await ctx.new_page()
      await page.goto(url)
"""
from contextlib import asynccontextmanager

from camoufox.async_api import AsyncCamoufox
from rich.console import Console

console = Console()


@asynccontextmanager
async def persistent_browser(headless: bool = True, verbose: bool = False):
    """
    异步上下文管理器，返回 Camoufox BrowserContext（Playwright 兼容）。

    Camoufox 基于定制 Firefox 引擎，C++ 级别反指纹伪装，
    可在 headless 模式下自动通过 Cloudflare Turnstile，
    无需人工验证，无需常驻浏览器进程。

    返回的 context 支持标准 Playwright API：
      - ctx.new_page()
      - page.goto() / page.content() / page.evaluate() 等

    Args:
        headless: 是否使用无头模式（默认 True，推荐）
        verbose:  是否输出调试日志

    Yields:
        BrowserContext — Playwright 兼容的浏览器上下文
    """
    if verbose:
        console.print("[dim]→ 启动 Camoufox 浏览器...[/dim]")

    async with AsyncCamoufox(
        headless=headless,
        humanize=True,
        i_know_what_im_doing=True,
    ) as browser:
        if verbose:
            console.print("[green]✓ Camoufox 浏览器已就绪[/green]")
        yield browser
