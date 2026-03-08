"""
ns.py — NodeSeek 数据工具 CLI 入口

用法:
  uv run ns.py hot                      # 实时热榜
  uv run ns.py hot --type daily         # 日榜
  uv run ns.py hot --type weekly        # 周榜
  uv run ns.py hot --type all           # 三榜全拉
  uv run ns.py hot --top 20             # 只显示前20条
  uv run ns.py hot --format csv         # CSV 输出

  uv run ns.py user shaw-deng           # 用户全部评论
  uv run ns.py user --uid 36700         # 按 UID 直接查
  uv run ns.py user shaw-deng --pages 3 # 限制3页
  uv run ns.py user shaw-deng --format md

  uv run ns.py post 637248              # 帖子详情
  uv run ns.py post 637248 637250       # 多个帖子
  uv run ns.py post 637248 --no-comments

  uv run ns.py search claude            # 关键词搜索
  uv run ns.py search vps --category trade --limit 30
  uv run ns.py search claude --format md
"""
import argparse
import asyncio
import sys

from rich.console import Console

console = Console()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ns",
        description="NodeSeek 数据聚合工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="输出调试信息")

    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")
    subparsers.required = True

    # ── hot ──────────────────────────────────────────────────
    hot = subparsers.add_parser("hot", help="获取热榜/日榜/周榜")
    hot.add_argument(
        "--type", "-t",
        choices=["hot", "daily", "weekly", "all"],
        default="hot",
        dest="rank_type",
        help="榜单类型 (默认: hot)",
    )
    hot.add_argument(
        "--top", type=int, default=0,
        help="只显示前 N 条，0 = 全部 (默认: 全部)",
    )
    hot.add_argument(
        "--format", "-f",
        choices=["json", "csv", "table"],
        default="json",
        dest="fmt",
        help="输出格式 (默认: json)",
    )
    hot.add_argument(
        "--output", "-o",
        default=None,
        help="输出目录 (默认: output/hot/)",
    )

    # ── user ─────────────────────────────────────────────────
    user = subparsers.add_parser("user", help="获取用户评论")
    user.add_argument("username", nargs="?", help="用户名")
    user.add_argument("--uid", type=int, help="直接指定 UID (跳过用户名解析)")
    user.add_argument(
        "--pages", type=int, default=0,
        help="限制拉取页数，0 = 全部 (默认: 全部)",
    )
    user.add_argument(
        "--format", "-f",
        choices=["json", "csv", "md"],
        default="json",
        dest="fmt",
        help="输出格式 (默认: json)",
    )
    user.add_argument(
        "--output", "-o",
        default=None,
        help="输出目录 (默认: output/users/)",
    )
    user.add_argument(
        "--cookie-file",
        default=None,
        help="Netscape 格式 cookie 文件 (可选)",
    )

    # ── post ─────────────────────────────────────────────────
    post = subparsers.add_parser("post", help="获取帖子详情+评论")
    post.add_argument("ids", nargs="+", type=int, help="帖子 ID")
    post.add_argument(
        "--no-comments", action="store_true",
        help="只抓正文，跳过评论",
    )
    post.add_argument(
        "--format", "-f",
        choices=["json", "md"],
        default="json",
        dest="fmt",
        help="输出格式 (默认: json)",
    )
    post.add_argument(
        "--output", "-o",
        default=None,
        help="输出目录 (默认: output/posts/)",
    )

    # ── search ───────────────────────────────────────────────
    search = subparsers.add_parser("search", help="关键词搜索帖子（调用聚合 API）")
    search.add_argument("keyword", nargs="?", default=None, help="搜索关键词")
    search.add_argument(
        "--category", "-c",
        default=None,
        help="分类过滤，如 trade / tech / daily / info / review",
    )
    search.add_argument(
        "--author", "-a",
        default=None,
        help="按作者过滤",
    )
    search.add_argument(
        "--limit", "-n",
        type=int, default=20,
        help="返回条数 (1-100, 默认: 20)",
    )
    search.add_argument(
        "--skip",
        type=int, default=0,
        help="分页偏移 (默认: 0)",
    )
    search.add_argument(
        "--format", "-f",
        choices=["table", "json", "md"],
        default="table",
        dest="fmt",
        help="输出格式 (默认: table)",
    )

    # ── sync-cookies ───────────────────────────────────────────────────
    sync = subparsers.add_parser(
        "sync-cookies",
        help="从已登录的 Chrome 中读取 NodeSeek cookies，保存到 .env",
    )
    sync.add_argument(
        "--browser",
        choices=["chrome", "firefox", "safari"],
        default="chrome",
        help="读取哪个浏览器的 cookies (默认: chrome)",
    )

    return parser


