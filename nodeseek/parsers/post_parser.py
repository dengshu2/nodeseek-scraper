"""
post_parser.py — 帖子 HTML 解析

从 Playwright 渲染的 HTML 中提取帖子标题、正文、评论。

DOM 结构（已验证）:
  第 1 页:
    div.post-title > h1               → 标题
    .content-item[id="0"]             → 主帖（楼层 0）
      .nsk-content-meta-info a[href^="/space/"] → 作者链接
      .date-created time[datetime]   → 时间
      article.post-content           → 正文
    #nsk-body-left .comment-container .content-item → 评论
  第 2+ 页:
    同上，但无主帖
  分页:
    a.pager-next                      → 下一页链接（存在则有下一页）
    [aria-label="pagination"]         → 分页控件（可解析总页数）

改进说明（参考 NodeGuaBot 用户脚本）:
  1. 评论容器精确化：用 #nsk-body-left .comment-container 作用域，避免误抓热门回复
  2. 楼层号：优先读 content-item[id] 属性（更直接），fallback 到 a.floor-link 文本
  3. 作者解析：优先 a[href^="/space/"]，fallback 到 a.author-name / img[alt]
  4. 图片提取：区分贴纸（/static/image/sticker/）与正文图片（含 data-src fallback）
  5. 外部链接提取：过滤站内链接，只保留外部 URL
  6. 楼层范围过滤：按 [(page-1)*10+1, page*10] 过滤跨页插入的热门回复
"""
from typing import Optional

from lxml import html as lhtml

from nodeseek.models import Comment, PostDetail
from nodeseek import config

# 每页评论数（实测值，也是 NodeSeek 固定规格）
COMMENTS_PER_PAGE = 10

# 贴纸图片 URL 路径标志
STICKER_PATH_MARKER = "/static/image/sticker/"


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

    # ── 第 1 页：解析主帖 ──────────────────────────────────
    if page_num == 1:
        title = _text(doc, "//h1") or _css_text(doc, "div.post-title")
        if not title:
            return None

        # 主帖：id="0" 的 content-item
        main_items = doc.cssselect('.content-item[id="0"]')
        if not main_items:
            # fallback: 取第一个 content-item
            main_items = doc.cssselect(".content-item")
        if not main_items:
            return None

        main = main_items[0]
        author = _pick_author(main)
        author_href = _css_attr(main, 'a[href^="/space/"]', "href") \
                      or _css_attr(main, "a.author-name", "href")
        post_time = _css_attr(main, ".date-created time", "datetime")
        category = _css_text(doc, "a.post-category")

        content_el = main.cssselect("article.post-content")
        content_text = _inner_texts(content_el[0]) if content_el else ""
        content_html = lhtml.tostring(content_el[0], encoding="unicode") if content_el else ""

        # 主帖图片/贴纸/外链
        post_images, post_stickers, post_links = _extract_media(
            content_el[0] if content_el else None,
            base_url=config.BASE_URL,
        )

        # 本页评论（精确作用域 + 楼层范围过滤）
        comments = _parse_comments(doc, page_num) if include_comments else []

        detail = PostDetail(
            id=post_id,
            title=title,
            url=url,
            author=author,
            author_url=_to_abs(author_href, config.BASE_URL),
            category=category,
            post_time=post_time,
            content=content_text,
            content_html=content_html,
            images=post_images,
            stickers=post_stickers,
            links=post_links,
            comments=comments,
        )

    else:
        # ── 第 2+ 页：只返回评论，其他字段留空 ───────────────
        comments = _parse_comments(doc, page_num) if include_comments else []
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

    detail.has_next_page = has_next
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

