"""
post.py — 帖子详情抓取（浏览器内 fetch + Promise.allSettled 并发）

核心优化:
  旧版: page.goto(url) → 浏览器完整渲染 → page.content() → 解析 HTML
        每页 ~3 秒，N 页 × M 帖子 完全串行

  新版: page.evaluate(fetch(url)) → 直接获取 HTML 文本 → 解析（不渲染）
        每页 ~300ms，多帖子 / 多页用 Promise.allSettled 并发
        速度提升 10~30 倍

原理（对标 user_crawler.py / user.py 已验证模式）:
  1. 启动 Camoufox 浏览器，访问主页建立 CF 会话（一次性，~3s）
  2. 在浏览器 JS 沙箱中用 fetch() 请求帖子页面 HTML
     - fetch() 自动携带浏览器的 cf_clearance cookie
     - 不做 DOM 渲染，只拿 HTML 文本（和 httpx 直接请求一样快）
  3. 用现有 post_parser.py 解析 HTML（纯 Python lxml，无需改动）
  4. 多帖子 / 多页通过 Promise.allSettled 并发 fetch

分页策略:
  1. fetch 第 1 页 → 解析主帖 + 评论 + has_next_page
  2. 从分页控件 [aria-label="pagination"] 提取总页数
  3. 已知总页数 → Promise.allSettled 一次性并发 fetch 2..N 页（~500ms）
  4. 未知总页数 → 串行逐页 fetch 直到无下一页（每页 ~300ms）
"""
import asyncio
import re
from typing import Optional

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from lxml import html as lhtml

from nodeseek.models import PostDetail, Comment
from nodeseek import config
from nodeseek.browser import persistent_browser

console = Console()

# 每页最多评论条数（实测值）
COMMENTS_PER_PAGE = 10

# Promise.allSettled 每批最大并发数（防 CF rate limit）
DEFAULT_BATCH_SIZE = 10

# ── JS 代码: 浏览器内 fetch ──────────────────────────────────

# 单个 URL fetch（返回 HTML 文本 + 状态码）
_FETCH_HTML_JS = """
async (url) => {
    try {
        const resp = await fetch(url);
        const html = await resp.text();
        return {html, status: resp.status};
    } catch (e) {
        return {html: '', _error: String(e)};
    }
}
"""

# 批量 URL 并发 fetch（Promise.allSettled，一次拿多个页面）
_BATCH_FETCH_HTML_JS = """
async (urls) => {
    const results = await Promise.allSettled(
        urls.map(async (url) => {
            const resp = await fetch(url);
            return {url, html: await resp.text(), status: resp.status};
        })
    );
    return results.map((r, i) => {
        if (r.status === 'fulfilled') return r.value;
        return {url: urls[i], html: '', _error: String(r.reason)};
    });
}
"""

# ── 智能 CF 等待 ──────────────────────────────────────────────

_CF_POLL_INTERVAL = 0.5
_CF_POLL_MAX = 20  # 最多等 10 秒


async def _wait_for_cf_ready(page, verbose: bool = False) -> None:
    """
    智能等待 CF challenge 通过。
    轮询 page.title()，不含 CF 关键词即视为就绪。
    替代固定 asyncio.sleep(CF_WAIT_SECONDS)，快的时候 0.5s 即通过。
    """
    for _ in range(_CF_POLL_MAX):
        try:
            title = await page.title()
            if "请稍候" not in title and "challenge" not in title.lower():
                return
        except Exception:
            pass
        await asyncio.sleep(_CF_POLL_INTERVAL)

    if verbose:
        console.print("[dim]  ⚠️  CF 智能等待超时，继续执行...[/dim]")


# ── 分页工具 ──────────────────────────────────────────────────

