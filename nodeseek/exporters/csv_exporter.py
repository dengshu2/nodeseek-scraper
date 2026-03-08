"""
csv_exporter.py — CSV 格式导出
"""
import csv
from dataclasses import asdict
from pathlib import Path
from typing import Optional

from nodeseek import config
from nodeseek.models import HotPost, UserProfile
from nodeseek.exporters.utils import make_output_dir, make_timestamp


def export_hot_csv(posts: list[HotPost], rank_type: str, output_dir: Optional[str] = None) -> Path:
    """导出热榜为 CSV，返回文件路径"""
    d = make_output_dir(config.HOT_OUTPUT_DIR, output_dir)
    path = d / f"{rank_type}_{make_timestamp()}.csv"

    if not posts:
        path.write_text("", encoding="utf-8")
        return path

    fieldnames = list(asdict(posts[0]).keys())
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for p in posts:
            writer.writerow(asdict(p))

    return path


def export_user_csv(profile: UserProfile, output_dir: Optional[str] = None) -> Path:
    """导出用户评论为 CSV，返回文件路径"""
    d = make_output_dir(config.USER_OUTPUT_DIR, output_dir)
    path = d / f"{profile.username}.csv"

    if not profile.comments:
        path.write_text("", encoding="utf-8")
        return path

    fieldnames = list(asdict(profile.comments[0]).keys())
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for c in profile.comments:
            writer.writerow(asdict(c))

    return path
