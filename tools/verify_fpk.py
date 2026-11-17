#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fpk 产物字节级换行验收——验收对象是 fnpack 之后的最终交付物。

规则（fnOS 打包铁律 2026-11-12 血泪 + 2026-11-17 整改）：
- bash 会执行的脚本（cmd/*、*.cgi、*.sh）：含 CRLF 直接 FAIL。
  CRLF 会让 NAS bash 的续行符断裂、报错指向无关模块（v0.1.40 cmd/main 事故）。
- manifest：fnpack.exe（Windows 版）打包固有写 CRLF，fnmedia-dl 线上发布版同款，
  由 fnOS 安装器解析、不经 bash 执行，允许存在，但显式报告，不许静默。
- 其余 UTF-8 可解码文本（json/html/js/css/无扩展名配置等）：含 CRLF FAIL。
- 二进制（UTF-8 不可解码）按字节原样跳过。

教训：换行防线必须覆盖到包内最终产物；只查工作区/stage 等于没查完。
检查一律数 \\r\\n 原始字节——grep 会吞 CR，不可信。
用法：python tools/verify_fpk.py <file.fpk>
"""
import io
import sys
import tarfile

errors = []
notes = []


def audit(label, data):
    crlf = data.count(b'\r\n')
    if crlf == 0:
        return
    is_shell = label.endswith(('.cgi', '.sh')) or label.startswith('cmd/')
    is_manifest = label.rsplit('/', 1)[-1] == 'manifest'
    if is_manifest:
        notes.append('manifest 含 CRLF=%d 行：fnpack.exe 打包固有行为（安装器解析、不经 bash），'
                     '与 fnmedia-dl 线上发布版同款，允许' % crlf)
    elif is_shell:
        errors.append('%s 含 CRLF=%d 行：bash 脚本必须纯 LF（血泪炸点）' % (label, crlf))
    else:
        # 其它文本
        try:
            data.decode('utf-8')
        except UnicodeDecodeError:
            return  # 二进制不动
        errors.append('%s 含 CRLF=%d 行：文本文件必须纯 LF' % (label, crlf))


def main():
    if len(sys.argv) != 2:
        print('用法：python tools/verify_fpk.py <file.fpk>')
        return 2
    p = sys.argv[1]
    try:
        outer = tarfile.open(p, 'r:gz')
    except Exception as e:
        print('[fpk] RESULT=FAIL （包无法解析：%s）' % e)
        return 1
    scanned = 0
    for m in outer.getmembers():
        if not m.isfile():
            continue
        b = outer.extractfile(m).read()
        scanned += 1
        if m.name == 'app.tgz':
            try:
                inner = tarfile.open(fileobj=io.BytesIO(b), mode='r:gz')
            except Exception as e:
                errors.append('app.tgz 无法解析：%s' % e)
                continue
            inner_names = set()
            ui_cfg = None
            for mi in inner.getmembers():
                inner_names.add(mi.name)
                if not mi.isfile():
                    continue
                ib = inner.extractfile(mi).read()
                scanned += 1
                if mi.name == 'ui/config':
                    ui_cfg = ib
                audit('app.tgz:' + mi.name, ib)
            # 结构检查（0.1.0.5）：桌面入口与 CGI 是安装后图标/打开的命脉，
            # 缺失或入口 JSON 不合法直接 FAIL，不让坏包出门。
            for need in ('ui/index.cgi', 'ui/config', 'www/index.html'):
                if need not in inner_names:
                    errors.append('app.tgz 缺少关键文件：%s' % need)
            if ui_cfg is not None:
                import json
                try:
                    doc = json.loads(ui_cfg.decode('utf-8'))
                    entries = doc.get('.url')
                    if not isinstance(entries, dict) or not entries:
                        errors.append('app.tgz:ui/config 的 .url 不是含条目的对象')
                    else:
                        for eid, ent in entries.items():
                            if not isinstance(ent, dict) or 'url' not in ent or 'title' not in ent:
                                errors.append('app.tgz:ui/config 入口 %s 缺 url/title' % eid)
                except Exception as e:
                    errors.append('app.tgz:ui/config JSON 不合法：%s' % e)
            continue
        audit(m.name, b)

    for n in notes:
        print('  附注: ' + n)
    if errors:
        print('[fpk] RESULT=FAIL （%d 项换行违规）' % len(errors))
        for e in errors:
            print('  - ' + e)
        return 1
    print('[fpk] RESULT=PASS  （%d 个文件字节级检查，脚本/文本全 LF）' % scanned)
    return 0


if __name__ == '__main__':
    sys.exit(main())
