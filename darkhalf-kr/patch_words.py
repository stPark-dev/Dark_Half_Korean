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


# 남는 칸을 건너뛸 <EE> 점프의 대상(뒤 여유 0xFF 구간). 칸이 1~2바이트만
# 남으면 점프(3바이트)가 안 들어가므로 단어를 여기로 옮기고 원래 자리에는
# 점프만 둔다. words.DATA_LIMIT 안쪽이다.
RELOC = 0x05c270


def _ptr(a):
    """같은 뱅크 점프 인자. 0xFF 가 섞이면 순차 주사가 엔트리로 센다."""
    lo, hi = a & 0xFF, (a >> 8) & 0xFF
    return None if 0xFF in (lo, hi) else bytes([0xEE, lo, hi])


def layout(rom, codes, tbl):
    """엔트리마다 쓸 바이트 [(시작주소, 바이트)] 와 넘친 항목.

    남는 칸은 **공백으로 채우지 않는다.** 그 공백이 그대로 그려져 「파르코⎵는」
    「마왕⎵⎵의」 처럼 단어마다 뒤에 공백이 붙었다 (실기 확인).

      칸이 딱 맞으면   단어
      3바이트 이상 남으면  단어 + <EE>→자기 0xFF + 채움
      1~2바이트 남으면   <EE>→RELOC 의 「단어 FF」 + 채움

    어느 경우든 0xFF 는 엔트리마다 하나, **원래 자리**에 남는다. 한때 남는
    칸을 전부 0xFF 로 채웠다가 표를 0xFF 로 순차 주사하는 루틴이 그것을 빈
    엔트리로 읽어 화면 전체가 붕괴했다 (image/깨짐2.png). 채움 바이트(0x20)는
    점프로 건너뛰므로 그려지지 않는다. 엔트리 시작 주소도 그대로다 — 포인터
    표와 설명문의 「F0 C4 <포인터>」 가 시작을 직접 가리킨다.
    """
    out, over, reloc = [], [], RELOC
    for k, ((addr, cap), (ja, kr)) in enumerate(zip(words.slots(rom), words.WORDS)):
        if kr is None: continue
        try:
            b = krcodec.encode(kr, codes, tbl)
        except KeyError as e:
            raise SystemExit(f"단어표 [{k:02X}] {kr!r} 인코딩 불가: {e}")
        if len(b) > cap:
            over.append((k, kr, len(b), cap)); continue
        gap = cap - len(b)
        jmp = _ptr(addr + cap)
        if gap == 0:
            body = b
        elif gap >= 3 and jmp:
            body = b + jmp
        else:
            stub = _ptr(reloc)
            assert stub and reloc + len(b) < words.DATA_LIMIT
            out.append((reloc, b + b'\xff')); reloc += len(b) + 1
            body = stub
        out.append((addr, body + bytes([0x20]) * (cap - len(body)) + b'\xff'))
    return out, over


def apply(rom, codes, tbl, verbose=False):
    """제자리 덮어쓰기. 반환: 넘친 항목 목록(비어야 정상)."""
    out, over = layout(rom, codes, tbl)
    for a, b in out: rom[a:a+len(b)] = b
    if verbose and not over:
        print(f"단어표: {sum(1 for _, kr in words.WORDS if kr)}엔트리 제자리 삽입 "
              f"(포인터 표 {words.PTR_TABLE:#08x} 무변경, 남는 칸은 <EE> 로 건너뜀)")
    return over


def verify(rom, orig, codes, tbl):
    """문자열이 원본 주소에 옳게 있고, 포인터 표가 그대로인지 확인."""
    bad = []
    out, _ = layout(orig, codes, tbl)
    for a, exp in out:
        got = bytes(rom[a:a+len(exp)])
        if got != exp: bad.append(("단어표", a, "", got.hex(), exp.hex()))
    n = 2 * words.COUNT
    if bytes(rom[words.PTR_TABLE:words.PTR_TABLE+n]) != bytes(orig[words.PTR_TABLE:words.PTR_TABLE+n]):
        bad.append(("단어표", -1, "포인터 표가 바뀌었다", "", ""))
    return bad
