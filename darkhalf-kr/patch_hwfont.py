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
import gfx, patch_menu

ENTRY = 0
# (블록 순번, 그 블록이 담당하는 코드 시작). 사본까지 전부 쓴다.
GROUPS = [(0, 0x00), (1, 0x40), (2, 0x80), (3, 0xC0),
          (4, 0x00), (5, 0x40), (6, 0x80), (7, 0xC0), (8, 0x00)]
SPAN = 0x40
BG_CODE = 0x20          # 공백 글리프 = 순수 배경 (확인용)
INK = 3

# 배경 후보. 앞에서부터 시도해 칸에 들어가는 첫 것을 쓴다.
#
# 한때 「가로줄」(행마다 색 1·2 교대)을 먼저 뒀다. 원본 노이즈 디더에 가장
# 가까우면서 칸에 들어가는 것이 그것뿐이었기 때문이다. 자모 조합으로 바꾸니
# 「단색」도 넉넉히 들어가고(456/770), **가로줄이 한글의 가로획과 섞여**
# 읽기를 방해한다는 것이 나란히 그려 보니 분명했다. 단색을 먼저 쓴다.
BG_KINDS = ("단색", "가로줄")

# 글리프는 **자모를 손으로 그려 조합한다** (hangul8.py).
#
# 한때 TrueType 을 8px 로 래스터했다. 후보 8개(malgunbd/malgun/NanumGothic/
# NanumBarunGothic x 크기 x 문턱)를 실제 이름으로 나란히 그려 NanumGothic
# 9px/60 을 골랐지만, 어느 조합으로도 **받침 ㅇ 이 두 픽셀 높이라 속공간을
# 낼 수 없었다.** 「방어」가 「밤어」, 「아무것도」가 「마루것노」, 「모두
# 도망」이 「보두 노맘」으로 읽혔다 (image/전투화면-선택지깨짐.png).
#
# 3x3 이상 채워진 덩어리의 가운데를 뚫는 후처리도 시험했는데, 그 덩어리가
# 2행뿐이라 걸리는 곳이 아예 없었다. 래스터로는 안 되는 문제였다.
#
# 자모 조합으로 바꾸니 전부 살아났다 — 방어 · 상태 · 아무것도 · 모두 도망 ·
# 지팡이 · 용세이버. 대조는 PROGRESS 4.42.

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
    import hangul8
    g = background(kind)
    if ch == " ": return g
    g[np.array(hangul8.glyph(ch))] = INK
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
    """이 폰트에 한글을 써도 되는 {코드: 음절}.

    단일바이트 한자 코드 31개는 **8x8 칸이 창 장식 그래픽**이라 건드리면
    창 귀퉁이에 글자가 나온다 (krcodec.hw_ui 주석, image/확인.png).
    대사 폰트(16x16)에서는 정상 글리프 자리라 회수 자체는 그대로 두고,
    이 폰트에서만 뺀다. allocate 가 그 코드를 풀 맨 뒤로 밀어 두므로
    목록·필드에 실리는 음절은 여기 오지 않는다.
    """
    import krcodec
    ui = krcodec.hw_ui()
    return {c[0]: ch for ch, c in codes.items()
            if len(c) == 1 and c[0] not in ui}


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
        n = sum(1 for c in single if lo <= c < lo + SPAN)
        # 쓸 한글이 없으면 손대지 않는다. 블록0(코드 0x00~0x3F)이 그렇다 —
        # 0x20~0x3F 는 전부 KEEP(공백·숫자·괄호·＋) 아니면 창 장식이다.
        # 재압축만 해도 3바이트를 넘긴다 (745 > 742). 우리 packer 가 원본보다
        # 나쁜 블록이 있다는 뜻이고, 건드릴 이유가 없으면 두는 것이 맞다.
        if n == 0:
            if verbose:
                print(f"  {addr:#08x} 코드 {lo:#02x}~{lo+SPAN-1:#02x}  한글 없음 — 원본 유지")
            continue
        blk = None
        for kind in BG_KINDS:
            b2 = bytearray(buf)
            for code, ch in single.items():
                if lo <= code < lo + SPAN:
                    put(b2, code - lo, render(ch, kind))
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
    # 창 장식 칸은 원본 그대로여야 한다.
    import krcodec
    for bi, lo in GROUPS:
        nb, ob = gfx.unpack(bytes(new), bl[bi]), gfx.unpack(bytes(orig), bl[bi])
        for code in krcodec.hw_ui():
            if not (lo <= code < lo + SPAN): continue
            k = code - lo
            if bytes(nb[k*16:(k+1)*16]) != bytes(ob[k*16:(k+1)*16]):
                bad.append((f"블록{bi}", f"{code:#02x}", "장식칸 덮음"))
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
