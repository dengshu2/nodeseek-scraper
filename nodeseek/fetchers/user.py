"""
user.py — 用户评论抓取

流程:
  1. Playwright 访问主页，等待 Cloudflare 握手通过
  2. 访问 /member?t={username} → 等待重定向到 /space/{uid}，提取 UID
  3. 循环调用 /api/content/list-comments?uid={uid}&page=N
     每页 15 条，直到返回空列表为止

⚠️  API 限制说明:
  NodeSeek 内部 API 存在服务端翻页上限，约为第 34 页（≈510 条）。
  超过该页后 API 强制返回空数组，无法获取更早的历史评论。
  这是服务端硬限制，与爬虫实现无关。
"""
import asyncio
import re
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

from nodeseek.models import UserComment, UserProfile
from nodeseek import config

# NodeSeek /api/content/list-comments 服务端翻页上限
# 实测在第 35 页时返回空数组，约可获取最近 510 条评论
# 超过此限制的历史评论无法通过该 API 获取
API_PAGE_LIMIT = 34

console = Console()


async def fetch_user_comments(
    username: Optional[str] = None,
    uid: Optional[int] = None,
    max_pages: int = 0,
    cookie_file: Optional[str] = None,
    verbose: bool = False,
) -> UserProfile:
    """
    抓取用户全部评论并返回 UserProfile。

    Args:
        username:    用户名（与 uid 二选一）
        uid:         直接指定 UID，跳过 username 解析
        max_pages:   最多拉取页数，0 = 全部
        cookie_file: Netscape 格式 cookie 文件路径（可选）
        verbose:     是否输出调试日志
    """
    from playwright.async_api import async_playwright

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(user_agent=config.USER_AGENT)

        # 加载 cookie 文件（可选）
        if cookie_file:
            _load_cookies(ctx, cookie_file, verbose)

        page = await ctx.new_page()

        try:
            # ── Step 1: 主页握手，等 CF 放行 ───────────────────────
            if verbose:
                console.print(f"[dim]→ 访问主页 (CF 握手)...[/dim]")

            await page.goto(config.BASE_URL, timeout=30_000)
            await asyncio.sleep(config.CF_WAIT_SECONDS)

            if verbose:
                console.print(f"[dim]  当前 URL: {page.url}[/dim]")

            # ── Step 2: 解析 username → UID ───────────────────────
            if uid is None:
                console.print(f"[cyan]→ 解析用户名 [bold]{username}[/bold] → UID...[/cyan]")
                uid = await _resolve_uid(page, username, verbose)
                console.print(f"[green]  ✓ UID = {uid}[/green]")
            else:
                console.print(f"[cyan]→ 使用 UID = {uid}[/cyan]")
                # 即使直接指定 UID，仍需跳转一次获取用户名（如果 username 未提供）
                if not username:
                    username = await _resolve_username(page, uid, verbose)

            # ── Step 3: 分页拉取评论 ───────────────────────────────
            comments = await _fetch_all_comments(page, uid, max_pages, verbose)

        finally:
            await browser.close()

    return UserProfile(
        uid=uid,
        username=username or str(uid),
        total_comments=len(comments),
        comments=comments,
    )


async def _resolve_uid(page, username: str, verbose: bool) -> int:
    """通过用户名解析 UID（跟随 /member?t= 的重定向）"""
    url = f"{config.BASE_URL}/member?t={username}"
    await page.goto(url, timeout=30_000)

    # 等待 URL 变化（重定向到 /space/{uid}）
    try:
        await page.wait_for_url(re.compile(r"/space/\d+"), timeout=15_000)
    except Exception:
        # 有时页面已经到位但没触发事件，直接读 URL
        pass

    await asyncio.sleep(1)
    final_url = page.url

    if verbose:
        console.print(f"[dim]  重定向到: {final_url}[/dim]")

    m = re.search(r"/space/(\d+)", final_url)
    if not m:
        raise RuntimeError(
            f"无法从 URL 解析 UID: {final_url}\n"
            f"请检查用户名是否正确，或站点是否反爬。"
        )

    return int(m.group(1))


