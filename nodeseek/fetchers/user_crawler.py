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
# 返回每个 UID 的状态: ok / not_found / cf_blocked / error
_BATCH_FETCH_JS = """
async (uids) => {
    const results = await Promise.allSettled(
        uids.map(async (uid) => {
            const resp = await fetch(`/api/account/getInfo/${uid}`, {
                headers: {'Accept': 'application/json'}
            });

            // CF 拦截通常返回 403 或非 JSON 内容
            const ct = resp.headers.get('content-type') || '';
            if (!resp.ok || !ct.includes('application/json')) {
                return {
                    uid,
                    _status: resp.status,
                    _blocked: true,
                    success: false
                };
            }

            const data = await resp.json();
            return {uid, ...data};
        })
    );
    return results.map((r, i) => {
        if (r.status === 'fulfilled') return r.value;
        return {uid: uids[i], success: false, _error: String(r.reason)};
    });
}
"""


async def _wait_for_cf_clearance(page, max_wait: int = 60) -> bool:
    """等待 CF 验证通过（页面标题不再是 '请稍候…'）"""
    for i in range(max_wait):
        title = await page.title()
        if "请稍候" not in title and "challenge" not in title.lower():
            return True
        if i == 0:
            console.print(
                "\n[yellow]⚠ CF 拦截，等待自动恢复...（最多等 60s）[/yellow]"
            )
        await asyncio.sleep(1)
    return False


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
    not_found_count = 0
    cf_block_count = 0
    error_count = 0
    consecutive_not_found = 0  # 连续「真正不存在」的 UID

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

                # ── 执行批量 fetch ──
                try:
                    results = await page.evaluate(_BATCH_FETCH_JS, uids)
                except Exception as e:
                    console.print(
                        f"\n[red]  ✗ 批次 {batch_start}-{batch_end} "
                        f"page.evaluate 失败: {e}[/red]"
                    )
                    error_count += len(uids)

                    # 可能是 CF 导致页面导航，尝试恢复
                    console.print("[dim]  → 尝试恢复: 重新访问主页...[/dim]")
                    try:
                        await page.goto(config.BASE_URL, timeout=30_000)
                        await asyncio.sleep(config.CF_WAIT_SECONDS)
                        if not await _wait_for_cf_clearance(page):
                            console.print(
                                "[bold red]✗ CF 恢复失败，保存进度并退出[/bold red]"
                            )
                            set_meta(conn, "crawl_last_uid", str(batch_start - 1))
                            break
                        console.print("[green]  ✓ CF 恢复成功，继续爬取[/green]")
                    except Exception:
                        set_meta(conn, "crawl_last_uid", str(batch_start - 1))
                        break

                    await asyncio.sleep(2)
                    continue

                # ── 解析结果 ──
                batch_saved = 0
                batch_blocked = 0

                for r in results:
                    # CF 拦截 — 不是真正的空号
                    if r.get("_blocked"):
                        batch_blocked += 1
                        cf_block_count += 1
                        continue

                    # fetch 本身失败（网络错误等）
                    if r.get("_error"):
                        error_count += 1
                        continue

                    # API 返回成功 + 有效数据
                    if r.get("success"):
                        detail = r.get("detail", {})
                        if detail.get("member_id"):
                            upsert_user_from_api(conn, detail)
                            batch_saved += 1
                            consecutive_not_found = 0
                            continue

                    # API 返回 success=false（用户真的不存在）
                    not_found_count += 1
                    consecutive_not_found += 1

                conn.commit()
                saved_count += batch_saved

                # 如果整批都被 CF 拦截，暂停并恢复
                if batch_blocked == len(uids):
                    console.print(
                        f"\n[yellow]⚠ 批次 {batch_start}-{batch_end} "
                        f"全部被 CF 拦截，尝试恢复...[/yellow]"
                    )
                    await page.goto(config.BASE_URL, timeout=30_000)
                    await asyncio.sleep(config.CF_WAIT_SECONDS)
                    if await _wait_for_cf_clearance(page):
                        console.print("[green]  ✓ CF 恢复，重试此批次[/green]")
                        # 不更新断点，下次循环会重试（通过调整 batch_start）
                        # 注意：range 不支持回退，我们用 continue + 不保存断点
                        continue
                    else:
                        console.print(
                            "[bold red]✗ CF 无法恢复，保存进度并退出[/bold red]"
                        )
                        set_meta(conn, "crawl_last_uid", str(batch_start - 1))
                        break

                # 更新进度
                done = batch_end - start_uid + 1
                progress.update(task, completed=done, saved=saved_count)

                # 保存断点
                set_meta(conn, "crawl_last_uid", str(batch_end))

                # 如果连续 2000 个 UID 真的不存在，大概率已到上限
                if consecutive_not_found >= 2000:
                    console.print(
                        f"\n[yellow]⚠ 连续 {consecutive_not_found} 个空 UID，"
                        f"已到达用户上限，自动停止[/yellow]"
                    )
                    break

                if delay > 0:
                    await asyncio.sleep(delay)

    set_meta(conn, "crawl_max_uid", str(max_uid))

    console.print(
        f"\n[bold green]✓ 爬取完成[/bold green]\n"
        f"  保存: {saved_count:,} 个用户\n"
        f"  真空号: {not_found_count:,}\n"
        f"  CF拦截: {cf_block_count:,}\n"
        f"  错误: {error_count:,}\n"
        f"  数据库: {conn.execute('SELECT COUNT(*) FROM users').fetchone()[0]:,} 条总记录"
    )
    conn.close()
