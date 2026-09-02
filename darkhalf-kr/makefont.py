#!/usr/bin/env python3
"""한글 글리프를 Dark Half 폰트 포맷으로 인코딩.

포맷: 16x16, 2bpp, 64바이트/글자, 타일순서 TL,TR,BL,BR
      각 타일 16바이트, row r 의 plane0 = byte[r*2], plane1 = byte[r*2+1]
      이 게임은 plane0 == plane1 (색 인덱스 3 단색)
"""
from PIL import Image, ImageDraw, ImageFont

FONT_PATH = "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf"
FONT_SIZE = 14
THRESHOLD = 110

_font = None
def _f():
    global _font
    if _font is None: _font = ImageFont.truetype(FONT_PATH, FONT_SIZE)
    return _font

def render_rows(ch):
    """문자 -> 16행 × 16비트 (bit15 = 왼쪽 픽셀)"""
    im = Image.new("L", (16, 16), 0)
    d = ImageDraw.Draw(im)
    f = _f()
    bb = f.getbbox(ch)
    x = (16 - (bb[2]-bb[0]))//2 - bb[0]
    y = (16 - (bb[3]-bb[1]))//2 - bb[1]
    d.text((x, y), ch, fill=255, font=f)
    px = im.load()
    rows = []
    for yy in range(16):
        v = 0
        for xx in range(16):
            if px[xx, yy] >= THRESHOLD: v |= 1 << (15-xx)
        rows.append(v)
    return rows

def rows_to_glyph(rows):
    """16행 -> 64바이트 (TL,TR,BL,BR)"""
    out = bytearray()
    for half in (0, 1):                 # 위 8행, 아래 8행
        for side in (0, 1):             # 왼쪽 8열, 오른쪽 8열
            for r in range(8):
                v = rows[half*8 + r]
                b = (v >> 8) & 0xFF if side == 0 else v & 0xFF
                out.append(b); out.append(b)     # plane0 == plane1
    # 위 코드는 TL,TR,BL,BR 순서로 16바이트씩 쌓는다
    return bytes(out)

def glyph_to_rows(g):
    """검증용 역변환: 64바이트 -> 16행"""
    rows = []
    for half in (0, 1):
        for r in range(8):
            l  = g[(half*2)*16   + r*2] | g[(half*2)*16   + r*2+1]
            rr = g[(half*2+1)*16 + r*2] | g[(half*2+1)*16 + r*2+1]
            rows.append((l << 8) | rr)
    return rows

def encode(ch):
    return rows_to_glyph(render_rows(ch))

if __name__ == "__main__":
    ok = True
    for ch in "한글테스트가나다라마안녕하세요":
        r = render_rows(ch)
        g = encode(ch)
        assert len(g) == 64, len(g)
        if glyph_to_rows(g) != r:
            ok = False; print(f"  왕복 실패: {ch}")
    print("왕복 검증:", "전부 일치 (인코더 정상)" if ok else "실패")
    for ch in "한글":
        for row in render_rows(ch):
            print("  " + f"{row:016b}".replace('0','.').replace('1','#'))
        print()
