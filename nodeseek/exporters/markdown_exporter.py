"""
markdown_exporter.py — Markdown 格式导出
"""
from datetime import datetime
from pathlib import Path
from typing import Optional

from nodeseek import config
from nodeseek.models import UserProfile


def _output_dir(subdir: Path, override: Optional[str]) -> Path:
    d = Path(override) if override else subdir
    d.mkdir(parents=True, exist_ok=True)
    return d


def export_user_md(profile: UserProfile, output_dir: Optional[str] = None) -> Path:
    """导出用户评论为 Markdown（适合 AI 分析）"""
    d = _output_dir(config.USER_OUTPUT_DIR, output_dir)
    path = d / f"{profile.username}.md"

    lines = [
        f"# {profile.username} 的评论记录",
        f"",
        f"- **UID**: {profile.uid}",
        f"- **用户名**: {profile.username}",
        f"- **总评论数**: {profile.total_comments}",
        f"- **导出时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"",
        f"---",
        f"",
    ]

    for i, c in enumerate(profile.comments, 1):
        post_url = f"{config.BASE_URL}/post-{c.post_id}-1"
        lines += [
            f"## [{i}] {c.post_title}",
            f"",
            f"- **帖子 ID**: [{c.post_id}]({post_url})",
            f"- **楼层**: #{c.floor_id}",
            f"- **赞数**: {c.rank}",
            f"",
            f"> {c.content}",
            f"",
            f"---",
            f"",
        ]

    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def export_post_md(detail, output_dir: Optional[str] = None) -> Path:
    """导出帖子详情为 Markdown"""
    d = _output_dir(config.POST_OUTPUT_DIR, output_dir)
    path = d / f"post_{detail.id}.md"

    lines = [
        f"# {detail.title}",
        f"",
        f"- **帖子 ID**: [{detail.id}]({detail.url})",
        f"- **作者**: [{detail.author}]({detail.author_url})",
        f"- **板块**: {detail.category}",
        f"- **发帖时间**: {detail.post_time}",
        f"- **导出时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"",
        f"## 正文",
        f"",
        detail.content,
        f"",
        f"---",
        f"",
    ]

    if detail.comments:
        lines += [f"## 评论（共 {len(detail.comments)} 条）", f""]
        for c in detail.comments:
            poster_tag = " `楼主`" if c.is_poster else ""
            lines += [
                f"### {c.floor} {c.author}{poster_tag}",
                f"",
                f"*{c.post_time}*",
                f"",
                f"> {c.content}",
                f"",
            ]

    path.write_text("\n".join(lines), encoding="utf-8")
    return path
