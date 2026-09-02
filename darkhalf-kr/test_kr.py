#!/usr/bin/env python3
"""한글 배정·폰트 기록·삽입 경로 테스트.

python3 darkhalf-kr/test_kr.py "Dark Half (Japan).sfc"
"""
import sys, os, subprocess, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

FAIL = []
def check(name, cond, detail=""):
    print(("  OK   " if cond else "  FAIL ") + name + (f"  {detail}" if detail and not cond else ""))
    if not cond: FAIL.append(name)

def main(rom_path):
    rom = open(rom_path, 'rb').read()
    import krcodec, makefont, pipeline
    from dump import load_tbl
    tbl = load_tbl(os.path.join(os.path.dirname(os.path.abspath(__file__)), "darkhalf.tbl"))

    print("[1] 뱅크 정의 — F7 은 0x3E 이후가 폰트 데이터가 아니다")
    banks = dict(krcodec.BANKS)
    check("F5 뱅크 256슬롯", banks.get(0xF5) == 256, f"{banks.get(0xF5)}")
    check("F6 뱅크 256슬롯", banks.get(0xF6) == 256, f"{banks.get(0xF6)}")
    check("F7 뱅크 96슬롯 (0x00-0x3D + 0xDE-0xFF)", banks.get(0xF7) == 96, f"{banks.get(0xF7)}")

    print("[2] 수용량")
    os.environ.pop("DH_KEEP_KANA", None)
    check("단일바이트 회수 145개", len(krcodec.reclaimable()) == 145, f"{len(krcodec.reclaimable())}")
    check("전면 번역 수용량 753자", krcodec.capacity() == 753, f"{krcodec.capacity()}")
    os.environ["DH_KEEP_KANA"] = "1"
    check("가나 보존 시 단일바이트 34개", len(krcodec.reclaimable()) == 34, f"{len(krcodec.reclaimable())}")
    os.environ.pop("DH_KEEP_KANA", None)

    print("[3] 글리프 기록 주소 — 뱅크별로 올바른 폰트 영역에 써야 한다")
    BASE = {1: 0x2F0000, 0xF5: 0x2F4000, 0xF6: 0x2F8000, 0xF7: 0x2FC000}
    for slot, want in ((bytes([0x22]), 0x2F0000 + 0x22*64),
                       (bytes([0xF5, 0x10]), 0x2F4000 + 0x10*64),
                       (bytes([0xF6, 0x10]), 0x2F8000 + 0x10*64),
                       (bytes([0xF7, 0x10]), 0x2FC000 + 0x10*64)):
        buf = bytearray(rom)
        pipeline.patch_font(buf, {"가": slot})
        got = [a for a in range(0x2F0000, 0x300000, 64) if buf[a:a+64] != rom[a:a+64]]
        tag = f"슬롯 {slot.hex()}"
        check(f"{tag} -> {want:#08x}", got == [want], f"실제 {[hex(x) for x in got]}")

    print("[4] F7 상위 슬롯은 절대 배정되지 않아야 한다 (폰트 아닌 데이터 영역)")
    codes, _, _ = krcodec.allocate(["".join(chr(0xAC00+i) for i in range(753))], tbl)
    bad = [ch for ch, s in codes.items()
           if len(s) == 2 and s[0] == 0xF7 and 0x3E <= s[1] < 0xDE]
    check("F7 0x3E-0xDD (정체불명 구간) 미배정", not bad, f"{len(bad)}개 배정됨")

    print("[5] 인코딩 왕복 — 배정한 코드로 인코딩하면 길이가 예측과 맞는다")
    codes, freq, st = krcodec.allocate(["가나다"], tbl)
    enc = krcodec.encode("가나다", codes, tbl)
    check("3음절 전부 단일바이트", len(enc) == 3, f"{len(enc)}바이트")
    check("제어 코드 보존 <1C>", krcodec.encode("<1C>", codes, tbl) == b'\x1c')
    check("개행 \\n -> 0xE3", krcodec.encode("\\n", codes, tbl) == b'\xe3')
    check("뱅크 태그 <A05> -> F5 05", krcodec.encode("<A05>", codes, tbl) == b'\xf5\x05')
    check("뱅크 태그 <C05> -> F7 05", krcodec.encode("<C05>", codes, tbl) == b'\xf7\x05')

    print("[6] 폰트 인코더 왕복")
    ok = all(makefont.glyph_to_rows(makefont.encode(c)) == makefont.render_rows(c)
             for c in "가나다라마바사아자차카타파하한글")
    check("makefont 왕복 일치", ok)

    print("[7] 파이프라인 왕복 (번역 없이) — 원본과 0바이트")
    out = subprocess.run([sys.executable, "darkhalf-kr/pipeline.py", "roundtrip", rom_path],
                         capture_output=True, text=True).stdout
    check("왕복 0바이트", "차이 0바이트" in out, out.strip().splitlines()[-1] if out else "")

    print("[8] 기존 UI 패치 회귀")
    with tempfile.TemporaryDirectory() as d:
        o = os.path.join(d, "t.sfc")
        r = subprocess.run([sys.executable, "darkhalf-kr/patch_all.py", rom_path, o],
                           capture_output=True, text=True)
        check("patch_all 정상 종료", r.returncode == 0 and os.path.exists(o), r.stderr[-200:])

    test_readable_safe(rom_path)
    test_readable_roundtrip(rom_path)

    print()
    if FAIL:
        print(f"실패 {len(FAIL)}개: " + ", ".join(FAIL)); sys.exit(1)
    print("전부 통과")

