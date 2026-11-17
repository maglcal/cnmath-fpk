#!/bin/bash
# 飞牛 fnOS 静态站点 CGI 分发入口。
# 静态文件根路径按官方文档写法（developer.fnnas.com · index.cgi）：
# BASE_PATH 必须与安装后的应用路径一致 = /var/apps/{appname}/target/www。
# 官方路径不存在时才回落脚本自身位置推导（本地模拟/非常规布局用）。
# 其余设计要点：完整 MIME；缓存头；拒绝目录穿越；只从 www 目录提供文件。
# 注意：本文件必须保持 LF 换行，CRLF 会让 NAS 上的 bash 直接报错。
set -u

BASE_PATH="/var/apps/cn-math-taxonomy/target/www"
if [ ! -d "${BASE_PATH}" ]; then
  SELF_DIR="$(cd "$(dirname "$0")" 2>/dev/null && pwd)"
  BASE_PATH="$(cd "${SELF_DIR}/../www" 2>/dev/null && pwd)"
fi

emit() {
  printf 'Status: %s\r\n' "$1"
  printf 'Content-Type: %s\r\n' "$2"
  printf 'Cache-Control: no-store\r\n'
  printf 'X-Content-Type-Options: nosniff\r\n'
  printf '\r\n'
  printf '%s\n' "$3"
  exit 0
}

if [ -z "${BASE_PATH}" ] || [ ! -d "${BASE_PATH}" ]; then
  emit "500 Internal Server Error" "text/plain; charset=utf-8" "应用静态文件目录缺失，请重新安装本应用。"
fi

RAW="${REQUEST_URI:-/}"
URI="${RAW%%\?*}"
REL="/"
case "${URI}" in
  *index.cgi*) REL="${URI#*index.cgi}" ;;
esac
[ -z "${REL}" ] && REL="/"
[ "${REL}" = "/" ] && REL="/index.html"
case "${REL}" in
  */) REL="${REL}index.html" ;;
esac

case "${REL}" in
  *..*|*%00*|*%2e*|*%2E*|*\\*)
    emit "400 Bad Request" "text/plain; charset=utf-8" "非法请求路径。"
    ;;
esac

TARGET="${BASE_PATH}${REL}"
if [ ! -f "${TARGET}" ] || [ ! -r "${TARGET}" ]; then
  emit "404 Not Found" "text/plain; charset=utf-8" "404 Not Found: ${REL}"
fi

case "${TARGET##*.}" in
  html|htm)      mime="text/html; charset=utf-8";            cache="no-cache" ;;
  css)           mime="text/css; charset=utf-8";             cache="public, max-age=3600" ;;
  js|mjs)        mime="application/javascript; charset=utf-8"; cache="public, max-age=3600" ;;
  json)          mime="application/json; charset=utf-8";     cache="public, max-age=3600" ;;
  webmanifest)   mime="application/manifest+json";           cache="public, max-age=3600" ;;
  txt|md)        mime="text/plain; charset=utf-8";           cache="public, max-age=3600" ;;
  png)           mime="image/png";                           cache="public, max-age=86400" ;;
  jpg|jpeg)      mime="image/jpeg";                          cache="public, max-age=86400" ;;
  gif)           mime="image/gif";                           cache="public, max-age=86400" ;;
  svg)           mime="image/svg+xml";                       cache="public, max-age=86400" ;;
  ico)           mime="image/x-icon";                        cache="public, max-age=86400" ;;
  woff2)         mime="font/woff2";                          cache="public, max-age=86400" ;;
  *)             mime="application/octet-stream";           cache="public, max-age=3600" ;;
esac

printf 'Content-Type: %s\r\n' "${mime}"
printf 'Cache-Control: %s\r\n' "${cache}"
printf 'X-Content-Type-Options: nosniff\r\n'
printf '\r\n'
cat -- "${TARGET}"
exit 0
