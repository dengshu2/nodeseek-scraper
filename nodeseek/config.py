"""
全局配置
"""
from pathlib import Path

# 项目根目录
ROOT_DIR = Path(__file__).parent.parent

# Playwright fallback 模式的 persistent profile（cookie 注入备用）
BROWSER_PROFILE_DIR = ROOT_DIR / ".browser-profile"

# 爬虫专用 headless Chrome Profile（与用户日常 Chrome 完全隔离）
# 自动启动时使用，内存占用 ~150-200MB，无 GUI 弹窗
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

# Playwright 浏览器 User-Agent
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

# Playwright 等待 Cloudflare 握手的时间（秒）
CF_WAIT_SECONDS = 4

# 用户评论 API 每页条数（固定 15）
USER_COMMENTS_PER_PAGE = 15
