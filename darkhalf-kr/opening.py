#!/usr/bin/env python3
"""오프닝 컷신 내레이션 — 스프라이트 글리프 + (타일, 속성) 스크립트.

## 어떻게 찾았나 (PROGRESS 4.18)

여섯 번 실패했다. 원인은 `gfx.blocks()` 의 버그였다 — 블록 목록 길이를
「첫 오프셋 ÷ 2」로 구했는데 엔트리 18·28 은 **첫 항목이 `0xFFFF`(빈 블록)**
이라 32767개로 잡혀 표에서 제외돼 있었다. 오프닝은 정확히 그 안이었다.

글리프는 **스크린샷에서 직접 뽑아** 대조했다. 에뮬레이터 창이 정확히 2배
스케일이라 나누기만 하면 원본 픽셀이 나온다. Noto 템플릿은 0.70 에 머물렀는데
(장식체라 TrueType 축소와 성질이 다르다) 스크린샷 템플릿은 **15자 전부 IoU
1.000** 이었다.

## 구조

배경 타일맵이 아니라 **스프라이트**다. 스크립트는 글자마다 2바이트다.

    (타일 하위바이트, OAM 속성)

속성은 OAM 바이트3 이다 — bit0=타일 9번째 비트(N), bit1~3=팔레트, bit4~5=우선도.

    N=1 (속성 0x21)  ->  VRAM 타일 = 512 + 하위      (544~767)
    N=0 (속성 0x22)  ->  VRAM 타일 = 768 + 하위      (768~1023)

    ff ff = 줄 끝      fe ff = 쪽 끝

검증: 「光」은 속성 0x22, 하위 0xAA -> 768+170 = VRAM 938 이고, 실제 VRAM
덤프의 938 이 「光」이다 (엔트리 22 블록 0x169c76 타일 10 과 바이트 일치).

## 글리프 슬롯

엔트리 18 의 블록 5~15 가 VRAM 544~895 에 순차로 올라간다 (블록 0~4 는 그림).
16x16 글리프는 타일 4개(t, t+1, t+16, t+17)이므로 블록마다 8자, **총 88칸**이다.

    VRAM 타일 = 544 + 32*(블록순번 - 5) + 블록내타일

VRAM 896 이상은 공용 한자 시트(엔트리 22)다. 23행의 `〜` `「` `」` 가 거기
있어서(910·928·932) **건드리지 않고 그대로 참조**한다. 다른 화면이 쓰는
시트라 손대면 안 된다.

두 칸은 예약한다 — 타일 544 는 원본에서 빈칸이라 **공백**으로 쓰고,
타일 838 은 `６`(원문 ６人) 이라 그대로 둔다. 남는 86칸에 한국어를 넣는다.

## 예산

원문은 23줄 273칸, 스크립트 648바이트다. 줄마다 **원문과 같은 칸 수**를
유지하고 한국어를 가운데 맞춤으로 넣는다. 그러면 바이트 길이가 원문과 같아
포인터를 건드릴 위험이 없다 (설정 화면에서 칸이 밀렸던 4.17.15 의 교훈).

고유 음절 83자 / 86칸. 「하늘과 땅이 나뉘고」(늘·땅·뉘) 처럼 한 번만 쓰는
음절이 많은 문구를 「천지가 갈라지고」로 바꿔 93 -> 83 으로 줄였다.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import gfx, patch_menu

TEXT = 0x9ED6E
TEXT_END = 0x9EFF4
ENTRY = 18
FIRST_BLOCK = 5          # 블록 0~4 는 그림이다
NBLOCK = 11              # 블록 5~15
VRAM0 = 544
SPACE_TILE = 544         # 원본에서 빈칸
KEEP_TILES = {544, 838}  # 공백, ６

FONT = "/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc"
SIZE = 15
THR = 100

# 원본 글리프는 중심에서 바깥으로 2 -> 3 -> 4 -> 5 방사형 그라데이션이다
# (메뉴 폰트의 단색 + 그림자와 다르다). 「闇」을 픽셀로 찍어 확인했다.
#
# 그런데 4색을 그대로 쓰면 **재압축이 칸을 넘는다.** 한글은 획이 흩어져서
# 색 경계가 많고, 우리 packer 는 원본이 쓰는 역참조(copy, $C03414) 명령을
# 내보내지 않기 때문이다. 실제로 원본 데이터를 그대로 재압축해도 넘친다
# (블록5: 419 > 395). 그래서 2색으로 근사한다.
#
#   4색      초과 7/11 블록
#   2색 4/5  초과 0/11  (310/395 ~ 440/468)
#   단색 4   초과 0/11  (204/395 ~ 348/468)
#
# 2색으로도 넉넉하고 원본의 방향(바깥 5, 안쪽 4)을 지킨다.
GRAD = ((5.0, 4),)
GRAD_OUT = 5

KR = [
    "빛은 어둠이 되고", "어둠은 빛을 낳는다", "모두 거기서 시작되어",
    "언젠가 거기로 돌아간다", "천지가 갈라지고", "대지에 생명이 태어날 때",
    "이미 루큐는 존재했다", "루큐는 어둠을 지배하고", "어느새 마왕이라 불렸다",
    "마왕의 힘은 절대였다", "인간은 마왕을 두려워", "그 힘에 굴복했다",
    "그러나 어느 때", "이 운명을 바꾸려는 자가", "나타났다",
    "영웅신 로그", "６인의 성기사", "그들은 마왕에게 맞서고",
    "마왕을 봉인했다", "인간이 두려워하던 시대는", "과거가 되고",
    "새 태양이 떴다", "〜「마왕신화」서설〜",
]

# 원본 시트에 그대로 있는 글자 -> 그 타일을 참조한다
FIXED = {"〜": 910, "「": 928, "」": 932, "６": 838, " ": SPACE_TILE}


def block_cap(rom, addr):
    """이 블록이 쓸 수 있는 바이트 수.

    patch_menu.block_limit 은 같은 엔트리 안에서만 다음 블록을 찾으므로
    엔트리의 **마지막 블록**에서 None 을 준다. 그때는 롬 전체에서 다음 블록을
    찾는다 (엔트리 18 의 마지막 블록 뒤는 엔트리 19 의 첫 블록이다).
    """
    cap = patch_menu.block_limit(bytes(rom), addr)
    if cap is not None: return cap
    nxt = None
    for e in range(41):
        for b in gfx.blocks(bytes(rom), e):
            if b and b > addr and (nxt is None or b < nxt): nxt = b
    if nxt is None: raise SystemExit(f"블록 {addr:#08x} 의 한도를 못 구했다")
    return nxt - (addr - 1)


def encode_tile(t):
    """VRAM 타일 -> (하위바이트, OAM 속성)."""
    if 512 <= t < 768: return t - 512, 0x21
    if 768 <= t < 1024: return t - 768, 0x22
    raise ValueError(f"타일 {t} 은 스프라이트 이름 범위 밖")


def slot_tile(j):
    """슬롯 번호 j(0~87) -> VRAM 타일."""
    return VRAM0 + (j // 8) * 32 + (j % 8) * 2


def slot_block_tile(j):
    """슬롯 번호 -> (블록 주소 순번, 블록 내 타일)."""
    return FIRST_BLOCK + j // 8, (j % 8) * 2


def render(ch):
    """16x16 색인 배열. 획 마스크를 방사형 그라데이션으로 칠한다."""
    f = ImageFont.truetype(FONT, SIZE)
    im = Image.new("L", (16, 16), 0)
    d = ImageDraw.Draw(im)
    bb = d.textbbox((0, 0), ch, font=f)
    d.text(((16 - (bb[2] - bb[0])) / 2 - bb[0],
            (16 - (bb[3] - bb[1])) / 2 - bb[1]), ch, 255, font=f)
    mask = np.array(im) > THR
    yy, xx = np.mgrid[0:16, 0:16]
    r = np.hypot(xx - 7.5, yy - 7.5)
    col = np.full((16, 16), GRAD_OUT, np.uint8)
    for lim, c in reversed(GRAD):
        col[r < lim] = c
    out = np.zeros((16, 16), np.uint8)
    out[mask] = col[mask]
    return out


def parse(rom):
    """스크립트를 토큰으로 쪼갠다. ('term', 2바이트) 또는 ('line', [칸수])."""
    out = []
    i = TEXT
    cur = 0
    while i < TEXT_END:
        lo, at = rom[i], rom[i + 1]
        if (lo, at) in ((0xFF, 0xFF), (0xFE, 0xFF)):
            if cur: out.append(("line", cur)); cur = 0
            out.append(("term", bytes([lo, at])))
        else:
            if at not in (0x21, 0x22):
                raise ValueError(f"{i:#08x} 뜻밖의 속성 {at:#02x}")
            cur += 1
        i += 2
    if cur: out.append(("line", cur))
    return out


def alloc():
    """음절 -> VRAM 타일. FIXED 는 원본 타일, 나머지는 남는 슬롯."""
    need = []
    for line in KR:
        for ch in line:
            if ch in FIXED or ch in need: continue
            need.append(ch)
    free = [slot_tile(j) for j in range(NBLOCK * 8) if slot_tile(j) not in KEEP_TILES]
    if len(need) > len(free):
        raise SystemExit(f"오프닝 글리프 {len(need)}자 > 슬롯 {len(free)}칸. "
                         f"문구를 고쳐 고유 음절을 줄여야 합니다.")
    m = dict(FIXED)
    for k, ch in enumerate(need): m[ch] = free[k]
    return m, need


def build_script(rom, cmap):
    """원문과 칸 수를 똑같이 유지하며 스크립트를 다시 만든다."""
    toks = parse(rom)
    out = bytearray()
    li = 0
    for kind, val in toks:
        if kind == "term":
            out += val; continue
        cap = val
        if li >= len(KR):
            raise SystemExit(f"원문 줄이 {li+1}개인데 번역이 {len(KR)}줄뿐이다")
        txt = KR[li]; li += 1
        if len(txt) > cap:
            raise SystemExit(f"{li}행 「{txt}」 {len(txt)}칸 > 원문 {cap}칸")
        lead = (cap - len(txt)) // 2
        cells = [" "] * lead + list(txt) + [" "] * (cap - len(txt) - lead)
        for ch in cells:
            lo, at = encode_tile(cmap[ch]); out += bytes([lo, at])
    if li != len(KR):
        raise SystemExit(f"원문 줄 {li}개 != 번역 {len(KR)}줄")
    if len(out) != TEXT_END - TEXT:
        raise SystemExit(f"스크립트 길이 {len(out)} != 원문 {TEXT_END - TEXT}")
    return bytes(out)


def apply(rom, verbose=False):
    rom = bytearray(rom)
    cmap, need = alloc()
    bl = [b for b in gfx.blocks(bytes(rom), ENTRY) if b]

    # 블록별로 묶어 한 번만 풀고 쓴다 (한 블록에 글자 8개가 들어간다)
    byblk = {}
    for ch in need:
        bi, tile = slot_block_tile([slot_tile(j) for j in range(NBLOCK * 8)]
                                   .index(cmap[ch]))
        byblk.setdefault(bi, []).append((tile, ch))
    for bi, lst in sorted(byblk.items()):
        addr = bl[bi]
        cap = block_cap(rom, addr)
        buf = bytearray(gfx.unpack(bytes(rom), addr))
        for tile, ch in lst:
            _put(buf, tile, render(ch))
        blk = gfx.block(bytes(buf))
        if cap is not None and len(blk) > cap:
            raise SystemExit(f"오프닝 블록 {addr:#08x} "
                             f"{[c for _, c in lst]}: {len(blk)}바이트 > 칸 {cap}")
        rom[addr - 1:addr - 1 + len(blk)] = blk
        if verbose:
            print(f"  {addr:#08x} {''.join(c for _, c in lst)}  {len(blk)}/{cap}바이트")

    rom[TEXT:TEXT_END] = build_script(bytes(rom), cmap)
    if verbose:
        print(f"오프닝: {len(KR)}줄 제자리 삽입 "
              f"({TEXT:#08x}~{TEXT_END:#08x}, 글리프 {len(need)}자/86칸)")
    return bytes(rom)


def _put(buf, t0, g):
    """4bpp 16x16 글리프를 t0, t0+1, t0+16, t0+17 에 쓴다."""
    for (oy, ox), t in zip([(0, 0), (0, 8), (8, 0), (8, 8)],
                           [t0, t0 + 1, t0 + 16, t0 + 17]):
        base = t * 32
        for r in range(8):
            p = [0, 0, 0, 0]
            for c in range(8):
                v = int(g[oy + r, ox + c])
                for j in range(4):
                    if (v >> j) & 1: p[j] |= 1 << (7 - c)
            buf[base + r*2]      = p[0]
            buf[base + r*2 + 1]  = p[1]
            buf[base + 16 + r*2] = p[2]
            buf[base + 16 + r*2 + 1] = p[3]


def verify(new, orig):
    cmap, need = alloc()
    bad = []
    want = build_script(orig, cmap)
    if bytes(new[TEXT:TEXT_END]) != want:
        bad.append(("스크립트", "바이트 불일치"))
    bl = [b for b in gfx.blocks(bytes(orig), ENTRY) if b]
    idx = [slot_tile(j) for j in range(NBLOCK * 8)]
    for ch in need:
        bi, tile = slot_block_tile(idx.index(cmap[ch]))
        buf = bytearray(gfx.unpack(bytes(new), bl[bi]))
        w = bytearray(len(buf)); _put(w, tile, render(ch))
        ids = [tile*32 + k for k in range(32)] + [(tile+16)*32 + k for k in range(32)]
        if any(buf[i] != w[i] for i in ids):
            bad.append((ch, f"블록 {bl[bi]:#08x} 타일 {tile}"))
    return bad


def written_range(orig):
    bl = [b for b in gfx.blocks(bytes(orig), ENTRY) if b]
    out = [(TEXT, TEXT_END)]
    for bi in range(FIRST_BLOCK, FIRST_BLOCK + NBLOCK):
        cap = block_cap(orig, bl[bi])
        out.append((bl[bi] - 1, bl[bi] - 1 + cap))
    return out
