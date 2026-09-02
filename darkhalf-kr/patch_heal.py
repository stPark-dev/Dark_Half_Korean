#!/usr/bin/env python3
"""ヒール(힐) 마법 설명문 한글화.

대상: 0x05B5CF, 38바이트 (뱅크 0x05 마법 설명 테이블 #19)
원문: ＨＰを回復する呪文 / アンデッドを消滅させる
앞 9바이트는 표시용 제어/서식이므로 원본 그대로 보존하고 본문만 교체한다.
길이를 원본과 동일하게 유지하므로 주소 이동이 없다.
"""
import sys, os, shutil
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import krcodec
from makefont import encode as enc_glyph
from dump import load_tbl

ADDR, LEN, PREFIX = 0x05B5CF, 38, 9
KO = "ＨＰ를 회복하는 주문\\n언데드를 소멸시킨다"
FB, B5, B6 = 0x2F0000, 0x2F4000, 0x2F8000

def main(src, dst):
    shutil.copy(src, dst)
    rom = bytearray(open(dst, 'rb').read())
    assert rom[ADDR+LEN] == 0xFF, "런 경계가 예상과 다름"
    t = load_tbl(os.path.join(os.path.dirname(os.path.abspath(__file__)), "darkhalf.tbl"))
    os.environ["DH_KEEP_KANA"] = "1"          # 가나 보존 -> 메뉴 정상
    codes, freq, st = krcodec.allocate([KO], t)
    body = krcodec.encode(KO, codes, t)
    cap = LEN - PREFIX
    assert len(body) <= cap, f"{len(body)}바이트 > 여유 {cap}바이트"
    new = rom[ADDR:ADDR+PREFIX] + body + bytes([0x20])*(cap-len(body))
    assert len(new) == LEN
    rom[ADDR:ADDR+LEN] = new
    for ch, slot in codes.items():
        a = FB + slot[0]*64 if len(slot) == 1 else (B5 if slot[0]==0xF5 else B6) + slot[1]*64
        rom[a:a+64] = enc_glyph(ch)
    rom[0xFFDC]=rom[0xFFDD]=0xFF; rom[0xFFDE]=rom[0xFFDF]=0x00
    c=(sum(rom[:0x200000])+2*sum(rom[0x200000:0x300000]))&0xFFFF; comp=c^0xFFFF
    rom[0xFFDC]=comp&0xFF; rom[0xFFDD]=comp>>8; rom[0xFFDE]=c&0xFF; rom[0xFFDF]=c>>8
    open(dst,'wb').write(rom)
    print(f"고유 음절 {st['unique']}자, 전부 단일바이트: {st['occ2']==0}")
    print(f"본문 {len(body)}/{cap}바이트 (남는 {cap-len(body)}바이트는 공백 패딩)")
    print(f"저장: {dst}")

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
