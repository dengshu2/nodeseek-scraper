"""
table_printer.py — 终端表格输出 (--format table)
"""
from datetime import datetime

from rich.console import Console
from rich.table import Table
from rich import box

from nodeseek.models import HotPost

console = Console()


def print_hot_table(posts: list[HotPost], rank_type: str) -> None:
    """在终端以表格形式渲染热榜数据"""
    label = {"hot": "实时热榜", "daily": "日榜", "weekly": "周榜"}.get(rank_type, rank_type)

    table = Table(
        title=f"NodeSeek {label}  (共 {len(posts)} 条)",
        box=box.ROUNDED,
        show_lines=False,
        highlight=True,
        header_style="bold cyan",
    )

    table.add_column("#",        style="dim",    width=4,  justify="right")
    table.add_column("标题",                      min_width=30, no_wrap=False)
    table.add_column("作者",     style="green",  width=14)
    table.add_column("板块",     style="yellow", width=8)
    table.add_column("评论",     justify="right", width=6)
    table.add_column("浏览",     justify="right", width=7)
    table.add_column("评分",     justify="right", width=8, style="magenta")
    table.add_column("发布时间", style="dim",    width=11)

    for i, p in enumerate(posts, 1):
        ts = datetime.fromtimestamp(p.timestamp).strftime("%m-%d %H:%M") if p.timestamp else "-"
        table.add_row(
            str(i),
            f"[link=https://www.nodeseek.com/post-{p.id}-1]{p.title}[/link]",
            p.author,
            p.category,
            str(p.comments),
            str(p.views),
            f"{p.score:.1f}",
            ts,
        )

    console.print(table)
