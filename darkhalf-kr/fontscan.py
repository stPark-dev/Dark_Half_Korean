#!/usr/bin/env python3
"""SNES 폰트 타일 스캐너 (v2).

v1 실패 원인: 밀도/여백 기준은 코드·구조체 데이터도 통과시킨다(후보 7만개).
v2의 두 축:
  1) 고립 픽셀 비율 - 진짜 글리프는 획이 연결돼 있다. 난수성 데이터는 점이 흩어진다.
  2) 연속 구간 길이 - 폰트는 글리프가 수백 개 연속으로 놓인다. 우연은 길게 못 간다.
"""
import sys

def tiles_1bpp(d, o): return [d[o+r] for r in range(8)], 8
def tiles_2bpp(d, o): return [d[o+r*2] | d[o+r*2+1] for r in range(8)], 16
MODES = {1: (8, tiles_1bpp), 2: (16, tiles_2bpp)}
POP = bytes(bin(i).count('1') for i in range(256))

def analyze(rows):
    """(ink, isolated) 반환. rows = 8개 바이트, bit7=왼쪽 픽셀"""
    g = [[(rows[y] >> (7-x)) & 1 for x in range(8)] for y in range(8)]
    ink = sum(map(sum, g)); iso = 0
    for y in range(8):
        for x in range(8):
            if not g[y][x]: continue
            n = 0
            if y > 0: n += g[y-1][x]
            if y < 7: n += g[y+1][x]
            if x > 0: n += g[y][x-1]
            if x < 7: n += g[y][x+1]
            if n == 0: iso += 1
    return ink, iso

def is_glyph(rows):
    ink, iso = analyze(rows)
    if ink == 0: return None           # 빈 타일: 허용하되 글리프로 세지 않음
    if ink < 5 or ink > 48: return False
    return (iso / ink) < 0.20          # 획 연결성

def scan(path, bpp, min_run=48):
    d = open(path,'rb').read()
    sz, rd = MODES[bpp]
    n = len(d)//sz
    flags = []
    for t in range(n):
        rows, _ = rd(d, t*sz)
        flags.append(is_glyph(rows))
    runs = []; start = None; good = 0; total = 0
    for t, f in enumerate(flags):
        if f is False:
            if start is not None and total and good/total >= 0.75 and total >= min_run:
                runs.append((start, t, good, total))
            start = None; good = total = 0
        else:
            if start is None: start = t
            total += 1
            if f: good += 1
    if start is not None and total >= min_run and good/total >= 0.75:
        runs.append((start, len(flags), good, total))
    runs.sort(key=lambda r: -(r[3]))
    return d, sz, rd, runs

def render(d, rd, sz, tile_idx, n=16):
    glyphs = [rd(d, (tile_idx+i)*sz)[0] for i in range(n)]
    for r in range(8):
        print("  " + " ".join(f"{g[r]:08b}".replace('0','.').replace('1','#') for g in glyphs))

if __name__ == "__main__":
    path = sys.argv[1]
    for bpp in (1, 2):
        d, sz, rd, runs = scan(path, bpp)
        print(f"\n{'='*70}\nbpp={bpp}  연속 구간 {len(runs)}개")
        for s, e, good, total in runs[:6]:
            print(f"\n--- 타일 {s}~{e}  offset {s*sz:#08x}-{e*sz:#08x}  "
                  f"글리프 {good}/{total} ({good/total*100:.0f}%) ---")
            render(d, rd, sz, s, 16)
