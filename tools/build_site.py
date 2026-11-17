#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从上游快照组装 app/www/：只搬运行时文件，按授权条件 1–7 做确定性裁剪与覆盖。

原则：
- 每个裁剪锚点都必须命中，命中不到直接 FAIL（上游一改就暴露，绝不静默漏过）。
- 上游源码只读，改造全在 overlay/ 覆盖层。
- 输出全部强制 LF。
用法：python tools/build_site.py --upstream DIR --root ROOT [--build-id ID] [--stats-config FILE]
"""
import argparse
import re
import shutil
import sys
import time
from pathlib import Path

RUNTIME_FILES = [
    'index.html',
    'explore/index.html', 'explore/app.js',
    'diagnose/index.html', 'diagnose/engine.js', 'diagnose/app.js',
    'diagnose/share.js', 'diagnose/style.css',
    'children/index.html', 'children/history.html', 'children/page.js',
    'children/history.js', 'children/children.css',
    'wrongbook/index.html', 'wrongbook/wrongbook.js', 'wrongbook/wrongbook.css',
]
DATA_FILES = [
    'topics.json', 'dependencies.json', 'id-aliases.json',
    'cn-curriculum-standards.json', 'questions.json',
]
HTML_PAGES = [
    'index.html', 'explore/index.html', 'diagnose/index.html',
    'children/index.html', 'children/history.html', 'wrongbook/index.html',
]

errors = []


def need(cond, msg):
    if not cond:
        errors.append(msg)


def patch(text, pattern, repl, label, count=1, flags=0):
    """替换并断言命中次数；0 次或次数不符都记 FAIL。"""
    new, n = re.subn(pattern, repl, text, count=0, flags=flags)
    if n != count:
        errors.append('裁剪锚点 [%s] 命中 %d 次，预期 %d 次' % (label, n, count))
    return new


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', required=True)
    ap.add_argument('--upstream', required=True)
    ap.add_argument('--build-id', default='local',
                    help='测试构建序号（如 0.1.0.10），打到关于页版本戳')
    ap.add_argument('--stats-config', default=None,
                    help='私有 stats-endpoint.js；不传则不注入，产物零统计请求')
    args = ap.parse_args()

    root = Path(args.root)
    src = Path(args.upstream)
    out = root / 'app/www'
    overlay = root / 'overlay'

    need(src.is_dir(), '上游目录不存在: %s' % src)
    need((src / 'LICENSE').is_file(), '上游 LICENSE 缺失')
    need((root / 'UPSTREAM_COMMIT').is_file(), 'UPSTREAM_COMMIT 缺失')
    if errors:
        return report()

    commit = (root / 'UPSTREAM_COMMIT').read_text(encoding='utf-8').strip()
    head = ''
    try:
        import subprocess
        head = subprocess.check_output(['git', '-C', str(src), 'rev-parse', 'HEAD'],
                                      text=True).strip()
    except Exception as e:
        errors.append('无法读取上游 HEAD: %s' % e)
    need(head == commit, '上游 HEAD(%s) 与 UPSTREAM_COMMIT(%s) 不一致；同步上游须显式更新钉版本' % (head[:8], commit[:8]))

    # 清场重建（app/www 是产物，非源码）
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    # 1. 复制运行时文件（白名单，绝不整仓 cp）
    for rel in RUNTIME_FILES:
        s = src / rel
        need(s.is_file(), '运行时文件缺失: %s' % rel)
        if s.is_file():
            d = out / rel
            d.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(s, d)

    # 2. assets/：整目录搬，随后删 PWA/推广/赞助相关
    shutil.copytree(src / 'assets', out / 'assets')
    for rel in ['assets/pwa.js', 'assets/pwa.css', 'assets/kp.css',
                'assets/stats-config.js', 'assets/stats.js', 'assets/og-cover.jpg']:
        p = out / rel
        if p.exists():
            p.unlink()
    for rel in ['assets/sponsor', 'assets/icons']:
        p = out / rel
        if p.exists():
            shutil.rmtree(p)

    # 3. 数据：只搬前端实际 fetch 的 5 个文件
    (out / 'data').mkdir(parents=True, exist_ok=True)
    for name in DATA_FILES:
        s = src / 'data' / name
        need(s.is_file(), '数据文件缺失: data/%s' % name)
        if s.is_file():
            shutil.copy2(s, out / 'data' / name)

    # 4. 逐页裁剪 + 注入
    for rel in HTML_PAGES:
        p = out / rel
        if not p.is_file():
            continue
        t = p.read_text(encoding='utf-8')
        prefix = '' if '/' not in rel else '../'

        # 4.1 禁 PWA：manifest / pwa.css / pwa.js / apple-touch-icon
        t = patch(t, r'\s*<link rel="manifest"[^>]*>\s*', '\n', rel + ' manifest', 1)
        t = patch(t, r'\s*<link rel="stylesheet" href="[^"]*pwa\.css">\s*', '\n', rel + ' pwa.css', 1)
        t = patch(t, r'\s*<script src="[^"]*pwa\.js"></script>\s*', '\n', rel + ' pwa.js', 1)
        t = re.sub(r'\s*<link rel="apple-touch-icon"[^>]*>\s*', '\n', t)

        # 4.2 移除商品推广 / 知识点索引 / 第三方搜索入口
        t = patch(t, r'\s*<a class="nav-link" href="[^"]*goods/">学习好物</a>', '', rel + ' nav goods', 1)
        # kp 入口只存在于首页与知识图谱页；其余页必须确认「本来就没有」，防止上游新增
        kp_expect = 1 if rel in ('index.html', 'explore/index.html') else 0
        t = patch(t, r'\s*<a class="nav-link" href="[^"]*kp/">知识点索引</a>', '',
                  rel + ' nav kp', kp_expect)
        t = patch(t, r'\s*<a class="btn btn-lg" href="[^"]*goods/">学习好物</a>', '',
                  rel + ' hero goods', 1 if rel == 'index.html' else 0)
        t = patch(t, r'\s*<a class="nav-link resource-search-btn"[\s\S]*?</a>', '',
                  rel + ' 资源搜索', 1 if rel == 'index.html' else 0)
        t = patch(t, r'\s*<a class="iq-card"[\s\S]*?</a>', '',
                  rel + ' 智商测试卡', 1 if rel == 'index.html' else 0)
        t = patch(t, r'\s*<a class="top-banner"[^>]*>[\s\S]*?</a>', '',
                  rel + ' 顶部导流横幅', 1)
        need('iq-card' not in t, rel + ' 智商测试卡未清干净')
        need('top-banner' not in t, rel + ' 顶部导流横幅未清干净')

        # 4.3 OG / Twitter 外链元信息（指向作者站点，属导流）
        t = re.sub(r'\s*<meta (?:property="og:|name="twitter:)[^>]*>', '', t)
        # 域名检查必须放在 OG 清理之后；此处页面不得出现任何第三方站点地址
        need('pansgo.com' not in t, rel + ' 仍含第三方域名')

        # 4.4 注入统计端点配置（仅当构建时给了私有配置）
        if args.stats_config:
            t = patch(t, r'(\s*<script src="[^"]*stats-config\.js"></script>)',
                      '\n<script src="%sassets/stats-endpoint.js"></script>\\1' % prefix,
                      rel + ' 注入端点', 1)

        # 4.5 footer 注入「关于 / 改动清单」入口
        footer = ('<footer class="site-footer">\n  <p>'
                  '<a href="%sABOUT-NAS.html">关于 / 数据来源</a> · '
                  '<a href="%sCHANGES.html">改动清单</a> · '
                  '<a href="https://github.com/xiaoyang111222/cn-math-taxonomy/issues/new/choose">提交 Issue</a>'
                  '</p>' % (prefix, prefix))
        t = patch(t, r'<footer class="site-footer">[\s\S]*?</footer>', footer + '\n</footer>',
                  rel + ' footer', 1)

        p.write_text(t, encoding='utf-8', newline='\n')

    # 5. 诊断页：移除第三方导流提示
    dj = out / 'diagnose/app.js'
    if dj.is_file():
        t = dj.read_text(encoding='utf-8')
        t = patch(t, r"\s*page\.append\(h\('p', \{ class: 'iq-line'[\s\S]*?\}\)\)\);",
                  '', 'diagnose iq-line', 1)
        dj.write_text(t, encoding='utf-8', newline='\n')

    # 6. 分享图：二维码指向作者站点 → 改为本地说明，不出外网
    sh = out / 'diagnose/share.js'
    if sh.is_file():
        t = sh.read_text(encoding='utf-8')
        t = patch(t, r"var SHARE_URL = 'https://math\.pansgo\.com/\?from=share';",
                  "var SHARE_URL = '';  // 本地离线版：不生成指向外部站点的二维码",
                  'share SHARE_URL', 1)
        t = patch(t, r'\s*drawQr\(ctx, SHARE_URL, qrX, qrY, qrSize\);',
                  "\n    ctx.fillStyle = '#0f766e';\n"
                  "    ctx.font = font(700, 40);\n"
                  "    ctx.textAlign = 'center';\n"
                  "    ctx.fillText('本地离线版', qrX + qrSize / 2, qrY + qrSize / 2);\n"
                  "    ctx.textAlign = 'left';",
                  'share drawQr', 1)
        t = patch(t, r"ctx\.fillText\('扫码打开本站', qrX \+ qrSize \+ 48, qrY \+ qrSize / 2 - 8\);",
                  "ctx.fillText('数据留在本机', qrX + qrSize + 48, qrY + qrSize / 2 - 8);",
                  'share 扫码文案', 1)
        sh.write_text(t, encoding='utf-8', newline='\n')

    # 7. 覆盖层：纯本地事件钩子、统计适配、关于页、改动清单、许可全文
    shutil.copy2(overlay / 'assets/stats.js', out / 'assets/stats.js')
    shutil.copy2(overlay / 'assets/stats-config.js', out / 'assets/stats-config.js')
    shutil.copy2(overlay / 'ABOUT-NAS.html', out / 'ABOUT-NAS.html')
    shutil.copy2(overlay / 'CHANGES.html', out / 'CHANGES.html')

    # 7.5 关于页版本戳：应用版本 / 测试构建号 / 上游快照 / 构建日期，构建时自动打戳。
    # 占位符不许流入产物（verify_grant 断言 {{ 已清零），源页缺占位同样 FAIL。
    mf = (root / 'manifest').read_text(encoding='utf-8')
    mv = re.search(r'^version=(.+)$', mf, re.M)
    need(bool(mv), 'manifest 缺少 version=')
    about = out / 'ABOUT-NAS.html'
    at = about.read_text(encoding='utf-8')
    for token, value in {
        '{{VER}}': (mv.group(1).strip() if mv else ''),
        '{{BUILD_ID}}': args.build_id,
        '{{UPSTREAM7}}': commit[:7],
        '{{BUILD_DATE}}': time.strftime('%Y-%m-%d'),
    }.items():
        need(token in at, 'ABOUT-NAS.html 缺少版本戳占位 %s' % token)
        at = at.replace(token, value)
    about.write_text(at, encoding='utf-8', newline='\n')

    if args.stats_config:
        sc = Path(args.stats_config)
        need(sc.is_file(), '指定的统计配置不存在: %s' % sc)
        if sc.is_file():
            shutil.copy2(sc, out / 'assets/stats-endpoint.js')
            # 关于页（统计开关所在页）必须先加载端点配置，否则 configured=false
            # 会把开关禁用成「当前构建未配置统计服务」。按 overlay/ABOUT-NAS.html
            # 锚点注释的约定，在注释行之前注入（0.1.0.9 修复：此前 4.4 只注入上游页）。
            about = out / 'ABOUT-NAS.html'
            t = about.read_text(encoding='utf-8')
            t = patch(t, r'(<!-- 构建脚本须在本行之前注入 stats-endpoint\.js)',
                      '\n<script src="assets/stats-endpoint.js"></script>\\1',
                      'ABOUT-NAS 注入端点', 1)
            about.write_text(t, encoding='utf-8', newline='\n')
    shutil.copy2(src / 'LICENSE', out / 'LICENSE-upstream.txt')

    # 8. 全量 LF：文本类按 UTF-8 可解码判定，二进制跳过
    for p in out.rglob('*'):
        if not p.is_file():
            continue
        b = p.read_bytes()
        if b'\r\n' not in b:
            continue
        try:
            b.decode('utf-8')
        except UnicodeDecodeError:
            continue
        p.write_bytes(b.replace(b'\r\n', b'\n'))

    print('[site] 产物文件 %d 个，体积 %.2f MB' % (
        sum(1 for p in out.rglob('*') if p.is_file()),
        sum(p.stat().st_size for p in out.rglob('*') if p.is_file()) / 1024 / 1024))
    return report()


def report():
    if errors:
        print('[site] RESULT=FAIL')
        for e in errors:
            print('  - ' + e)
        return 1
    print('[site] RESULT=PASS')
    return 0


if __name__ == '__main__':
    sys.exit(main())
