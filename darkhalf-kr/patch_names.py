#!/usr/bin/env python3
"""이름표 한글화 — 원본 자리에 그대로 덮어쓴다.

제자리여야 하는 이유는 nametbl.py 주석을 볼 것. 요약하면 마법 문자열을
가리키는 표가 셋이고(0x040300, 0x04f139, 0x05b517) 그중 하나는 설명문
본문에 박힌 「F0 C4 <포인터>」 다. 옮기면 메뉴에서 게임이 멈춘다.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nametbl, krcodec


def apply(rom, codes, tbl, verbose=False):
    over = []
    for spec, wl in nametbl.TABLES:
        for k, ((addr, cap), (ja, kr)) in enumerate(zip(nametbl.slots(rom, spec), wl)):
            if kr is None: continue
            try:
                b = krcodec.encode(kr, codes, tbl)
            except KeyError as e:
                raise SystemExit(f"{spec['name']} [{k:02X}] {kr!r} 인코딩 불가: {e}")
            if len(b) > cap:
                over.append((spec["name"], k, kr, len(b), cap)); continue
            rom[addr:addr+len(b)] = b
            rom[addr+len(b)] = 0xFF
            for a in range(addr+len(b)+1, addr+cap+1): rom[a] = 0xFF
        if verbose and not over:
            print(f"{spec['name']}: {sum(1 for _, k2 in wl if k2)}엔트리 제자리 삽입 "
                  f"(포인터 표 {spec['ptr']:#08x} 무변경)")
    return over


def verify(rom, orig, codes, tbl):
    bad = []
    for spec, wl in nametbl.TABLES:
        for k, ((addr, cap), (ja, kr)) in enumerate(zip(nametbl.slots(orig, spec), wl)):
            if kr is None: continue
            j = addr
            while rom[j] != 0xFF: j += 1
            got = bytes(rom[addr:j])
            want = krcodec.encode(kr, codes, tbl)
            if got != want: bad.append((spec["name"], k, kr, got.hex(), want.hex()))
        n = 2 * spec["count"]
        if bytes(rom[spec["ptr"]:spec["ptr"]+n]) != bytes(orig[spec["ptr"]:spec["ptr"]+n]):
            bad.append((spec["name"], -1, "포인터 표가 바뀌었다", "", ""))
    return bad
