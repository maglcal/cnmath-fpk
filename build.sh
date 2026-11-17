#!/bin/bash
# 中小学知识图谱（本地版）· 飞牛 fnOS 应用构建入口
# 链路：钉版本校验 → 组装站点（裁剪+覆盖）→ 生成图标 → 合规闸门 → fnpack 打包
# 只有合规闸门 RESULT=PASS 才允许产出 .fpk。
# 用法：bash build.sh [--upstream DIR] [--stats-config FILE] [--test]
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
UPSTREAM="${ROOT}/.build/cn-math-taxonomy"
STATS_CONFIG=""
TEST_BUILD=0
OUT="${ROOT}/dist"

while [ $# -gt 0 ]; do
  case "$1" in
    --upstream) UPSTREAM="$2"; shift 2 ;;
    --stats-config) STATS_CONFIG="$2"; shift 2 ;;
    --test) TEST_BUILD=1; shift ;;
    *) echo "未知参数: $1" >&2; exit 1 ;;
  esac
done

PY=python
command -v python >/dev/null 2>&1 || PY=python3

VER="$(sed -n 's/^version=//p' "${ROOT}/manifest" | head -1)"
# 分支测试版序号自动递增：vX.Y.Z.x（不带 main- 前缀）。重打同号请先删除旧产物。
N=1
while [ -e "${OUT}/cnmath-v${VER}.${N}.fpk" ]; do N=$((N + 1)); done
BUILD_ID="${VER}.${N}"

echo "==> 1/5 生成原创图标"
"${PY}" "${ROOT}/tools/make_icons.py" "${ROOT}" | sed 's/^/    /'

echo "==> 2/5 组装站点（上游只读，裁剪锚点不命中即失败）"
if [ -n "${STATS_CONFIG}" ]; then
  "${PY}" "${ROOT}/tools/build_site.py" --root "${ROOT}" --upstream "${UPSTREAM}" \
    --build-id "${BUILD_ID}" --stats-config "${STATS_CONFIG}"
else
  "${PY}" "${ROOT}/tools/build_site.py" --root "${ROOT}" --upstream "${UPSTREAM}" --build-id "${BUILD_ID}"
fi

echo "==> 3/5 引用完整性 + 上架合规闸门（授权条件 1–7）"
"${PY}" "${ROOT}/tools/check_refs.py" "${ROOT}/app/www"
if [ -d "${UPSTREAM}" ]; then
  "${PY}" "${ROOT}/tools/verify_grant.py" --root "${ROOT}" --upstream "${UPSTREAM}"
else
  "${PY}" "${ROOT}/tools/verify_grant.py" --root "${ROOT}"
fi

[ "${TEST_BUILD}" -eq 1 ] && { echo "==> 测试模式：仅校验，不打包"; exit 0; }

# 4/5 组装 fnpack stage
STAGE="${ROOT}/.build/stage"
rm -rf "${STAGE}"
mkdir -p "${STAGE}/app/ui" "${STAGE}/app/www" "${STAGE}/cmd" "${STAGE}/config" "${STAGE}/wizard"
cp "${ROOT}/manifest" "${STAGE}/manifest"
cp "${ROOT}/ICON.PNG" "${ROOT}/ICON_256.PNG" "${STAGE}/"
cp -a "${ROOT}/app/ui/." "${STAGE}/app/ui/"
cp -a "${ROOT}/app/www/." "${STAGE}/app/www/"
cp -a "${ROOT}/cmd/." "${STAGE}/cmd/"
cp -a "${ROOT}/config/." "${STAGE}/config/"
cp -a "${ROOT}/wizard/." "${STAGE}/wizard/"
# LICENSE 放进应用文件区（随 app.tgz 落到应用目录），fpk 外层保持与已验证应用
# 一致的最小条目集（manifest/cmd/config/wizard/ICON/app.tgz）——外层多出的根文件
# 是 0.1.0.4 与线上正常包的唯一结构差异，v0.1.0.5 起消除。
cp "${ROOT}/LICENSE" "${STAGE}/app/LICENSE"
chmod +x "${STAGE}/cmd/"* "${STAGE}/app/ui/index.cgi"

# stage 二次 LF 兜底（cp -a 不产生 CRLF，但 Windows 上手工改过文件就可能混进来）
"${PY}" - "${STAGE}" <<'PYLF'
import sys, pathlib
bad = []
for p in pathlib.Path(sys.argv[1]).rglob('*'):
    if not p.is_file(): continue
    b = p.read_bytes()
    if b'\r\n' not in b: continue
    try: b.decode('utf-8')
    except UnicodeDecodeError: continue
    p.write_bytes(b.replace(b'\r\n', b'\n')); bad.append(str(p))
print('    stage LF 清理:', len(bad), '个文件')
PYLF
echo "==> 4/5 stage 组装完成"

# 5/5 fnpack
FNPACK="${ROOT}/.tools/fnpack.exe"
if [ ! -x "${FNPACK}" ]; then
  FNPACK="$(command -v fnpack || true)"
fi
if [ -z "${FNPACK}" ] || [ ! -x "${FNPACK}" ]; then
  echo "ERROR: 未找到 fnpack，请把官方 fnpack 放到 ${ROOT}/.tools/fnpack.exe" >&2
  exit 1
fi
mkdir -p "${OUT}"
WORK="$(mktemp -d)"
( cd "${WORK}" && "${FNPACK}" build --directory "${STAGE}" )
BUILT="$(find "${WORK}" "${STAGE}" -maxdepth 2 -name '*.fpk' -print -quit 2>/dev/null || true)"
[ -n "${BUILT}" ] || { echo "ERROR: fnpack 未产出 .fpk" >&2; exit 1; }
FINAL="${OUT}/cnmath-v${BUILD_ID}.fpk"
mv "${BUILT}" "${FINAL}"
rm -rf "${WORK}"

# 5.5 包内字节级换行验收：fnpack 之后的产物才是交付物（2026-11-17 整改，
# 补上打包后验收这道缺失工序）。不过就地删除产物，禁止误交付。
if ! "${PY}" "${ROOT}/tools/verify_fpk.py" "${FINAL}"; then
  rm -f "${FINAL}"
  echo "ERROR: 包内换行验收未过，已删除产物，禁止交付。" >&2
  exit 1
fi
( cd "${OUT}" && sha256sum "$(basename "${FINAL}")" > "$(basename "${FINAL}").sha256" )
echo "==> 5/5 打包完成: ${FINAL}"
echo "    本包为分支测试版，真机验收通过后合并发布 main-v${VER}。"