async def cmd_hot(args: argparse.Namespace) -> None:
    from nodeseek.fetchers.hot import fetch_hot
    from nodeseek.exporters.json_exporter import export_hot
    from nodeseek.exporters.csv_exporter import export_hot_csv

    types = ["hot", "daily", "weekly"] if args.rank_type == "all" else [args.rank_type]

    for rank_type in types:
        console.print(f"[cyan]→ 拉取 [bold]{rank_type}[/bold] 榜...[/cyan]")
        posts = await fetch_hot(rank_type, verbose=args.verbose)

        if args.top > 0:
            posts = posts[: args.top]

        console.print(f"[green]  ✓ 获取 {len(posts)} 条[/green]")

        if args.fmt == "json":
            path = export_hot(posts, rank_type, output_dir=args.output)
            console.print(f"[dim]  → {path}[/dim]")
        elif args.fmt == "csv":
            path = export_hot_csv(posts, rank_type, output_dir=args.output)
            console.print(f"[dim]  → {path}[/dim]")
        else:
            # table — 直接在终端显示，不写文件
            from nodeseek.exporters.table_printer import print_hot_table
            print_hot_table(posts, rank_type)


async def cmd_user(args: argparse.Namespace) -> None:
    from nodeseek.fetchers.user import fetch_user_comments
    from nodeseek.exporters.json_exporter import export_user

    if not args.username and not args.uid:
        console.print("[red]错误: 需要指定用户名或 --uid[/red]")
        sys.exit(1)

    profile = await fetch_user_comments(
        username=args.username,
        uid=args.uid,
        max_pages=args.pages,
        verbose=args.verbose,
    )

    console.print(
        f"[green]✓ 用户 [bold]{profile.username}[/bold] "
        f"(UID={profile.uid}) 共 {profile.total_comments} 条评论[/green]"
    )

    if args.fmt == "json":
        path = export_user(profile, output_dir=args.output)
        console.print(f"[dim]→ {path}[/dim]")
    elif args.fmt == "md":
        from nodeseek.exporters.markdown_exporter import export_user_md
        path = export_user_md(profile, output_dir=args.output)
        console.print(f"[dim]→ {path}[/dim]")
    elif args.fmt == "csv":
        from nodeseek.exporters.csv_exporter import export_user_csv
        path = export_user_csv(profile, output_dir=args.output)
        console.print(f"[dim]→ {path}[/dim]")


async def cmd_post(args: argparse.Namespace) -> None:
    from nodeseek.fetchers.post import fetch_posts
    from nodeseek.exporters.json_exporter import export_post

    console.print(f"[cyan]→ 抓取帖子: {args.ids}[/cyan]")
    posts = await fetch_posts(
        post_ids=args.ids,
        include_comments=not args.no_comments,
        verbose=args.verbose,
    )

    if not posts:
        console.print("[yellow]没有成功抓取到任何帖子[/yellow]")
        return

    for detail in posts:
        if args.fmt == "json":
            path = export_post(detail, output_dir=args.output)
            console.print(f"[dim]  → {path}[/dim]")
        elif args.fmt == "md":
            from nodeseek.exporters.markdown_exporter import export_post_md
            path = export_post_md(detail, output_dir=args.output)
            console.print(f"[dim]  → {path}[/dim]")

