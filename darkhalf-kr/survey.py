#!/usr/bin/env python3
"""텍스트 구간 조사 (v3 - 2단계).

단일 지표는 전부 실패했다:
  · 가나 밀도만       -> 오답 뱅크0x03(44.6%) > 정답 뱅크0x05(32.4%)
  · 한자esc 밀도만    -> 임계값 부근 그래픽 구간이 섞임
  · 상용문자 밀도만    -> 정답 시스템메시지(15.0%) ≈ 오답 뱅크0x02(14.5%)

v3: 싼 지표로 후보를 넓게 잡고(1단계), 실제 디코딩으로 확정한다(2단계).
    디코딩 검증은 정답 59~82% vs 오답 4~27% 로 명확히 갈린다.
"""
import sys, os, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dump import load_tbl, decode

BLK = 0x400
ESC_MIN = 0.020          # 1단계: 느슨하게
JP_MIN  = 0.35           # 2단계: 디코딩 검증 하한
COMMON = set("のはにをたてでとしかるないうまですっりらくきこそあおもみやよれわん、。「」")

def esc_density(seg):
    n = len(seg); e = 0; i = 0
    while i < n-1:
        if seg[i] in (0xF5, 0xF6): e += 2; i += 2
        else: i += 1
    return e/max(1, n)

def candidates(rom, blk=BLK):
    runs = []; cur = None
    for b in range(0, len(rom), blk):
        if esc_density(rom[b:b+blk]) >= ESC_MIN:
            if cur is None: cur = [b, b+blk]
            else: cur[1] = b+blk
        elif cur:
            runs.append(tuple(cur)); cur = None
    if cur: runs.append(tuple(cur))
    merged = []
    for r in runs:
        if merged and r[0]-merged[-1][1] <= blk*2: merged[-1] = (merged[-1][0], r[1])
        else: merged.append(r)
    return merged

def jp_ratio(rom, lo, hi, t):
    """0xFF 런들을 디코딩해 일본어답게 읽히는 비율"""
    runs = []; s = lo
    for i in range(lo, hi):
        if rom[i] == 0xFF:
            if i > s: runs.append(rom[s:i])
            s = i+1
    good = tot = 0
    for r in runs:
        if len(r) < 6: continue
        c = re.sub(r"<[^>]*>|\\n", "", decode(r, t))
        if len(c) < 4: continue
        tot += 1
        if sum(1 for ch in c if ch in COMMON)/len(c) >= 0.30: good += 1
    return (good/tot if tot else 0.0), tot

def survey(rom, t):
    out = []
    for a, b in candidates(rom):
        r, n = jp_ratio(rom, a, b, t)
        out.append((a, b, r, n, r >= JP_MIN and n >= 5))
    return out

if __name__ == "__main__":
    rom = open(sys.argv[1], 'rb').read()
    t = load_tbl(os.path.join(os.path.dirname(os.path.abspath(__file__)), "darkhalf.tbl"))
    res = survey(rom, t)
    ok = [x for x in res if x[4]]
    print(f"1단계 후보 {len(res)}구간 -> 2단계 확정 {len(ok)}구간\n")
    print(" 구간                     크기   런수  일본어비율  판정")
    for a, b, r, n, good in res:
        print(f" {a:#08x}-{b:#08x} {(b-a)//1024:4d}KB {n:5d}  {r*100:6.1f}%   "
              f"{'텍스트' if good else '탈락'}")
    print(f"\n확정 텍스트 총 {sum(b-a for a,b,_,_,g in res if g)/1024:.0f}KB")
