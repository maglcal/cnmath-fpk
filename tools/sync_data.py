#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""上游数据同步器（上游 2026-11-25 仓库拆分后的双轨机制）。

背景：上游把网站源码迁出至私有仓，公开仓只留数据与数据工具链。
本工程策略：站点源码冻结在 UPSTREAM_COMMIT（拆分前最后完整快照），
数据持续从上游 origin/main 同步白名单文件，落在快照仓 data-sync 分支上。

双 commit 钉版本：
- UPSTREAM_COMMIT       站点基线（冻结，不再变化）
- UPSTREAM_DATA_COMMIT  数据同步点（origin/main 上的 commit，每次同步更新）

用法：
  python tools/sync_data.py --list            # 只列出上游数据提交清单（人审）
  python tools/sync_data.py --apply           # 执行同步（含上游数据侧测试）
  python tools/sync_data.py --apply --skip-tests   # 逃生口：跳过上游测试（不推荐）

纪律：
- --apply 前必须先 --list 人审提交清单（工具不替你审）。
- 白名单外的数据文件（data/_qbatches、data/mappings 等）冻结引擎不 fetch，不搬运。
- questions.json 单文件是上游拆分过渡期的双写产物；一旦上游废弃单文件，
  白名单 checkout 会直接 FAIL（fail loud），届时需人工决定拼接预案，绝不静默降级。
