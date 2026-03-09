"""
test_config.py — 全局配置测试

验证：
1. 路径常量存在且合理
2. URL 常量格式正确
3. 数值常量值
"""
from pathlib import Path

from nodeseek import config


class TestConfigPaths:
    def test_root_dir_exists(self):
        assert config.ROOT_DIR.exists()

    def test_root_dir_is_project_root(self):
        """ROOT_DIR 应该是项目根目录（包含 ns.py）"""
        assert (config.ROOT_DIR / "ns.py").exists()

    def test_output_dir_under_root(self):
        assert config.OUTPUT_DIR == config.ROOT_DIR / "output"

    def test_subdirs(self):
        assert config.HOT_OUTPUT_DIR == config.OUTPUT_DIR / "hot"
        assert config.POST_OUTPUT_DIR == config.OUTPUT_DIR / "posts"
        assert config.USER_OUTPUT_DIR == config.OUTPUT_DIR / "users"


class TestConfigURLs:
    def test_base_url(self):
        assert config.BASE_URL == "https://www.nodeseek.com"

    def test_hot_api_urls_keys(self):
        assert set(config.HOT_API_URLS.keys()) == {"hot", "daily", "weekly"}

    def test_hot_api_urls_format(self):
        for key, url in config.HOT_API_URLS.items():
            assert url.startswith("https://"), f"{key} URL should start with https://"
            assert url.endswith(".json"), f"{key} URL should end with .json"


class TestConfigValues:
    def test_cf_wait_seconds(self):
        assert isinstance(config.CF_WAIT_SECONDS, (int, float))
        assert config.CF_WAIT_SECONDS > 0

    def test_user_comments_per_page(self):
        assert config.USER_COMMENTS_PER_PAGE == 15
