#!/usr/bin/env python3
"""[은퇴] 메뉴 UI + 마법/아이템 설명문 한글화 — build.py 로 대체됨.

이 경로는 더 쓰지 않는다. 두 가지 이유다.

1. 자체 배정(DH_KEEP_KANA=1)으로 폰트를 따로 덮는다. build.py 는 회수
   정책으로 배정하므로 두 배정이 같은 폰트 영역을 놓고 다투고, 나중에
   돌린 쪽이 이긴다.
2. MENU 13개가 전부 대사 세그먼트 안에 있고 그 세그먼트들은 이미 TSV 에서
   번역됐다. 따로 덮으면 TSV 번역을 잘라 먹는다.

남겨 두는 이유는 MENU 주소 목록이 기록으로서 값이 있기 때문이다.
설명문 데이터(patch_desc.KO)와 find_runs 는 build.py 가 계속 쓴다.


전부 제자리(원본과 동일 길이) 삽입이므로 주소 이동이 없고 포인터를 건드리지 않는다.
메뉴 라벨은 예산이 3~8바이트로 빡빡하므로 단일바이트 코드를 우선 배정한다.
"""
import sys, os, shutil
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("DH_KEEP_KANA", "1")
import krcodec
from makefont import encode as enc_glyph
from dump import load_tbl
from patch_desc import find_runs, KO as DESC, PREFIX

from pipeline import FONT_BASE, patch_font   # 폰트 주소 계산은 한 곳에서만

# (주소, 원본 바이트 길이, 한국어)  — <ED>出 뒤 라벨 구간
MENU = [
 (0x040c14, 3, "예"),        (0x040c1f, 3, "아니오"),
 (0x040f3b, 5, "시전"),      (0x040fe0, 5, "사용"),
 (0x040fef, 5, "버리기"),    (0x040ffe, 5, "설명"),
 (0x041020, 6, "장비"),      (0x0411cb, 7, "마법 사용"),
 (0x0411de, 7, "아무것도 안함"), (0x0411f1, 8, "모두 도망"),
 (0x04121c, 7, "상황 보기"), (0x04122f, 7, "상대 안함"),
 (0x0418aa, 4, "되돌리기"),
]

def main(src, dst):
    shutil.copy(src, dst)
    rom = bytearray(open(dst, 'rb').read())
    t = load_tbl(os.path.join(os.path.dirname(os.path.abspath(__file__)), "darkhalf.tbl"))
    menu_txt = [m[2] for m in MENU]
    codes, freq, st = krcodec.allocate(list(DESC.values()) + menu_txt, t, priority=menu_txt)
    print(f"고유 음절 {st['unique']}/{st['capacity']}자 | 평균 {st['avg_bytes']:.2f} 바이트/음절")

    over = []
    def put(addr, cap, txt):
        b = krcodec.encode(txt, codes, t)
        if len(b) > cap: over.append((hex(addr), len(b), cap, txt)); return
        rom[addr:addr+cap] = b + bytes([0x20])*(cap-len(b))

    runs = find_runs(bytes(rom))
    for idx, txt in DESC.items():
        ad, ln = runs[idx]
        put(ad+PREFIX, ln-PREFIX, txt)
    for ad, ln, txt in MENU:
        put(ad, ln, txt)

    if over:
        print(f"!! 예산 초과 {len(over)}개")
        for a, n, c, x in over: print(f"   {a} {n}/{c}바이트  {x}")
        sys.exit(1)

    for ch, slot in codes.items():
        a = FONT_BASE[None] + slot[0]*64 if len(slot) == 1 else FONT_BASE[slot[0]] + slot[1]*64
        rom[a:a+64] = enc_glyph(ch)
    rom[0xFFDC]=rom[0xFFDD]=0xFF; rom[0xFFDE]=rom[0xFFDF]=0x00
    c=(sum(rom[:0x200000])+2*sum(rom[0x200000:0x300000]))&0xFFFF; comp=c^0xFFFF
    rom[0xFFDC]=comp&0xFF; rom[0xFFDD]=comp>>8; rom[0xFFDE]=c&0xFF; rom[0xFFDF]=c>>8
    open(dst,'wb').write(rom)
    print(f"설명문 {len(DESC)}개 + 메뉴 {len(MENU)}개 삽입 -> {dst}")

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