async def cmd_sync_cookies(args: argparse.Namespace) -> None:
    """
    从用户真实浏览器中自动提取 NodeSeek cookies，保存到 .env。
    这样 Playwright 就能带着真实的 cf_clearance 发请求，绕过 CF 拦截。
    """
    from nodeseek.browser import load_cookies_from_chrome, save_cookies_to_env, _cookiejar_to_list
    from nodeseek import config
    import browser_cookie3

    browser_name = getattr(args, "browser", "chrome")
    console.print(f"[cyan]→ 从 [bold]{browser_name}[/bold] 读取 NodeSeek cookies...[/cyan]")
    console.print("[dim]  可能会弹出 macOS 键盘访问权限请求，请允许。[/dim]")

    try:
        if browser_name == "chrome":
            jar = browser_cookie3.chrome(domain_name="nodeseek.com")
        elif browser_name == "firefox":
            jar = browser_cookie3.firefox(domain_name="nodeseek.com")
        else:
            jar = browser_cookie3.safari(domain_name="nodeseek.com")

        cookies = _cookiejar_to_list(jar)
    except Exception as e:
        console.print(f"[red]读取 cookies 失败: {e}[/red]")
        return

    if not cookies:
        console.print(
            "[yellow]⚠️  未找到 NodeSeek 相关 cookies，"
            "请确认 Chrome 中已登录 nodeseek.com。[/yellow]"
        )
        return

    # 显示关键 cookie
    key_names = {"cf_clearance", "memberInfo", "__cf_bm"}
    found_keys = [c["name"] for c in cookies if c["name"] in key_names]
    console.print(f"[green]✓ 找到 {len(cookies)} 条 cookies，关键: {', '.join(found_keys) or '无'}[/green]")

    if "cf_clearance" not in found_keys:
        console.print(
            "[yellow]⚠️  未找到 cf_clearance，建议先在 Chrome 中访问node seek.com 任意页面，"
            "常规浏览 1~2 分钟后再运行此命令。[/yellow]"
        )

    env_path = save_cookies_to_env(cookies)
    console.print(
        f"[green bold]✓ 已将 {len(cookies)} 条 cookies 写入 {env_path}。[/green bold]\n"
        f"[dim]后续运行 post/user 命令将自动使用这些 cookies。[/dim]\n"
        f"[dim]cf_clearance 通常有和期 1~24 小时，过期后重新运行此命令即可。[/dim]"
    )

async def cmd_search(args: argparse.Namespace) -> None:
    from nodeseek.fetchers.search import search_posts

    if not args.keyword and not args.category and not args.author:
        console.print("[red]错误: 至少指定关键词、--category 或 --author 之一[/red]")
        sys.exit(1)

    kw_display = args.keyword or ""
    cat_display = f" [{args.category}]" if args.category else ""
    console.print(f"[cyan]→ 搜索[bold]{kw_display}{cat_display}[/bold]...[/cyan]")

    resp = await search_posts(
        keyword=args.keyword,
        category=args.category,
        author=args.author,
        limit=args.limit,
        skip=args.skip,
        verbose=args.verbose,
    )

    console.print(
        f"[green]  ✓ 共 {resp.total} 条，显示 {len(resp.results)} 条[/green]"
    )

    if not resp.results:
        console.print("[yellow]没有匹配的帖子[/yellow]")
        return

    if args.fmt == "table":
        from rich.table import Table
        table = Table(show_header=True, header_style="bold magenta", box=None)
        table.add_column("#",        style="dim",    width=4)
        table.add_column("post_id",  style="cyan",   width=8)
        table.add_column("分类",     style="yellow",  width=10)
        table.add_column("标题",                      ratio=4)
        table.add_column("作者",     style="green",   width=14)
        table.add_column("发布时间", style="dim",     width=20)
        for i, r in enumerate(resp.results, 1):
            pub = r.pub_date[:16].replace("T", " ") if r.pub_date else ""
            table.add_row(str(i), str(r.post_id), r.category, r.title, r.author, pub)
        console.print(table)

    elif args.fmt == "json":
        import json
        output = {
            "total": resp.total,
            "skip": resp.skip,
            "limit": resp.limit,
            "data": [
                {
                    "post_id": r.post_id,
                    "title": r.title,
                    "description": r.description,
                    "category": r.category,
                    "author": r.author,
                    "pub_date": r.pub_date,
                    "link": r.link,
                }
                for r in resp.results
            ],
        }
        console.print_json(json.dumps(output, ensure_ascii=False))

    elif args.fmt == "md":
        lines = [
            f"# 搜索结果：{args.keyword or ''}\n",
            f"共 {resp.total} 条，显示 {len(resp.results)} 条\n",
        ]
        for i, r in enumerate(resp.results, 1):
            pub = r.pub_date[:16].replace("T", " ") if r.pub_date else ""
            lines.append(f"## {i}. {r.title}")
            lines.append(f"- **作者**: {r.author}  **分类**: {r.category}  **时间**: {pub}")
            lines.append(f"- **链接**: {r.link}")
            if r.description:
                lines.append(f"- **摘要**: {r.description}")
            lines.append("")
        console.print("\n".join(lines))


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    dispatch = {
        "hot":          cmd_hot,
        "user":         cmd_user,
        "post":         cmd_post,
        "search":       cmd_search,
        "sync-cookies": cmd_sync_cookies,
    }

    try:
        asyncio.run(dispatch[args.command](args))
    except KeyboardInterrupt:
        console.print("\n[yellow]已中断[/yellow]")
        sys.exit(0)


if __name__ == "__main__":
    main()
