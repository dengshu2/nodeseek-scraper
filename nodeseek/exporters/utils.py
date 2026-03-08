"""
exporters/utils.py — 导出器公共工具函数

原 json_exporter / csv_exporter / markdown_exporter 各自重复定义的
_output_dir() 和 _ts() 提取到这里统一维护。
"""
from datetime import datetime
from pathlib import Path
from typing import Optional


def make_output_dir(subdir: Path, override: Optional[str]) -> Path:
    """解析输出目录，不存在时自动创建，返回最终 Path"""
    d = Path(override) if override else subdir
    d.mkdir(parents=True, exist_ok=True)
    return d


def make_timestamp() -> str:
    """返回当前时间戳字符串，格式：YYYYMMDD_HHMMSS"""
    return datetime.now().strftime("%Y%m%d_%H%M%S")
