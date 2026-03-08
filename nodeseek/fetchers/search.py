"""
search.py — 关键词搜索（调用 nodeseek.dengshu.ovh API）

数据源: 自建聚合 API (https://nodeseek.dengshu.ovh/api/posts)
  - 支持关键词全文搜索 (?search=xxx)
  - 支持分类过滤 (?category=xxx)
  - 支持作者过滤 (?author=xxx)
  - 无 Cloudflare 保护，直接 httpx 即可

API 响应格式:
  {
    "total": 31283,
    "skip": 0,
    "limit": 20,
    "data": [{ "post_id", "title", "description", "category", "author", "pub_date", "link" }]
  }
"""
from typing import Optional

import httpx
from rich.console import Console

from nodeseek.models import SearchResponse, SearchResult

console = Console()

# 自建聚合 API 地址
SEARCH_API_URL = "https://nodeseek.dengshu.ovh/api/posts"


async def search_posts(
    keyword: Optional[str] = None,
    category: Optional[str] = None,
    author: Optional[str] = None,
    limit: int = 20,
    skip: int = 0,
    verbose: bool = False,
) -> SearchResponse:
    """
    关键词搜索帖子，返回 SearchResponse。

    Args:
        keyword:  搜索关键词（匹配标题或作者名）
        category: 分类过滤，如 "trade" / "tech" / "daily"
        author:   按作者过滤
        limit:    最多返回条数 (1-100, 默认 20)
        skip:     分页偏移（默认 0）
        verbose:  是否输出调试日志
    """
    params: dict[str, str | int] = {
        "skip": skip,
        "limit": min(limit, 100),
    }
    if keyword:
        params["search"] = keyword
    if category:
        params["category"] = category
    if author:
        params["author"] = author

    if verbose:
        console.print(f"[dim]  GET {SEARCH_API_URL} params={params}[/dim]")

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(SEARCH_API_URL, params=params)
        resp.raise_for_status()
        data = resp.json()

    if verbose:
        console.print(
            f"[dim]  HTTP {resp.status_code} | "
            f"total={data.get('total')} | "
            f"returned={len(data.get('data', []))}[/dim]"
        )

    results = [
        SearchResult(
            post_id=item.get("post_id", 0),
            title=item.get("title", ""),
            description=item.get("description", ""),
            category=item.get("category", ""),
            author=item.get("author", ""),
            pub_date=item.get("pub_date", ""),
            link=item.get("link", ""),
        )
        for item in data.get("data", [])
    ]

    return SearchResponse(
        total=data.get("total", 0),
        skip=data.get("skip", 0),
        limit=data.get("limit", limit),
        results=results,
    )
