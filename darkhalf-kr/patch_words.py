#!/usr/bin/env python3
"""단어표 한글화 — <EB>xx 가 가리키는 56개 단어를 한국어로 바꾼다.

구조와 근거는 words.py 주석에 있다. 요약하면 포인터 표 56개(0x05c0a6)가
0xFF 종료 문자열들(0x05c11a~)을 가리키고, 뒤에 0xFF 채움 여유가 넉넉하다.
그래서 길이를 자유롭게 바꾸고 포인터만 다시 써 주면 된다.

원본 바이트를 먼저 스냅샷한다. 새 문자열을 같은 구간에 순차로 쓰기 때문에,
'원문 유지' 엔트리를 나중에 읽으면 이미 덮인 것을 읽게 된다.
"""
import os, sys, struct
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import words, krcodec

# 포인터 값은 뱅크 내 오프셋 그 자체다. HiROM 뱅크 $C5 의 주소 $C11A 가
# ROM 0x05C11A 이므로 값에 0x8000 을 따로 씌우거나 벗기면 안 된다.
BANK = words.DATA & ~0xFFFF


def read_original(rom):
    """엔트리별 원본 바이트 (0xFF 종료자 제외)."""
    out, i = [], words.DATA
    for _ in range(words.COUNT):
        j = i
        while rom[j] != 0xFF: j += 1
        out.append(bytes(rom[i:j])); i = j + 1
    return out


def apply(rom, codes, tbl, verbose=False):
    """rom(bytearray) 을 제자리 수정. 반환: (사용 끝 주소, 바이트 수)"""
    orig = read_original(rom)
    blobs = []
    for k, (ja, kr) in enumerate(words.WORDS):
        if kr is None:
            blobs.append(orig[k])
        else:
            try:
                blobs.append(krcodec.encode(kr, codes, tbl))
            except KeyError as e:
                raise SystemExit(f"단어표 [{k:02X}] {kr!r} 인코딩 불가: {e}")

    # 문자열 순차 배치 + 포인터 갱신
    addr = words.DATA
    ptrs = []
    for b in blobs:
        ptrs.append(addr - BANK)
        rom[addr:addr+len(b)] = b
        rom[addr+len(b)] = 0xFF
        addr += len(b) + 1
    if addr > words.DATA_LIMIT:
        raise SystemExit(f"단어표가 상한 초과 {addr:#08x} > {words.DATA_LIMIT:#08x}")
    # 남은 원본 자리를 0xFF 로 지운다 (짧아졌을 때 옛 바이트가 남지 않게)
    old_end = words.DATA
    for b in orig: old_end += len(b) + 1
    for a in range(addr, max(addr, old_end)): rom[a] = 0xFF

    for k, p in enumerate(ptrs):
        struct.pack_into("<H", rom, words.PTR_TABLE + 2*k, p)

    used = addr - words.DATA
    if verbose:
        print(f"단어표: {len(blobs)}엔트리 / {used}바이트 "
              f"({words.DATA:#08x}~{addr:#08x}, 원본 {old_end-words.DATA}바이트)")
    return addr, used


def verify(rom, codes, tbl):
    """포인터가 가리키는 곳을 되읽어 기대 바이트와 같은지 확인."""
    bad = []
    for k, (ja, kr) in enumerate(words.WORDS):
        p = struct.unpack_from("<H", rom, words.PTR_TABLE + 2*k)[0]
        a = BANK + p
        j = a
        while rom[j] != 0xFF: j += 1
        got = bytes(rom[a:j])
        if kr is not None:
            want = krcodec.encode(kr, codes, tbl)
            if got != want: bad.append((k, kr, got.hex(), want.hex()))
    return bad
