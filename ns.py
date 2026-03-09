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

注意：post/user/profile 命令使用 Camoufox（反指纹 Firefox）自动绕过 Cloudflare，无需手动验证。
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
    user.add_argument(
        "--no-profile", action="store_true",
        help="不获取用户基本资料（仅拉取评论）",
    )

    # ── profile ──────────────────────────────────────────────
    prof = subparsers.add_parser("profile", help="获取用户基本资料")
    prof.add_argument("username", nargs="?", help="用户名")
    prof.add_argument("--uid", type=int, help="直接指定 UID")
    prof.add_argument(
        "--format", "-f",
        choices=["table", "json"],
        default="table",
        dest="fmt",
        help="输出格式 (默认: table — Rich 卡片)",
    )
    prof.add_argument(
        "--output", "-o",
        default=None,
        help="输出目录 (默认: output/users/)，仅 json 格式有效",
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
    search.add_argument(
        "--output", "-o",
        default=None,
        help="输出目录 (默认: output/search/)，仅 json/md 格式有效",
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

    # 附带获取用户基本资料（除非 --no-profile）
    if not args.no_profile:
        try:
            from nodeseek.fetchers.profile import fetch_user_profile
            info = await fetch_user_profile(uid=profile.uid, verbose=args.verbose)
            profile.info = info
        except Exception as e:
            console.print(f"[yellow]⚠️ 获取用户资料失败: {e}[/yellow]")

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
        from nodeseek.exporters.search_exporter import export_search_json
        path = export_search_json(resp, keyword=args.keyword, output_dir=args.output)
        console.print(f"[dim]  → {path}[/dim]")

    elif args.fmt == "md":
        from nodeseek.exporters.search_exporter import export_search_md
        path = export_search_md(resp, keyword=args.keyword, output_dir=args.output)
        console.print(f"[dim]  → {path}[/dim]")


async def cmd_profile(args: argparse.Namespace) -> None:
    from nodeseek.fetchers.profile import fetch_user_profile

    if not args.username and not args.uid:
        console.print("[red]错误: 需要指定用户名或 --uid[/red]")
        sys.exit(1)

    info = await fetch_user_profile(
        username=args.username,
        uid=args.uid,
        verbose=args.verbose,
    )

    if args.fmt == "table":
        # Rich Panel 卡片展示
        from rich.panel import Panel
        from rich.table import Table

        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column("key", style="bold")
        table.add_column("val", style="cyan")
        table.add_column("key2", style="bold")
        table.add_column("val2", style="cyan")

        table.add_row("等级", f"Lv {info.rank}", "主题帖", str(info.n_post))
        table.add_row("鸡腿", str(info.coin), "评论数", str(info.n_comment))
        table.add_row("星辰", str(info.stardust), "粉丝", str(info.fans))
        table.add_row("注册", info.created_at_str or info.created_at[:10], "关注", str(info.follows))

        panel = Panel(table, title=f"{info.username} (UID={info.uid})", border_style="green")
        console.print(panel)

    elif args.fmt == "json":
        from nodeseek.exporters.json_exporter import export_profile
        path = export_profile(info, output_dir=args.output)
        console.print(f"[dim]→ {path}[/dim]")


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    dispatch = {
        "hot":     cmd_hot,
        "user":    cmd_user,
        "post":    cmd_post,
        "search":  cmd_search,
        "profile": cmd_profile,
    }

    try:
        asyncio.run(dispatch[args.command](args))
    except KeyboardInterrupt:
        console.print("\n[yellow]已中断[/yellow]")
        sys.exit(0)


if __name__ == "__main__":
    main()
