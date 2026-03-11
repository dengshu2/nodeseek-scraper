"""
browser.py - 浏览器 context 管理 (Camoufox 反指纹引擎)

## 工作原理

使用 Camoufox（定制 Firefox 引擎）自动绕过 Cloudflare Turnstile：

  - C++ 级指纹伪装，引擎层面拦截指纹检测
  - headless=True  -> 完全无头，无 GUI 弹窗，无常驻进程
  - humanize=True  -> 内置类人行为模拟（鼠标移动、打字延迟）
  - 每次命令启动独立浏览器实例，用完即释放

## 与旧方案的对比

  旧方案（Chrome CDP）：需 GUI 模式 + 人工首次验证 Turnstile + 常驻进程
  新方案（Camoufox）：  headless 自动绕过，零人工干预，无常驻进程

## 使用方式

  async with persistent_browser() as ctx:
      page = await ctx.new_page()
      await page.goto(url)

## 并发保护（进程级文件锁）

  Camoufox 在 macOS 上不支持多实例并行运行（进程间 IPC/profile 冲突）。
  persistent_browser 内部通过 /tmp/ns_camoufox.lock 实现进程互斥：
  - 若已有其他 ns.py 进程持有浏览器，当前进程会等待其释放后再启动
  - 等待期间每 2 秒打印一次提示，最长等待 120 秒后超时报错
  - 正常单进程使用时锁的开销可忽略不计
"""
import asyncio
import fcntl
import os
import time
from contextlib import asynccontextmanager
import platform
import sys

from camoufox.async_api import AsyncCamoufox
from rich.console import Console

console = Console()

# 进程级互斥锁文件路径（防止多个 ns.py 实例同时启动 Camoufox）
_LOCK_FILE = "/tmp/ns_camoufox.lock"
_LOCK_TIMEOUT = 120  # 最长等待秒数
_LOCK_POLL = 2       # 轮询间隔秒数


def _check_camoufox_version_compat() -> None:
    """
    macOS arm64 专用：检测 Camoufox 浏览器二进制版本，过新则输出警告。

    问题记录：
      Camoufox 146.0.1-beta.25 在 macOS arm64 上存在 bug：
      访问 NodeSeek 帖子页时 Firefox 内核抛出 NS_ERROR_FAILURE
      (nsIStreamListener.onDataAvailable)，导致 page.content() 返回乱码。

    锁定版本：135.0.1-beta.24
    修复跟踪：https://github.com/daijro/camoufox/issues
    """
    if sys.platform != 'darwin' or platform.machine().lower() != 'arm64':
        return  # 只影响 macOS arm64

    try:
        from camoufox.pkgman import installed_verstr
        ver = installed_verstr()  # e.g. '146.0.1-beta.25'
        # 解析 beta 版本号
        if '-beta.' in ver:
            beta_num = int(ver.split('-beta.')[-1])
            if beta_num >= 25:
                console.print(
                    "\n[bold red]Camoufox 版本警告！[/bold red]"
                    f"\n  已安装版本 [yellow]{ver}[/yellow] 在 macOS arm64 上存在已知 Bug，"
                    "\n  可能导致帖子页返回乱码、抓取失败。"
                    "\n  [dim]请降级到 135.0.1-beta.24： bash scripts/fix-camoufox-macos.sh[/dim]"
                    "\n  [dim]上游进展：https://github.com/daijro/camoufox/issues[/dim]\n"
                )
    except Exception:
        pass  # 检测失败不阻塑正常流程


def _acquire_lock() -> int:
    """
    获取进程级文件锁（阻塞轮询，直到成功或超时）。

    Returns:
        已打开的锁文件 fd（调用方负责在结束时调用 _release_lock）

    Raises:
        TimeoutError: 超过 _LOCK_TIMEOUT 秒仍无法获取锁
    """
    fd = os.open(_LOCK_FILE, os.O_CREAT | os.O_RDWR)
    deadline = time.monotonic() + _LOCK_TIMEOUT
    warned = False

    while True:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return fd  # 成功获取锁
        except BlockingIOError:
            if not warned:
                console.print(
                    "[yellow]检测到另一个 ns.py 正在使用浏览器，"
                    "等待其完成后再启动...[/yellow]"
                )
                warned = True
            if time.monotonic() > deadline:
                os.close(fd)
                raise TimeoutError(
                    f"等待 Camoufox 浏览器锁超时（>{_LOCK_TIMEOUT}s），"
                    "请检查是否有僵尸 ns.py 进程残留。\n"
                    f"可手动删除锁文件后重试：rm {_LOCK_FILE}"
                )
            time.sleep(_LOCK_POLL)


def _release_lock(fd: int) -> None:
    """释放文件锁并关闭 fd"""
    try:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
    except Exception:
        pass


@asynccontextmanager
async def persistent_browser(headless: bool = True, verbose: bool = False):
    """
    异步上下文管理器，返回 Camoufox BrowserContext（Playwright 兼容）。

    Camoufox 基于定制 Firefox 引擎，C++ 级别反指纹伪装，
    可在 headless 模式下自动通过 Cloudflare Turnstile，
    无需人工验证，无需常驻浏览器进程。

    内置进程级文件锁，防止多个 ns.py 并行启动时产生冲突。
    若已有其他进程持有浏览器，会自动等待后再启动，不会崩溃。

    返回的 context 支持标准 Playwright API：
      - ctx.new_page()
      - page.goto() / page.content() / page.evaluate() 等

    Args:
        headless: 是否使用无头模式（默认 True，推荐）
        verbose:  是否输出调试日志

    Yields:
        BrowserContext -- Playwright 兼容的浏览器上下文
    """
    if verbose:
        console.print("[dim]-> 启动 Camoufox 浏览器...[/dim]")

    _check_camoufox_version_compat()  # macOS arm64 版本兼容性检测

    # 获取进程级互斥锁，阻塞等待直到其他 ns.py 释放浏览器
    # 使用 run_in_executor 以非阻塞方式在线程池中执行同步轮询
    lock_fd = await asyncio.get_event_loop().run_in_executor(None, _acquire_lock)

    try:
        async with AsyncCamoufox(
            headless=headless,
            humanize=True,
            i_know_what_im_doing=True,
        ) as browser:
            if verbose:
                console.print("[green]Camoufox 浏览器已就绪[/green]")
            yield browser
    finally:
        _release_lock(lock_fd)
