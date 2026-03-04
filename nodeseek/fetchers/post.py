"""
post.py — 帖子详情抓取

工作流:
  1. Playwright 访问主页（CF 握手）
  2. 从 post-{id}-1 开始，自动检测翻页，抓完所有评论
  3. 每页 10 条评论，通过 .pager-next 检测是否有下一页
  4. 支持多帖子批量抓取（共享同一浏览器）

分页说明:
  - 第 1 页: 1 个主帖 + 最多 10 条评论，URL = /post-{id}-1
  - 第 N 页: 10 条评论（无主帖），URL = /post-{id}-N
  - 通过 a.pager-next 判断是否有下一页
"""
import asyncio
from typing import Optional

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from nodeseek.models import PostDetail, Comment
from nodeseek import config

console = Console()

# 每页最多评论条数（实测值）
COMMENTS_PER_PAGE = 10


async def fetch_posts(
    post_ids: list[int],
    include_comments: bool = True,
    verbose: bool = False,
) -> list[PostDetail]:
    """
    批量抓取帖子详情（自动翻页拉取全部评论）。

    Args:
        post_ids:         帖子 ID 列表
        include_comments: 是否包含评论（False 则只抓第 1 页主帖）
        verbose:          是否输出调试日志

    Returns:
        PostDetail 列表（顺序与输入 ID 一致，失败的跳过）
    """
    from playwright.async_api import async_playwright
    from nodeseek.parsers.post_parser import parse_post_page

    results: list[PostDetail] = []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(user_agent=config.USER_AGENT)

        # CF 握手
        page = await ctx.new_page()
        if verbose:
            console.print("[dim]→ 访问主页 (CF 握手)...[/dim]")
        await page.goto(config.BASE_URL, timeout=30_000)
        await asyncio.sleep(config.CF_WAIT_SECONDS)

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            transient=True,
            console=console,
        ) as progress:
            for post_id in post_ids:
                task = progress.add_task(f"抓取帖子 {post_id}...", total=None)

                try:
                    detail = await _fetch_single_post(
                        page=page,
                        post_id=post_id,
                        include_comments=include_comments,
                        verbose=verbose,
                        progress=progress,
                        task=task,
                    )

                    if detail:
                        results.append(detail)
                        console.print(
                            f"[green]  ✓ [{post_id}] 「{detail.title[:35]}」"
                            f" — {len(detail.comments)} 条评论[/green]"
                        )
                    else:
                        console.print(f"[yellow]  ⚠️ 帖子 {post_id} 解析失败，跳过[/yellow]")

                except Exception as e:
                    console.print(f"[red]  ✗ 帖子 {post_id} 抓取出错: {e}[/red]")
                    if verbose:
                        import traceback
                        console.print(f"[dim]{traceback.format_exc()}[/dim]")

                finally:
                    progress.remove_task(task)

        await browser.close()

    return results


async def _fetch_single_post(
    page,
    post_id: int,
    include_comments: bool,
    verbose: bool,
    progress,
    task,
) -> Optional[PostDetail]:
    """抓取单个帖子，自动翻页收集所有评论"""
    from nodeseek.parsers.post_parser import parse_post_page

    detail: Optional[PostDetail] = None
    all_comments: list[Comment] = []
    page_num = 1

    while True:
        url = f"{config.BASE_URL}/post-{post_id}-{page_num}"

        if verbose:
            console.print(f"[dim]  → GET {url}[/dim]")

        progress.update(task, description=f"帖子 {post_id} 第 {page_num} 页...")

        await page.goto(url, timeout=30_000)

        try:
            await page.wait_for_selector(".content-item", timeout=15_000)
        except Exception:
            if page_num == 1:
                console.print(f"[yellow]  ⚠️ 帖子 {post_id}: 未找到内容，可能 CF 未通过[/yellow]")
            break

        html = await page.content()
        parsed = parse_post_page(
            html=html,
            post_id=post_id,
            url=f"{config.BASE_URL}/post-{post_id}-1",
            page_num=page_num,
            include_comments=include_comments,
        )

        if parsed is None:
            break

        # 第 1 页：建立 PostDetail 基础结构
        if page_num == 1:
            detail = parsed
            if not include_comments:
                break  # 不需要评论，直接返回
        else:
            # 第 2+ 页：只追加评论
            if parsed.comments:
                all_comments.extend(parsed.comments)
            else:
                break  # 该页无评论，已到末尾

        # 检测是否有下一页
        if not parsed._has_next_page:  # type: ignore[attr-defined]
            break

        page_num += 1

    # 合并所有评论到 detail
    if detail and include_comments:
        detail.comments = (detail.comments or []) + all_comments

    return detail
