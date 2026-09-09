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
        # 남는 칸은 **공백(0x20)** 으로 채우고 종료자는 **원래 자리**에 둔다.
        #
        # 한때 남는 칸을 전부 0xFF 로 채웠다. 「종료자 뒤라 표시에 영향이
        # 없다」 고 봤는데 틀렸다. 원본 표에는 연속 0xFF 가 **한 쌍도 없다.**
        # 0xFF 로 채우면 마법표에 31쌍, 단어표에 67쌍이 생기고, 표를 0xFF
        # 구분자로 **순차 주사**하는 루틴이 그것을 빈 엔트리로 읽는다. 그러면
        # 인덱스가 밀려 목록에 엉뚱한 이름이 나오고(image/깨짐.png), 끝내 표를
        # 넘어 뒤쪽 0xFF 채움 구간까지 읽어 **화면 전체가 붕괴한다**
        # (image/깨짐2.png — broken.dmp 에 0xFF 연속 9,886바이트가 찍혔다).
        #
        # 공백으로 채우면 엔트리마다 0xFF 가 정확히 하나, 원본과 같은 자리에
        # 남는다. 포인터로 읽어도 뒤에 공백만 붙고, 순차로 훑어도 경계가 같다.
        for a in range(addr+len(b), addr+cap): rom[a] = 0x20
        rom[addr+cap] = 0xFF
    if verbose and not over:
        print(f"단어표: {sum(1 for _, kr in words.WORDS if kr)}엔트리 제자리 삽입 "
              f"(포인터 표 {words.PTR_TABLE:#08x} 무변경)")
    return over


def verify(rom, orig, codes, tbl):
    """문자열이 원본 주소에 옳게 있고, 포인터 표가 그대로인지 확인."""
    bad = []
    for k, ((addr, cap), (ja, kr)) in enumerate(zip(words.slots(orig), words.WORDS)):
        if kr is None: continue
        # apply 가 쓰는 배치를 그대로 대조한다 — 한국어 + 공백 채움 + 0xFF.
        #
        # rstrip(b'\x20') 으로 뒤 공백을 떼는 방식은 쓰면 안 된다. 이스케이프의
        # **인덱스 바이트가 0x20 일 수 있어서** 글자를 잘라 먹는다 (「국왕」
        # 「마왕」 이 그렇게 6건 오검출됐다).
        want = krcodec.encode(kr, codes, tbl)
        exp = want + bytes([0x20]) * (cap - len(want)) + bytes([0xFF])
        got = bytes(rom[addr:addr+cap+1])
        if got != exp: bad.append(("단어표", k, kr, got.hex(), exp.hex()))
    n = 2 * words.COUNT
    if bytes(rom[words.PTR_TABLE:words.PTR_TABLE+n]) != bytes(orig[words.PTR_TABLE:words.PTR_TABLE+n]):
        bad.append(("단어표", -1, "포인터 표가 바뀌었다", "", ""))
    return bad
