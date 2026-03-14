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
  uv run ns.py user tmall wjgppx yeling # 批量查询（共享浏览器，只冷启动一次）
  uv run ns.py user --uid 36700         # 按 UID 直接查
  uv run ns.py user shaw-deng --pages 3 # 限制3页
  uv run ns.py user shaw-deng --format md

  uv run ns.py post 637248              # 帖子详情
  uv run ns.py post 637248 637250       # 多帖子并发（浏览器内 JS fetch）
  uv run ns.py post 637248 637250 -j 15 # 每批并发 fetch 15 个页面
  uv run ns.py post 637248 --no-comments

  uv run ns.py profile shaw-deng        # 用户资料
  uv run ns.py profile tmall wjgppx yeling  # 批量查询（共享浏览器，只冷启动一次）

  uv run ns.py search claude            # 关键词搜索
  uv run ns.py search vps --category trade --limit 30
  uv run ns.py search claude --format md

注意：post/user/profile 命令使用 Camoufox（反指纹 Firefox）自动绕过 Cloudflare，无需手动验证。
速度优化：post 命令使用浏览器内 JS fetch（不渲染页面），速度提升 10~30 倍。
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
    user.add_argument("username", nargs="*", help="用户名（支持多个，批量时共享浏览器）")
    user.add_argument("--uid", type=int, help="直接指定 UID (跳过用户名解析)，仅单用户时有效")
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
    prof.add_argument("username", nargs="*", help="用户名（支持多个，批量时共享浏览器）")
    prof.add_argument("--uid", type=int, help="直接指定 UID，仅单用户时有效")
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
        "--concurrency", "-j",
        type=int,
        default=10,
        metavar="N",
        help="每批并发 fetch 页面数 (default: 10)",
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

    # ── sync-users ────────────────────────────────────────────
    sync = subparsers.add_parser("sync-users", help="全量枚举 UID 爬取用户资料到 SQLite")
    sync.add_argument(
        "--start", type=int, default=1,
        help="起始 UID (默认: 1)",
    )
    sync.add_argument(
        "--max", type=int, default=55000,
        dest="max_uid",
        help="最大 UID (默认: 55000，会自动检测上限停止)",
    )
    sync.add_argument(
        "--batch", type=int, default=20,
        dest="batch_size",
        help="每批并发数 (默认: 20)",
    )
    sync.add_argument(
        "--resume", action="store_true",
        help="从上次断点继续",
    )
    sync.add_argument(
        "--delay", type=float, default=0.3,
        help="每批间隔秒数 (默认: 0.3)",
    )

    # ── lookup ───────────────────────────────────────────────
    lk = subparsers.add_parser("lookup", help="从本地 DB 查询用户")
    lk.add_argument("username", nargs="?", help="用户名")
    lk.add_argument("--uid", type=int, help="按 UID 查")
    lk.add_argument(
        "--search", "-s", default=None, dest="keyword",
        help="模糊搜索用户名",
    )
    lk.add_argument(
        "--limit", "-n", type=int, default=20,
        help="搜索返回条数 (默认: 20)",
    )
    lk.add_argument(
        "--stats", action="store_true",
        help="显示数据库统计信息",
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
    from nodeseek.exporters.json_exporter import export_user

    usernames = args.username or []

    # 批量模式：多用户名，共享浏览器实例（含 profile 附带查询）
    if len(usernames) > 1:
        from nodeseek.fetchers.user import fetch_users_batch
        console.print(
            f"[bold cyan]批量模式：{len(usernames)} 个用户，共享单一 Camoufox 实例[/bold cyan]"
        )
        profiles = await fetch_users_batch(
            usernames=usernames,
            max_pages=args.pages,
            include_profile=not args.no_profile,
            verbose=args.verbose,
        )
        for profile in profiles:
            info = profile.info
            info_str = (
                f" | Lv{info.rank} 鸡腿{info.coin} 粉丝{info.fans}"
                if info else ""
            )
            console.print(
                f"[green]✓ 用户 [bold]{profile.username}[/bold] "
                f"(UID={profile.uid}) 共 {profile.total_comments} 条评论{info_str}[/green]"
            )
            if args.fmt == "json":
                path = export_user(profile, output_dir=args.output)
                console.print(f"[dim]  → {path}[/dim]")
            elif args.fmt == "md":
                from nodeseek.exporters.markdown_exporter import export_user_md
                path = export_user_md(profile, output_dir=args.output)
                console.print(f"[dim]  → {path}[/dim]")
            elif args.fmt == "csv":
                from nodeseek.exporters.csv_exporter import export_user_csv
                path = export_user_csv(profile, output_dir=args.output)
                console.print(f"[dim]  → {path}[/dim]")
        return

    # 单用户模式（小兼容 --uid 参数）
    username = usernames[0] if usernames else None
    if not username and not args.uid:
        console.print("[red]错误: 需要指定用户名或 --uid[/red]")
        sys.exit(1)

    from nodeseek.fetchers.user import fetch_user_comments
    profile = await fetch_user_comments(
        username=username,
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
        concurrency=args.concurrency,
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
    usernames = args.username or []

    # 批量模式：多用户名，共享浏览器实例
    if len(usernames) > 1:
        from nodeseek.fetchers.profile import fetch_user_profiles_batch
        console.print(
            f"[bold cyan]批量模式：{len(usernames)} 个用户，共享单一 Camoufox 实例[/bold cyan]"
        )
        results = await fetch_user_profiles_batch(usernames=usernames, verbose=args.verbose)
        if args.fmt == "json":
            from nodeseek.exporters.json_exporter import export_profile
            for info in results:
                path = export_profile(info, output_dir=args.output)
                console.print(f"[dim]→ {path}[/dim]")
        else:
            for info in results:
                _print_profile_card(info)
        return

    # 单用户模式（小兼容 --uid 参数）
    username = usernames[0] if usernames else None
    if not username and not args.uid:
        console.print("[red]错误: 需要指定用户名或 --uid[/red]")
        sys.exit(1)

    from nodeseek.fetchers.profile import fetch_user_profile
    info = await fetch_user_profile(
        username=username,
        uid=args.uid,
        verbose=args.verbose,
    )

    if args.fmt == "table":
        _print_profile_card(info)
    elif args.fmt == "json":
        from nodeseek.exporters.json_exporter import export_profile
        path = export_profile(info, output_dir=args.output)
        console.print(f"[dim]→ {path}[/dim]")


def _print_profile_card(info) -> None:
    """Rich Panel 卡片展示用户资料"""
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


async def cmd_sync_users(args: argparse.Namespace) -> None:
    from nodeseek.fetchers.user_crawler import crawl_users

    await crawl_users(
        start_uid=args.start,
        max_uid=args.max_uid,
        batch_size=args.batch_size,
        resume=args.resume,
        delay=args.delay,
    )


async def cmd_lookup(args: argparse.Namespace) -> None:
    from nodeseek.db import (
        get_connection, get_user_by_uid, get_user_by_username,
        search_users, get_user_count, get_meta,
    )

    conn = get_connection()

    if args.stats:
        count = get_user_count(conn)
        last_uid = get_meta(conn, "crawl_last_uid") or "未同步"
        console.print(
            f"[bold]数据库统计[/bold]\n"
            f"  用户总数: [cyan]{count:,}[/cyan]\n"
            f"  最后同步 UID: [cyan]{last_uid}[/cyan]"
        )
        conn.close()
        return

    if args.keyword:
        results = search_users(conn, args.keyword, limit=args.limit)
        if not results:
            console.print("[yellow]未找到匹配用户[/yellow]")
        else:
            from rich.table import Table
            table = Table(show_header=True, header_style="bold magenta", box=None)
            table.add_column("UID",   style="cyan",  width=8)
            table.add_column("用户名", style="green", ratio=2)
            table.add_column("等级",  width=6)
            table.add_column("帖子",  width=6)
            table.add_column("评论",  width=8)
            table.add_column("粉丝",  width=6)
            table.add_column("注册时间", style="dim", width=12)
            for u in results:
                table.add_row(
                    str(u["uid"]), u["username"], f"Lv{u['rank']}",
                    str(u["n_post"]), str(u["n_comment"]),
                    str(u["fans"]), (u.get("created_at_str") or u.get("created_at", ""))[:10],
                )
            console.print(table)
            console.print(f"[dim]共 {len(results)} 条结果[/dim]")
        conn.close()
        return

    user = None
    if args.uid:
        user = get_user_by_uid(conn, args.uid)
    elif args.username:
        user = get_user_by_username(conn, args.username)
    else:
        console.print("[red]错误: 需要指定用户名、--uid 或 --search[/red]")
        conn.close()
        sys.exit(1)

    if not user:
        console.print("[yellow]用户不在本地数据库中，请先运行 sync-users[/yellow]")
        conn.close()
        return

    from rich.panel import Panel
    from rich.table import Table

    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("key", style="bold")
    table.add_column("val", style="cyan")
    table.add_column("key2", style="bold")
    table.add_column("val2", style="cyan")

    table.add_row("等级", f"Lv {user['rank']}", "主题帖", str(user["n_post"]))
    table.add_row("鸡腿", str(user["coin"]), "评论数", str(user["n_comment"]))
    table.add_row("星辰", str(user["stardust"]), "粉丝", str(user["fans"]))
    table.add_row("注册", user.get("created_at_str") or user.get("created_at", "")[:10], "关注", str(user["follows"]))

    panel = Panel(table, title=f"{user['username']} (UID={user['uid']})", border_style="green")
    console.print(panel)
    conn.close()


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    dispatch = {
        "hot":        cmd_hot,
        "user":       cmd_user,
        "post":       cmd_post,
        "search":     cmd_search,
        "profile":    cmd_profile,
        "sync-users": cmd_sync_users,
        "lookup":     cmd_lookup,
    }

    try:
        asyncio.run(dispatch[args.command](args))
    except KeyboardInterrupt:
        console.print("\n[yellow]已中断[/yellow]")
        sys.exit(0)


if __name__ == "__main__":
    main()
