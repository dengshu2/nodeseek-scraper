"""
test_exporters.py — 导出器模块测试

验证所有导出器：
1. JSON 导出（热榜、帖子、用户评论、用户资料）
2. CSV 导出（热榜、用户评论）
3. Markdown 导出（用户评论、帖子详情）
4. 搜索结果导出（JSON、Markdown）
5. 自定义输出目录
6. 空数据处理
7. 导出工具函数
"""
import json
import csv
from pathlib import Path

import pytest

from nodeseek.models import (
    HotPost, PostDetail, Comment, UserProfile, UserComment,
    UserBasicInfo, SearchResult, SearchResponse,
)
from nodeseek.exporters.json_exporter import (
    export_hot, export_post, export_user, export_profile,
)
from nodeseek.exporters.csv_exporter import export_hot_csv, export_user_csv
from nodeseek.exporters.markdown_exporter import export_user_md, export_post_md
from nodeseek.exporters.search_exporter import export_search_json, export_search_md
from nodeseek.exporters.utils import make_output_dir, make_timestamp


# ── Fixtures ──────────────────────────────────────────────────

@pytest.fixture
def sample_hot_posts():
    return [
        HotPost(
            id=1, title="热帖一", author="alice", author_id=100,
            timestamp=1700000000, views=500, comments=30,
            summary="摘要一", category="tech", score=9.5, rank_type="hot",
        ),
        HotPost(
            id=2, title="热帖二", author="bob", author_id=200,
            timestamp=1700001000, views=300, comments=15,
            summary="摘要二", category="daily", score=7.2, rank_type="hot",
        ),
    ]


@pytest.fixture
def sample_post_detail():
    return PostDetail(
        id=999, title="测试帖子", url="https://www.nodeseek.com/post-999-1",
        author="alice", author_url="https://www.nodeseek.com/space/12345",
        category="技术交流", post_time="2024-01-01T10:00:00Z",
        content="这是正文内容", content_html="<p>这是正文内容</p>",
        images=["https://img.example.com/pic.jpg"],
        stickers=["thumbsup"],
        links=[{"text": "GitHub", "url": "https://github.com/example"}],
        comments=[
            Comment(
                floor="#1", author="bob", author_url="/space/222",
                content="好帖！", post_time="2024-01-01T10:05:00Z",
                is_poster=False,
                images=["https://cdn.example.com/img1.png"],
            ),
            Comment(
                floor="#2", author="charlie", author_url="/space/333",
                content="同意", post_time="2024-01-01T10:10:00Z",
                is_poster=True,
                stickers=["laugh"],
                links=[{"text": "参考", "url": "https://example.com/ref"}],
            ),
        ],
    )


@pytest.fixture
def sample_user_profile():
    info = UserBasicInfo(
        uid=36700, username="shaw-deng", rank=5,
        coin=100, stardust=50, n_post=10, n_comment=200,
        follows=3, fans=8, created_at="2023-06-01T00:00:00Z",
        created_at_str="2023年06月01日",
    )
    return UserProfile(
        uid=36700, username="shaw-deng", total_comments=2,
        comments=[
            UserComment(post_id=1, post_title="帖一", floor_id=5, content="评论一", rank=3),
            UserComment(post_id=2, post_title="帖二", floor_id=1, content="评论二", rank=0),
        ],
        info=info,
    )


@pytest.fixture
def sample_search_response():
    return SearchResponse(
        total=100, skip=0, limit=20,
        results=[
            SearchResult(
                post_id=1, title="搜索结果一", description="描述一",
                category="trade", author="alice",
                pub_date="2024-01-01T00:00:00Z",
                link="https://www.nodeseek.com/post-1-1",
            ),
            SearchResult(
                post_id=2, title="搜索结果二", description="",
                category="tech", author="bob",
                pub_date="2024-01-02T12:30:00Z",
                link="https://www.nodeseek.com/post-2-1",
            ),
        ],
    )


