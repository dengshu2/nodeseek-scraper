"""
test_models.py — 数据模型单元测试

验证所有 dataclass 模型的：
1. 基本实例化和字段默认值
2. 可选字段
3. dataclass 序列化 (asdict)
"""
from dataclasses import asdict

from nodeseek.models import (
    HotPost,
    Comment,
    PostDetail,
    UserBasicInfo,
    UserComment,
    UserProfile,
    SearchResult,
    SearchResponse,
)


class TestHotPost:
    def test_basic_creation(self):
        p = HotPost(
            id=1, title="test", author="alice", author_id=100,
            timestamp=1700000000, views=50, comments=3,
            summary="短摘要", category="tech", score=9.5, rank_type="hot",
        )
        assert p.id == 1
        assert p.title == "test"
        assert p.score == 9.5
        assert p.rank_type == "hot"

    def test_asdict(self):
        p = HotPost(
            id=2, title="t", author="b", author_id=1,
            timestamp=0, views=0, comments=0,
            summary="", category="", score=0.0, rank_type="daily",
        )
        d = asdict(p)
        assert d["id"] == 2
        assert d["rank_type"] == "daily"
        assert isinstance(d, dict)


class TestComment:
    def test_defaults(self):
        c = Comment(
            floor="#1", author="bob", author_url="/space/1",
            content="hello", post_time="2024-01-01T00:00:00Z",
            is_poster=False,
        )
        assert c.images == []
        assert c.stickers == []
        assert c.links == []

    def test_with_media(self):
        c = Comment(
            floor="#2", author="charlie", author_url="/space/2",
            content="带图", post_time="2024-01-01",
            is_poster=True,
            images=["https://img.example.com/1.jpg"],
            stickers=["thumbsup"],
            links=[{"text": "外链", "url": "https://example.com"}],
        )
        assert len(c.images) == 1
        assert c.stickers == ["thumbsup"]
        assert c.links[0]["url"] == "https://example.com"


class TestPostDetail:
    def test_defaults(self):
        d = PostDetail(
            id=100, title="帖子标题", url="https://example.com/post-100-1",
            author="alice", author_url="/space/1",
            category="tech", post_time="2024-01-01",
            content="正文", content_html="<p>正文</p>",
        )
        assert d.images == []
        assert d.stickers == []
        assert d.links == []
        assert d.comments == []
        assert d.has_next_page is False

    def test_with_comments(self):
        c = Comment(
            floor="#1", author="b", author_url="",
            content="评论", post_time="", is_poster=False,
        )
        d = PostDetail(
            id=1, title="t", url="u", author="a", author_url="",
            category="", post_time="", content="", content_html="",
            comments=[c],
        )
        assert len(d.comments) == 1


class TestUserBasicInfo:
    def test_creation(self):
        info = UserBasicInfo(
            uid=36700, username="shaw-deng", rank=5,
            coin=100, stardust=50, n_post=10, n_comment=200,
            follows=3, fans=8, created_at="2023-06-01T00:00:00Z",
            created_at_str="2023年06月01日",
        )
        assert info.uid == 36700
        assert info.username == "shaw-deng"
        assert info.rank == 5
        assert info.fans == 8


class TestUserComment:
    def test_creation(self):
        c = UserComment(
            post_id=637248, post_title="测试帖",
            floor_id=5, content="评论内容", rank=3,
        )
        assert c.post_id == 637248
        assert c.rank == 3


class TestUserProfile:
    def test_defaults(self):
        p = UserProfile(uid=1, username="test", total_comments=0)
        assert p.comments == []
        assert p.info is None

    def test_with_info(self):
        info = UserBasicInfo(
            uid=1, username="test", rank=1,
            coin=0, stardust=0, n_post=0, n_comment=0,
            follows=0, fans=0, created_at="", created_at_str="",
        )
        p = UserProfile(uid=1, username="test", total_comments=5, info=info)
        assert p.info.uid == 1

    def test_asdict_with_info(self):
        """序列化完整的 UserProfile（包含嵌套 info）"""
        info = UserBasicInfo(
            uid=1, username="u", rank=0,
            coin=0, stardust=0, n_post=0, n_comment=0,
            follows=0, fans=0, created_at="", created_at_str="",
        )
        p = UserProfile(
            uid=1, username="u", total_comments=1,
            comments=[UserComment(
                post_id=1, post_title="t", floor_id=1,
                content="c", rank=0,
            )],
            info=info,
        )
        d = asdict(p)
        assert d["info"]["uid"] == 1
        assert len(d["comments"]) == 1


class TestSearchResult:
    def test_creation(self):
        r = SearchResult(
            post_id=123, title="搜索帖子",
            description="描述", category="trade",
            author="alice", pub_date="2024-01-01T00:00:00Z",
            link="https://www.nodeseek.com/post-123-1",
        )
        assert r.post_id == 123
        assert r.category == "trade"


class TestSearchResponse:
    def test_defaults(self):
        resp = SearchResponse(total=100, skip=0, limit=20)
        assert resp.results == []

    def test_with_results(self):
        r = SearchResult(
            post_id=1, title="t", description="d",
            category="c", author="a", pub_date="", link="",
        )
        resp = SearchResponse(total=1, skip=0, limit=20, results=[r])
        assert len(resp.results) == 1
        assert resp.total == 1
