"""大图幅本地 OCR，坐标使用 PDF 显示页的点单位。"""
from pathlib import Path
import json
import re
import time
import unicodedata

DPI = 300
TILE = 2000
DEFAULT_THRESHOLD = 165


def starts(length):
    if length <= TILE:
        return [0]
    step = round(TILE * .90)
    return [0, *range(step, length - (TILE-step), step)]


def columns(rows, width):
    # 用常规正文行在页中部的覆盖率找栏缝。仅排除跨栏标题、图框和页签。
    import numpy as np
    cover = np.zeros(width + 1)
    for x, y, r, b in rows:
        if width * .04 < r - x < width * .72:
            cover[x] += 1
            cover[r] -= 1
    profile = np.cumsum(cover)[:width]
    lo, hi = int(width * .41), int(width * .61)
    if profile.max() < 5:
        return None
    idx = np.arange(lo, hi)
    mid = int(idx[np.argmin(profile[idx] + np.abs(idx-width/2)/width)])
    return mid if profile[mid] < profile.max() * .18 else None


def join_boxes(boxes, width):
    divider = columns(boxes, width)
    groups = {}
    for box in sorted(boxes, key=lambda b: ((b[1] + b[3])/2, b[0])):
        x,y,r,b = box
        band = int(divider is not None and (x+r)/2 >= divider)
        lines = groups.setdefault(band, [])
        candidates = [q for q in lines if min(q[3],b)-max(q[1],y) > .62 * min(b-y,q[3]-q[1])
                      and abs((b+y-q[3]-q[1])/2) < .4 * max(b-y,q[3]-q[1])
                      and x < q[2] + (b-y)*.55 and r > q[0] - (b-y)*.55]
        if candidates:
            for prior in candidates:
                x,y,r,b=min(x,prior[0]),min(y,prior[1]),max(r,prior[2]),max(b,prior[3])
                lines.remove(prior)
        lines.append([x,y,r,b])
    return [box for band in sorted(groups) for box in sorted(groups[band],key=lambda q:(round((q[1]+q[3])/24),q[0]))]
