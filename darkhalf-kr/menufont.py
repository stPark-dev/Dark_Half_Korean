#!/usr/bin/env python3
"""메뉴 폰트(4bpp) 한글 글리프 — 세이브 화면·아이템 목록·오프닝용.

## 대사 폰트와 무엇이 다른가

| | 대사 폰트 | 메뉴 폰트 |
|---|---|---|
| 깊이 | 2bpp (플레인 동일 = 단색) | **4bpp** (플레인 4개가 다름) |
| 위치 | `0x2F0000` 비압축 | 뱅크 `0x16` **압축** (`gfx.py`) |
| 배치 | TL,TR,BL,BR | `n, n+1 / n+16, n+17` (16타일 폭) |

## 색 번호

원본 글리프(`規`)의 색 분포는 `0:101 5:72 9:32 7:27 4:12 13:12` 이다.
**5 가 본체**이고 7·9·4·13 은 테두리 음영이다. 실제 팔레트 색은 화면마다
다르므로(CGRAM 은 다른 화면 것뿐이다) 색 번호의 **역할**만 맞춘다.

한글은 획이 단순해서 본체 색 하나로 칠해도 읽힌다. 음영을 흉내내면 원본에
가까워지지만, 잘못 넣으면 획이 뭉개진다. 그래서 기본은 단색 5 다.
"""
import sys, os
from PIL import Image, ImageDraw, ImageFont

FONT = "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf"
SIZE = 14
THR = 110
BODY = 5          # 원본 본체 색


def render(ch, size=SIZE, thr=THR):
    """문자 -> 16x16 색번호 배열 (0 = 배경)."""
    im = Image.new("L", (16, 16), 0)
    d = ImageDraw.Draw(im)
    f = ImageFont.truetype(FONT, size)
    bb = f.getbbox(ch)
    d.text(((16-(bb[2]-bb[0]))//2 - bb[0], (16-(bb[3]-bb[1]))//2 - bb[1]),
           ch, fill=255, font=f)
    p = im.load()
    return [[BODY if p[x, y] >= thr else 0 for x in range(16)] for y in range(16)]


def put(buf, t0, g):
    """16x16 색번호 배열을 버퍼의 타일 t0, t0+1, t0+16, t0+17 에 쓴다.

    4bpp 타일 = 플레인0/1 인터리브 16바이트 + 플레인2/3 인터리브 16바이트.
    """
    def wr(t, ox, oy):
        o = t * 32
        for r in range(8):
            v = [0, 0, 0, 0]
            for c in range(8):
                col = g[oy + r][ox + c]
                for pl in range(4):
                    if (col >> pl) & 1: v[pl] |= 1 << (7 - c)
            buf[o + r*2]      = v[0]
            buf[o + r*2 + 1]  = v[1]
            buf[o + 16 + r*2]     = v[2]
            buf[o + 16 + r*2 + 1] = v[3]
    wr(t0, 0, 0); wr(t0 + 1, 8, 0)
    wr(t0 + 16, 0, 8); wr(t0 + 17, 8, 8)


if __name__ == "__main__":
    g = render(sys.argv[1] if len(sys.argv) > 1 else "규")
    for row in g: print("  " + "".join(f"{v:x}" if v else "." for v in row))
