#!/usr/bin/env python3
"""패치 검증: 게임 렌더러의 코드->글리프 해석을 그대로 흉내내 메시지를 그린다."""
import sys
from PIL import Image, ImageDraw
FB, BF5, BF6 = 0x2F0000, 0x2F4000, 0x2F8000

def rows(rom, o):
    out=[]
    for half in (0,1):
        for r in range(8):
            l  = rom[o+(half*2)*16   + r*2] | rom[o+(half*2)*16   + r*2+1]
            rr = rom[o+(half*2+1)*16 + r*2] | rom[o+(half*2+1)*16 + r*2+1]
            out.append((l<<8)|rr)
    return out

def msg_glyphs(rom, addr):
    """메시지를 글리프 주소열로 해석. 제어 코드는 건너뛴다."""
    out=[]; i=addr
    while rom[i] != 0xFF:
        x=rom[i]
        if x in (0xF5,0xF6):
            out.append(((BF5 if x==0xF5 else BF6) + rom[i+1]*64, f"{x:02X}{rom[i+1]:02X}")); i+=2
        elif x < 0x20 or 0xE6 <= x <= 0xFF:
            i += 1                              # 제어 코드
        else:
            out.append((FB + x*64, f"{x:02X}")); i += 1
    return out

def strip(rom, items, path, scale=4):
    cell=16*scale
    img=Image.new("L",(10+len(items)*(cell+6), 34+cell),255); d=ImageDraw.Draw(img)
    for i,(a,lab) in enumerate(items):
        ox=6+i*(cell+6); oy=28
        d.text((ox+cell//2-12,10),lab,fill=0)
        r=rows(rom,a)
        for y in range(16):
            for x in range(16):
                if (r[y]>>(15-x))&1:
                    d.rectangle([ox+x*scale,oy+y*scale,ox+x*scale+scale-1,oy+y*scale+scale-1],fill=0)
    img.save(path); return img.size

if __name__=="__main__":
    rom=open(sys.argv[1],'rb').read()
    # 체크섬 재검증
    c=(sum(rom[:0x200000])+2*sum(rom[0x200000:0x300000]))&0xFFFF
    tmp=bytearray(rom); tmp[0xFFDC]=tmp[0xFFDD]=0xFF; tmp[0xFFDE]=tmp[0xFFDF]=0x00
    calc=(sum(tmp[:0x200000])+2*sum(tmp[0x200000:0x300000]))&0xFFFF
    st=rom[0xFFDE]|(rom[0xFFDF]<<8); sc=rom[0xFFDC]|(rom[0xFFDD]<<8)
    print(f"체크섬 저장 {st:#06x} 계산 {calc:#06x} 보수 {sc:#06x} -> "
          f"{'유효' if calc==st and (st^sc)==0xFFFF else '무효'}")
    print("1단계 글리프:", strip(rom,[(FB+c*64,f"{c:02X}") for c in range(0xB1,0xB6)],
                                "darkhalf-kr/verify_level1.png"))
    items=msg_glyphs(rom,0x040c7b)
    print(f"2단계 메시지 글리프 {len(items)}개:", strip(rom,items,"darkhalf-kr/verify_level2.png"))
