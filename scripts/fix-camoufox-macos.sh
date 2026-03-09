#!/usr/bin/env bash
# =============================================================================
# fix-camoufox-macos.sh — macOS arm64 Camoufox 版本锁定恢复脚本
# =============================================================================
#
# 用途：
#   将 Camoufox 浏览器二进制降级/锁定到 135.0.1-beta.24（macOS arm64 稳定版）
#
# 背景：
#   Camoufox 146.0.1-beta.25 在 macOS arm64 上存在严重 Bug：
#   访问 NodeSeek 帖子页时 Firefox 内核抛出
#   NS_ERROR_FAILURE (nsIStreamListener.onDataAvailable)，
#   导致 page.content() 返回乱码二进制，帖子/用户抓取全部失效。
#
#   Windows x86_64 / Linux 不受影响，仅 macOS arm64 需要此脚本。
#
# 升级方式（修复确认后）：
#   1. 在 https://github.com/daijro/camoufox/releases 确认新版已修复上述 Bug
#   2. 修改本脚本中的 TARGET_VERSION / TARGET_RELEASE 为新版本号
#   3. 重新运行本脚本
#
# 使用方式：
#   bash scripts/fix-camoufox-macos.sh
#
# =============================================================================

set -e

TARGET_VERSION="135.0.1"
TARGET_RELEASE="beta.24"
TARGET_TAG="v${TARGET_VERSION}-${TARGET_RELEASE}"
DOWNLOAD_URL="https://github.com/daijro/camoufox/releases/download/${TARGET_TAG}/camoufox-${TARGET_VERSION}-${TARGET_RELEASE}-mac.arm64.zip"
INSTALL_DIR="${HOME}/Library/Caches/camoufox"
TMP_ZIP="/tmp/camoufox-${TARGET_VERSION}-${TARGET_RELEASE}-mac.arm64.zip"

echo "=============================================="
echo " Camoufox macOS arm64 版本锁定脚本"
echo " 目标版本: ${TARGET_VERSION}-${TARGET_RELEASE}"
echo "=============================================="
echo ""

# 检查平台
if [[ "$(uname)" != "Darwin" ]] || [[ "$(uname -m)" != "arm64" ]]; then
    echo "⚠️  此脚本仅适用于 macOS arm64（Apple Silicon）"
    echo "   当前平台: $(uname) / $(uname -m)"
    exit 1
fi

# 检查当前已安装版本
CURRENT_VER=""
if [[ -f "${INSTALL_DIR}/version.json" ]]; then
    CURRENT_VER=$(python3 -c "import json; d=json.load(open('${INSTALL_DIR}/version.json')); print(d['version']+'-'+d['release'])" 2>/dev/null || echo "unknown")
    echo "📦 当前版本: ${CURRENT_VER}"
fi

TARGET_FULL="${TARGET_VERSION}-${TARGET_RELEASE}"
if [[ "${CURRENT_VER}" == "${TARGET_FULL}" ]]; then
    echo "✅ 已是目标版本 ${TARGET_FULL}，无需操作"
    exit 0
fi

echo "📥 下载 Camoufox ${TARGET_FULL} (macOS arm64)..."
echo "   URL: ${DOWNLOAD_URL}"
echo ""

curl -L --progress-bar "${DOWNLOAD_URL}" -o "${TMP_ZIP}"

# 验证文件
if ! file "${TMP_ZIP}" | grep -q "Zip archive"; then
    echo "❌ 下载失败，文件不是有效 zip"
    rm -f "${TMP_ZIP}"
    exit 1
fi

echo ""
echo "🗑️  清理旧版本: ${INSTALL_DIR}"
rm -rf "${INSTALL_DIR}"
mkdir -p "${INSTALL_DIR}"

echo "📦 解压安装..."
unzip -q "${TMP_ZIP}" -d "${INSTALL_DIR}"

echo "📝 写入版本信息..."
echo "{\"version\":\"${TARGET_VERSION}\",\"release\":\"${TARGET_RELEASE}\"}" > "${INSTALL_DIR}/version.json"

echo "🔐 修复权限..."
chmod -R 755 "${INSTALL_DIR}"

echo ""
echo "✅ 安装完成！"
echo "   版本: $(python3 -c "import json; d=json.load(open('${INSTALL_DIR}/version.json')); print(d['version']+'-'+d['release'])")"
echo ""
echo "🧹 清理临时文件..."
rm -f "${TMP_ZIP}"

echo ""
echo "▶  验证："
echo "   uv run ns.py post 642746 --format json"