def _parse_comments(doc, page_num: int) -> list[Comment]:
    """
    从精确作用域内提取评论，并按楼层范围过滤。

    作用域优先：#nsk-body-left .comment-container .content-item
    Fallback：全页所有 .content-item（排除 id="0" 的主帖）

    楼层范围过滤：只保留属于当前页的楼层号，防止跨页插入的热门回复污染。
    """
    # 精确作用域
    items = doc.cssselect("#nsk-body-left .comment-container .content-item")
    if not items:
        # fallback：全部 content-item，排除主帖
        all_items = doc.cssselect(".content-item")
        items = [el for el in all_items if el.get("id") != "0"]

    # 预期楼层范围
    floor_min = (page_num - 1) * COMMENTS_PER_PAGE + 1
    floor_max = page_num * COMMENTS_PER_PAGE

    comments = []
    for ci in items:
        # 解析楼层号：优先读 [id] 属性，fallback 到 a.floor-link 文本
        floor_num = _parse_floor_num(ci)
        if floor_num is not None:
            # 过滤出范围外的楼层（热门回复等跨页插入内容）
            if not (floor_min <= floor_num <= floor_max):
                continue
            floor_str = f"#{floor_num}"
        else:
            # 无法解析楼层号时，从文本提取（不做范围过滤）
            floor_str = _css_text(ci, "a.floor-link") or ""

        author = _pick_author(ci)
        if not author:
            continue  # 跳过无作者的空块

        author_href = _css_attr(ci, 'a[href^="/space/"]', "href") \
                      or _css_attr(ci, "a.author-name", "href")
        post_time = _css_attr(ci, ".date-created time", "datetime")
        is_poster = bool(ci.cssselect(".is-poster"))

        content_el = ci.cssselect("article.post-content")
        content = _inner_texts(content_el[0]) if content_el else ""

        # 评论图片/贴纸/外链
        images, stickers, links = _extract_media(
            content_el[0] if content_el else None,
            base_url=config.BASE_URL,
        )

        comments.append(Comment(
            floor=floor_str,
            author=author,
            author_url=_to_abs(author_href, config.BASE_URL),
            content=content,
            post_time=post_time,
            is_poster=is_poster,
            images=images,
            stickers=stickers,
            links=links,
        ))
    return comments


def _parse_floor_num(el) -> Optional[int]:
    """
    解析楼层号整数。
    优先读 content-item[id] 属性（NodeGuaBot 方式），fallback 到 a.floor-link 文本。
    返回 None 表示无法解析。
    """
    # 方式 1：[id] 属性（每个 content-item 的 id 就是楼层号）
    id_val = el.get("id", "").strip()
    if id_val.isdigit():
        num = int(id_val)
        if num > 0:  # 0 是主帖，跳过
            return num

    # 方式 2：a.floor-link 文本（如 "#5"）
    floor_links = el.cssselect("a.floor-link")
    if floor_links:
        text = (floor_links[0].text_content() or "").strip().lstrip("#")
        if text.isdigit():
            return int(text)

    return None


def _pick_author(el) -> str:
    """
    解析作者名，策略优先级（参考 NodeGuaBot）:
    1. .nsk-content-meta-info 下的 a[href^="/space/"] 文本
    2. a.author-name 文本
    3. a[href^="/space/"] img[alt]（头像 alt）
    """
    # 优先从 meta-info 区域找
    meta = el.cssselect(".nsk-content-meta-info")
    search_root = meta[0] if meta else el

    # 1. 用户空间链接文字
    space_links = search_root.cssselect('a[href^="/space/"]')
    for a in space_links:
        t = (a.text_content() or "").replace("\n", " ").strip()
        if t:
            return t

    # 2. author-name class
    names = el.cssselect("a.author-name")
    if names:
        t = (names[0].text_content() or "").strip()
        if t:
            return t

    # 3. img[alt] fallback
    if space_links:
        imgs = space_links[0].cssselect("img")
        if imgs:
            t = (imgs[0].get("alt") or "").strip()
            if t:
                return t

    return ""


def _extract_media(
    article_el,
    base_url: str,
) -> tuple[list[str], list[str], list[dict]]:
    """
    从 article 元素中提取：
    - images: 正文图片 URL（绝对 URL，排除贴纸）
    - stickers: 贴纸名称列表
    - links: 外部链接 [{text, url}]（排除站内链接）

    参照 NodeGuaBot 的 extractPost() 逻辑。
    """
    images: list[str] = []
    stickers: list[str] = []
    links: list[dict] = []

    if article_el is None:
        return images, stickers, links

    # 图片提取
    for img in article_el.cssselect("img"):
        raw_src = img.get("src") or img.get("data-src") or ""
        abs_src = _to_abs(raw_src, base_url)
        if not abs_src:
            continue

        if STICKER_PATH_MARKER in abs_src:
            alt = (img.get("alt") or "").strip()
            stickers.append(alt if alt else "sticker")
        else:
            images.append(abs_src)

    # 外部链接提取
    for a in article_el.cssselect("a[href]"):
        href = a.get("href") or ""
        abs_url = _to_abs(href, base_url)
        if not abs_url.startswith("http"):
            continue
        if abs_url.startswith(base_url):
            continue  # 排除站内链接
        text = (a.text_content() or "").replace("\n", " ").strip()
        links.append({"text": text, "url": abs_url})

    return images, stickers, links


def _to_abs(url: str, base_url: str) -> str:
    """将相对 URL 转为绝对 URL"""
    if not url:
        return ""
    if url.startswith("http"):
        return url
    if url.startswith("//"):
        return "https:" + url
    if url.startswith("/"):
        return base_url + url
    return base_url + "/" + url


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
