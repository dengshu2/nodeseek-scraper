"""
db.py — SQLite 数据库封装

存储 username ↔ uid 全量映射及用户资料缓存。
数据库文件默认位于项目根目录 nodeseek.db。
"""
import sqlite3
from pathlib import Path
from typing import Optional

from nodeseek import config

DB_PATH = config.ROOT_DIR / "nodeseek.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    uid            INTEGER PRIMARY KEY,
    username       TEXT NOT NULL,
    rank           INTEGER DEFAULT 0,
    coin           INTEGER DEFAULT 0,
    stardust       INTEGER DEFAULT 0,
    n_post         INTEGER DEFAULT 0,
    n_comment      INTEGER DEFAULT 0,
    follows        INTEGER DEFAULT 0,
    fans           INTEGER DEFAULT 0,
    created_at     TEXT DEFAULT '',
    created_at_str TEXT DEFAULT '',
    fetched_at     TEXT DEFAULT (datetime('now'))
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_users_username
    ON users(username);

CREATE TABLE IF NOT EXISTS sync_meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""


def get_connection(db_path: Optional[Path] = None) -> sqlite3.Connection:
    """获取 SQLite 连接（自动建表）。"""
    path = db_path or DB_PATH
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    return conn


def upsert_user(
    conn: sqlite3.Connection,
    uid: int,
    username: str,
    rank: int = 0,
    coin: int = 0,
    stardust: int = 0,
    n_post: int = 0,
    n_comment: int = 0,
    follows: int = 0,
    fans: int = 0,
    created_at: str = "",
    created_at_str: str = "",
) -> None:
    """插入或更新用户记录。"""
    conn.execute(
        """
        INSERT INTO users (uid, username, rank, coin, stardust,
                           n_post, n_comment, follows, fans,
                           created_at, created_at_str, fetched_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        ON CONFLICT(uid) DO UPDATE SET
            username       = excluded.username,
            rank           = excluded.rank,
            coin           = excluded.coin,
            stardust       = excluded.stardust,
            n_post         = excluded.n_post,
            n_comment      = excluded.n_comment,
            follows        = excluded.follows,
            fans           = excluded.fans,
            created_at     = excluded.created_at,
            created_at_str = excluded.created_at_str,
            fetched_at     = datetime('now')
        """,
        (uid, username, rank, coin, stardust,
         n_post, n_comment, follows, fans,
         created_at, created_at_str),
    )


def upsert_user_from_api(conn: sqlite3.Connection, detail: dict) -> None:
    """从 API 响应的 detail 字典直接写入。"""
    upsert_user(
        conn,
        uid=detail.get("member_id", 0),
        username=detail.get("member_name", ""),
        rank=detail.get("rank", 0),
        coin=detail.get("coin", 0),
        stardust=detail.get("stardust", 0),
        n_post=detail.get("nPost", 0),
        n_comment=detail.get("nComment", 0),
        follows=detail.get("follows", 0),
        fans=detail.get("fans", 0),
        created_at=detail.get("created_at", ""),
        created_at_str=detail.get("created_at_str", ""),
    )


def get_uid_by_username(conn: sqlite3.Connection, username: str) -> Optional[int]:
    """根据用户名查 UID，未找到返回 None。"""
    row = conn.execute(
        "SELECT uid FROM users WHERE username = ?", (username,)
    ).fetchone()
    return row["uid"] if row else None


def get_user_by_uid(conn: sqlite3.Connection, uid: int) -> Optional[dict]:
    """根据 UID 查完整用户记录。"""
    row = conn.execute("SELECT * FROM users WHERE uid = ?", (uid,)).fetchone()
    return dict(row) if row else None


def get_user_by_username(conn: sqlite3.Connection, username: str) -> Optional[dict]:
    """根据用户名查完整用户记录。"""
    row = conn.execute(
        "SELECT * FROM users WHERE username = ?", (username,)
    ).fetchone()
    return dict(row) if row else None


def get_meta(conn: sqlite3.Connection, key: str) -> Optional[str]:
    """读取同步元数据。"""
    row = conn.execute(
        "SELECT value FROM sync_meta WHERE key = ?", (key,)
    ).fetchone()
    return row["value"] if row else None


def set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    """写入同步元数据。"""
    conn.execute(
        "INSERT INTO sync_meta (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
    conn.commit()


def get_user_count(conn: sqlite3.Connection) -> int:
    """用户总数。"""
    row = conn.execute("SELECT COUNT(*) AS cnt FROM users").fetchone()
    return row["cnt"]


def search_users(
    conn: sqlite3.Connection,
    keyword: str,
    limit: int = 20,
) -> list[dict]:
    """模糊搜索用户名。"""
    rows = conn.execute(
        "SELECT * FROM users WHERE username LIKE ? ORDER BY uid LIMIT ?",
        (f"%{keyword}%", limit),
    ).fetchall()
    return [dict(r) for r in rows]
