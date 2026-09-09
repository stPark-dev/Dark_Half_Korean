#!/usr/bin/env python3
"""반각 폰트 — 목록 창(마법·아이템·장비)이 쓰는 8x8 2bpp 폰트.

## 왜 필요한가

목록 창은 **바이트 하나를 타일 하나로** 그린다. 타일맵의 타일 번호가 대사
폰트의 단일바이트 코드와 그대로 같다 (PROGRESS 4.34).

    타일맵 행9  140 107 176 146 176 124 110 157
              = 8C 6B B0 92 B0 7C 6E 9D = フ ォ ー メ ー シ ョ ン

즉 이스케이프를 해석하지 않는다. 그래서

  - 이름 음절은 **전부 단일바이트**여야 한다
  - 코드 N 의 글리프가 **이 폰트에도** 있어야 한다

대사 폰트(16x16)에서 회수한 141칸을 여기에도 한글로 채워야 양쪽이 맞는다.

## 위치 (PROGRESS 4.35.1)

압축 그래픽 엔트리 0 이다. VRAM `0x2000` 부터 문자 코드순으로 올라간다.

    블록0 0x1000c5 -> 코드 0x00~0x3F      블록2 0x100659 -> 0x80~0xBF
    블록1 0x1003aa -> 코드 0x40~0x7F      블록3 0x10095a -> 0xC0~0xFF
    블록4~7 은 0~3 의 사본, 블록8 은 블록0 의 세 번째 사본

사본까지 같이 써야 한다. 내용이 바이트 단위로 동일함을 확인했다
(0/4/8, 1/5, 2/6, 3/7).

한때 이 엔트리를 4bpp 로 읽고 「창 배경 격자」라고 판단했다 (4.33.3). 4bpp
타일 256 의 바이트 주소가 2bpp 폰트 베이스와 같은 `0x2000` 이라 그랬다.

## 그리기 규칙

색 3 이 획이고 색 1·2 는 **모든 글리프에 공통인 고정 디더 배경**이다.
공백 글리프(코드 `0x20`)가 순수 배경이라 그것으로 확인했다 — 「A」의 비획
픽셀이 공백과 일치한다.

**그런데 그 노이즈 배경을 그대로 쓰면 칸을 넘는다.** 색 경계가 많아 압축이
나빠진다. 배경별로 재 보면

    원본노이즈  746/742✗  774/688✗  751/770   775/810
    체커        761/742✗  798/688✗  799/770✗  780/810
    가로줄      716/742   676/688   623/770   678/810   <- 전부 들어간다
    단색        674/742   602/688   498/770   611/810
    투명        688/742   635/688   549/770   639/810

**가로줄**(행마다 1·2 교대)을 쓴다. 들어가는 것 중 원본 질감에 가장 가깝다.
블록마다 다른 배경을 쓰면 한 낱말 안에서 질감이 갈리므로 전부 같게 한다.
넘치면 단색으로 내려가는 대체를 뒀다.

## 압축

`gfx.pack` 에 역참조(복사) 명령을 넣어야 들어간다. 넣기 전에는 **원본을
그대로 재압축해도 칸을 넘었다** (블록0: 896 > 742). 넣은 뒤 한글 삽입 결과는

    블록0 688/742   블록1 635/688   블록2 549/770   블록3 639/810
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import gfx, patch_menu

ENTRY = 0
# (블록 순번, 그 블록이 담당하는 코드 시작). 사본까지 전부 쓴다.
GROUPS = [(0, 0x00), (1, 0x40), (2, 0x80), (3, 0xC0),
          (4, 0x00), (5, 0x40), (6, 0x80), (7, 0xC0), (8, 0x00)]
SPAN = 0x40
BG_CODE = 0x20          # 공백 글리프 = 순수 배경 (확인용)
INK = 3

# 배경 후보. 앞에서부터 시도해 칸에 들어가는 첫 것을 쓴다.
BG_KINDS = ("가로줄", "단색")

# 8x8 에 한글을 넣으면 ㅇ·ㅎ 의 속공간이 메워진다. 후보 8개를 실제 이름으로
# 나란히 그려 골랐다 (malgunbd/malgun/NanumGothic/NanumBarunGothic x 크기 x 문턱).
# NanumGothic 9px 문턱 60 이 가장 낫다 — 무라마사·독무·죽음·용세이버·마계문·
# 결계가 제대로 읽힌다. malgunbd 는 「무라마사」가 「부라마사」로, 「오거」가
# 「모거」로 보였다.
#
# 남는 한계: **받침 ㅇ 은 두 픽셀 높이라 속공간을 낼 수 없다.** 그래서 「방어」가
# 「밤어」, 「강화」가 「감화」, 「상태」가 「삼태」로 보인다. 3x3 이상 채워진
# 덩어리의 가운데를 뚫는 후처리를 시험했지만 그 덩어리 자체가 2행뿐이라
# 걸리는 곳이 없었다. 제대로 고치려면 8x8 자모를 손으로 그려 조합해야 한다.
FONT = "/usr/share/fonts/truetype/nanum/NanumGothic.ttf"
SIZE = 9
THR = 60

_bgcache = None


def _tile(buf, k):
    b = buf[k*16:(k+1)*16]
    g = np.zeros((8, 8), np.uint8)
    for r in range(8):
        p0, p1 = b[r*2], b[r*2+1]
        for c in range(8):
            bit = 7 - c
            g[r, c] = ((p0 >> bit) & 1) | (((p1 >> bit) & 1) << 1)
    return g


def orig_background(rom):
    """원본의 노이즈 배경 (공백 글리프). 대조·참고용."""
    global _bgcache
    if _bgcache is None:
        bl = [b for b in gfx.blocks(bytes(rom), ENTRY) if b]
        _bgcache = _tile(gfx.unpack(bytes(rom), bl[0]), BG_CODE)
    return _bgcache


def background(kind):
    g = np.zeros((8, 8), np.uint8)
    if kind == "가로줄":
        for r in range(8): g[r, :] = 1 if r % 2 == 0 else 2
    elif kind == "단색":
        g[:] = 1
    else:
        raise ValueError(kind)
    return g


def render(ch, kind=BG_KINDS[0]):
    """8x8 색인 배열. 배경 위에 색 3 으로 획을 얹는다."""
    g = background(kind)
    if ch == " ": return g
    f = ImageFont.truetype(FONT, SIZE)
    im = Image.new("L", (8, 8), 0)
    d = ImageDraw.Draw(im)
    bb = d.textbbox((0, 0), ch, font=f)
    d.text(((8 - (bb[2] - bb[0])) / 2 - bb[0],
            (8 - (bb[3] - bb[1])) / 2 - bb[1]), ch, 255, font=f)
    g[np.array(im) > THR] = INK
    return g


def put(buf, k, g):
    """2bpp 8x8 을 블록 내 타일 k 에 쓴다."""
    for r in range(8):
        p0 = p1 = 0
        for c in range(8):
            v = int(g[r, c])
            if v & 1: p0 |= 1 << (7 - c)
            if v & 2: p1 |= 1 << (7 - c)
        buf[k*16 + r*2] = p0
        buf[k*16 + r*2 + 1] = p1


def single_codes(codes):
    """단일바이트로 배정된 {코드: 음절}."""
    return {c[0]: ch for ch, c in codes.items() if len(c) == 1}


def block_cap(rom, addr):
    cap = patch_menu.block_limit(bytes(rom), addr)
    if cap is not None: return cap
    nxt = None
    for e in range(41):
        for b in gfx.blocks(bytes(rom), e):
            if b and b > addr and (nxt is None or b < nxt): nxt = b
    if nxt is None: raise SystemExit(f"블록 {addr:#08x} 한도를 못 구했다")
    return nxt - (addr - 1)


def apply(rom, codes, verbose=False):
    rom = bytearray(rom)
    single = single_codes(codes)
    bl = [b for b in gfx.blocks(bytes(rom), ENTRY) if b]
    for bi, lo in GROUPS:
        addr = bl[bi]
        cap = block_cap(rom, addr)
        buf = bytearray(gfx.unpack(bytes(rom), addr))
        n = 0
        blk = None
        for kind in BG_KINDS:
            b2 = bytearray(buf); n = 0
            for code, ch in single.items():
                if lo <= code < lo + SPAN:
                    put(b2, code - lo, render(ch, kind)); n += 1
            cand = gfx.block(bytes(b2))
            if len(cand) <= cap: blk = cand; used = kind; break
        if blk is None:
            raise SystemExit(f"반각 폰트 블록 {addr:#08x}: 어느 배경으로도 칸 {cap} 초과")
        rom[addr-1:addr-1+len(blk)] = blk
        if verbose:
            print(f"  {addr:#08x} 코드 {lo:#02x}~{lo+SPAN-1:#02x}  한글 {n:>3}자  "
                  f"{len(blk)}/{cap}바이트  배경 {used}")
    if verbose:
        print(f"반각 폰트: 블록 {len(GROUPS)}개 제자리 삽입 (단일바이트 {len(single)}자)")
    return bytes(rom)


def verify(new, orig, codes):
    single = single_codes(codes)
    bl = [b for b in gfx.blocks(bytes(orig), ENTRY) if b]
    bad = []
    for bi, lo in GROUPS:
        buf = gfx.unpack(bytes(new), bl[bi])
        for code, ch in single.items():
            if not (lo <= code < lo + SPAN): continue
            k = code - lo
            got = bytes(buf[k*16:(k+1)*16])
            # 배경 후보 중 하나와 맞으면 통과 (apply 가 칸에 맞춰 골랐다)
            ok = False
            for kind in BG_KINDS:
                w = bytearray(16); put(w, 0, render(ch, kind))
                if got == bytes(w): ok = True; break
            if not ok: bad.append((f"블록{bi}", f"{code:#02x}", ch))
    return bad


def written_range(orig):
    bl = [b for b in gfx.blocks(bytes(orig), ENTRY) if b]
    return [(bl[bi] - 1, bl[bi] - 1 + block_cap(orig, bl[bi])) for bi, _ in GROUPS]
