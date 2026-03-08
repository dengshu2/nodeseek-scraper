"""
NodeSeek 数据模型定义
"""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class HotPost:
    """热榜/日榜/周榜帖子"""
    id: int
    title: str
    author: str
    author_id: int
    timestamp: int
    views: int
    comments: int
    summary: str
    category: str
    score: float
    rank_type: str          # "hot" | "daily" | "weekly"


@dataclass
class Comment:
    """帖子评论（帖子详情内）"""
    floor: str              # "#1", "#2"
    author: str
    author_url: str
    content: str
    post_time: str          # ISO 8601
    is_poster: bool


@dataclass
class PostDetail:
    """帖子详情（含正文和评论）"""
    id: int
    title: str
    url: str
    author: str
    author_url: str
    category: str
    post_time: str
    content: str            # 纯文本
    content_html: str       # HTML
    comments: list[Comment] = field(default_factory=list)


@dataclass
class UserComment:
    """用户单条评论记录"""
    post_id: int
    post_title: str
    floor_id: int
    content: str
    rank: int


@dataclass
class UserProfile:
    """用户评论汇总"""
    uid: int
    username: str
    total_comments: int
    comments: list[UserComment] = field(default_factory=list)


@dataclass
class SearchResult:
    """搜索结果条目（来自 nodeseek.dengshu.ovh 聚合 API）"""
    post_id: int
    title: str
    description: str
    category: str
    author: str
    pub_date: str       # ISO 8601
    link: str


@dataclass
class SearchResponse:
    """搜索响应（分页元数据 + 结果列表）"""
    total: int
    skip: int
    limit: int
    results: list[SearchResult] = field(default_factory=list)