# ── JSON Exporter Tests ──────────────────────────────────────

class TestJsonExporter:
    def test_export_hot(self, sample_hot_posts, tmp_path):
        path = export_hot(sample_hot_posts, "hot", output_dir=str(tmp_path))
        assert path.exists()
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["rank_type"] == "hot"
        assert data["count"] == 2
        assert len(data["posts"]) == 2
        assert data["posts"][0]["title"] == "热帖一"
        assert "generated_at" in data

    def test_export_post(self, sample_post_detail, tmp_path):
        path = export_post(sample_post_detail, output_dir=str(tmp_path))
        assert path.exists()
        assert path.name == "post_999.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["id"] == 999
        assert data["title"] == "测试帖子"
        assert len(data["comments"]) == 2
        assert "generated_at" in data

    def test_export_user(self, sample_user_profile, tmp_path):
        path = export_user(sample_user_profile, output_dir=str(tmp_path))
        assert path.exists()
        assert path.name == "shaw-deng.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["uid"] == 36700
        assert data["total_comments"] == 2
        assert len(data["comments"]) == 2
        # profile info 应该被附带
        assert "profile" in data
        assert data["profile"]["rank"] == 5

    def test_export_user_without_info(self, tmp_path):
        """无 info 的 profile 不应包含 profile 字段"""
        profile = UserProfile(uid=1, username="test", total_comments=0)
        path = export_user(profile, output_dir=str(tmp_path))
        data = json.loads(path.read_text(encoding="utf-8"))
        assert "profile" not in data

    def test_export_profile(self, tmp_path):
        info = UserBasicInfo(
            uid=1, username="test_user", rank=3,
            coin=50, stardust=20, n_post=5, n_comment=100,
            follows=2, fans=10, created_at="2024-01-01",
            created_at_str="2024年01月01日",
        )
        path = export_profile(info, output_dir=str(tmp_path))
        assert path.exists()
        assert path.name == "test_user_profile.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["uid"] == 1
        assert data["rank"] == 3

    def test_export_hot_empty(self, tmp_path):
        """空列表也应正常导出"""
        path = export_hot([], "hot", output_dir=str(tmp_path))
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["count"] == 0
        assert data["posts"] == []


# ── CSV Exporter Tests ────────────────────────────────────────

