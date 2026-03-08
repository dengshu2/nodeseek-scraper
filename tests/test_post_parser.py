"""
test_post_parser.py — 解析器单元测试

使用模拟 HTML（贴近真实 NodeSeek DOM 结构）验证：
1. 主帖解析（标题、作者、时间、内容）
2. 评论解析（楼层、作者、是否楼主）
3. 图片提取（区分贴纸 vs 正文图片）
4. 外部链接提取（过滤站内链接）
5. 楼层范围过滤（排除热门回复跨页插入）
6. 作者解析 fallback 链（/space/ 链接 → author-name → img[alt]）
7. 第 2+ 页解析（只返回评论）
8. 分页检测（a.pager-next）
"""
import pytest
from nodeseek.parsers.post_parser import parse_post_page

# ──────────────────────────────────────────────────────────────
# 测试用 HTML 片段
# ──────────────────────────────────────────────────────────────

BASE_POST_HTML = """<!DOCTYPE html>
<html>
<head><title>Test</title></head>
<body>
<div id="nsk-body-left">
  <div class="post-title"><h1>这是帖子标题</h1></div>
  <a class="post-category">技术交流</a>

  <!-- 主帖（id=0） -->
  <div class="nsk-post-wrapper">
    <div class="content-item" id="0">
      <div class="nsk-content-meta-info">
        <a href="/space/12345">alice</a>
        <div class="date-created"><time datetime="2024-01-01T10:00:00Z">2024-01-01</time></div>
      </div>
      <article class="post-content">
        <p>这是主帖内容，很精彩。</p>
        <img src="https://img.nodeseek.com/picture.jpg" alt="图片">
        <img src="https://img.nodeseek.com/static/image/sticker/like.png" alt="点赞">
        <a href="https://github.com/example/repo">GitHub 仓库</a>
        <a href="https://www.nodeseek.com/post-123-1">站内帖子</a>
      </article>
    </div>
  </div>

  <!-- 评论列表 -->
  <div class="comment-container">
    <div class="content-item" id="1">
      <div class="nsk-content-meta-info">
        <a href="/space/22222">bob</a>
        <span class="is-poster"></span>
        <div class="date-created"><time datetime="2024-01-01T10:05:00Z">2024-01-01</time></div>
      </div>
      <a class="floor-link">#1</a>
      <article class="post-content">
        <p>楼主回复自己，带图片</p>
        <img src="https://cdn.example.com/image1.png" alt="">
      </article>
    </div>

    <div class="content-item" id="2">
      <div class="nsk-content-meta-info">
        <a href="/space/33333">charlie</a>
        <div class="date-created"><time datetime="2024-01-01T10:10:00Z">2024-01-01</time></div>
      </div>
      <a class="floor-link">#2</a>
      <article class="post-content">
        <p>普通回复，带外链</p>
        <a href="https://example.com/page">外部资源</a>
      </article>
    </div>

    <!-- 热门回复（楼层 42，跨页插入，应被过滤） -->
    <div class="content-item" id="42">
      <div class="nsk-content-meta-info">
        <a href="/space/99999">hot_user</a>
        <div class="date-created"><time datetime="2024-01-05T08:00:00Z">2024-01-05</time></div>
      </div>
      <a class="floor-link">#42</a>
      <article class="post-content"><p>热门回复，楼层越界，应被过滤</p></article>
    </div>
  </div>
</div>
</body>
</html>"""

PAGE2_HTML = """<!DOCTYPE html>
<html>
<body>
<div id="nsk-body-left">
  <a class="pager-next" href="/post-999-3">下一页</a>
  <div class="comment-container">
    <div class="content-item" id="11">
      <div class="nsk-content-meta-info">
        <a href="/space/55555">dave</a>
        <div class="date-created"><time datetime="2024-01-02T09:00:00Z">2024-01-02</time></div>
      </div>
      <a class="floor-link">#11</a>
      <article class="post-content"><p>第2页第1条评论</p></article>
    </div>
    <div class="content-item" id="12">
      <div class="nsk-content-meta-info">
        <a href="/space/66666">eve</a>
        <div class="date-created"><time datetime="2024-01-02T09:05:00Z">2024-01-02</time></div>
      </div>
      <a class="floor-link">#12</a>
      <article class="post-content"><p>第2页第2条评论</p></article>
    </div>
    <!-- 越界楼层，应被过滤 -->
    <div class="content-item" id="5">
      <div class="nsk-content-meta-info">
        <a href="/space/77777">old_post</a>
        <div class="date-created"><time datetime="2024-01-01T15:00:00Z">2024-01-01</time></div>
      </div>
      <a class="floor-link">#5</a>
      <article class="post-content"><p>第1页的楼层，不应出现在第2页</p></article>
    </div>
  </div>
</div>
</body>
</html>"""

FALLBACK_AUTHOR_HTML = """<!DOCTYPE html>
<html>
<body>
<div id="nsk-body-left">
  <div class="post-title"><h1>Fallback 测试帖</h1></div>
  <div class="nsk-post-wrapper">
    <div class="content-item" id="0">
      <div class="nsk-content-meta-info">
        <!-- 没有 /space/ 链接，靠 author-name fallback -->
        <a class="author-name" href="/member/frank">frank</a>
        <div class="date-created"><time datetime="2024-02-01T00:00:00Z">2024-02-01</time></div>
      </div>
      <article class="post-content"><p>fallback 测试</p></article>
    </div>
  </div>
  <div class="comment-container">
    <div class="content-item" id="1">
      <div class="nsk-content-meta-info">
        <!-- img[alt] fallback -->
        <a href="/space/88888"><img alt="grace" src="/avatar.png"></a>
        <div class="date-created"><time datetime="2024-02-01T01:00:00Z">2024-02-01</time></div>
      </div>
      <a class="floor-link">#1</a>
      <article class="post-content"><p>img alt fallback 评论</p></article>
    </div>
  </div>
</div>
</body>
</html>"""

