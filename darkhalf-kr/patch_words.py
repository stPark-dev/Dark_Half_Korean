#!/usr/bin/env python3
"""단어표 한글화 — 원본 자리에 그대로 덮어쓴다.

## 제자리여야 하는 이유

포인터 표 0x05c0a6 만 이 문자열들을 가리키는 것이 아니다. 설명문 본문이
「F0 C4 <포인터>」 형태로 단어 주소를 직접 박아 쓴다. 처음에는 문자열을
재배치하고 포인터 표만 고쳤는데, 그 결과 메뉴에서 게임이 멈췄다.

그래서 각 엔트리는 원본 시작 주소를 지키고 포인터 표는 건드리지 않는다.
칸이 좁으므로 이 항목들은 예산 우선 배정을 받아야 한다 (words.pairs()).
"""
import os, sys, struct
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import words, krcodec


def apply(rom, codes, tbl, verbose=False):
    """제자리 덮어쓰기. 반환: 넘친 항목 목록(비어야 정상)."""
    over = []
    for k, ((addr, cap), (ja, kr)) in enumerate(zip(words.slots(rom), words.WORDS)):
        if kr is None: continue
        try:
            b = krcodec.encode(kr, codes, tbl)
        except KeyError as e:
            raise SystemExit(f"단어표 [{k:02X}] {kr!r} 인코딩 불가: {e}")
        if len(b) > cap:
            over.append((k, kr, len(b), cap)); continue
        rom[addr:addr+len(b)] = b
        rom[addr+len(b)] = 0xFF
        # 남는 칸은 0xFF 로 채운다. 종료자 뒤라 표시에 영향이 없고,
        # 옛 일본어 바이트가 남아 다른 참조에 읽히는 일을 막는다.
        for a in range(addr+len(b)+1, addr+cap+1): rom[a] = 0xFF
    if verbose and not over:
        print(f"단어표: {sum(1 for _, kr in words.WORDS if kr)}엔트리 제자리 삽입 "
              f"(포인터 표 {words.PTR_TABLE:#08x} 무변경)")
    return over


def verify(rom, orig, codes, tbl):
    """문자열이 원본 주소에 옳게 있고, 포인터 표가 그대로인지 확인."""
    bad = []
    for k, ((addr, cap), (ja, kr)) in enumerate(zip(words.slots(orig), words.WORDS)):
        if kr is None: continue
        j = addr
        while rom[j] != 0xFF: j += 1
        got = bytes(rom[addr:j])
        want = krcodec.encode(kr, codes, tbl)
        if got != want: bad.append(("단어표", k, kr, got.hex(), want.hex()))
    n = 2 * words.COUNT
    if bytes(rom[words.PTR_TABLE:words.PTR_TABLE+n]) != bytes(orig[words.PTR_TABLE:words.PTR_TABLE+n]):
        bad.append(("단어표", -1, "포인터 표가 바뀌었다", "", ""))
    return bad
