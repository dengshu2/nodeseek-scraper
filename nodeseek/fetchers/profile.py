"""
profile.py — 用户基本资料获取

API:
  GET /api/account/getInfo/{uid}

返回字段包括：等级、鸡腿、星辰、主题帖数、评论数、关注数、粉丝数、注册时间。
该 API 需要通过 Cloudflare 保护（使用 Camoufox 浏览器内 fetch 自动绕过）。
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
    获取用户基本资料。

    Args:
        username:  用户名（与 uid 二选一，会先解析为 UID）
        uid:       直接指定 UID
        verbose:   是否输出调试日志

    Returns:
        UserBasicInfo 数据对象
    """
    async with persistent_browser(headless=True) as ctx:
        page = await ctx.new_page()

        # 会话预热（Camoufox 自动绕过 CF）
        if verbose:
            console.print("[dim]→ 访问主页 (会话预热)...[/dim]")
        await page.goto(config.BASE_URL, timeout=30_000)
        await asyncio.sleep(config.CF_WAIT_SECONDS)

        # 解析 username → UID
        if uid is None:
            if not username:
                raise ValueError("需要提供 username 或 uid")
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