# ──────────────────────────────────────────────────────────────
# 测试用例
# ──────────────────────────────────────────────────────────────

class TestPage1Parsing:
    """第1页完整解析测试"""

    def setup_method(self):
        self.result = parse_post_page(
            html=BASE_POST_HTML,
            post_id=999,
            url="https://www.nodeseek.com/post-999-1",
            page_num=1,
            include_comments=True,
        )

    def test_parse_returns_result(self):
        assert self.result is not None

    def test_title(self):
        assert self.result.title == "这是帖子标题"

    def test_author(self):
        assert self.result.author == "alice"

    def test_post_time(self):
        assert "2024-01-01T10:00:00" in self.result.post_time

    def test_category(self):
        assert self.result.category == "技术交流"

    def test_main_post_image_extracted(self):
        """正文图片应被提取"""
        assert "https://img.nodeseek.com/picture.jpg" in self.result.images

    def test_main_post_sticker_filtered(self):
        """贴纸不应出现在 images，应在 stickers"""
        sticker_url = "https://img.nodeseek.com/static/image/sticker/like.png"
        assert sticker_url not in self.result.images
        assert "点赞" in self.result.stickers

    def test_main_post_external_link(self):
        """外部链接应被提取"""
        urls = [lk["url"] for lk in self.result.links]
        assert "https://github.com/example/repo" in urls

    def test_main_post_internal_link_excluded(self):
        """站内链接不应被提取"""
        urls = [lk["url"] for lk in self.result.links]
        assert not any("nodeseek.com" in u for u in urls)

    def test_no_next_page(self):
        """第1页无 pager-next，has_next 应为 False"""
        assert self.result.has_next_page is False


class TestCommentParsing:
    """评论解析测试"""

    def setup_method(self):
        self.result = parse_post_page(
            html=BASE_POST_HTML,
            post_id=999,
            url="https://www.nodeseek.com/post-999-1",
            page_num=1,
            include_comments=True,
        )
        self.comments = self.result.comments

    def test_comment_count(self):
        """第1页应有2条评论（热门回复#42被过滤）"""
        assert len(self.comments) == 2

    def test_floor_filter_excludes_out_of_range(self):
        """楼层范围过滤：#42 应被排除"""
        floors = [c.floor for c in self.comments]
        assert "#42" not in floors
        assert "hot_user" not in [c.author for c in self.comments]

    def test_comment_1_author(self):
        assert self.comments[0].author == "bob"
        assert self.comments[0].floor == "#1"

    def test_comment_2_author(self):
        assert self.comments[1].author == "charlie"
        assert self.comments[1].floor == "#2"

    def test_comment_image(self):
        """评论里的图片应被提取"""
        c1 = self.comments[0]
        assert "https://cdn.example.com/image1.png" in c1.images

    def test_comment_external_link(self):
        """评论里的外链应被提取"""
        c2 = self.comments[1]
        urls = [lk["url"] for lk in c2.links]
        assert "https://example.com/page" in urls

    def test_is_poster_flag(self):
        """is-poster class 应被识别"""
        c1 = self.comments[0]
        assert c1.is_poster is True
        c2 = self.comments[1]
        assert c2.is_poster is False


class TestPage2Parsing:
    """第2页解析测试"""

    def setup_method(self):
        self.result = parse_post_page(
            html=PAGE2_HTML,
            post_id=999,
            url="https://www.nodeseek.com/post-999-2",
            page_num=2,
            include_comments=True,
        )

    def test_has_next_page(self):
        """第2页有 pager-next，should be True"""
        assert self.result.has_next_page is True

    def test_comment_count_page2(self):
        """第2页：楼层11-20，#5 被过滤，只剩2条"""
        assert len(self.result.comments) == 2

    def test_floor_range_page2(self):
        """第2页楼层范围是 11-20"""
        floors = [c.floor for c in self.result.comments]
        assert "#11" in floors
        assert "#12" in floors
        assert "#5" not in floors

    def test_page2_no_title(self):
        """第2页不解析标题"""
        assert self.result.title == ""


class TestAuthorFallback:
    """作者解析 fallback 测试"""

    def setup_method(self):
        self.result = parse_post_page(
            html=FALLBACK_AUTHOR_HTML,
            post_id=888,
            url="https://www.nodeseek.com/post-888-1",
            page_num=1,
            include_comments=True,
        )

    def test_author_name_fallback(self):
        """主帖无 /space/ 链接时，fallback 到 a.author-name"""
        assert self.result.author == "frank"

    def test_img_alt_fallback(self):
        """评论作者无文字链接时，fallback 到 img[alt]"""
        assert len(self.result.comments) == 1
        assert self.result.comments[0].author == "grace"


class TestNoComments:
    """不含评论模式"""

    def test_include_comments_false(self):
        result = parse_post_page(
            html=BASE_POST_HTML,
            post_id=999,
            url="https://www.nodeseek.com/post-999-1",
            page_num=1,
            include_comments=False,
        )
        assert result is not None
        assert result.comments == []


class TestInvalidHtml:
    """异常 HTML 处理"""

    def test_empty_html_returns_none(self):
        result = parse_post_page(
            html="<html><body></body></html>",
            post_id=1,
            url="https://www.nodeseek.com/post-1-1",
            page_num=1,
        )
        assert result is None

    def test_no_h1_returns_none(self):
        html = "<html><body><div class='content-item' id='0'><article class='post-content'>text</article></div></body></html>"
        result = parse_post_page(
            html=html,
            post_id=1,
            url="https://www.nodeseek.com/post-1-1",
            page_num=1,
        )
        assert result is None
