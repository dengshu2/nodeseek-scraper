"""
json_exporter.py — JSON 格式导出
"""
import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

from nodeseek import config
from nodeseek.models import HotPost, UserProfile


def _output_dir(subdir: Path, override: Optional[str]) -> Path:
    d = Path(override) if override else subdir
    d.mkdir(parents=True, exist_ok=True)
    return d


def _ts() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def export_hot(posts: list[HotPost], rank_type: str, output_dir: Optional[str] = None) -> Path:
    """导出热榜为 JSON，返回文件路径"""
    d = _output_dir(config.HOT_OUTPUT_DIR, output_dir)
    path = d / f"{rank_type}_{_ts()}.json"

    payload = {
        "rank_type": rank_type,
        "generated_at": datetime.now().isoformat(),
        "count": len(posts),
        "posts": [asdict(p) for p in posts],
    }

    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def export_user(profile: UserProfile, output_dir: Optional[str] = None) -> Path:
    """导出用户评论为 JSON，返回文件路径"""
    d = _output_dir(config.USER_OUTPUT_DIR, output_dir)
    path = d / f"{profile.username}.json"

    payload = {
        "uid": profile.uid,
        "username": profile.username,
        "total_comments": profile.total_comments,
        "generated_at": datetime.now().isoformat(),
        "comments": [asdict(c) for c in profile.comments],
    }

    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def export_post(detail, output_dir: Optional[str] = None) -> Path:
    """导出帖子详情为 JSON，返回文件路径"""
    from nodeseek.models import PostDetail
    d = _output_dir(config.POST_OUTPUT_DIR, output_dir)
    path = d / f"post_{detail.id}.json"

    payload = {
        "generated_at": datetime.now().isoformat(),
        **asdict(detail),
    }

    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
