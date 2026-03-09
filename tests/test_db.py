"""
test_db.py — 数据库模块测试

使用临时 SQLite 数据库验证：
1. 建表和连接
2. upsert_user / upsert_user_from_api
3. 查询（by uid / username / 模糊搜索）
4. sync_meta（set / get）
5. 用户计数
6. 边界场景（重复插入、空表查询）
"""
import sqlite3
import tempfile
from pathlib import Path

import pytest

from nodeseek.db import (
    get_connection,
    upsert_user,
    upsert_user_from_api,
    get_uid_by_username,
    get_user_by_uid,
    get_user_by_username,
    get_meta,
    set_meta,
    get_user_count,
    search_users,
)


@pytest.fixture
def db_conn(tmp_path):
    """创建临时数据库连接"""
    db_path = tmp_path / "test_nodeseek.db"
    conn = get_connection(db_path)
    yield conn
    conn.close()


class TestConnection:
    def test_connection_creates_tables(self, db_conn):
        """连接后应自动创建 users 和 sync_meta 表"""
        cursor = db_conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = [row[0] for row in cursor.fetchall()]
        assert "users" in tables
        assert "sync_meta" in tables

    def test_users_table_columns(self, db_conn):
        """users 表应包含所有预期列"""
        cursor = db_conn.execute("PRAGMA table_info(users)")
        columns = {row[1] for row in cursor.fetchall()}
        expected = {
            "uid", "username", "rank", "coin", "stardust",
            "n_post", "n_comment", "follows", "fans",
            "created_at", "created_at_str", "fetched_at",
        }
        assert expected.issubset(columns)


class TestUpsertUser:
    def test_insert_new_user(self, db_conn):
        upsert_user(db_conn, uid=1, username="alice", rank=5, coin=100)
        db_conn.commit()

        user = get_user_by_uid(db_conn, 1)
        assert user is not None
        assert user["username"] == "alice"
        assert user["rank"] == 5
        assert user["coin"] == 100

    def test_update_existing_user(self, db_conn):
        """upsert 同一 UID 应更新记录"""
        upsert_user(db_conn, uid=1, username="alice", rank=3)
        db_conn.commit()
        upsert_user(db_conn, uid=1, username="alice_updated", rank=6)
        db_conn.commit()

        user = get_user_by_uid(db_conn, 1)
        assert user["username"] == "alice_updated"
        assert user["rank"] == 6

    def test_default_values(self, db_conn):
        """未显式传入的字段应使用默认值"""
        upsert_user(db_conn, uid=99, username="default_user")
        db_conn.commit()

        user = get_user_by_uid(db_conn, 99)
        assert user["coin"] == 0
        assert user["stardust"] == 0
        assert user["n_post"] == 0
        assert user["fans"] == 0


class TestUpsertFromAPI:
    def test_from_api_detail(self, db_conn):
        """从 API 响应字典直接写入"""
        detail = {
            "member_id": 36700,
            "member_name": "shaw-deng",
            "rank": 5,
            "coin": 100,
            "stardust": 50,
            "nPost": 10,
            "nComment": 200,
            "follows": 3,
            "fans": 8,
            "created_at": "2023-06-01T00:00:00Z",
            "created_at_str": "2023年06月01日",
        }
        upsert_user_from_api(db_conn, detail)
        db_conn.commit()

        user = get_user_by_uid(db_conn, 36700)
        assert user is not None
        assert user["username"] == "shaw-deng"
        assert user["n_post"] == 10
        assert user["n_comment"] == 200

    def test_from_api_partial(self, db_conn):
        """API 字典缺少部分字段时应使用默认值"""
        detail = {"member_id": 1, "member_name": "partial"}
        upsert_user_from_api(db_conn, detail)
        db_conn.commit()

        user = get_user_by_uid(db_conn, 1)
        assert user["rank"] == 0
        assert user["coin"] == 0


class TestQueries:
    @pytest.fixture(autouse=True)
    def seed_data(self, db_conn):
        """预插入测试数据"""
        for uid, name in [(1, "alice"), (2, "bob"), (3, "alice_jr")]:
            upsert_user(db_conn, uid=uid, username=name, rank=uid)
        db_conn.commit()

    def test_get_uid_by_username(self, db_conn):
        assert get_uid_by_username(db_conn, "alice") == 1
        assert get_uid_by_username(db_conn, "bob") == 2

    def test_get_uid_by_username_not_found(self, db_conn):
        assert get_uid_by_username(db_conn, "nonexistent") is None

    def test_get_user_by_uid(self, db_conn):
        user = get_user_by_uid(db_conn, 2)
        assert user is not None
        assert user["username"] == "bob"

    def test_get_user_by_uid_not_found(self, db_conn):
        assert get_user_by_uid(db_conn, 999) is None

    def test_get_user_by_username(self, db_conn):
        user = get_user_by_username(db_conn, "alice")
        assert user is not None
        assert user["uid"] == 1

    def test_get_user_by_username_not_found(self, db_conn):
        assert get_user_by_username(db_conn, "nobody") is None

    def test_search_users(self, db_conn):
        """模糊搜索 'alice' 应返回 alice 和 alice_jr"""
        results = search_users(db_conn, "alice")
        assert len(results) == 2
        names = {r["username"] for r in results}
        assert names == {"alice", "alice_jr"}

    def test_search_users_no_match(self, db_conn):
        results = search_users(db_conn, "xyz_impossible")
        assert len(results) == 0

    def test_search_users_limit(self, db_conn):
        results = search_users(db_conn, "alice", limit=1)
        assert len(results) == 1

    def test_get_user_count(self, db_conn):
        assert get_user_count(db_conn) == 3


class TestMeta:
    def test_set_and_get_meta(self, db_conn):
        set_meta(db_conn, "crawl_last_uid", "5000")
        assert get_meta(db_conn, "crawl_last_uid") == "5000"

    def test_get_meta_not_found(self, db_conn):
        assert get_meta(db_conn, "nonexistent_key") is None

    def test_update_meta(self, db_conn):
        set_meta(db_conn, "key1", "v1")
        set_meta(db_conn, "key1", "v2")
        assert get_meta(db_conn, "key1") == "v2"
