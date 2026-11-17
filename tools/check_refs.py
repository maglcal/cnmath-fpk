#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""产物引用完整性：所有本地静态资源引用必须能解析到真实文件。

站点挂在 CGI 子路径下，一个悬空引用在浏览器里就是静默 404，
图谱不报错但直接白屏。这项检查进构建链，不允许「先发再说」。

路径基点规则：
- HTML/CSS 的 src/href/url() 按「引用所在文件目录」解析；
- JS 的 fetch('...') 与数据文件字符串按「页面 URL」解析，
  故用「站点根 + 所有 HTML 页面所在目录」作候选基点，任一命中即可。
"""
import re
import sys
from pathlib import Path

EXTERNAL = re.compile(r'^(https?:|data:|mailto:|javascript:|#|//)', re.I)
STATIC_LIKE = re.compile(r'\.(?:json|js|css|png|jpe?g|gif|svg|webp|woff2?|txt|html?)$', re.I)
PAGE_EXTS = ('.html', '.js', '.css')


def main(www):
    www = Path(www).resolve()
    errors = []
    checked = 0

    pages = [p.parent for p in www.rglob('*.html')]
    bases = [www] + sorted(set(pages), key=str)

    def exists_at(base, ref):
        clean = ref.split('?')[0].split('#')[0]
        if not clean:
            return True
        target = (base / clean).resolve()
        try:
            target.relative_to(www)
        except ValueError:
            return False
        return (target / 'index.html').is_file() if clean.endswith('/') else target.is_file()

    def check(owner, ref, js=False):
        nonlocal checked
        if not ref or EXTERNAL.match(ref) or ref.startswith('{{'):
            return
        # 动态拼接前缀（如 fetch('../data/' + file)）：不是完整引用，跳过
        if js and ref.endswith('/'):
            return
        checked += 1
        if js:
            ok = any(exists_at(b, ref) for b in bases)
            # 纯数据文件名（var files = ['topics.json', ...]）按 data/ 目录解析
            if not ok and '/' not in ref and STATIC_LIKE.search(ref):
                ok = (www / 'data' / ref).is_file()
        else:
            ok = exists_at(owner.parent, ref)
        if not ok:
            errors.append('%s: 悬空引用 %s' % (owner.relative_to(www), ref))

    for p in sorted(www.rglob('*')):
        if not p.is_file() or p.suffix not in PAGE_EXTS:
            continue
        rel = p.relative_to(www)
        if rel.parts[:2] == ('assets', 'vendor'):
            continue            # 第三方库原样保留，内部字符串不是站点资源引用
        try:
            s = p.read_text(encoding='utf-8')
        except (UnicodeDecodeError, OSError):
            continue

        if p.suffix == '.html':
            for m in re.finditer(r'(?:src|href)\s*=\s*["\']([^"\']+)["\']', s, re.I):
                check(p, m.group(1))
        elif p.suffix == '.css':
            for m in re.finditer(r'\burl\(\s*["\']?([^"\')]+)["\']?\s*\)', s, re.I):
                check(p, m.group(1))

        if p.suffix in ('.html', '.js'):
            # fetch 只检查看起来像静态路径的字面量，跳过 fetch(url) 这类变量
            for m in re.finditer(r'fetch\(\s*["\']([^"\']+)["\']', s):
                if '/' in m.group(1) or STATIC_LIKE.search(m.group(1)):
                    check(p, m.group(1), js=True)
            # 数据文件清单字符串（如 'topics.json'）
            for m in re.finditer(r"['\"]([A-Za-z0-9_./-]+\.json)['\"]", s):
                check(p, m.group(1), js=True)

    print('[refs] 检查 %d 条本地引用' % checked)
    if errors:
        print('[refs] RESULT=FAIL')
        for e in errors[:40]:
            print('  - ' + e)
        if len(errors) > 40:
            print('  ... 还有 %d 条' % (len(errors) - 40))
        return 1
    print('[refs] RESULT=PASS')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else 'app/www'))