def _extract_total_pages(html_text: str) -> int:
    """
    从分页控件中提取总页数。

    解析 [aria-label="pagination"] 区域内的链接，
    从文本或 href（如 /post-637248-5）中提取最大页码。

    Returns:
        总页数（>= 1），0 表示无法解析分页控件。
    """
    try:
        doc = lhtml.fromstring(html_text)
    except Exception:
        return 0

    # 寻找分页容器
    pagers = doc.cssselect('[aria-label="pagination"]')
    if not pagers:
        pagers = doc.cssselect('.nsk-pager')
    if not pagers:
        return 0

    max_page = 1
    pager = pagers[0]

    # 从链接文本提取页码（"1", "2", "5"）
    for a in pager.cssselect('a'):
        text = (a.text_content() or "").strip()
        if text.isdigit():
            max_page = max(max_page, int(text))

    # 从 href 提取页码（如 /post-637248-5 → 5）
    for a in pager.cssselect('a[href]'):
        href = a.get("href", "")
        m = re.search(r'-(\d+)(?:\?|#|$)', href)
        if m:
            max_page = max(max_page, int(m.group(1)))

    return max_page


# ── 公开接口 ──────────────────────────────────────────────────

async def fetch_posts(
    post_ids: list[int],
    include_comments: bool = True,
    concurrency: int = DEFAULT_BATCH_SIZE,
    verbose: bool = False,
) -> list[PostDetail]:
    """
    批量抓取帖子详情（浏览器内 fetch，不渲染页面）。

    使用 page.evaluate(fetch(...)) 替代 page.goto()，
    速度从 ~3s/页 降至 ~300ms/页。
    多帖子的第 1 页通过 Promise.allSettled 并发获取。

    Args:
        post_ids:         帖子 ID 列表
        include_comments: 是否包含评论（False 则只抓第 1 页主帖）
        concurrency:      每批并发 fetch 数量（默认 10）
        verbose:          是否输出调试日志

    Returns:
        PostDetail 列表（顺序与输入 ID 一致，失败的跳过）
    """
    if not post_ids:
        return []

    results: list[PostDetail] = []

    async with persistent_browser(headless=True) as ctx:
        page = await ctx.new_page()

        # ── 会话预热（一次性） ──
        if verbose:
            console.print("[dim]→ 访问主页 (会话预热)...[/dim]")
        await page.goto(config.BASE_URL, timeout=30_000)
        await _wait_for_cf_ready(page, verbose)
        console.print("[green]  ✓ CF 会话就绪[/green]")

        # ── 并发 fetch 所有帖子的第 1 页 ──
        first_page_urls = [f"/post-{pid}-1" for pid in post_ids]

        if len(post_ids) > 1:
            console.print(
                f"[bold cyan]JS fetch 模式：{len(post_ids)} 个帖子，"
                f"浏览器内 Promise.allSettled 并发[/bold cyan]"
            )
            first_pages = await page.evaluate(
                _BATCH_FETCH_HTML_JS, first_page_urls
            )
        else:
            result = await page.evaluate(
                _FETCH_HTML_JS, first_page_urls[0]
            )
            first_pages = [result]

        # ── 处理每个帖子 ──
        for post_id, fp_result in zip(post_ids, first_pages):
            try:
                detail = await _process_post(
                    page=page,
                    post_id=post_id,
                    first_page_html=fp_result.get("html", ""),
                    first_page_error=fp_result.get("_error"),
                    include_comments=include_comments,
                    batch_size=concurrency,
                    verbose=verbose,
                )
                if detail:
                    results.append(detail)
                    console.print(
                        f"[green]  ✓ [{post_id}] 「{detail.title[:35]}」"
                        f" — {len(detail.comments)} 条评论[/green]"
                    )
                else:
                    console.print(
                        f"[yellow]  ⚠️ 帖子 {post_id} 解析失败，跳过[/yellow]"
                    )
            except Exception as e:
                console.print(f"[red]  ✗ 帖子 {post_id} 出错: {e}[/red]")
                if verbose:
                    import traceback
                    console.print(f"[dim]{traceback.format_exc()}[/dim]")

    return results