def test_readable_roundtrip(rom_path):
    """모든 세그먼트에서 '판독문 -> 인코딩'이 원본 바이트와 일치하는지.

    번역은 판독문을 복사해 일본어 구간만 교체하는 방식이다. 따라서 판독문의
    비(非)한글 부분이 원본과 다른 바이트로 인코딩되면 조용히 깨진다.
    이 검사가 없어서 뱅크 한자(降 등)를 옮겨 적은 세그먼트가 인코딩 불가로
    터졌다 — krcodec 이 뱅크 한자를 되받도록 고친 뒤 이 불변식으로 지킨다.
    """
    import krcodec, pipeline
    from dump import load_tbl, decode
    from kanji import KANJI
    tbl = load_tbl(os.path.join(os.path.dirname(os.path.abspath(__file__)), "darkhalf.tbl"))
    rom = open(rom_path, 'rb').read()
    segs, _, _, _ = pipeline.segments(rom)
    bad_txt, bad_len = [], []
    for sg in segs:
        raw = rom[sg["addr"]:sg["addr"]+sg["len"]]
        if not raw: continue
        txt = decode(raw, tbl, KANJI)
        try:
            enc = krcodec.encode(txt, {}, tbl)
        except KeyError as e:
            bad_txt.append((sg["addr"], str(e))); continue
        # 같은 글리프가 단일바이트와 뱅크 양쪽에 있으면 바이트는 달라질 수 있다.
        # 지켜야 하는 것은 '표시가 같고 길이가 늘지 않는다' 이다.
        if decode(enc, tbl, KANJI) != txt: bad_txt.append((sg["addr"], "표시 불일치"))
        if len(enc) > len(raw): bad_len.append((sg["addr"], len(enc)-len(raw)))
    print("[10] 전 세그먼트 판독문 왕복 (표시 보존 + 길이 비증가)")
    check(f"표시 보존 {len(segs)}개", not bad_txt, f"실패 {len(bad_txt)}개 예: {bad_txt[:3]}")
    check("길이 비증가", not bad_len, f"증가 {len(bad_len)}개 예: {bad_len[:3]}")


def test_readable_safe(rom_path):
    """판독 컬럼의 태그/문자를 그대로 인코딩했을 때 원본 바이트가 보존되는지.

    번역 작업은 '제어 골격을 그대로 두고 일본어 구간만 교체'하는 방식이므로,
    판독문에서 옮겨 적은 비(非)한글 부분이 원본과 다른 바이트로 인코딩되면
    조용히 깨진다. ★(0xE2/E4/E5/FF 공유) 같은 모호 글리프가 대표적이다.
    """
    import krcodec
    from dump import load_tbl, decode, ambiguous
    tbl = load_tbl(os.path.join(os.path.dirname(os.path.abspath(__file__)), "darkhalf.tbl"))
    amb = ambiguous(tbl)
    print("[9] 판독문 -> 바이트 보존 (모호 글리프 안전성)")
    check("★ 은 태그로 남는다", "★" not in decode(bytes([0xE2, 0xE4, 0xFF]), tbl, {}))
    bad = [c for c in amb if c not in krcodec.CTRL and chr(0) != ""
           and decode(bytes([c]), tbl, {}) != f"<{c:02X}>"]
    check("모호 글리프 전부 태그", not bad, f"{[hex(c) for c in bad]}")
    rt = 0
    for c in range(0x20, 0xE0):
        txt = decode(bytes([c]), tbl, {})
        try:
            if krcodec.encode(txt, {}, tbl) != bytes([c]): rt += 1
        except KeyError:
            rt += 1
    check("단일바이트 판독->인코딩 왕복", rt == 0, f"불일치 {rt}개")
    from dump import CTRL_KANJI
    bad2 = [c for c, g in CTRL_KANJI.items()
            if decode(bytes([c]), tbl, {}) != f"<{g}>"
            or krcodec.encode(f"<{g}>", {}, tbl) != bytes([c])]
    check("제어범위 한자 <魔><士><見><入> 왕복", not bad2, f"{[hex(c) for c in bad2]}")

if __name__ == "__main__":
    main(sys.argv[1])
