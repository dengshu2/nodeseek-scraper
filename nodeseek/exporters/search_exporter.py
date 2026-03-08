"""
search_exporter.py — 搜索结果导出

支持格式：
  - json: 写入 output/search/ 目录
  - md:   写入 output/search/ 目录
"""
import json
from pathlib import Path
from typing import Optional

from nodeseek.models import SearchResponse
from nodeseek.exporters.utils import make_output_dir, make_timestamp

_SEARCH_OUTPUT_DIR = "output/search"


def export_search_json(
    resp: SearchResponse,
    keyword: Optional[str] = None,
    output_dir: Optional[str] = None,
) -> Path:
    """导出搜索结果为 JSON 文件"""
    d = make_output_dir(Path(_SEARCH_OUTPUT_DIR), output_dir)
    safe_kw = (keyword or "all").replace(" ", "_")
    path = d / f"search_{safe_kw}_{make_timestamp()}.json"

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
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def export_search_md(
    resp: SearchResponse,
    keyword: Optional[str] = None,
    output_dir: Optional[str] = None,
) -> Path:
    """导出搜索结果为 Markdown 文件（适合 AI 分析）"""
    d = make_output_dir(Path(_SEARCH_OUTPUT_DIR), output_dir)
    safe_kw = (keyword or "all").replace(" ", "_")
    path = d / f"search_{safe_kw}_{make_timestamp()}.md"

    lines = [
        f"# 搜索结果：{keyword or ''}",
        f"",
        f"共 {resp.total} 条，显示 {len(resp.results)} 条",
        f"",
    ]
    for i, r in enumerate(resp.results, 1):
        pub = r.pub_date[:16].replace("T", " ") if r.pub_date else ""
        lines += [
            f"## {i}. {r.title}",
            f"",
            f"- **作者**: {r.author}  **分类**: {r.category}  **时间**: {pub}",
            f"- **链接**: {r.link}",
        ]
        if r.description:
            lines.append(f"- **摘要**: {r.description}")
        lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")
    return path
