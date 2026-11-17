#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""上架合规闸门：逐条校验原作者 2026-11-16 书面确认的 7 项条件。

只有 RESULT=PASS 才允许产出 .fpk。任何 FAIL 都是硬阻断，不许「先出包再说」。
用法：python tools/verify_grant.py --root ROOT [--upstream DIR]
"""
import argparse
import json
import re
import sys
from pathlib import Path

errors = []
notes = []


def need(cond, msg):
    if not cond:
        errors.append(msg)
    return cond


def text(p):
    return p.read_text(encoding='utf-8')


def manifest_kv(root):
    d = {}
    for line in text(root / 'manifest').splitlines():
        if '=' in line and not line.startswith('#'):
            k, v = line.split('=', 1)
            d[k.strip()] = v.strip()
    return d


def check_c1(root, www):
    """条件 1：永久免费，零推广零导流零收益，零外部请求。

    检查口径：只判定「会真正发起网络请求或引导跳转的引用」。
    第三方库源码注释、许可文本与课标数据来源里的 URL 是原样保留的上游内容，
    不是请求也不构成导流，逐字检查会误报，故不纳入域名白名单扫描。
    """
    files = [p for p in www.rglob('*') if p.is_file()]
    need(bool(files), 'app/www/ 为空，尚未构建产物')

    # 允许的可点击外链域名：署名、原站、许可、Issue（授权条件 2 明确要求保留）
    allowed_hosts = {
        'github.com', 'math.pansgo.com', 'creativecommons.org',
        'xiaoyang111222.github.io', 'w3.org',
    }
    anchor_re = re.compile(r'<a\s[^>]*href="https?://([A-Za-z0-9._-]+)', re.I)
    bad_anchors = []
    for p in files:
        if p.suffix != '.html':
            continue
        try:
            s = p.read_text(encoding='utf-8')
        except (UnicodeDecodeError, OSError):
            continue
        for m in anchor_re.finditer(s):
            if m.group(1) not in allowed_hosts:
                bad_anchors.append('%s: %s' % (p.relative_to(www), m.group(1)))
    need(not bad_anchors, '产物存在未授权可点击外链：\n    ' +
         '\n    '.join(sorted(set(bad_anchors))[:20]))

    # 自动加载型外部引用（script/link/img/iframe/fetch/sendBeacon）一律禁止
    auto = re.compile(
        r'(?:<script[^>]+src|<link[^>]+href|<img[^>]+src|<iframe[^>]+src)="https?://'
        r'|(?:fetch|sendBeacon)\(\s*["\']https?://'
        r'|new\s+Image\(\)\.src\s*=\s*["\']https?://'
        r'|importScripts\(\s*["\']https?://', re.I)
    for p in files:
        if p.suffix not in ('.html', '.js', '.css'):
            continue
        try:
            s = p.read_text(encoding='utf-8')
        except (UnicodeDecodeError, OSError):
            continue
        need(not auto.search(s), '%s 存在自动加载型外部引用' % p.relative_to(www))

    # 页面级导流痕迹：只查「实际渲染的元素/引用」，不查说明文字与 CSS 类名定义
    page_targets = [p for p in files
                    if p.suffix in ('.html', '.js') and 'assets/vendor' not in str(p)]
    banned_patterns = {
        'goods/ 入口': r'href="[^"]*goods/"',
        'kp/ 入口': r'href="[^"]*kp/"',
        '智商测试卡': r'<a[^>]+class="iq-card"|test\.pansgo\.com|儿童智商测试',
        '资源搜索导流': r'resource-search-btn|网盘资源搜索',
        'PWA 引用': r'<script[^>]+pwa\.js|<link[^>]+manifest\.webmanifest|serviceWorker\.register',
        '云信标': r'cloudflareinsights|cf-beacon',
        '上游统计端点': r'workers\.dev/collect|math-pansgo-stats',
    }
    for label, pat in banned_patterns.items():
        hits = []
        for p in page_targets:
            try:
                if re.search(pat, p.read_text(encoding='utf-8'), re.I):
                    hits.append(str(p.relative_to(www)))
            except (UnicodeDecodeError, OSError):
                pass
        need(not hits, '产物残留 %s：%s' % (label, ', '.join(hits[:6])))

    need(not (www / 'goods').exists(), 'goods/ 目录未删除')
    need(not (www / 'kp').exists(), 'kp/ 目录存在')
    need(not (www / 'sw.js').exists() and not (www / 'manifest.webmanifest').exists(),
         'PWA 文件未删除')

    mf = manifest_kv(root)
    need('永久免费' in mf.get('desc', ''), 'manifest desc 未声明永久免费')
    need('无商业推广' in mf.get('desc', ''), 'manifest desc 未声明无商业推广')
    # 变现词只查对外展示文案，说明页里「不暗示…赞助」这类否定句不算
    display_blob = mf.get('desc', '') + json.dumps(
        json.loads(text(root / 'wizard/install')), ensure_ascii=False) + text(root / 'app/ui/config')
    need(not re.search(r'打赏|捐赠|付费解锁|会员专享|立即购买|推广链接|淘宝联盟|京东联盟',
                       display_blob), '对外展示文案含变现词')
    notes.append('条件1 PASS：零自动加载外部引用、零推广导流、免费声明齐全')


def check_c2(root, www, upstream):
    """条件 2：署名、四个链接、许可全文、改编声明、改动清单、vendor 许可。"""
    about = www / 'ABOUT-NAS.html'
    need(about.is_file(), '缺失 ABOUT-NAS.html')
    if about.is_file():
        s = text(about)
        for label, token in [
            ('原作者署名', 'xiaoyang111222'),
            ('原仓库链接', 'https://github.com/xiaoyang111222/cn-math-taxonomy'),
            ('原在线站点链接', 'https://math.pansgo.com/'),
            ('CC BY-NC 4.0', 'CC BY-NC 4.0'),
            ('许可全文链接', 'LICENSE-upstream.txt'),
            ('基于原项目改编', '基于原项目改编'),
            ('改动清单链接', 'CHANGES.html'),
        ]:
            need(token in s, '关于页缺失：%s' % label)

    # 打包铁律要求全仓 LF，上游文本是 CRLF；按「归一化换行后逐字节一致」比对，
    # 既保住许可全文未被删改，又不违反换行纪律。
    def norm(p):
        return p.read_bytes().replace(b'\r\n', b'\n')

    lic = www / 'LICENSE-upstream.txt'
    need(lic.is_file(), '缺失随包许可全文 LICENSE-upstream.txt')
    if upstream and lic.is_file():
        src = upstream / 'LICENSE'
        need(src.is_file() and norm(src) == norm(lic),
             'LICENSE-upstream.txt 与上游 LICENSE 内容不一致（不得删改许可全文）')

    changes = www / 'CHANGES.html'
    need(changes.is_file(), '缺失改动清单 CHANGES.html')
    if changes.is_file():
        s = text(changes)
        need('0.1.0' in s, '改动清单缺少当前版本条目')

    for pat in ['LICENSE-cytoscape.txt', 'LICENSE-dagre.txt',
                'LICENSE-cytoscape-dagre.txt', 'LICENSE-qrcode-generator.txt', 'VENDOR.md']:
        need((www / 'assets/vendor' / pat).is_file(), 'vendor 许可文件缺失: %s' % pat)
    if upstream:
        for pat in ['LICENSE-cytoscape.txt', 'LICENSE-dagre.txt',
                    'LICENSE-cytoscape-dagre.txt', 'LICENSE-qrcode-generator.txt', 'VENDOR.md']:
            a, b = www / 'assets/vendor' / pat, upstream / 'assets/vendor' / pat
            need(a.is_file() and b.is_file() and norm(a) == norm(b),
                 'vendor 许可内容被改动: %s' % pat)
    notes.append('条件2 PASS：署名/链接/许可全文/改编声明/清单/vendor 许可齐全')


def check_c3(root, www):
    """条件 3：显示名与描述不出现禁用词，不暗示背书。"""
    banned = ['官方', '授权', '合作']
    mf = manifest_kv(root)
    need(mf.get('display_name') == '中小学知识图谱（本地版）',
         'display_name 不是获准的名称：%s' % mf.get('display_name'))
    for field in ['display_name', 'desc', 'changelog']:
        v = mf.get(field, '')
        for w in banned:
            need(w not in v, 'manifest %s 含禁用词「%s」' % (field, w))

    uic = json.loads(text(root / 'app/ui/config'))
    for key, entry in uic.get('.url', {}).items():
        for field in ['title', 'desc']:
            for w in banned:
                need(w not in entry.get(field, ''),
                     'ui/config %s.%s 含禁用词「%s」' % (key, field, w))

    wz = json.loads(text(root / 'wizard/install'))
    blob = json.dumps(wz, ensure_ascii=False)
    for w in banned:
        need(w not in blob, '安装向导文案含禁用词「%s」' % w)

    # 关于页必须明确否认背书（否定语境允许出现这些词，但不能缺）
    if (www / 'ABOUT-NAS.html').is_file():
        s = text(www / 'ABOUT-NAS.html')
        need('不构成合作、代理或背书关系' in s or '不暗示' in s,
             '关于页缺少不构成背书关系的明确声明')
    notes.append('条件3 PASS：显示名/描述/向导零禁用词，关于页明确否认背书')


def check_c4(root, www):
    """条件 4：统计默认关闭锁死（含安装向导选择入口），仅三类事件，无个人信息字段。"""
    cfg = www / 'assets/stats-config.js'
    need(cfg.is_file(), '缺失统计适配层 stats-config.js')
    if cfg.is_file():
        s = text(cfg)
        need('defaultEnabled' not in s, '统计层出现 defaultEnabled，默认关闭可能被配置绕过')
        need('CFG.defaultEnabled' not in s, '统计层仍读取配置默认态')
        need('CFG.INSTALL_DEFAULT' not in s, '统计层从配置读取安装默认态，配置可绕过默认关闭')
        # 出厂默认关闭：INSTALL_DEFAULT 锚点恒 false，只能由 cmd 回调在用户显式选择后烧写
        need('var INSTALL_DEFAULT = false;' in s,
             '统计层出厂 INSTALL_DEFAULT 不是 false，默认关闭未锁死')
        need('var INSTALL_DEFAULT = true;' not in s,
             '统计层出厂即默认开启，违反授权条件 4')
        # 开启优先级：localStorage 显式 '1' > 显式 '0' > 安装向导选择
        need("if (v === '1') return true;" in s, 'enabled() 缺少「显式开启」优先判定')
        need("if (v === '0') return false;" in s, 'enabled() 缺少「显式关闭」优先判定')
        need('return INSTALL_DEFAULT === true;' in s, 'enabled() 未以安装向导选择作回落')
        for t in re.findall(r"push\('([a-z_]+)'", s):
            need(t in ('install', 'open', 'update'), '出现未授权事件类型: %s' % t)
        for forbidden in ['ev.path', 'ev.props', 'location.pathname', 'location.href',
                          'navigator.userAgent', 'document.cookie']:
            need(forbidden not in s, '统计层出现可能外泄的字段: %s' % forbidden)
        need('cloudflareToken: \'\'' in s, 'cloudflareToken 未置空')
        need("endpoint: ''" in s, '上游原始 endpoint 未置空')

    endpoint = www / 'assets/stats-endpoint.js'
    # script 标签级匹配（注释里的文字提及不算引用）
    ep_tag = re.compile(r'<script[^>]+src="[^"]*stats-endpoint\.js"')
    cfg_tag = re.compile(r'<script[^>]+src="[^"]*stats-config\.js"')
    if endpoint.is_file():
        need('defaultEnabled' not in text(endpoint), '统计端点配置含默认开启开关')
        # 注入了端点的构建：凡加载 stats-config.js 的页面都必须先加载端点配置，
        # 否则关于页会误判「未配置」而禁用统计开关（0.1.0.9 修复的缺口，防复发）。
        for p in www.rglob('*.html'):
            s = text(p)
            need(not cfg_tag.search(s) or ep_tag.search(s),
                 '%s 加载了 stats-config.js 却未注入 stats-endpoint.js' % p.relative_to(www))
    else:
        # 未注入端点时，页面不得有指向该文件的 script 引用（否则 404 且开关不可用）
        for p in www.rglob('*.html'):
            need(not ep_tag.search(text(p)),
                 '%s 引用了不存在的 stats-endpoint.js' % p.relative_to(www))
        notes.append('条件4 附注：本次构建未注入统计端点，统计完全零请求')

    if (www / 'ABOUT-NAS.html').is_file():
        s = text(www / 'ABOUT-NAS.html')
        need('默认关闭' in s, '关于页未声明统计默认关闭')
        need('主动开启' in s, '关于页未提供主动开启入口')
        need('一键关闭' not in s or '关闭后零上报' in s, '关于页缺少关闭后零上报说明')
        need('安装向导' in s, '关于页未说明安装向导的统计选择入口')
    wz_obj = json.loads(text(root / 'wizard/install'))
    wz = json.dumps(wz_obj, ensure_ascii=False)
    need('默认关闭' in wz, '安装向导未告知统计默认关闭')
    need('主动开启' in wz, '安装向导未告知需主动开启')
    # 安装向导的统计选择必须默认关闭：唯一 radio 项且 initValue=off
    stat_items = [it for step in wz_obj for it in step.get('items', [])
                  if it.get('field') == 'wizard_stats_consent']
    need(len(stat_items) == 1, '安装向导缺少唯一的统计选择项 wizard_stats_consent')
    if stat_items:
        need(stat_items[0].get('type') == 'radio' and stat_items[0].get('initValue') == 'off',
             '统计选择默认值不是「不开启」，违反默认关闭')
    # 安装/升级回调必须实现「用户显式选择 → 烧写/恢复」链路，且空值绝不凭空开启
    ic = text(root / 'cmd/install_callback')
    need('wizard_stats_consent' in ic, '安装回调未处理向导统计选择')
    need('INSTALL_DEFAULT = true' in ic, '安装回调未实现统计默认值烧写')
    need('cnmath-stats-consent' in ic, '安装回调未持久化统计选择')
    # 回归防护（2026-11-17 真机安装事故）：
    # ① 向导字段值可能是 JSON 形态（["on"]），必须规范化后再比对；
    # ② app.tgz 解包剥掉 app/ 层，安装根下直接是 ui/ 与 www/，禁止写死 app/ui 旧层级。
    need('tr -d' in ic, '安装回调未规范化向导字段值形态（JSON 序列化兼容）')
    need('app/ui/index.cgi' not in ic and 'app/www/' not in ic,
         '安装回调写死了 app/ 旧布局层级（app.tgz 解包后安装根下直接是 ui/ 与 www/）')
    uc = text(root / 'cmd/upgrade_callback')
    need('cnmath-stats-consent' in uc and 'INSTALL_DEFAULT' in uc,
         '升级回调未按持久化选择恢复统计默认值')
    need('app/www/' not in uc, '升级回调写死了 app/ 旧布局层级')
    notes.append('条件4 PASS：默认关闭锁死（安装向导默认不开启）、仅三类事件、告知与关闭入口齐全')


def check_c5(root, www):
    """条件 5：清单版本与上游 commit 一致。"""
    mf = manifest_kv(root)
    ver = mf.get('version', '')
    commit = text(root / 'UPSTREAM_COMMIT').strip()
    need(bool(re.fullmatch(r'\d+\.\d+\.\d+', ver)), 'manifest version 不是三段式: %s' % ver)
    if (www / 'CHANGES.html').is_file():
        s = text(www / 'CHANGES.html')
        m = re.search(r'data-version="([^"]+)"', s)
        need(bool(m) and m.group(1) == ver,
             'CHANGES.html 的 data-version(%s) 与 manifest.version(%s) 不一致' %
             (m.group(1) if m else '缺失', ver))
        m2 = re.search(r'data-upstream-commit="([^"]+)"', s)
        need(bool(m2) and m2.group(1) == commit,
             'CHANGES.html 的上游 commit 与 UPSTREAM_COMMIT 不一致')
        need(ver in s, 'CHANGES.html 缺少 %s 的版本条目' % ver)
    need((root / 'AUTHORIZATION-GRANTED.md').is_file(), '缺失授权回信留档')
    notes.append('条件5 PASS：清单版本/commit 与工程一致，授权留档存在')


def check_c6(root, www):
    """条件 6：不冒名提供支持。"""
    if (www / 'ABOUT-NAS.html').is_file():
        s = text(www / 'ABOUT-NAS.html')
        need('不为本应用提供任何支持、服务或承诺' in s,
             '关于页缺少「原作者不提供支持」声明')
        need('原仓库提交 Issue' in s or 'issues/new/choose' in s,
             '关于页未把题目问题引导到上游 Issue')
    wz = json.dumps(json.loads(text(root / 'wizard/install')), ensure_ascii=False)
    need('不为本应用提供任何支持、服务或承诺' in wz,
         '安装向导缺少「原作者不提供支持」声明')
    notes.append('条件6 PASS：不冒名支持，问题引导至上游 Issue')


def check_c7(root, www):
    """条件 7：范围、失效与下架义务。"""
    lic = text(root / 'LICENSE')
    for token in ['自动失效', '即时下架', '不构成双方的合作、代理或背书关系',
                  '仅限上述非商业分发']:
        need(token in lic, 'LICENSE 第三节缺少：%s' % token)
    comp = root / 'COMPLIANCE.md'
    need(comp.is_file(), '缺失 COMPLIANCE.md')
    if comp.is_file():
        need('飞牛官方应用中心' in text(comp), 'COMPLIANCE.md 未限定分发渠道')
        need('GitHub Release' in text(comp), 'COMPLIANCE.md 未列出未授权渠道')
    need((root / 'AUTHORIZATION-REQUEST.md').is_file(), '缺失授权请求函留档')
    notes.append('条件7 PASS：范围/失效/下架义务已写入 LICENSE 与合规文档')


def check_lf(root, www):
    """全仓 LF（含无扩展名脚本），CRLF 会让 NAS 上的 bash 静默炸掉。

    只检查「UTF-8 可解码的文本」；PNG/EXE 等二进制里天然可能含 0D0A 字节序列，
    不能按文本处理（否则误报，且强行改写会直接损坏文件）。
    """
    skip_dirs = {'.build', '.tools', 'dist', '.git', '__pycache__'}
    bin_ext = {'.png', '.jpg', '.jpeg', '.gif', '.ico', '.webp', '.bmp',
               '.exe', '.dll', '.fpk', '.zip', '.7z', '.gz', '.woff', '.woff2'}
    bad = []
    for base in [root, www]:
        for p in base.rglob('*'):
            if not p.is_file() or skip_dirs.intersection(p.parts) or p.suffix.lower() in bin_ext:
                continue
            b = p.read_bytes()
            try:
                b.decode('utf-8')
            except UnicodeDecodeError:
                continue
            if b'\r\n' in b:
                bad.append(str(p.relative_to(root)))
    need(not bad, '以下文本文件含 CRLF：%s' % ', '.join(bad[:10]))
    notes.append('LF 检查 PASS：全仓文本文件无 CRLF（二进制按字节原样保留）')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', required=True)
    ap.add_argument('--upstream', default=None)
    a = ap.parse_args()
    root = Path(a.root)
    www = root / 'app/www'
    upstream = Path(a.upstream) if a.upstream else None

    check_c1(root, www)
    check_c2(root, www, upstream)
    check_c3(root, www)
    check_c4(root, www)
    check_c5(root, www)
    check_c6(root, www)
    check_c7(root, www)
    check_lf(root, www)

    for n in notes:
        print('  ' + n)
    if errors:
        print('\nRESULT=FAIL  （%d 项不合规，禁止产出 .fpk）' % len(errors))
        for e in errors:
            print('  - ' + e)
        return 1
    print('\nRESULT=PASS  （7 项条件全部满足，允许产出 .fpk）')
    return 0


if __name__ == '__main__':
    sys.exit(main())
