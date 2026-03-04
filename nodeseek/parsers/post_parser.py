"""
post_parser.py — 帖子 HTML 解析

从 Playwright 渲染的 HTML 中提取帖子标题、正文、评论。

DOM 结构（已验证）:
  第 1 页:
    div.post-title > h1               → 标题
    div.content-item (第一个)         → 主帖
      a.author-name                  → 作者
      .date-created time[datetime]   → 时间
      article.post-content           → 正文
    div.content-item (后续，≤10个)    → 评论
  第 2+ 页:
    div.content-item (全部≤10个)      → 评论（无主帖）
  分页:
    a.pager-next                      → 下一页链接（存在则有下一页）
"""
from typing import Optional

from lxml import html as lhtml

from nodeseek.models import Comment, PostDetail
from nodeseek import config


def parse_post_page(
    html: str,
    post_id: int,
    url: str,
    page_num: int = 1,
    include_comments: bool = True,
) -> Optional[PostDetail]:
    """
    解析帖子单页 HTML。

    - page_num=1: 提取标题、主帖正文、本页评论
    - page_num>1: 只提取本页评论（通过 PostDetail.comments 返回）
    - 结果对象上附加 _has_next_page 属性供 fetcher 翻页判断

    解析失败返回 None。
    """
    doc = lhtml.fromstring(html)

    # ── 检测是否有下一页 ───────────────────────────────────
    has_next = bool(doc.cssselect("a.pager-next"))

    # ── 获取所有 content-item ─────────────────────────────
    items = doc.cssselect(".content-item")
    if not items:
        return None

    # ── 第 1 页：解析主帖 ──────────────────────────────────
    if page_num == 1:
        title = _text(doc, "//h1") or _css_text(doc, "div.post-title")
        if not title:
            return None

        main = items[0]
        author = _css_text(main, "a.author-name")
        author_href = _css_attr(main, "a.author-name", "href")
        post_time = _css_attr(main, ".date-created time", "datetime")
        category = _css_text(doc, "a.post-category")

        content_el = main.cssselect("article.post-content")
        content_text = _inner_texts(content_el[0]) if content_el else ""
        content_html = lhtml.tostring(content_el[0], encoding="unicode") if content_el else ""

        # 本页评论（主帖之后的 content-item）
        comments = _parse_comments(items[1:]) if include_comments else []

        detail = PostDetail(
            id=post_id,
            title=title,
            url=url,
            author=author,
            author_url=_abs(author_href),
            category=category,
            post_time=post_time,
            content=content_text,
            content_html=content_html,
            comments=comments,
        )

    else:
        # ── 第 2+ 页：只返回评论，其他字段留空 ───────────────
        comments = _parse_comments(items) if include_comments else []
        detail = PostDetail(
            id=post_id,
            title="",
            url=url,
            author="",
            author_url="",
            category="",
            post_time="",
            content="",
            content_html="",
            comments=comments,
        )

    # 附加翻页标记（供 fetcher 使用）
    detail._has_next_page = has_next  # type: ignore[attr-defined]
    return detail


def parse_post_detail(
    html: str,
    post_id: int,
    url: str,
    include_comments: bool = True,
) -> Optional[PostDetail]:
    """向后兼容接口：仅解析第 1 页（不翻页）"""
    return parse_post_page(html, post_id, url, page_num=1, include_comments=include_comments)


# ── 内部工具 ──────────────────────────────────────────────

def _parse_comments(items) -> list[Comment]:
    """从 content-item 列表中批量解析评论"""
    comments = []
    for ci in items:
        floor = _css_text(ci, "a.floor-link")
        author = _css_text(ci, "a.author-name")
        if not author:
            continue  # 跳过无作者的空块

        author_href = _css_attr(ci, "a.author-name", "href")
        post_time = _css_attr(ci, ".date-created time", "datetime")
        is_poster = bool(ci.cssselect(".is-poster"))

        content_el = ci.cssselect("article.post-content")
        content = _inner_texts(content_el[0]) if content_el else ""

        comments.append(Comment(
            floor=floor,
            author=author,
            author_url=_abs(author_href),
            content=content,
            post_time=post_time,
            is_poster=is_poster,
        ))
    return comments


def _text(doc, xpath: str) -> str:
    els = doc.xpath(xpath)
    return (els[0].text_content() or "").strip() if els else ""


def _css_text(el, selector: str) -> str:
    found = el.cssselect(selector)
    return (found[0].text_content() or "").strip() if found else ""


def _css_attr(el, selector: str, attr: str) -> str:
    found = el.cssselect(selector)
    return (found[0].get(attr) or "").strip() if found else ""


def _inner_texts(el) -> str:
    return " ".join(t.strip() for t in el.itertext() if t.strip())


def _abs(href: str) -> str:
    if not href:
        return ""
    if href.startswith("http"):
        return href
    return config.BASE_URL + ("" if href.startswith("/") else "/") + href
