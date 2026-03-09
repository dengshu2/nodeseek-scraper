"""
user_crawler.py — 全量 UID 枚举爬取

遍历 UID 1 ~ max_uid，批量调用 /api/account/getInfo/{uid}，
将所有 username ↔ uid 映射写入 SQLite。

使用 page.evaluate + Promise.all 在浏览器内并发 fetch，
单次 CF 验证后即可全程自动跑完。
"""
import asyncio

from rich.console import Console
from rich.progress import Progress, BarColumn, TextColumn, TimeRemainingColumn

from nodeseek.browser import persistent_browser
from nodeseek import config
from nodeseek.db import get_connection, upsert_user_from_api, get_meta, set_meta

console = Console()

# 浏览器内批量 fetch 的 JS 代码
_BATCH_FETCH_JS = """
async (uids) => {
    const results = await Promise.allSettled(
        uids.map(uid =>
            fetch(`/api/account/getInfo/${uid}`, {
                headers: {'Accept': 'application/json'}
            })
            .then(r => r.json())
            .then(data => ({uid, ...data}))
        )
    );
    return results.map((r, i) => {
        if (r.status === 'fulfilled') return r.value;
        return {uid: uids[i], success: false, error: String(r.reason)};
    });
}
"""


async def crawl_users(
    start_uid: int = 1,
    max_uid: int = 50000,
    batch_size: int = 20,
    resume: bool = False,
    delay: float = 0.3,
) -> None:
    """
    全量或增量爬取用户资料。

    Args:
        start_uid:   起始 UID
        max_uid:     最大 UID（到达后停止）
        batch_size:  每批并发数（推荐 20）
        resume:      是否从上次断点继续
        delay:       每批之间的间隔（秒）
    """
    conn = get_connection()

    # 断点续传
    if resume:
        last = get_meta(conn, "crawl_last_uid")
        if last:
            start_uid = int(last) + 1
            console.print(f"[yellow]↺ 从断点 UID={start_uid} 继续[/yellow]")

    total = max_uid - start_uid + 1
    if total <= 0:
        console.print("[green]✓ 已经是最新，无需爬取[/green]")
        conn.close()
        return

    console.print(
        f"[cyan]→ 开始爬取 UID {start_uid} ~ {max_uid}"
        f" ({total:,} 个，每批 {batch_size})[/cyan]"
    )

    saved_count = 0
    empty_count = 0
    error_count = 0
    consecutive_empty = 0  # 连续空 UID 计数，用于自动探测上限

    async with persistent_browser(headless=True) as ctx:
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()

        # CF 握手
        console.print("[dim]→ CF 握手...[/dim]")
        await page.goto(config.BASE_URL, timeout=30_000)
        await asyncio.sleep(config.CF_WAIT_SECONDS)

        title = await page.title()
        if "challenge" in title.lower() or "请稍候" in title:
            console.print(
                "[bold red]✗ 需要手动通过 Cloudflare 验证！[/bold red]\n"
                "  请在任务栏 Chrome 中打开 https://www.nodeseek.com\n"
                "  完成验证后，重新运行此命令。"
            )
            conn.close()
            return

        console.print(f"[green]✓ CF 通过 (页面: {title[:30]})[/green]")

        with Progress(
            TextColumn("[bold cyan]{task.description}"),
            BarColumn(bar_width=40),
            TextColumn("{task.completed}/{task.total}"),
            TextColumn("saved={task.fields[saved]}"),
            TimeRemainingColumn(),
            console=console,
        ) as progress:
            task = progress.add_task(
                "爬取用户", total=total, saved=0
            )

            for batch_start in range(start_uid, max_uid + 1, batch_size):
                batch_end = min(batch_start + batch_size - 1, max_uid)
                uids = list(range(batch_start, batch_end + 1))

                try:
                    results = await page.evaluate(_BATCH_FETCH_JS, uids)
                except Exception as e:
                    console.print(f"\n[red]  ✗ 批次 {batch_start}-{batch_end} 失败: {e}[/red]")
                    error_count += len(uids)
                    # 保存已有进度后继续
                    set_meta(conn, "crawl_last_uid", str(batch_start - 1))
                    await asyncio.sleep(2)
                    continue

                batch_saved = 0
                for r in results:
                    if r.get("success"):
                        detail = r.get("detail", {})
                        if detail.get("member_id"):
                            upsert_user_from_api(conn, detail)
                            batch_saved += 1
                            consecutive_empty = 0
                        else:
                            consecutive_empty += 1
                    else:
                        empty_count += 1
                        consecutive_empty += 1

                conn.commit()
                saved_count += batch_saved

                # 更新进度
                done = batch_end - start_uid + 1
                progress.update(task, completed=done, saved=saved_count)

                # 保存断点
                set_meta(conn, "crawl_last_uid", str(batch_end))

                # 如果连续 2000 个 UID 都是空的，大概率已到上限
                # （早期 UID 段有大量空洞，需要较高阈值避免误停）
                if consecutive_empty >= 2000:
                    console.print(
                        f"\n[yellow]⚠ 连续 {consecutive_empty} 个空 UID，"
                        f"已到达用户上限，自动停止[/yellow]"
                    )
                    break

                if delay > 0:
                    await asyncio.sleep(delay)

    set_meta(conn, "crawl_max_uid", str(max_uid))

    console.print(
        f"\n[bold green]✓ 爬取完成[/bold green]\n"
        f"  保存: {saved_count:,} 个用户\n"
        f"  空号: {empty_count:,}\n"
        f"  错误: {error_count:,}\n"
        f"  数据库: {conn.execute('SELECT COUNT(*) FROM users').fetchone()[0]:,} 条总记录"
    )
    conn.close()
