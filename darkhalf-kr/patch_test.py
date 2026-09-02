#!/usr/bin/env python3
"""한글 삽입 개념검증 패치.

두 단계를 한 ROM 에 함께 넣는다.
  1단계: 가나 글리프 5개(あいうえお)를 한글로 교체
         -> 아무 대사에나 즉시 나타난다. 2bpp 포맷/타일순서/렌더경로 검증.
  2단계: 시스템 메시지 1개를 한글 문장으로 교체
         -> 한자뱅크 이스케이프(F5/F6) 경로까지 검증.

원본은 건드리지 않고 별도 파일로 저장한다.
"""
import sys, shutil
sys.path.insert(0, __file__.rsplit('/',1)[0])
from makefont import encode, glyph_to_rows

FB, BF5, BF6 = 0x2F0000, 0x2F4000, 0x2F8000

# 1단계: 코드 -> 한글
LEVEL1 = {0xB1:'한', 0xB2:'글', 0xB3:'테', 0xB4:'스', 0xB5:'트'}
# 2단계: 미사용 한자뱅크 슬롯 -> 한글  (F5 09/0F, F6 B7/B8/BA 는 어디서도 참조되지 않음)
LEVEL2_SLOTS = [(0xF5,0x09,'가'), (0xF5,0x0F,'진'),
                (0xF6,0xB7,'게'), (0xF6,0xB8,'없'), (0xF6,0xBA,'다')]
MSG_ADDR, MSG_LEN = 0x040c7b, 13      # 시스템 메시지 (원문: 아무것도 안 가지고 있다는 안내)

def glyph_addr(bank, idx):
    return (BF5 if bank == 0xF5 else BF6) + idx*64

def snes_checksum(d):
    return (sum(d[:0x200000]) + 2*sum(d[0x200000:0x300000])) & 0xFFFF

def fix_checksum(rom):
    rom[0xFFDC] = 0xFF; rom[0xFFDD] = 0xFF
    rom[0xFFDE] = 0x00; rom[0xFFDF] = 0x00
    c = snes_checksum(rom); comp = c ^ 0xFFFF
    rom[0xFFDC] = comp & 0xFF; rom[0xFFDD] = comp >> 8
    rom[0xFFDE] = c & 0xFF;    rom[0xFFDF] = c >> 8
    return c, comp

def main(src, dst):
    shutil.copy(src, dst)
    rom = bytearray(open(dst,'rb').read())

    for code, ch in LEVEL1.items():
        rom[FB+code*64 : FB+code*64+64] = encode(ch)
    print(f"1단계: 가나 글리프 {len(LEVEL1)}개 교체 -> {''.join(LEVEL1.values())}")

    codes = {}
    for bank, idx, ch in LEVEL2_SLOTS:
        a = glyph_addr(bank, idx)
        rom[a:a+64] = encode(ch)
        codes[ch] = bytes([bank, idx])
    text = "가진게없다"
    new = bytes([0xFA, 0x01]) + b''.join(codes[c] for c in text) + bytes([0x21])
    assert len(new) <= MSG_LEN, f"메시지가 {len(new)}바이트로 원본 {MSG_LEN}바이트를 초과"
    rom[MSG_ADDR : MSG_ADDR+len(new)] = new
    rom[MSG_ADDR+len(new)] = 0xFF                      # 메시지 종료
    print(f"2단계: 메시지 @{MSG_ADDR:#08x} 교체 -> '{text}!' ({len(new)}/{MSG_LEN}바이트)")

    c, comp = fix_checksum(rom)
    open(dst,'wb').write(rom)
    print(f"체크섬 갱신: {c:#06x} / 보수 {comp:#06x}")
    print(f"저장: {dst}")

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
