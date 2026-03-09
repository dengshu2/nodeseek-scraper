"""
全局配置
"""
from pathlib import Path

# 项目根目录
ROOT_DIR = Path(__file__).parent.parent

# (已移除: Chrome CDP Profile，改用 Camoufox 无状态模式)

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
# 访问主页后的等待时间（秒）— Camoufox 自动绕过 CF，仅需等页面渲染
CF_WAIT_SECONDS = 2

# 用户评论 API 每页条数（固定 15）
USER_COMMENTS_PER_PAGE = 15
