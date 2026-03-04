"""
hot.py — 热榜/日榜/周榜抓取

数据源: 第三方公开 API (https://api.bimg.eu.org)
  - hot.json    实时热榜 (每分钟更新, ~30条)
  - daily.json  日榜     (每5分钟更新, ~50条)
  - weekly.json 周榜     (每60分钟更新, ~100条)

无 Cloudflare 保护，直接 httpx.get() 即可。
"""
import httpx
from rich.console import Console

from nodeseek.models import HotPost
from nodeseek import config

console = Console()


async def fetch_hot(rank_type: str, verbose: bool = False) -> list[HotPost]:
    """
    拉取指定榜单数据，返回 HotPost 列表。

    Args:
        rank_type: "hot" | "daily" | "weekly"
        verbose:   是否输出调试日志
    """
    url = config.HOT_API_URLS[rank_type]

    if verbose:
        console.print(f"[dim]  GET {url}[/dim]")

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        data = resp.json()

    if verbose:
        console.print(
            f"[dim]  HTTP {resp.status_code} | "
            f"updated_at={data.get('updated_at')} | "
            f"posts={len(data.get('posts', []))}[/dim]"
        )

    posts = []
    for entry in data.get("posts", []):
        p = entry.get("post", {})
        posts.append(HotPost(
            id=p.get("id", 0),
            title=p.get("title", ""),
            author=p.get("author", ""),
            author_id=p.get("author_id", 0),
            timestamp=p.get("post_timestamp", 0),
            views=p.get("views", 0),
            comments=p.get("comments", 0),
            summary=p.get("summary", ""),
            category=p.get("category", ""),
            score=entry.get("score", 0.0),
            rank_type=rank_type,
        ))

    return posts
