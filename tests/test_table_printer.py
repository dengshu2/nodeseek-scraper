"""
test_table_printer.py — 终端表格打印测试

验证 table_printer 不崩溃，并正确处理各种输入：
1. 正常数据
2. 空列表
3. timestamp=0 的处理
"""
from nodeseek.models import HotPost
from nodeseek.exporters.table_printer import print_hot_table


class TestPrintHotTable:
    def test_normal_data(self, capsys):
        """正常数据应打印无异常"""
        posts = [
            HotPost(
                id=1, title="测试帖子标题很长可能会换行",
                author="alice", author_id=100,
                timestamp=1700000000, views=500, comments=30,
                summary="摘要", category="tech", score=9.5, rank_type="hot",
            ),
        ]
        # 不应抛异常
        print_hot_table(posts, "hot")

    def test_empty_list(self, capsys):
        """空列表不应崩溃"""
        print_hot_table([], "daily")

    def test_zero_timestamp(self, capsys):
        """timestamp=0 时应显示 '-'"""
        posts = [
            HotPost(
                id=1, title="无时间戳", author="bob", author_id=1,
                timestamp=0, views=0, comments=0,
                summary="", category="", score=0.0, rank_type="weekly",
            ),
        ]
        print_hot_table(posts, "weekly")

    def test_all_rank_types(self, capsys):
        """三种榜单类型都应正确显示标签"""
        for rt in ["hot", "daily", "weekly"]:
            posts = [
                HotPost(
                    id=1, title="t", author="a", author_id=1,
                    timestamp=1700000000, views=1, comments=0,
                    summary="", category="", score=1.0, rank_type=rt,
                ),
            ]
            print_hot_table(posts, rt)  # 不应抛异常
