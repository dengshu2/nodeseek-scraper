"""
test_cli.py — CLI 命令行参数解析测试

验证 ns.py 的 argparse 配置：
1. 各子命令的参数解析
2. 默认值
3. 必需参数缺失时的行为
4. --format / --output 选项
"""
import pytest
import sys
import os

# 确保项目根目录在 sys.path 上，以便导入 ns.py
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ns import build_parser


@pytest.fixture
def parser():
    return build_parser()


class TestHotCommand:
    def test_default_args(self, parser):
        args = parser.parse_args(["hot"])
        assert args.command == "hot"
        assert args.rank_type == "hot"
        assert args.top == 0
        assert args.fmt == "json"
        assert args.output is None

    def test_type_daily(self, parser):
        args = parser.parse_args(["hot", "--type", "daily"])
        assert args.rank_type == "daily"

    def test_type_all(self, parser):
        args = parser.parse_args(["hot", "-t", "all"])
        assert args.rank_type == "all"

    def test_top(self, parser):
        args = parser.parse_args(["hot", "--top", "20"])
        assert args.top == 20

    def test_format_table(self, parser):
        args = parser.parse_args(["hot", "-f", "table"])
        assert args.fmt == "table"

    def test_format_csv(self, parser):
        args = parser.parse_args(["hot", "--format", "csv"])
        assert args.fmt == "csv"

    def test_output_dir(self, parser):
        args = parser.parse_args(["hot", "--output", "/tmp/custom"])
        assert args.output == "/tmp/custom"


class TestUserCommand:
    def test_username(self, parser):
        args = parser.parse_args(["user", "shaw-deng"])
        assert args.command == "user"
        assert args.username == "shaw-deng"
        assert args.uid is None
        assert args.pages == 0
        assert args.fmt == "json"

    def test_uid(self, parser):
        args = parser.parse_args(["user", "--uid", "36700"])
        assert args.uid == 36700
        assert args.username is None

    def test_pages(self, parser):
        args = parser.parse_args(["user", "test", "--pages", "3"])
        assert args.pages == 3

    def test_format_md(self, parser):
        args = parser.parse_args(["user", "test", "-f", "md"])
        assert args.fmt == "md"

    def test_format_csv(self, parser):
        args = parser.parse_args(["user", "test", "--format", "csv"])
        assert args.fmt == "csv"

    def test_no_profile(self, parser):
        args = parser.parse_args(["user", "test", "--no-profile"])
        assert args.no_profile is True

    def test_no_profile_default(self, parser):
        args = parser.parse_args(["user", "test"])
        assert args.no_profile is False


class TestProfileCommand:
    def test_username(self, parser):
        args = parser.parse_args(["profile", "shaw-deng"])
        assert args.command == "profile"
        assert args.username == "shaw-deng"
        assert args.uid is None
        assert args.fmt == "table"

    def test_uid(self, parser):
        args = parser.parse_args(["profile", "--uid", "36700"])
        assert args.uid == 36700

    def test_format_json(self, parser):
        args = parser.parse_args(["profile", "test", "-f", "json"])
        assert args.fmt == "json"


class TestPostCommand:
    def test_single_id(self, parser):
        args = parser.parse_args(["post", "637248"])
        assert args.command == "post"
        assert args.ids == [637248]
        assert args.no_comments is False
        assert args.fmt == "json"

    def test_multiple_ids(self, parser):
        args = parser.parse_args(["post", "637248", "637250", "637252"])
        assert args.ids == [637248, 637250, 637252]

    def test_no_comments(self, parser):
        args = parser.parse_args(["post", "1", "--no-comments"])
        assert args.no_comments is True

    def test_format_md(self, parser):
        args = parser.parse_args(["post", "1", "-f", "md"])
        assert args.fmt == "md"


class TestSearchCommand:
    def test_keyword(self, parser):
        args = parser.parse_args(["search", "claude"])
        assert args.command == "search"
        assert args.keyword == "claude"
        assert args.category is None
        assert args.author is None
        assert args.limit == 20
        assert args.skip == 0
        assert args.fmt == "table"

    def test_category(self, parser):
        args = parser.parse_args(["search", "vps", "--category", "trade"])
        assert args.category == "trade"

    def test_author(self, parser):
        args = parser.parse_args(["search", "--author", "shaw-deng"])
        assert args.author == "shaw-deng"
        assert args.keyword is None

    def test_limit(self, parser):
        args = parser.parse_args(["search", "test", "--limit", "50"])
        assert args.limit == 50

    def test_skip(self, parser):
        args = parser.parse_args(["search", "test", "--skip", "20"])
        assert args.skip == 20

    def test_format_json(self, parser):
        args = parser.parse_args(["search", "test", "-f", "json"])
        assert args.fmt == "json"

    def test_format_md(self, parser):
        args = parser.parse_args(["search", "test", "--format", "md"])
        assert args.fmt == "md"


class TestSyncUsersCommand:
    def test_defaults(self, parser):
        args = parser.parse_args(["sync-users"])
        assert args.command == "sync-users"
        assert args.start == 1
        assert args.max_uid == 55000
        assert args.batch_size == 20
        assert args.resume is False
        assert args.delay == 0.3

    def test_custom(self, parser):
        args = parser.parse_args([
            "sync-users", "--start", "1000", "--max", "60000",
            "--batch", "50", "--resume", "--delay", "0.5",
        ])
        assert args.start == 1000
        assert args.max_uid == 60000
        assert args.batch_size == 50
        assert args.resume is True
        assert args.delay == 0.5


class TestLookupCommand:
    def test_username(self, parser):
        args = parser.parse_args(["lookup", "shaw-deng"])
        assert args.command == "lookup"
        assert args.username == "shaw-deng"
        assert args.uid is None
        assert args.keyword is None
        assert args.stats is False

    def test_uid(self, parser):
        args = parser.parse_args(["lookup", "--uid", "36700"])
        assert args.uid == 36700

    def test_search(self, parser):
        args = parser.parse_args(["lookup", "-s", "alice"])
        assert args.keyword == "alice"

    def test_stats(self, parser):
        args = parser.parse_args(["lookup", "--stats"])
        assert args.stats is True

    def test_limit(self, parser):
        args = parser.parse_args(["lookup", "-s", "test", "-n", "50"])
        assert args.limit == 50


class TestVerboseFlag:
    def test_verbose_default(self, parser):
        args = parser.parse_args(["hot"])
        assert args.verbose is False

    def test_verbose_set(self, parser):
        args = parser.parse_args(["-v", "hot"])
        assert args.verbose is True

    def test_verbose_long(self, parser):
        args = parser.parse_args(["--verbose", "search", "test"])
        assert args.verbose is True


class TestMissingCommand:
    def test_no_command_exits(self, parser):
        """未指定命令时应报错退出"""
        with pytest.raises(SystemExit):
            parser.parse_args([])
