#!/usr/bin/env python3
"""마법/아이템 설명문 한글화 (뱅크 0x05).

각 설명문은 앞 9바이트가 표시 제어·서식이고 그 뒤가 본문이다.
길이를 원본과 동일하게 유지(부족분은 공백 패딩)하므로 주소 이동이 없고
포인터를 건드리지 않는다. 뱅크 0x05 의 포인터 구조를 모르는 상태에서
가장 안전한 방식이다.
"""
import sys, os, shutil
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import krcodec
from makefont import encode as enc_glyph
from dump import load_tbl

PREFIX = 9
from pipeline import FONT_BASE      # 폰트 주소 계산은 pipeline 한 곳에만 둔다

KO = {
 0: "화염으로 감싼다",
 1: "냉기로 공격한다",
 2: "빛을 한 점에 모아\\n피해를 준다",
 3: "적을 바람으로 벤다",
 4: "소울의 힘을 적에게\\n부딪친다",
 5: "죽음으로 이끈다\\n성공률낮음",
 6: "ＨＰ를 회복\\n언데드를 소멸시킨다",
 7: "언데드 혼란 마비 독\\n수면 상태를 회복",
 8: "실드 등 주문 효과를\\n무효화한다",
 9: "직접 공격을 막는다",
10: "주문 공격을 막는다",
11: "적을 혼란시킨다",
12: "적을 마비시켜\\n직접 공격을 막는다",
13: "적을 중독시킨다\\n독은 방어력을 낮춘다",
14: "적을 잠재운다",
15: "공격력을 잠시\\n올린다",
16: "적을 언데드 상태로\\n바꾼다",
17: "몬스터를 부하로\\n만든다",
18: "세상에 남은\\n<EB><14>의 기도",
19: "<EB><0D>의 성아래마을\\n가족에게",
}

def find_runs(rom):
    FF = b'\xFF'; out = []
    for lo, hi in ((0x05b000, 0x05b800), (0x05bc00, 0x05c400)):
        a = lo
        while a < hi:
            if rom[a] == 0xFF:
                e = rom.find(FF, a+1)
                if 0 < e <= hi and e-a-1 >= 8 and rom[a+1:a+3] == bytes([0xED, 0x3C]):
                    out.append((a+1, e-a-1))
                a = e if e > a else a+1
            else: a += 1
    return out

def main(src, dst):
    shutil.copy(src, dst)
    rom = bytearray(open(dst, 'rb').read())
    t = load_tbl(os.path.join(os.path.dirname(os.path.abspath(__file__)), "darkhalf.tbl"))
    os.environ["DH_KEEP_KANA"] = "1"
    runs = find_runs(bytes(rom))
    codes, freq, st = krcodec.allocate(list(KO.values()), t)
    print(f"고유 음절 {st['unique']}/{st['capacity']}자 | "
          f"단일바이트 {st['single_slots']}자가 출현의 {st['occ1']/(st['occ1']+st['occ2'])*100:.0f}% "
          f"-> 평균 {st['avg_bytes']:.2f} 바이트/음절\n")
    over = []
    for idx, txt in KO.items():
        ad, ln = runs[idx]
        cap = ln - PREFIX
        body = krcodec.encode(txt, codes, t)
        if len(body) > cap:
            over.append((idx, len(body), cap, txt)); continue
        rom[ad+PREFIX:ad+ln] = body + bytes([0x20])*(cap-len(body))
    if over:
        print(f"!! 예산 초과 {len(over)}개 — 줄여야 합니다")
        for i, n, c, x in over: print(f"   #{i:2d} {n:3d}/{c:3d}바이트 (초과 {n-c:2d})  {x}")
        sys.exit(1)
    for ch, slot in codes.items():
        a = FONT_BASE[None] + slot[0]*64 if len(slot) == 1 else FONT_BASE[slot[0]] + slot[1]*64
        rom[a:a+64] = enc_glyph(ch)
    rom[0xFFDC]=rom[0xFFDD]=0xFF; rom[0xFFDE]=rom[0xFFDF]=0x00
    c=(sum(rom[:0x200000])+2*sum(rom[0x200000:0x300000]))&0xFFFF; comp=c^0xFFFF
    rom[0xFFDC]=comp&0xFF; rom[0xFFDD]=comp>>8; rom[0xFFDE]=c&0xFF; rom[0xFFDF]=c>>8
    open(dst,'wb').write(rom)
    print(f"설명문 {len(KO)}개 삽입 완료 -> {dst}")

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
