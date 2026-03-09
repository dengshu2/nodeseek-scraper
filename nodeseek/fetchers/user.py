"""
user.py — 用户评论抓取

流程:
  1. 使用 persistent_browser（Camoufox 反指纹引擎）启动浏览器
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
from typing import Optional

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

from nodeseek.models import UserComment, UserProfile
from nodeseek import config
from nodeseek.browser import persistent_browser

# NodeSeek /api/content/list-comments 服务端翻页上限
# 实测在第 35 页时返回空数组，约可获取最近 510 条评论
# 超过此限制的历史评论无法通过该 API 获取
API_PAGE_LIMIT = 34

console = Console()


async def fetch_user_comments(
    username: Optional[str] = None,
    uid: Optional[int] = None,
    max_pages: int = 0,
    verbose: bool = False,
) -> UserProfile:
    """
    抓取单个用户全部评论并返回 UserProfile（独立浏览器实例）。

    如需批量查询多个用户，请使用 fetch_users_batch()，
    可复用同一浏览器实例，节省大量冷启动时间。

    Args:
        username:  用户名（与 uid 二选一）
        uid:       直接指定 UID，跳过 username 解析
        max_pages: 最多拉取页数，0 = 全部
        verbose:   是否输出调试日志
    """
    async with persistent_browser(headless=True) as ctx:
        page = await ctx.new_page()
        await _warmup_session(page, verbose)
        return await _fetch_user_on_page(
            page, username=username, uid=uid, max_pages=max_pages, verbose=verbose
        )


async def fetch_users_batch(
    usernames: list[str],
    max_pages: int = 0,
    include_profile: bool = True,
    verbose: bool = False,
) -> list[UserProfile]:
    """
    批量抓取多个用户的评论，所有请求共享同一 Camoufox 实例。

    与逐个调用 fetch_user_comments() 相比，节省了 (N-1) 次浏览器冷启动
    （每次约 3~4 秒），N 个用户只需启动一次浏览器。

    include_profile=True 时，在同一浏览器会话内附带查询用户基本资料（等级/鸡腿等），
    不需额外启动第二个浏览器实例。

    Args:
        usernames:       用户名列表
        max_pages:       单个用户最多拉取页数，0 = 全部
        include_profile: 是否附带获取用户基本资料（默认 True）
        verbose:         是否输出调试日志

    Returns:
        UserProfile 列表（顺序与输入一致，失败的跳过）
    """
    results: list[UserProfile] = []

    async with persistent_browser(headless=True) as ctx:
        page = await ctx.new_page()
        await _warmup_session(page, verbose)

        for i, username in enumerate(usernames, 1):
            console.print(
                f"[cyan]({i}/{len(usernames)}) 抓取用户 [bold]{username}[/bold] 的评论...[/cyan]"
            )
            try:
                profile = await _fetch_user_on_page(
                    page, username=username, max_pages=max_pages, verbose=verbose
                )
                # 在同一浏览器会话内附带查询用户基本资料（UID 已知，直接 API 调用）
                if include_profile:
                    try:
                        from nodeseek.fetchers.profile import _fetch_profile_on_page
                        info = await _fetch_profile_on_page(
                            page, uid=profile.uid, verbose=verbose
                        )
                        profile.info = info
                    except Exception as e:
                        console.print(f"[yellow]  ⚠️ {username} 基本资料获取失败: {e}[/yellow]")
                results.append(profile)
            except Exception as e:
                console.print(f"[yellow]  ⚠️ {username} 抓取失败，跳过: {e}[/yellow]")

    return results


# ── 内部实现─────────────────────────────────────────────────────────────────

async def _warmup_session(page, verbose: bool) -> None:
    """会话预热：访问主页让 Camoufox 自动绕过 CF"""
    if verbose:
        console.print("[dim]→ 访问主页 (会话预热)...[/dim]")
    await page.goto(config.BASE_URL, timeout=30_000)
    await asyncio.sleep(config.CF_WAIT_SECONDS)


async def _fetch_user_on_page(
    page,
    username: Optional[str] = None,
    uid: Optional[int] = None,
    max_pages: int = 0,
    verbose: bool = False,
) -> UserProfile:
    """在已有 page 上执行单个用户评论抓取（不负责浏览器生命周期）"""
    # 解析 username → UID：先查本地 DB，命中则跳过网络重定向
    if uid is None:
        try:
            from nodeseek.db import get_connection, get_uid_by_username
            conn = get_connection()
            uid = get_uid_by_username(conn, username)
            conn.close()
            if uid:
                console.print(f"[dim]  DB 命中: {username} → UID={uid}[/dim]")
        except Exception:
            pass  # DB 不存在时 fallback 到网络
        if uid is None:
            console.print(f"[cyan]→ 解析用户名 [bold]{username}[/bold] → UID...[/cyan]")
            uid = await _resolve_uid(page, username, verbose)
            console.print(f"[green]  ✓ UID = {uid}[/green]")
    else:
        console.print(f"[cyan]→ 使用 UID = {uid}[/cyan]")
        if not username:
            username = await _resolve_username(page, uid, verbose)

    # 分页拉取评论
    comments = await _fetch_all_comments(page, uid, max_pages, verbose)

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

    username: Optional[str] = None
    try:
        # 按优先级列出候选选择器，NodeSeek 页面结构变化时可在此追加
        username = await page.eval_on_selector(
            ".username, h1.username, .user-name, .profile-name",
            "el => el.innerText.trim()",
        )
    except Exception:
        pass  # 选择器未命中时 eval_on_selector 抛 Exception

    if not username:
        console.print(
            f"[yellow]⚠️  无法从页面解析 UID={uid} 的用户名"
            f"（选择器未命中，可能页面结构已变更），将以 UID 字符串代替[/yellow]"
        )
        username = str(uid)
    elif verbose:
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

            result = await page.evaluate(
                "([uid, page]) => fetch("
                "`/api/content/list-comments?uid=${uid}&page=${page}`,"
                " {headers: {'Accept': 'application/json'}})"
                ".then(r => r.json())",
                [uid, page_num],
            )

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