"""
import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

# 与 build_site.py 的 DATA_FILES 保持一致（冻结引擎实际 fetch 的数据文件）
DATA_FILES = [
    'topics.json', 'dependencies.json', 'id-aliases.json',
    'cn-curriculum-standards.json', 'questions.json',
]


def git(snap, *args, check=True):
    return subprocess.run(['git', '-C', str(snap)] + list(args),
                          capture_output=True, text=True, check=check)


def die(msg):
    print('ERROR: %s' % msg)
    sys.exit(1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', default=None, help='工程根（默认脚本上一级）')
    ap.add_argument('--upstream', default=None, help='快照仓目录（默认 <root>/.build/cn-math-taxonomy）')
    ap.add_argument('--ref', default='origin/main', help='数据来源 ref（默认 origin/main）')
    ap.add_argument('--list', action='store_true', help='只列提交清单，不做任何改动')
    ap.add_argument('--apply', action='store_true', help='执行同步')
    ap.add_argument('--skip-tests', action='store_true', help='跳过上游数据侧测试（不推荐）')
    args = ap.parse_args()

    if args.apply == args.list:
        die('必须且只能指定 --list 或 --apply 之一')

    root = Path(args.root) if args.root else Path(__file__).resolve().parent.parent
    snap = Path(args.upstream) if args.upstream else root / '.build/cn-math-taxonomy'
    up_commit_file = root / 'UPSTREAM_COMMIT'
    data_commit_file = root / 'UPSTREAM_DATA_COMMIT'

    if not snap.is_dir():
        die('快照仓不存在: %s' % snap)
    if not up_commit_file.is_file():
        die('UPSTREAM_COMMIT 缺失')
    base = up_commit_file.read_text(encoding='utf-8').strip()

    r = git(snap, 'fetch', 'origin', check=False)
    if r.returncode != 0:
        die('fetch 失败: %s' % r.stderr.strip())
    r = git(snap, 'rev-parse', '--verify', args.ref + '^{commit}', check=False)
    if r.returncode != 0:
        die('ref 不存在: %s' % args.ref)
    ref = r.stdout.strip()

    # 数据健康前提：白名单文件在来源 ref 上必须齐全
    missing = [f for f in DATA_FILES
               if git(snap, 'cat-file', '-e', '%s:data/%s' % (ref, f), check=False).returncode != 0]
    if missing:
        die('来源 ref 缺少白名单数据文件（可能上游废弃单文件，须人工裁决）: %s'
            % ', '.join(missing))

    # 人审清单：站点基线以来触及 data/ 的提交
    log = git(snap, 'log', '--oneline', '--no-decorate', '%s..%s' % (base, ref), '--', 'data/')
    commits = [ln for ln in log.stdout.splitlines() if ln.strip()]
    touched = git(snap, 'diff', '--name-only', '%s..%s' % (base, ref), '--', 'data/').stdout.split()
    touched = sorted({t for t in touched if t.startswith('data/')})
    in_scope = [t for t in touched if t[5:] in DATA_FILES]
    out_scope = [t for t in touched if t[5:] not in DATA_FILES]

    print('== 数据同步人审清单 ==')
    print('站点基线（UPSTREAM_COMMIT，冻结）: %s' % base[:12])
    print('数据来源 ref                     : %s = %s' % (args.ref, ref[:12]))
    print('上游 data/ 提交 %d 个:' % len(commits))
    for ln in commits:
        print('  ' + ln)
    print('白名单内变更文件 %d 个: %s' % (len(in_scope), ', '.join(in_scope) or '（无）'))
    if out_scope:
        print('白名单外变更（冻结引擎不 fetch，不搬运）%d 个: %s'
              % (len(out_scope), ', '.join(out_scope[:8]) + ('...' if len(out_scope) > 8 else '')))
    if not commits:
        print('上游数据无更新，无需同步。')
        return 0

    if args.list:
        print('\n[--list] 仅列清单。人审后执行: python tools/sync_data.py --apply')
        return 0

    # --apply：快照工作树必须干净，且 HEAD 在 data-sync 分支链上（或站点基线本身）
    st = git(snap, 'status', '--porcelain')
    if st.stdout.strip():
        die('快照工作树有未提交改动，拒绝同步:\n%s' % st.stdout.strip()[:500])
    head = git(snap, 'rev-parse', 'HEAD').stdout.strip()
    anc = git(snap, 'merge-base', '--is-ancestor', base, head, check=False)
    if anc.returncode != 0:
        die('当前快照 HEAD(%s) 不包含站点基线(%s)，快照仓状态异常' % (head[:12], base[:12]))

    # 1. 数据健康检查：在临时目录展开来源 ref，跑上游数据侧测试链
    if not args.skip_tests:
        print('\n== 上游数据侧测试（来源 ref 全量展开）==')
        with tempfile.TemporaryDirectory(prefix='cnm-sync-') as td:
            arc = subprocess.run(['git', '-C', str(snap), 'archive', ref],
                                 capture_output=True, check=True)
            (Path(td) / 'up').mkdir()
            subprocess.run(['tar', '-xf', '-'], input=arc.stdout, cwd=Path(td) / 'up',
                           check=True)
            up = Path(td) / 'up'
            import shutil as _sh
            node = _sh.which('node')
            steps = [
                ['python', 'tests/test_verify_exact.py'],
                ['python', 'scripts/validate.py'],
                ['python', 'scripts/check_figures.py'],
                ['python', 'scripts/verify_questions.py', '--report', str(Path(td) / 'report.json')],
            ]
            if node:
                steps += [['node', 'tests/test_question_ids.js']]
            else:
                print('  （node 不可用，跳过 node 数据测试）')
            failed = []
            for cmd in steps:
                rr = subprocess.run(cmd, cwd=up, capture_output=True, text=True)
                tag = 'PASS' if rr.returncode == 0 else 'FAIL'
                print('  [%s] %s' % (tag, ' '.join(cmd[1:])))
                if rr.returncode != 0:
                    tail = (rr.stdout + rr.stderr).strip().splitlines()
                    for ln in tail[-8:]:
                        print('      ' + ln)
                    failed.append(cmd[1])
            if failed:
                die('上游数据测试未过，禁止同步: %s' % ', '.join(failed))
        print('  全部通过。')
    else:
        print('\n[--skip-tests] 跳过上游数据侧测试（此构建质量自负）')

    # 2. 白名单 checkout + 落同步 commit（data-sync 分支链）
    git(snap, 'checkout', '-B', 'data-sync')
    for f in DATA_FILES:
        git(snap, 'checkout', ref, '--', 'data/' + f)
    prev_data = data_commit_file.read_text(encoding='utf-8').strip() if data_commit_file.is_file() else base
    msg = ('数据同步：上游 %s（%s..%s）\n\n来源 ref: %s\n上一数据点: %s\n白名单文件: %s\n'
           % (ref[:12], base[:8], ref[:8], args.ref, prev_data[:12], ', '.join(DATA_FILES)))
    git(snap, 'commit', '-m', msg)
    new_head = git(snap, 'rev-parse', 'HEAD').stdout.strip()

    # 3. 写 UPSTREAM_DATA_COMMIT
    data_commit_file.write_text(ref + '\n', encoding='utf-8', newline='\n')

    print('\n== 同步完成 ==')
    print('快照仓 data-sync HEAD: %s' % new_head[:12])
    print('UPSTREAM_DATA_COMMIT : %s' % ref[:12])
    print('下一步: bash build.sh --test  （闸门全过再考虑出包/发版）')
    return 0


if __name__ == '__main__':
    sys.exit(main())