class TestCsvExporter:
    def test_export_hot_csv(self, sample_hot_posts, tmp_path):
        path = export_hot_csv(sample_hot_posts, "daily", output_dir=str(tmp_path))
        assert path.exists()
        assert path.suffix == ".csv"

        with path.open("r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        assert len(rows) == 2
        assert rows[0]["title"] == "热帖一"
        assert rows[0]["rank_type"] == "hot"

    def test_export_hot_csv_empty(self, tmp_path):
        """空列表应生成空文件"""
        path = export_hot_csv([], "hot", output_dir=str(tmp_path))
        assert path.exists()
        assert path.read_text(encoding="utf-8") == ""

    def test_export_user_csv(self, sample_user_profile, tmp_path):
        path = export_user_csv(sample_user_profile, output_dir=str(tmp_path))
        assert path.exists()
        assert path.name == "shaw-deng.csv"

        with path.open("r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        assert len(rows) == 2
        assert rows[0]["post_title"] == "帖一"

    def test_export_user_csv_no_comments(self, tmp_path):
        profile = UserProfile(uid=1, username="empty", total_comments=0)
        path = export_user_csv(profile, output_dir=str(tmp_path))
        assert path.read_text(encoding="utf-8") == ""


# ── Markdown Exporter Tests ───────────────────────────────────

class TestMarkdownExporter:
    def test_export_user_md(self, sample_user_profile, tmp_path):
        path = export_user_md(sample_user_profile, output_dir=str(tmp_path))
        assert path.exists()
        assert path.name == "shaw-deng.md"

        text = path.read_text(encoding="utf-8")
        assert "shaw-deng 的评论记录" in text
        assert "UID" in text
        assert "36700" in text
        assert "帖一" in text
        assert "评论一" in text
        # 应包含用户资料表格
        assert "用户资料" in text
        assert "Lv 5" in text

    def test_export_user_md_without_info(self, tmp_path):
        """无 info 的 profile 不应包含用户资料部分"""
        profile = UserProfile(
            uid=1, username="noinfo", total_comments=1,
            comments=[UserComment(
                post_id=1, post_title="t", floor_id=1, content="c", rank=0,
            )],
        )
        path = export_user_md(profile, output_dir=str(tmp_path))
        text = path.read_text(encoding="utf-8")
        assert "用户资料" not in text

    def test_export_post_md(self, sample_post_detail, tmp_path):
        path = export_post_md(sample_post_detail, output_dir=str(tmp_path))
        assert path.exists()
        assert path.name == "post_999.md"

        text = path.read_text(encoding="utf-8")
        assert "测试帖子" in text
        assert "alice" in text
        assert "这是正文内容" in text
        assert "bob" in text
        assert "好帖！" in text
        # 应包含图片和链接
        assert "pic.jpg" in text
        assert "GitHub" in text
        # 评论数标题
        assert "评论（共 2 条）" in text
        # 楼主标记
        assert "楼主" in text


# ── Search Exporter Tests ─────────────────────────────────────

class TestSearchExporter:
    def test_export_search_json(self, sample_search_response, tmp_path):
        path = export_search_json(
            sample_search_response, keyword="test", output_dir=str(tmp_path),
        )
        assert path.exists()
        assert "search_test_" in path.name

        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["total"] == 100
        assert len(data["data"]) == 2
        assert data["data"][0]["title"] == "搜索结果一"

    def test_export_search_json_no_keyword(self, sample_search_response, tmp_path):
        """无关键词时应使用 'all' 作为文件名部分"""
        path = export_search_json(
            sample_search_response, keyword=None, output_dir=str(tmp_path),
        )
        assert "search_all_" in path.name

    def test_export_search_md(self, sample_search_response, tmp_path):
        path = export_search_md(
            sample_search_response, keyword="claude", output_dir=str(tmp_path),
        )
        assert path.exists()

        text = path.read_text(encoding="utf-8")
        assert "搜索结果：claude" in text
        assert "搜索结果一" in text
        assert "搜索结果二" in text
        assert "共 100 条" in text

    def test_export_search_md_empty_description(self, sample_search_response, tmp_path):
        """空描述不应生成摘要行"""
        path = export_search_md(
            sample_search_response, keyword="test", output_dir=str(tmp_path),
        )
        text = path.read_text(encoding="utf-8")
        # 第二个结果 description 为空，不应有其摘要行
        lines = text.split("\n")
        # 找到第二个结果的标题位置
        idx = next(i for i, l in enumerate(lines) if "搜索结果二" in l)
        # 往下找，不应有 **摘要**: 行（直到下一条或结尾）
        after_lines = lines[idx+1:idx+5]
        assert not any("**摘要**:" in l and l.strip() == "- **摘要**:" for l in after_lines)


# ── Utils Tests ───────────────────────────────────────────────

class TestExporterUtils:
    def test_make_output_dir_default(self, tmp_path):
        subdir = tmp_path / "test_sub"
        result = make_output_dir(subdir, None)
        assert result == subdir
        assert result.exists()

    def test_make_output_dir_override(self, tmp_path):
        override = str(tmp_path / "custom_dir")
        result = make_output_dir(Path("default"), override)
        assert result == Path(override)
        assert result.exists()

    def test_make_timestamp_format(self):
        ts = make_timestamp()
        # 格式: YYYYMMDD_HHMMSS
        assert len(ts) == 15
        assert ts[8] == "_"
        # 年月日部分应是数字
        assert ts[:8].isdigit()
        assert ts[9:].isdigit()
