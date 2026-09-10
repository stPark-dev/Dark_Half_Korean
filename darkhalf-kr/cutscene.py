#!/usr/bin/env python3
"""컷신 「復活節第１日」 — BG 타일맵으로 그리는 16x16 글자.

## 구조 (PROGRESS 4.41)

오프닝(4.18)은 스프라이트였는데 이쪽은 **BG 타일맵**이다. 글자 하나가
16x16 = 2x2 타일이고, 윗줄과 아랫줄이 **서로 다른 블록**으로 들어간다
(윗줄 T·T+1, 아랫줄 T+0x10·T+0x11).

    글꼴   문자 베이스 VRAM 0x4000, 4bpp
           = 압축 그래픽 엔트리 28 블록 6~17 (VRAM 0x4000~0x7000, 96글자)
    본문   롬 평문 0x0f0b92~0x0f1476 의 타일맵 스트림

스트림 명령은 셋뿐이다.

    FFFF <w16> <w16>   줄 머리 (위치·시간)
    FFFE <n16> <tile>  이 타일부터 n개를 1씩 증가시키며 쓴다
    <tile16>           리터럴 타일맵 워드 (상위 6비트는 팔레트·우선순위)

## 왜 안전한가

엔트리 28 블록 6~17 은 **이 컷신 전용 글꼴**이다. 96칸이 전부 글자이고
(숫자 ８ + 가나 39 + 한자 49), 다른 타일맵 구간을 이 글꼴로 풀면 뜻이 없는
글자열이 나온다 — 그쪽은 같은 VRAM 자리에 다른 엔트리를 올린다.

## 칸을 바꾸지 않는다

한국어를 원문과 **같은 칸 수**로 맞춰 리터럴 워드만 바꿔 쓴다. 그러면
스트림 길이가 1바이트도 변하지 않는다.

증가 런(FFFE)도 그대로 둔다. 런이 덮는 글자들을 시트에서 **연속한 칸**에
배치하면 시작 타일과 개수가 원본과 같아진다.

    復活節第 = c0 부터 8타일 런  ->  부 활 절 ␣ 를 c0 c2 c4 c6 에 둔다
    降臨節第 = 降 臨 + c4 부터 4타일 런  ->  강 림 + (절 ␣) 그대로
    栄光     = 126 부터 4타일 런        ->  광 의 를 126 128 에 둔다

## 색

원본은 줄에 따라 색이 갈린다 — 붉은 머리글(팔레트 7)은 6~10, 초록 본문
(팔레트 2)은 12~15 를 쓴다. 같은 글자가 양쪽에 나오면 안 되므로, 머리글에
쓰는 「부 일 말 종」은 본문용 사본을 따로 둔다. 공백은 색이 없어 하나면 된다.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import gfx, patch_menu

ENTRY = 28
BLOCKS = list(range(6, 18))          # VRAM 0x4000~0x7000 = 타일 0x000~0x17F
LO, HI = 0x0f0b92, 0x0f1476
NSLOT = 96                            # 12행 x 8글자

# 16x16 은 반각(4.37.7)과 달리 넉넉해서 글꼴 선택이 쉽다. 후보 7개를 문제
# 글자(고 모 노 보 왔 짖 헤 퍼 께 력 영 광 혼 끝)로 재 보니 NanumGothicBold 는
# 15px 에서 「고」의 ㄱ 이 ㅗ 에 붙어 「ㅗ」로 읽혔다. NanumGothic 16px 가
# 획이 또렷하다.
FONT = "/usr/share/fonts/truetype/nanum/NanumGothic.ttf"
SIZE, THR = 16, 110
INK_HEAD, INK_BODY = 10, 14           # 원본이 쓰는 색 (머리글 6~10 / 본문 12~15)

# (원문, 한국어) — 칸 수가 같아야 한다. 전각 숫자는 원본 숫자 글리프를 그대로 쓴다.
TEXT = [
    ("復活節第１日",            "부활절 １일"),
    ("わがうちに憂いは満ちぬ",   "내 안에 근심이 가득"),
    ("降臨節第１日",            "강림절 １일"),
    ("願わしき時の鐘よ",        "기다리던 종이여"),
    ("復活節第２日",            "부활절 ２일"),
    ("なんじらは泣きさけび",     "너희는 울부짖으리라"),
    ("降臨節第２日",            "강림절 ２일"),
    ("わが終わりの近づけるを",   "나의 끝이 가까웠음을"),
    ("復活節第３日",            "부활절 ３일"),
    ("なんじはさきに告げられたり", "너에게 이미 고하여졌노라"),
    ("降臨節第３日",            "강림절 ３일"),
    ("彼はおのれの羊の名を呼びて", "제 양들의 이름을 부르며"),
    ("復活節第４日",            "부활절 ４일"),
    ("響きわたれ、なんじら歌よ",  "울려 퍼져라 너희 노래"),
    ("降臨節第４日",            "강림절 ４일"),
    ("わがなすすべての業に",     "내가 하는 모든 일"),
    ("復活節第５日",            "부활절 ５일"),
    ("きたれ、なんじ甘き死の時よ", "오라 달콤한 죽음의 때여"),
    ("降臨節第５日",            "강림절 ５일"),
    ("われらに救いのきたれるは",  "우리에게 구원이 왔음은"),
    ("復活節第６日",            "부활절 ６일"),
    ("ちから強き栄光の王",       "힘세고 영광의 왕"),
    ("降臨節第６日",            "강림절 ６일"),
    ("魂よ、つまずくなかれ",     "혼이여 걸리지 말라"),
    ("終末節第７日",            "종말절 ７일"),
    ("わが心の血は海に泳ぐ",     "마음이 피에 헤엄쳐"),
]

DIGITS = "１２３４５６７８"           # 슬롯 0~7 — 원본 글리프를 그대로 둔다


def slot_of(tile):
    """타일 번호 -> 글자 칸. 아랫줄(+0x10)도 같은 칸으로 접는다."""
    return (tile // 0x20) * 8 + ((tile % 0x20) % 0x10) // 2
def tile_of(slot):  return (slot // 8) * 0x20 + (slot % 8) * 2


def parse(rom, lo=LO, hi=HI):
    """[{hdr, items}] — items 는 ('lit', 주소, 워드) / ('run', 주소, n, 워드)."""
    out, a = [], lo
    while a < hi - 1:
        v = rom[a] | (rom[a+1] << 8)
        if v == 0xFFFF:
            out.append({'hdr': a, 'items': []}); a += 6; continue
        if v == 0xFFFE:
            if out: out[-1]['items'].append(
                ('run', a, rom[a+2] | (rom[a+3] << 8), rom[a+4] | (rom[a+5] << 8)))
            a += 6; continue
        if out: out[-1]['items'].append(('lit', a, v))
        a += 2
    return out


def rows(rom):
    """글자를 담은 블록만. 윗줄/아랫줄이 번갈아 나온다."""
    out = []
    for b in parse(rom):
        cs = []
        for it in b['items']:
            if it[0] == 'run':
                t0 = it[3] & 0x3FF
                cs += [t0 + i for i in range(0, it[2], 2)]
            else:
                t = it[2] & 0x3FF
                if t % 2 == 0: cs.append(t)
        # 아랫줄은 타일이 +0x10 이라 (t%0x20)>=0x10 이다. 둘 다 받는다.
        # 같은 타일이 이어지는 블록은 화면 지움이다 (0x0f1402 의 48워드).
        if len(cs) >= 3 and all(t < 0x180 for t in cs) and len(set(cs)) > 1:
            out.append((b, cs))
    return out


def layout(rom):
    """{슬롯: 글자}, {(줄번호, 위치): 슬롯} 을 만든다.

    머리글 칸은 런이 고정하므로 원본 자리를 그대로 쓴다. 나머지는 남는 칸에
    빈도순으로 채운다.
    """
    rs = rows(rom)
    assert len(rs) == 2 * len(TEXT), f"줄 수 {len(rs)} != {2*len(TEXT)}"
    fixed = {}                         # 슬롯 -> 글자
    place = {}                         # (줄, 위치) -> 슬롯
    # 1) 런이 덮는 자리는 원본 슬롯을 그대로 쓴다
    for li, (b, cs) in enumerate(rs[::2]):
        kr = TEXT[li][1]
        assert len(kr) == len(cs), f"{li} 칸 {len(kr)}!={len(cs)}  {kr}"
        i = 0
        for it in b['items']:
            if it[0] == 'run':
                for k in range(0, it[2], 2):
                    s = slot_of((it[3] & 0x3FF) + k)
                    ch = kr[i]
                    if s in fixed: assert fixed[s] == ch, (s, fixed[s], ch)
                    fixed[s] = ch; place[(li, i)] = s; i += 1
            elif (it[2] & 0x3FF) % 2 == 0:
                i += 1
    # 2) 숫자는 원본 슬롯 그대로
    for li, (b, cs) in enumerate(rs[::2]):
        kr = TEXT[li][1]
        for i, (ch, t) in enumerate(zip(kr, cs)):
            if ch in DIGITS:
                s = DIGITS.index(ch)
                assert slot_of(t) == s, (li, i, hex(t), s)
                fixed[s] = ch; place[(li, i)] = s
    # 3) 머리글에만 나오는 글자는 머리글 색, 본문 글자는 본문 색.
    #    같은 글자가 양쪽에 나오면 사본을 따로 둔다.
    head_li = {li for li, (ja, kr) in enumerate(TEXT) if '節第' in ja}
    used = dict(fixed)                 # 슬롯 -> 글자
    ink = {s: (INK_HEAD if s in fixed and s not in (75, 76) else INK_BODY)
           for s in fixed}
    for s in range(8): ink[s] = INK_HEAD
    free = [s for s in range(NSLOT) if s not in used]
    body = {}                          # 글자 -> 슬롯 (본문용)
    for li, (ja, kr) in enumerate(TEXT):
        for i, ch in enumerate(kr):
            if (li, i) in place: continue
            if ch == ' ':
                place[(li, i)] = 51; continue      # 공백은 머리글 것과 공용
            key = ch if li not in head_li else ('H', ch)
            if key in body:
                place[(li, i)] = body[key]; continue
            s = free.pop(0)
            body[key] = s; used[s] = ch
            ink[s] = INK_HEAD if li in head_li else INK_BODY
            place[(li, i)] = s
    return used, place, ink, rs


_F = None
def _glyph(ch):
    global _F
    if _F is None: _F = ImageFont.truetype(FONT, SIZE)
    im = Image.new("L", (16, 16), 0); d = ImageDraw.Draw(im)
    b = d.textbbox((0, 0), ch, font=_F)
    d.text(((16 - (b[2]-b[0]))/2 - b[0], (16 - (b[3]-b[1]))/2 - b[1]), ch, 255, font=_F)
    return np.array(im) > THR


def _put(buf, tile, g, ink):
    for dx, dy, tt in ((0, 0, tile), (1, 0, tile+1), (0, 1, tile+0x10), (1, 1, tile+0x11)):
        o = (tt % 32) * 32
        for y in range(8):
            p = [0, 0, 0, 0]
            for x in range(8):
                v = ink if g[dy*8+y, dx*8+x] else 0
                for k in range(4):
                    if (v >> k) & 1: p[k] |= 1 << (7-x)
            buf[o+y*2], buf[o+y*2+1] = p[0], p[1]
            buf[o+16+y*2], buf[o+16+y*2+1] = p[2], p[3]


def block_cap(rom, addr):
    cap = patch_menu.block_limit(bytes(rom), addr)
    if cap is not None: return cap
    nxt = None
    for e in range(41):
        for b in gfx.blocks(bytes(rom), e):
            if b and b > addr and (nxt is None or b < nxt): nxt = b
    return nxt - (addr - 1)


def apply(rom, verbose=False):
    rom = bytearray(rom)
    used, place, ink, rs = layout(bytes(rom))
    # --- 글꼴 ---
    bl = gfx.blocks(bytes(rom), ENTRY)
    for bi in BLOCKS:
        addr = bl[bi]; cap = block_cap(rom, addr)
        buf = bytearray(gfx.unpack(bytes(rom), addr))
        lo_t, hi_t = (bi - 6) * 32, (bi - 5) * 32        # 이 블록이 담는 타일
        n = 0
        for s, ch in used.items():
            t = tile_of(s)
            if not (lo_t <= t < hi_t): continue
            if ch in DIGITS: continue                     # 숫자는 원본 유지
            _put(buf, t, _glyph(ch), ink[s]); n += 1
        blk = gfx.block(bytes(buf))
        if len(blk) > cap:
            raise SystemExit(f"컷신 글꼴 블록 {addr:#08x}: {len(blk)}/{cap} 초과")
        rom[addr-1:addr-1+len(blk)] = blk
        if verbose: print(f"  {addr:#08x} 블록{bi:2d} 한글 {n:2d}자  {len(blk)}/{cap}바이트")
    # --- 타일맵 ---
    for li in range(len(TEXT)):
        for half in (0, 1):
            b, cs = rs[li*2 + half]
            i = 0
            for it in b['items']:
                if it[0] == 'run':
                    s0 = place[(li, i)]
                    for k in range(0, it[2], 2):
                        assert place[(li, i)] == s0 + k//2, "런 자리가 연속이 아니다"
                        i += 1
                    w = (it[3] & 0xFC00) | (tile_of(s0) + half*0x10)
                    rom[it[1]+4], rom[it[1]+5] = w & 0xFF, w >> 8
                    continue
                t = it[2] & 0x3FF
                if t % 2: continue                        # 글자의 오른쪽 반
                w = (it[2] & 0xFC00) | (tile_of(place[(li, i)]) + half*0x10)
                rom[it[1]], rom[it[1]+1] = w & 0xFF, w >> 8
                # 오른쪽 반 타일도 따라간다
                nx = it[1] + 2
                if nx < HI and (rom[nx] | (rom[nx+1] << 8)) & 0x3FF == t + 1:
                    w2 = w + 1
                    rom[nx], rom[nx+1] = w2 & 0xFF, w2 >> 8
                i += 1
    if verbose:
        print(f"컷신: {len(TEXT)}줄 제자리 삽입 (글자 {len(used)}칸/{NSLOT})")
    return bytes(rom)


def written_range(orig):
    """이 패처가 건드리는 구간 [(시작, 끝)]. 역검증 [5] 가 쓴다."""
    bl = gfx.blocks(bytes(orig), ENTRY)
    r = [(LO, HI)]
    for bi in BLOCKS:
        a = bl[bi]; r.append((a - 1, a - 1 + block_cap(orig, a)))
    return r


def verify(new, orig):
    """새 롬에서 다시 읽어 한국어와 맞는지."""
    used, place, ink, rs = layout(orig)
    inv = {}
    for (li, i), s in place.items(): inv.setdefault(li, {})[i] = s
    nrs = rows(new)
    bad = []
    for li, (ja, kr) in enumerate(TEXT):
        _, cs = nrs[li*2]
        got = ''.join(used.get(slot_of(t), '?') for t in cs)
        if got != kr: bad.append((li, kr, got))
    return bad


if __name__ == "__main__":
    rom = open(sys.argv[1], 'rb').read()
    used, place, ink, rs = layout(rom)
    print(f"글자 {len(used)}칸 / {NSLOT}")
    for li, (ja, kr) in enumerate(TEXT):
        print(f"  {len(kr):2d}칸  {ja:<15} -> {kr}")
