#!/usr/bin/env python3
"""이름표 한글화 — 원본 자리에 그대로 덮어쓴다.

제자리여야 하는 이유는 nametbl.py 주석을 볼 것. 요약하면 마법 문자열을
가리키는 표가 셋이고(0x040300, 0x04f139, 0x05b517) 그중 하나는 설명문
본문에 박힌 「F0 C4 <포인터>」 다. 옮기면 메뉴에서 게임이 멈춘다.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nametbl, krcodec


def apply(rom, codes, tbl, verbose=False):
    over = []
    for spec, wl in nametbl.TABLES:
        for k, ((addr, cap), (ja, kr)) in enumerate(zip(nametbl.slots(rom, spec), wl)):
            if kr is None: continue
            try:
                b = krcodec.encode(kr, codes, tbl)
            except KeyError as e:
                raise SystemExit(f"{spec['name']} [{k:02X}] {kr!r} 인코딩 불가: {e}")
            if len(b) > cap:
                over.append((spec["name"], k, kr, len(b), cap)); continue
            rom[addr:addr+len(b)] = b
        # 남는 칸은 **공백(0x20)** 으로 채우고 종료자는 **원래 자리**에 둔다.
        #
        # 한때 남는 칸을 전부 0xFF 로 채웠다. 「종료자 뒤라 표시에 영향이
        # 없다」 고 봤는데 틀렸다. 원본 표에는 연속 0xFF 가 **한 쌍도 없다.**
        # 0xFF 로 채우면 마법표에 31쌍, 단어표에 67쌍이 생기고, 표를 0xFF
        # 구분자로 **순차 주사**하는 루틴이 그것을 빈 엔트리로 읽는다. 그러면
        # 인덱스가 밀려 목록에 엉뚱한 이름이 나오고(image/깨짐.png), 끝내 표를
        # 넘어 뒤쪽 0xFF 채움 구간까지 읽어 **화면 전체가 붕괴한다**
        # (image/깨짐2.png — broken.dmp 에 0xFF 연속 9,886바이트가 찍혔다).
        #
        # 공백으로 채우면 엔트리마다 0xFF 가 정확히 하나, 원본과 같은 자리에
        # 남는다. 포인터로 읽어도 뒤에 공백만 붙고, 순차로 훑어도 경계가 같다.
            for a in range(addr+len(b), addr+cap): rom[a] = 0x20
            rom[addr+cap] = 0xFF
        if verbose and not over:
            print(f"{spec['name']}: {sum(1 for _, k2 in wl if k2)}엔트리 제자리 삽입 "
                  f"(포인터 표 {spec['ptr']:#08x} 무변경)")
    return over


def verify(rom, orig, codes, tbl):
    bad = []
    for spec, wl in nametbl.TABLES:
        for k, ((addr, cap), (ja, kr)) in enumerate(zip(nametbl.slots(orig, spec), wl)):
            if kr is None: continue
            # apply 가 쓰는 배치를 그대로 대조한다 (patch_words.verify 주석 참조).
            want = krcodec.encode(kr, codes, tbl)
            exp = want + bytes([0x20]) * (cap - len(want)) + bytes([0xFF])
            got = bytes(rom[addr:addr+cap+1])
            if got != exp: bad.append((spec["name"], k, kr, got.hex(), exp.hex()))
        n = 2 * spec["count"]
        if bytes(rom[spec["ptr"]:spec["ptr"]+n]) != bytes(orig[spec["ptr"]:spec["ptr"]+n]):
            bad.append((spec["name"], -1, "포인터 표가 바뀌었다", "", ""))
    return bad
