#!/usr/bin/env python3
"""Dark Half 폰트 시트 추출.

확정된 구조:
  16x16 글리프 / 2bpp (plane0==plane1) / 64바이트per글자 / 타일순서 TL,TR,BL,BR
  단일바이트 코드:  0x2F0000 + code*64        (256자)
  한자 뱅크 F5 xx:  0x2F4000 + xx*64          (추정)
  한자 뱅크 F6 xx:  0x2F8000 + xx*64          (추정)
"""
import sys
from PIL import Image, ImageDraw

SINGLE_BASE = 0x2F0000
BANK_F5     = 0x2F4000
BANK_F6     = 0x2F8000

def glyph_rows(rom, o):
    """16행 × 16비트"""
    rows = []
    for half in (0, 1):                       # 위쪽 타일쌍, 아래쪽 타일쌍
        for r in range(8):
            l  = rom[o+(half*2)*16   + r*2] | rom[o+(half*2)*16   + r*2+1]
            rr = rom[o+(half*2+1)*16 + r*2] | rom[o+(half*2+1)*16 + r*2+1]
            rows.append((l << 8) | rr)
    return rows

def sheet(rom, base, count, path, label, scale=2, cols=16):
    cell = 16*scale
    pad_l, pad_t = 30, 14
    rows_n = (count + cols - 1)//cols
    img = Image.new("L", (pad_l + cols*(cell+2), pad_t + rows_n*(cell+2)), 255)
    d = ImageDraw.Draw(img)
    for c in range(cols):
        d.text((pad_l + c*(cell+2) + cell//2 - 4, 2), f"{c:X}", fill=0)
    for i in range(count):
        gy, gx = divmod(i, cols)
        if gy*cols == i:
            d.text((2, pad_t + gy*(cell+2) + cell//2 - 4), f"{(base and i)//cols*cols + i - i%cols:02X}"[-2:], fill=0)
        rows = glyph_rows(rom, base + i*64)
        ox = pad_l + gx*(cell+2); oy = pad_t + gy*(cell+2)
        for y in range(16):
            for x in range(16):
                if (rows[y] >> (15-x)) & 1:
                    d.rectangle([ox+x*scale, oy+y*scale,
                                 ox+x*scale+scale-1, oy+y*scale+scale-1], fill=0)
    img.save(path)
    print(f"{label}: {count}자 -> {path}  ({img.width}x{img.height})")

if __name__ == "__main__":
    rom = open(sys.argv[1], 'rb').read()
    out = sys.argv[2] if len(sys.argv) > 2 else "darkhalf-kr"
    sheet(rom, SINGLE_BASE, 256, f"{out}/font_single.png", "단일바이트 코드 00-FF")
    sheet(rom, BANK_F5,     256, f"{out}/font_bank_F5.png", "한자뱅크 F5")
    sheet(rom, BANK_F6,     256, f"{out}/font_bank_F6.png", "한자뱅크 F6")
