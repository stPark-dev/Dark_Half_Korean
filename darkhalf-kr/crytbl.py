#!/usr/bin/env python3
"""전투 울음소리 표 (0x05b39c ~ 0x05b409).

`image/오류-호세전투대사.png` 의 「안가가렇렇렇은！」이 이것이다. 원문은
`ヒィィーーーッ！` 이고, 회수된 가나 슬롯을 가리키니 한글 잡음으로 나온다.

포인터 표가 바로 앞 `0x05b300` 에 있고 문자열은 0xFF 로 끝난다. 단어표와
같은 구조라 **제자리로만** 쓴다 (남는 칸은 공백 0x20, 종료자는 원래 자리).

## 렌더러를 못 갈랐다 — 그래서 팔레트 음절만 쓴다

말풍선이라 대사 렌더러 같지만 확증이 없다. 이 표 자체에는 2바이트
이스케이프가 0곳인데(전부 가나라 당연하다) 앞뒤 설명문에는 32곳·116곳이
있어 정황으로도 안 갈린다.

그래서 **어느 쪽이든 안전하도록 단일바이트 음절만** 쓴다. 의성어라 낱말을
고를 자유가 넓어 값이 들지 않는다.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

DATA = 0x05b39c
LIMIT = 0x05b409

# (원문, 한국어). 칸이 아니라 바이트가 상한이다.
# 「。」는 0x2E 이고 인코더 표에 없어서(0xA1 과 글리프가 같다) 원본과 같은
# 바이트를 <2E> 로 직접 쓴다.
_D = "<2E>"
WORDS = [
    ("ゼェゼェ。。。",      "하아하아" + _D*2),
    ("ふぅ。。はぁ。。",     "오오" + _D*2 + "하아" + _D*2),
    ("すまない。。。",      "용서해라" + _D*2),
    ("はぁはぁ。。。",      "하아 하아" + _D),
    ("ヒューッ！",        "아아아！"),
    ("ウォゥ ウォゥッ！",   "오오 오오！"),
    ("ブルブル。。。",      "바르르" + _D*3),
    ("シューシュー。。。",   "스스스스" + _D*2),
    ("クケケ。。。。",      "그그그" + _D*2),
    ("ブモッ ブモッ！",     "모오 모오！"),
    ("ヒィィーーーッ！",    "이이이이！"),
    ("キャウン キャウン！",  "카오 카오！"),
]


def slots(rom):
    """[(시작주소, 쓸 수 있는 바이트)] — 마지막 1바이트는 0xFF 종료자 몫."""
    st, i = [], DATA
    while i < LIMIT:
        st.append(i); j = i
        while rom[j] != 0xFF: j += 1
        i = j + 1
    return [(a, (st[k+1] if k+1 < len(st) else LIMIT) - a - 1)
            for k, a in enumerate(st)]


def pairs(rom):
    return [(cap, kr) for (a, cap), (_, kr) in zip(slots(rom), WORDS) if kr]


def texts():
    return [kr for _, kr in WORDS if kr]


def apply(rom, codes, tbl):
    import krcodec
    rom = bytearray(rom)
    over = []
    for (a, cap), (_, kr) in zip(slots(bytes(rom)), WORDS):
        if not kr: continue
        b = krcodec.encode(kr, codes, tbl)
        if len(b) > cap: over.append((a, kr, len(b), cap)); continue
        rom[a:a+cap] = b + bytes([0x20]) * (cap - len(b))
        rom[a+cap] = 0xFF                      # 종료자는 원래 자리 (4.29)
    return bytes(rom), over


def verify(new, orig, codes, tbl):
    import krcodec
    bad = []
    for (a, cap), (_, kr) in zip(slots(orig), WORDS):
        if not kr: continue
        want = krcodec.encode(kr, codes, tbl)
        exp = want + bytes([0x20]) * (cap - len(want)) + bytes([0xFF])
        if bytes(new[a:a+cap+1]) != exp: bad.append((a, kr))
    return bad


if __name__ == "__main__":
    rom = open(sys.argv[1], 'rb').read()
    for (a, cap), (ja, kr) in zip(slots(rom), WORDS):
        print(f"  {a:#08x} {cap:2d}B  {ja:<16} -> {kr}")
