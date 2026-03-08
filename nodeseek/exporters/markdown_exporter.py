"""
markdown_exporter.py — Markdown 格式导出
"""
from datetime import datetime
from pathlib import Path
from typing import Optional

from nodeseek import config
from nodeseek.models import UserProfile
from nodeseek.exporters.utils import make_output_dir


def export_user_md(profile: UserProfile, output_dir: Optional[str] = None) -> Path:
    """导出用户评论为 Markdown（适合 AI 分析）"""
    d = make_output_dir(config.USER_OUTPUT_DIR, output_dir)
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
    d = make_output_dir(config.POST_OUTPUT_DIR, output_dir)
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

    # 主帖图片
    if detail.images:
        lines += ["## 正文图片", ""]
        for img_url in detail.images:
            lines.append(f"![]({img_url})")
        lines.append("")

    # 主帖贴纸
    if detail.stickers:
        lines += [f"**贴纸**: {', '.join(detail.stickers)}", ""]

    # 主帖外链
    if detail.links:
        lines += ["## 正文外链", ""]
        for lk in detail.links:
            text = lk.get("text") or lk.get("url", "")
            lines.append(f"- [{text}]({lk['url']})")
        lines.append("")

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
            # 评论图片
            if c.images:
                for img_url in c.images:
                    lines.append(f"![]({img_url})")
                lines.append("")
            # 评论贴纸
            if c.stickers:
                lines.append(f"*贴纸: {', '.join(c.stickers)}*")
                lines.append("")
            # 评论外链
            if c.links:
                for lk in c.links:
                    text = lk.get("text") or lk.get("url", "")
                    lines.append(f"🔗 [{text}]({lk['url']})")
                lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")
    return path
