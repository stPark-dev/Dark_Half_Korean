#!/usr/bin/env python3
"""메뉴 폰트 출처 진단용 ROM 생성.

아이템 액션 메뉴 3항목에 서로 다른 코드 범위를 배정하고,
각 코드의 메인 폰트(0x2F0000) 글리프를 한글로 덮어쓴다.
게임에서 무엇이 보이는지가 곧 판정이다:
  한글이 보이면      -> 그 코드 범위는 메인 폰트를 씀
  원래 가나가 보이면 -> 글리프가 다른 곳에서 옴
  깨져 보이면        -> 그 코드가 메뉴 폰트 범위 밖
"""
import sys, os, shutil, hashlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from makefont import encode as enc_glyph

FB = 0x2F0000
PLAN = [
    (0x040fe0, 5, [0xB1, 0xB2], "사용", "히라가나 범위 (원래 あ い)"),
    (0x040fef, 5, [0x22, 0x23], "버리", "한자 범위 (원래 生 兵)"),
    (0x040ffe, 5, [0x71, 0x72], "설명", "가타카나 범위 (원래 ア イ)"),
]

def main(src, dst):
    shutil.copy(src, dst)
    rom = bytearray(open(dst, 'rb').read())
    for ad, ln, codes, word, note in PLAN:
        for c, ch in zip(codes, word):
            rom[FB + c*64: FB + (c+1)*64] = enc_glyph(ch)
        rom[ad:ad+ln] = bytes(codes) + bytes([0x20]) * (ln - len(codes))
        print(f"  @{ad:#08x} '{word}' <- 코드 {[f'{c:02X}' for c in codes]}  ({note})")
    rom[0xFFDC] = rom[0xFFDD] = 0xFF
    rom[0xFFDE] = rom[0xFFDF] = 0x00
    c = (sum(rom[:0x200000]) + 2*sum(rom[0x200000:0x300000])) & 0xFFFF
    comp = c ^ 0xFFFF
    rom[0xFFDC] = comp & 0xFF; rom[0xFFDD] = comp >> 8
    rom[0xFFDE] = c & 0xFF;    rom[0xFFDF] = c >> 8
    open(dst, 'wb').write(rom)
    print(f"\n저장: {dst}")
    print(f"md5: {hashlib.md5(bytes(rom)).hexdigest()}  체크섬: {c:#06x} (유효)")

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
