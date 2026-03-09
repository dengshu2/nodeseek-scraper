"""
profile.py — 用户基本资料获取

API:
  GET /api/account/getInfo/{uid}

返回字段包括：等级、鸡腿、星辰、主题帖数、评论数、关注数、粉丝数、注册时间。
该 API 需要通过 Cloudflare 保护（使用 Camoufox 浏览器内 fetch 自动绕过）。

批量接口（浏览器复用）:
  fetch_user_profiles_batch(usernames)  →  List[UserBasicInfo]
  所有用户共享同一 Camoufox 实例，只冷启动一次，节省 N-1 次启动开销。
"""
import asyncio
import re
from typing import Optional

from rich.console import Console

from nodeseek.models import UserBasicInfo
from nodeseek import config
from nodeseek.browser import persistent_browser

console = Console()


async def fetch_user_profile(
    username: Optional[str] = None,
    uid: Optional[int] = None,
    verbose: bool = False,
) -> UserBasicInfo:
    """
    获取单个用户基本资料（独立浏览器实例）。

    如需批量查询多个用户，请使用 fetch_user_profiles_batch()，
    可复用同一浏览器实例，节省大量冷启动时间。

    Args:
        username:  用户名（与 uid 二选一，会先解析为 UID）
        uid:       直接指定 UID
        verbose:   是否输出调试日志

    Returns:
        UserBasicInfo 数据对象
    """
    async with persistent_browser(headless=True) as ctx:
        page = await ctx.new_page()
        await _warmup_session(page, verbose)
        return await _fetch_profile_on_page(page, username=username, uid=uid, verbose=verbose)


async def fetch_user_profiles_batch(
    usernames: list[str],
    verbose: bool = False,
) -> list[UserBasicInfo]:
    """
    批量获取多个用户的基本资料，所有请求共享同一 Camoufox 实例。

    与逐个调用 fetch_user_profile() 相比，节省了 (N-1) 次浏览器冷启动
    （每次约 3~4 秒），N 个用户只需启动一次浏览器。

    Args:
        usernames:  用户名列表
        verbose:    是否输出调试日志

    Returns:
        UserBasicInfo 列表（顺序与输入一致，查询失败的用 None 占位后过滤掉）
    """
    results: list[UserBasicInfo] = []

    async with persistent_browser(headless=True) as ctx:
        page = await ctx.new_page()
        await _warmup_session(page, verbose)

        for i, username in enumerate(usernames, 1):
            console.print(
                f"[cyan]({i}/{len(usernames)}) 查询用户 [bold]{username}[/bold]...[/cyan]"
            )
            try:
                info = await _fetch_profile_on_page(
                    page, username=username, verbose=verbose
                )
                results.append(info)
            except Exception as e:
                console.print(f"[yellow]  ⚠️ {username} 查询失败，跳过: {e}[/yellow]")

    return results


# ── 内部实现（可注入已有 page）─────────────────────────────────────────────────

async def _warmup_session(page, verbose: bool) -> None:
    """会话预热：访问主页让 Camoufox 自动绕过 CF"""
    if verbose:
        console.print("[dim]→ 访问主页 (会话预热)...[/dim]")
    await page.goto(config.BASE_URL, timeout=30_000)
    await asyncio.sleep(config.CF_WAIT_SECONDS)


async def _fetch_profile_on_page(
    page,
    username: Optional[str] = None,
    uid: Optional[int] = None,
    verbose: bool = False,
) -> UserBasicInfo:
    """
    在已有 page 上执行 profile 查询（不负责浏览器生命周期）。

    供 fetch_user_profile() 和 fetch_user_profiles_batch() 共用。
    也供 user.py 在合并浏览器场景中调用。
    """
    # 解析 username → UID：先查本地 DB，命中则跳过网络重定向
    if uid is None:
        if not username:
            raise ValueError("需要提供 username 或 uid")
        try:
            from nodeseek.db import get_connection, get_uid_by_username
            conn = get_connection()
            uid = get_uid_by_username(conn, username)
            conn.close()
            if uid:
                console.print(f"[dim]  DB 命中: {username} → UID={uid}[/dim]")
        except Exception:
            pass  # DB 不存在或未同步时 fallback 到网络
        if uid is None:
            console.print(f"[cyan]→ 解析用户名 [bold]{username}[/bold] → UID...[/cyan]")
            uid = await _resolve_uid(page, username, verbose)
            console.print(f"[green]  ✓ UID = {uid}[/green]")

    # 调用 API
    console.print(f"[cyan]→ 获取用户资料 (UID={uid})...[/cyan]")
    result = await page.evaluate(
        "uid => fetch(`/api/account/getInfo/${uid}`, "
        "{headers: {'Accept': 'application/json'}})"
        ".then(r => r.json())",
        uid,
    )

    if verbose:
        console.print(f"[dim]  API 响应: {result}[/dim]")

    if not result.get("success"):
        raise RuntimeError(
            f"API 返回 success=false（UID={uid}）\n"
            f"响应: {result}"
        )

    detail = result.get("detail", {})

    info = UserBasicInfo(
        uid=detail.get("member_id", uid),
        username=detail.get("member_name", username or str(uid)),
        rank=detail.get("rank", 0),
        coin=detail.get("coin", 0),
        stardust=detail.get("stardust", 0),
        n_post=detail.get("nPost", 0),
        n_comment=detail.get("nComment", 0),
        follows=detail.get("follows", 0),
        fans=detail.get("fans", 0),
        created_at=detail.get("created_at", ""),
        created_at_str=detail.get("created_at_str", ""),
    )

    console.print(
        f"[green]✓ {info.username} (Lv{info.rank}) — "
        f"帖子 {info.n_post} / 评论 {info.n_comment} / 粉丝 {info.fans}[/green]"
    )
    return info


async def _resolve_uid(page, username: str, verbose: bool) -> int:
    """通过用户名解析 UID（跟随 /member?t= 的重定向）"""
    url = f"{config.BASE_URL}/member?t={username}"
    await page.goto(url, timeout=30_000)

    try:
        await page.wait_for_url(re.compile(r"/space/\d+"), timeout=15_000)
    except Exception:
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
