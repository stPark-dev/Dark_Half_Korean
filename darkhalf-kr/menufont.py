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

FONT = "/usr/share/fonts/malgun.ttf"     # 1px 획이 깔끔하게 나온다
SIZE = 14
THR = 110

# 원본은 획 색으로 4·7·9·13 을 디더링해 중간색을 만든다 (削 의 긴 직선 획이
# 4,9,9,4,9,7,d 처럼 섞여 있다). 흉내내면 원본에 가깝지만 **자리에 안 들어간다** —
# 색이 섞이면 압축이 나빠져 블록이 787바이트가 되고 칸은 786뿐이다.
#
#   4색 디더+그림자   787  초과 1
#   2색(9,7)+그림자   795  초과 9
#   단색 9+그림자     770  가능   <- 이걸 쓴다
#   단색 9, 그림자 없음 749  가능
#
# 그래서 단색으로 간다. 9 는 원본 획에서 가장 많이 쓰이는 색(削 30px)이라
# 확실히 보이는 색이다. 원본보다 평평해 보이지만 읽힌다.
DITHER = (9,)
SHADOW = 5      # 우하단 1px 그림자. 배경과 가까운 색이라 획에 쓰면 안 보인다


def render(ch, size=SIZE, thr=THR, shadow=True):
    """문자 -> 16x16 색번호 배열.

    ## 원본의 그리기 규칙 (削·規 를 색별로 분해해 확인)

        ..#######o.      # = 획 (4/7/9/13 디더)
        ..#ooooo#o.      o = 색 5, 획의 우하단 1px 그림자
        ..#o....#o.      . = 색 0, 투명

    획은 **1px** 이다. 처음에 색 5(그림자색)로 2px 획을 그렸더니 화면에서
    아무것도 안 보였다 (PROGRESS 4.17.9).
    """
    im = Image.new("L", (16, 16), 0)
    d = ImageDraw.Draw(im)
    f = ImageFont.truetype(FONT, size)
    bb = f.getbbox(ch)
    d.text(((16-(bb[2]-bb[0]))//2 - bb[0], (16-(bb[3]-bb[1]))//2 - bb[1]),
           ch, fill=255, font=f)
    p = im.load()
    ink = [[p[x, y] >= thr for x in range(16)] for y in range(16)]
    g = [[0]*16 for _ in range(16)]
    if shadow:
        for y in range(16):
            for x in range(16):
                if ink[y][x] and y+1 < 16 and x+1 < 16 and not ink[y+1][x+1]:
                    g[y+1][x+1] = SHADOW
    for y in range(16):
        for x in range(16):
            if ink[y][x]: g[y][x] = DITHER[(x*5 + y*3) % len(DITHER)]
    return g


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