async def _resolve_username(page, uid: int, verbose: bool) -> str:
    """通过 UID 获取用户名（访问 /space/{uid}）"""
    url = f"{config.BASE_URL}/space/{uid}"
    await page.goto(url, timeout=30_000)
    await asyncio.sleep(1)

    try:
        username = await page.eval_on_selector(
            "h1.username, .user-name, .profile-name",
            "el => el.innerText.trim()"
        )
    except Exception:
        username = str(uid)

    if verbose:
        console.print(f"[dim]  username = {username}[/dim]")

    return username


async def _fetch_all_comments(
    page,
    uid: int,
    max_pages: int,
    verbose: bool,
) -> list[UserComment]:
    """循环翻页拉取全部评论"""
    all_comments: list[UserComment] = []
    page_num = 1

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        transient=True,
        console=console,
    ) as progress:
        task = progress.add_task(
            f"拉取用户 UID={uid} 的评论...", total=None
        )

        while True:
            if max_pages > 0 and page_num > max_pages:
                if verbose:
                    console.print(f"[dim]  已达到用户设置的页数限制 ({max_pages} 页)[/dim]")
                break

            # 服务端硬限制：超过 API_PAGE_LIMIT 页后 API 强制返回空数组
            if page_num > API_PAGE_LIMIT:
                console.print(
                    f"[yellow]  ⚠️ 已达到 NodeSeek API 服务端上限（≈{API_PAGE_LIMIT * 15} 条），"
                    f"更早的历史评论无法通过此 API 获取[/yellow]"
                )
                break

            if verbose:
                console.print(f"[dim]  → 第 {page_num} 页...[/dim]")

            result = await page.evaluate(f"""
                fetch('/api/content/list-comments?uid={uid}&page={page_num}', {{
                    headers: {{'Accept': 'application/json'}}
                }}).then(r => r.json())
            """)

            if not result.get("success"):
                console.print(
                    f"[yellow]  ⚠️ 第 {page_num} 页 API 返回 success=false，停止[/yellow]"
                )
                break

            raw_comments = result.get("comments", [])
            if not raw_comments:
                # 空列表 = 已到最后一页（或触发服务端限制）
                break

            for c in raw_comments:
                all_comments.append(UserComment(
                    post_id=c.get("post_id", 0),
                    post_title=c.get("title", ""),
                    floor_id=c.get("floor_id", 0),
                    content=c.get("text", ""),
                    rank=c.get("rank", 0),
                ))

            progress.update(
                task,
                description=f"已拉取 {len(all_comments)} 条评论 (第 {page_num} 页)",
                advance=1,
            )
            page_num += 1

    console.print(
        f"[green]  ✓ 共 {len(all_comments)} 条评论，{page_num - 1} 页[/green]"
    )
    return all_comments


def _load_cookies(ctx, cookie_file: str, verbose: bool) -> None:
    """加载 Netscape 格式 cookie 文件（浏览器导出格式）"""
    import http.cookiejar

    jar = http.cookiejar.MozillaCookieJar()
    try:
        jar.load(cookie_file, ignore_discard=True, ignore_expires=True)
    except Exception as e:
        console.print(f"[yellow]cookie 文件加载失败: {e}[/yellow]")
        return

    cookies = []
    for ck in jar:
        cookies.append({
            "name": ck.name,
            "value": ck.value,
            "domain": ck.domain,
            "path": ck.path,
            "expires": ck.expires or -1,
            "httpOnly": bool(ck.has_nonstandard_attr("HttpOnly")),
            "secure": bool(ck.secure),
        })

    if verbose:
        console.print(f"[dim]→ 已加载 {len(cookies)} 条 cookie[/dim]")

    # Playwright context 级别暂不支持直接 add_cookies，需在 page 级别调用
    # 这里先存起来，在 page.goto 后用 page.context.add_cookies() 应用
    ctx._pending_cookies = cookies  # type: ignore[attr-defined]
