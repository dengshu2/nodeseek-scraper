"""
全局配置
"""
from pathlib import Path

# 项目根目录
ROOT_DIR = Path(__file__).parent.parent

# 爬虫专用 headless Chrome Profile（与用户日常 Chrome 完全隔离）
SCRAPER_CDP_PROFILE_DIR = ROOT_DIR / ".chrome-scraper-profile"

# 默认输出目录
OUTPUT_DIR = ROOT_DIR / "output"

# 各类输出子目录
HOT_OUTPUT_DIR    = OUTPUT_DIR / "hot"
POST_OUTPUT_DIR   = OUTPUT_DIR / "posts"
USER_OUTPUT_DIR   = OUTPUT_DIR / "users"

# NodeSeek 站点
BASE_URL = "https://www.nodeseek.com"

# 第三方热榜 API
HOT_API_URLS = {
    "hot":    "https://api.bimg.eu.org/hot.json",
    "daily":  "https://api.bimg.eu.org/daily.json",
    "weekly": "https://api.bimg.eu.org/weekly.json",
}

# Playwright 浏览器 User-Agent（按实际平台选取以保持指纹一致）
def _make_user_agent() -> str:
    import platform
    _ua_tpl = "Mozilla/5.0 ({os_part}) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    os_parts = {
        "Windows": "Windows NT 10.0; Win64; x64",
        "Darwin":  "Macintosh; Intel Mac OS X 10_15_7",
        "Linux":   "X11; Linux x86_64",
    }
    return _ua_tpl.format(os_part=os_parts.get(platform.system(), os_parts["Linux"]))

USER_AGENT = _make_user_agent()

# Playwright 等待 Cloudflare 握手的时间（秒）
CF_WAIT_SECONDS = 4

# 用户评论 API 每页条数（固定 15）
USER_COMMENTS_PER_PAGE = 15
