#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成原创应用图标（纯标准库，无 Pillow/依赖）。

图案为自绘的「知识点节点 + 先修连线」抽象图，不使用上游 favicon / 图标，
避免与原项目品牌混淆（授权条件 3）。输出 PNG RGBA，所有字节手写，保证 LF 链路干净。
"""
import math
import struct
import sys
import zlib
from pathlib import Path

BG = (15, 118, 110)        # 深青
BG_LIGHT = (24, 148, 136)
NODE = (223, 243, 239)
EDGE = (190, 232, 224)
ACCENT = (255, 214, 102)

# 归一化坐标：4 个知识点 + 4 条先修边
NODES = [(0.27, 0.30), (0.70, 0.26), (0.46, 0.60), (0.76, 0.71)]
EDGES = [(0, 2), (1, 2), (2, 3), (0, 1)]
R = 0.082
LINE_W = 0.019


def _chunk(tag, data):
    return (struct.pack('>I', len(data)) + tag + data
            + struct.pack('>I', zlib.crc32(tag + data) & 0xffffffff))


def _png(width, height, rows):
    raw = b''.join(b'\x00' + bytes(v for px in row for v in px) for row in rows)
    comp = zlib.compress(raw, 9)
    return (b'\x89PNG\r\n\x1a\n'
            + _chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0))
            + _chunk(b'IDAT', comp)
            + _chunk(b'IEND', b''))


def _render(size):
    s = 3                       # 3x 超采样后盒式降采样，边缘不锯齿
    n = size * s
    px = [[(0, 0, 0, 0) for _ in range(n)] for _ in range(n)]

    def put(x, y, color, alpha=255):
        if 0 <= x < n and 0 <= y < n:
            px[y][x] = (color[0], color[1], color[2], alpha)

    # 圆角矩形底
    rad = 0.20 * n
    for y in range(n):
        for x in range(n):
            cx = min(x, n - 1 - x)
            cy = min(y, n - 1 - y)
            inside = True
            if cx < rad and cy < rad:
                inside = (cx - rad) ** 2 + (cy - rad) ** 2 <= rad ** 2
            if inside:
                t = y / n
                c = tuple(int(BG[i] * (1 - t) + BG_LIGHT[i] * t) for i in range(3))
                put(x, y, c)

    # 先修连线
    for a, b in EDGES:
        x1, y1 = NODES[a][0] * n, NODES[a][1] * n
        x2, y2 = NODES[b][0] * n, NODES[b][1] * n
        dist = math.hypot(x2 - x1, y2 - y1)
        steps = int(dist) + 1
        half = LINE_W * n / 2
        for i in range(steps + 1):
            t = i / steps
            cx, cy = x1 + (x2 - x1) * t, y1 + (y2 - y1) * t
            for dy in range(-int(half) - 1, int(half) + 2):
                for dx in range(-int(half) - 1, int(half) + 2):
                    if dx * dx + dy * dy <= half * half:
                        put(int(cx) + dx, int(cy) + dy, EDGE)

    # 节点（外圈 + 内芯）
    nr = R * n
    for idx, (nx, ny) in enumerate(NODES):
        cx, cy = nx * n, ny * n
        for dy in range(-int(nr) - 1, int(nr) + 2):
            for dx in range(-int(nr) - 1, int(nr) + 2):
                d2 = dx * dx + dy * dy
                if d2 <= nr * nr:
                    c = NODE if idx != 3 else ACCENT
                    put(int(cx) + dx, int(cy) + dy, c)
        ir = nr * 0.40
        for dy in range(-int(ir) - 1, int(ir) + 2):
            for dx in range(-int(ir) - 1, int(ir) + 2):
                if dx * dx + dy * dy <= ir * ir:
                    put(int(cx) + dx, int(cy) + dy, BG)

    # 降采样
    out = []
    for y in range(size):
        row = []
        for x in range(size):
            acc = [0, 0, 0, 0]
            for dy in range(s):
                for dx in range(s):
                    p = px[y * s + dy][x * s + dx]
                    for k in range(4):
                        acc[k] += p[k]
            row.append(tuple(v // (s * s) for v in acc))
        out.append(row)
    return _png(size, size, out)


def main(root):
    root = Path(root)
    targets = [
        (root / 'ICON.PNG', 64),
        (root / 'ICON_256.PNG', 256),
        (root / 'ICON_512.PNG', 512),
        (root / 'app/ui/images/icon_64.png', 64),
        (root / 'app/ui/images/icon_256.png', 256),
    ]
    for path, size in targets:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(_render(size))
        print('[icon] %s %dx%d %d bytes' % (path.relative_to(root), size, size, path.stat().st_size))


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else '.')
