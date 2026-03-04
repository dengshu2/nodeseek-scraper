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
        cookie_file=args.cookie_file,
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


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    dispatch = {
        "hot":  cmd_hot,
        "user": cmd_user,
        "post": cmd_post,
    }

    try:
        asyncio.run(dispatch[args.command](args))
    except KeyboardInterrupt:
        console.print("\n[yellow]已中断[/yellow]")
        sys.exit(0)


if __name__ == "__main__":
    main()
