#!/usr/bin/env python3
"""이름표 한글화 — 포인터 표 + 0xFF 종료 문자열 구조를 다시 쓴다.

구조와 근거는 nametbl.py 주석에 있다. patch_words.py 와 같은 방식이다.
원본 바이트를 먼저 스냅샷한다. 새 문자열을 같은 구간에 순차로 쓰기 때문에
'원문 유지' 엔트리를 나중에 읽으면 이미 덮인 것을 읽게 된다.
"""
import os, sys, struct
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nametbl, krcodec


def read_original(rom, spec):
    out, i = [], spec["data"]
    for _ in range(spec["count"]):
        j = i
        while rom[j] != 0xFF: j += 1
        out.append(bytes(rom[i:j])); i = j + 1
    return out


def apply_one(rom, spec, wordlist, codes, tbl, verbose=False):
    orig = read_original(rom, spec)
    blobs = []
    for k, (ja, kr) in enumerate(wordlist):
        if kr is None:
            blobs.append(orig[k])
        else:
            try:
                blobs.append(krcodec.encode(kr, codes, tbl))
            except KeyError as e:
                raise SystemExit(f"{spec['name']} [{k:02X}] {kr!r} 인코딩 불가: {e}")

    addr = spec["data"]
    ptrs = []
    for b in blobs:
        ptrs.append(addr - spec["bank"])
        rom[addr:addr+len(b)] = b
        rom[addr+len(b)] = 0xFF
        addr += len(b) + 1
    if addr > spec["limit"]:
        raise SystemExit(f"{spec['name']} 구간 초과 {addr:#08x} > {spec['limit']:#08x}")
    # 짧아진 꼬리를 0xFF 로 지운다 (옛 바이트가 남아 보이지 않게)
    old_end = spec["data"]
    for b in orig: old_end += len(b) + 1
    for a in range(addr, max(addr, old_end)): rom[a] = 0xFF

    for k, p in enumerate(ptrs):
        struct.pack_into("<H", rom, spec["ptr"] + 2*k, p)

    if verbose:
        print(f"{spec['name']}: {len(blobs)}엔트리 / {addr-spec['data']}바이트 "
              f"({spec['data']:#08x}~{addr:#08x}, 원본 {old_end-spec['data']}바이트)")
    return addr


def apply(rom, codes, tbl, verbose=False):
    for spec, wl in nametbl.TABLES:
        apply_one(rom, spec, wl, codes, tbl, verbose=verbose)


def verify(rom, codes, tbl):
    """포인터를 따라가 되읽어 기대 바이트와 비교."""
    bad = []
    for spec, wl in nametbl.TABLES:
        for k, (ja, kr) in enumerate(wl):
            if kr is None: continue
            p = struct.unpack_from("<H", rom, spec["ptr"] + 2*k)[0]
            a = spec["bank"] + p; j = a
            while rom[j] != 0xFF: j += 1
            got = bytes(rom[a:j])
            want = krcodec.encode(kr, codes, tbl)
            if got != want:
                bad.append((spec["name"], k, kr, got.hex(), want.hex()))
    return bad