# ── 内部实现 ──────────────────────────────────────────────────

async def _process_post(
    page,
    post_id: int,
    first_page_html: str,
    first_page_error: Optional[str],
    include_comments: bool,
    batch_size: int,
    verbose: bool,
) -> Optional[PostDetail]:
    """处理单个帖子：解析第 1 页 + 获取后续页评论。"""
    from nodeseek.parsers.post_parser import parse_post_page

    # ── 校验第 1 页 ──
    if not first_page_html or first_page_error:
        if verbose:
            console.print(
                f"[dim]  ✗ 帖子 {post_id} 第 1 页获取失败: "
                f"{first_page_error or 'empty html'}[/dim]"
            )
        return None

    # ── 解析第 1 页（主帖 + 本页评论） ──
    detail = parse_post_page(
        html=first_page_html,
        post_id=post_id,
        url=f"{config.BASE_URL}/post-{post_id}-1",
        page_num=1,
        include_comments=include_comments,
    )

    if not detail:
        return None

    # 不需要评论或没有下一页 → 直接返回
    if not include_comments or not detail.has_next_page:
        return detail

    # ── 获取后续页评论 ──
    all_comments = list(detail.comments)

    # 尝试从分页控件获取总页数
    total_pages = _extract_total_pages(first_page_html)

    if total_pages > 1:
        # ✅ 已知总页数：Promise.allSettled 一次性并发 fetch 全部后续页
        if verbose:
            console.print(
                f"[dim]  → 帖子 {post_id}: 共 {total_pages} 页，"
                f"并发 fetch 第 2~{total_pages} 页[/dim]"
            )

        remaining_urls = [
            f"/post-{post_id}-{n}" for n in range(2, total_pages + 1)
        ]

        # 分批 fetch（每批 batch_size 个，防 CF rate limit）
        for batch_start in range(0, len(remaining_urls), batch_size):
            batch_urls = remaining_urls[batch_start:batch_start + batch_size]
            batch_results = await page.evaluate(
                _BATCH_FETCH_HTML_JS, batch_urls
            )

            for j, item in enumerate(batch_results):
                if not item.get("html") or item.get("_error"):
                    if verbose:
                        console.print(
                            f"[dim]  ⚠ 页 {batch_start + j + 2} 获取失败: "
                            f"{item.get('_error', 'empty')}[/dim]"
                        )
                    continue
                page_num = batch_start + j + 2
                parsed = parse_post_page(
                    html=item["html"],
                    post_id=post_id,
                    url=f"{config.BASE_URL}/post-{post_id}-{page_num}",
                    page_num=page_num,
                    include_comments=True,
                )
                if parsed and parsed.comments:
                    all_comments.extend(parsed.comments)
    else:
        # ⏳ 未知总页数：串行逐页 fetch 直到无下一页
        if verbose:
            console.print(
                f"[dim]  → 帖子 {post_id}: 总页数未知，串行逐页 fetch[/dim]"
            )

        page_num = 2
        while True:
            url = f"/post-{post_id}-{page_num}"
            result = await page.evaluate(_FETCH_HTML_JS, url)

            if result.get("_error") or not result.get("html"):
                break

            parsed = parse_post_page(
                html=result["html"],
                post_id=post_id,
                url=f"{config.BASE_URL}/post-{post_id}-{page_num}",
                page_num=page_num,
                include_comments=True,
            )

            if not parsed or not parsed.comments:
                break

            all_comments.extend(parsed.comments)

            if not parsed.has_next_page:
                break

            page_num += 1

    # ── 合并评论并按楼层号排序 ──
    def _floor_key(c: Comment) -> int:
        s = c.floor.lstrip("#")
        return int(s) if s.isdigit() else 0

    detail.comments = sorted(all_comments, key=_floor_key)

    return detail
