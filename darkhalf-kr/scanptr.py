#!/usr/bin/env python3
"""포인터 테이블 전수 조사.

리포인팅을 하려면 '어떤 메시지를 어떤 포인터가 가리키는지'를 하나도 빠짐없이
알아야 한다. 하나라도 놓치면 그 포인터가 엉뚱한 주소를 가리켜 게임이 깨진다.

방법: 유효 메시지 시작(0xFF 다음 바이트) 집합을 만들고,
      ROM 전체에서 그 주소로 해석되는 u16 이 stride 2 로 연속되는 구간을 찾는다.
"""
import sys, numpy as np
sys.path.insert(0, __file__.rsplit('/',1)[0])
from dump import text_regions

def valid_starts(rom):
    v = set()
    for ra, rb in text_regions(rom):
        for i in range(ra, rb-1):
            if rom[i] == 0xFF and rom[i+1] != 0xFF:
                v.add(i+1)
    return v

def runs_of_true(mask, min_len):
    """True 가 연속되는 구간 [start, length]"""
    idx = np.flatnonzero(np.diff(np.concatenate(([0], mask.view(np.int8), [0]))))
    out = []
    for s, e in zip(idx[0::2], idx[1::2]):
        if e - s >= min_len: out.append((int(s), int(e-s)))
    return out

def scan(rom_bytes, min_entries=6):
    rom = np.frombuffer(rom_bytes, dtype=np.uint8)
    u16 = rom[:-1].astype(np.uint32) | (rom[1:].astype(np.uint32) << 8)
    valid = valid_starts(rom_bytes)
    banks = sorted(set(a & 0xFF0000 for a in valid))
    tables = []
    for B in banks:
        lut = np.zeros(0x10000, dtype=bool)
        for a in valid:
            if (a & 0xFF0000) == B: lut[a & 0xFFFF] = True
        mask = lut[u16]
        for par in (0, 1):
            sub = mask[par::2]
            for s, ln in runs_of_true(sub, min_entries):
                off = par + s*2
                tables.append((off, ln, B))
    tables.sort(key=lambda t: -t[1])
    return tables, valid

if __name__ == "__main__":
    rom_bytes = open(sys.argv[1], 'rb').read()
    tables, valid = scan(rom_bytes)
    # 겹치는 후보 제거 (긴 것 우선)
    taken = np.zeros(len(rom_bytes), dtype=bool)
    kept = []
    for off, ln, B in tables:
        if taken[off:off+ln*2].any(): continue
        taken[off:off+ln*2] = True
        kept.append((off, ln, B))
    kept.sort()
    print(f"포인터 테이블 {len(kept)}개 발견 (항목 6개 이상)\n")
    print(" 테이블주소   항목  대상뱅크    가리키는 범위")
    covered = set()
    rom = np.frombuffer(rom_bytes, dtype=np.uint8)
    for off, ln, B in kept:
        vs = [B + (rom_bytes[off+2*i] | (rom_bytes[off+2*i+1] << 8)) for i in range(ln)]
        covered.update(vs)
        print(f"  {off:#08x}  {ln:5d}  {B:#08x}  {min(vs):#08x}-{max(vs):#08x}")
    print(f"\n메시지 시작 {len(valid)}개 중 포인터로 도달 가능: {len(covered & valid)}개 "
          f"({len(covered & valid)/len(valid)*100:.1f}%)")
    miss = sorted(valid - covered)
    print(f"미도달 {len(miss)}개, 앞 10개: {[hex(x) for x in miss[:10]]}")
