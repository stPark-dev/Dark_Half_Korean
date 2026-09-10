#!/usr/bin/env python3
"""몬스터·화자 이름표 (0x04f672 ~ 0x04f8f9) — 구조 해독.

## 한때 「미해결」이라고 적어 뒀던 것

PROGRESS 4.10 은 이 표를 「엔트리가 서로 겹쳐 읽힌다 / 절반만 가능」으로
봤다. 겹친 게 아니라 **읽는 법을 몰랐던 것**이다. 아이템표(4.37)와 같은
조립 언어를 쓴다.

    EE lo hi      ptr 로 꼬리 점프한다. **이 엔트리는 여기서 끝난다**
    F0 C4 lo hi   ptr 의 문자열을 끼워 넣고 계속 읽는다
    EB N          단어표 N 번을 끼워 넣는다
    0xFF          끝

핵심은 **<EE> 도 종료자라는 것**이다. 그래서 엔트리 사이에 0xFF 가 없는
곳이 많고, 0xFF 로만 자르면 여러 엔트리가 하나로 뭉쳐 보인다. 그렇게 뭉친
덩어리를 보고 「겹쳐 읽힌다」고 판단했었다.

제대로 자르면 **107 엔트리**가 나온다 (0xFF 로만 자르면 72개).

    0x04f691  ジャイアント + EE->0x04f68c(バット)   = ジャイアントバット
    0x04f69b  Ｐ           + EE->0x04f68c          = Ｐバット
    0x04f708  F0C4->0x04f701(コボルド) + Ｋ         = コボルドＫ

「F7 비글리프 참조 5개」(4.10)도 오해였다. `f0c401f74b` 를 순차로 훑으면
`f7 4b` 가 F7 이스케이프로 보이는데, 실제로는 `F0 C4` 의 포인터 하이바이트와
그 뒤 글자다. 같은 이유로 「몬스터 이름에 뱅크 이스케이프 14곳」도 0곳이다.

## 이 표는 타일 직접이다 (한글 음절이 전부 단일바이트여야 한다)

원본이 쓰는 2바이트 이스케이프 수를 표별로 세면 갈린다.

    아이템·장비·마법표  0곳    <- 타일 직접(확인됨)
    몬스터·화자 이름표  0곳    <- 여기
    단어표             47곳   <- 대사 렌더러
    메인 대사        3,432곳  <- 대사 렌더러

107개 이름에 한 곳도 없다. 대사 렌더러를 쓴다면 한자가 섞였을 것이다
(단어표는 57엔트리에 47곳을 쓴다). 타일 직접으로 본다.
"""
import sys, os, unicodedata
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

LO, HI = 0x04f672, 0x04f8f9
BANK = 0x040000


def bounds(rom, lo=LO, hi=HI):
    """엔트리 경계 [(시작, 끝)]. 0xFF 또는 <EE> lo hi 로 끝난다."""
    out, a = [], lo
    while a < hi:
        s = a
        while a < hi:
            b = rom[a]
            if b == 0xFF: a += 1; break
            if b == 0xEE: a += 3; break
            if b == 0xF0 and rom[a+1] == 0xC4: a += 4; continue
            a += 1
        out.append((s, a))
    return out


def assemble(rom, a, depth=0, words_slots=None):
    """엔트리를 조립기가 보는 대로 편다."""
    out = []
    if depth > 8: return out
    while True:
        b = rom[a]
        if b == 0xFF: return out
        if b == 0xEE:
            return out + assemble(rom, BANK | rom[a+1] | (rom[a+2] << 8),
                                  depth+1, words_slots)
        if b == 0xF0 and rom[a+1] == 0xC4:
            out += assemble(rom, BANK | rom[a+2] | (rom[a+3] << 8),
                            depth+1, words_slots)
            a += 4; continue
        if b == 0xEB and words_slots is not None and rom[a+1] < len(words_slots):
            out += assemble(rom, words_slots[rom[a+1]][0], depth+1, words_slots)
            a += 2; continue
        out.append(b); a += 1


def readable(bs, tbl):
    """조립 결과를 사람이 읽을 문자열로. 0x01/0x02 는 탁점·반탁점 결합이다."""
    o = []
    for b in bs:
        if b in (0x01, 0x02):
            if o: o[-1] = unicodedata.normalize('NFC', o[-1] + ('゙' if b == 0x01 else '゚'))
            continue
        x = tbl.get(bytes([b])) or tbl.get(b) or f'<{b:02x}>'
        o.append(x)
    return ''.join(o)


def entries(rom, tbl, words_slots=None):
    """[(시작, 끝, 원문)] 107개."""
    out = []
    for s, e in bounds(rom):
        bs = assemble(rom, s, words_slots=words_slots)
        if bs: out.append((s, e, readable(bs, tbl)))
    return out


if __name__ == "__main__":
    from dump import load_tbl
    import words
    rom = open(sys.argv[1], 'rb').read()
    tbl = load_tbl(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "darkhalf.tbl"))
    ws = words.slots(rom)
    es = entries(rom, tbl, ws)
    print(f"엔트리 {len(es)}개")
    for s, e, ja in es:
        print(f"  {s:#08x}-{e:#08x} ({e-s:2d}B)  {ja}")
