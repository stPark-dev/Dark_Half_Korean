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
    from dump import load_tbl, decode
    tbl = load_tbl(os.path.join(os.path.dirname(os.path.abspath(__file__)), "darkhalf.tbl"))

    print("[1] 뱅크 정의 — F7 은 0x3E 이후가 폰트 데이터가 아니다")
    banks = dict(krcodec.BANKS)
    # F5 는 UI 가 직접 그리는 東西南北(4D~50)을 뺀다 (krcodec.UI_KANJI).
    check("F5 뱅크 251슬롯 (0xFF·UI한자 제외)",
          banks.get(0xF5) == 255 - len(krcodec.UI_KANJI), f"{banks.get(0xF5)}")
    check("F6 뱅크 255슬롯 (0xFF 제외)", banks.get(0xF6) == 255, f"{banks.get(0xF6)}")
    check("F7 뱅크 95슬롯 (0x00-0x3D + 0xDE-0xFE)", banks.get(0xF7) == 95, f"{banks.get(0xF7)}")

    # F4 는 배정 풀에서 빠져 있어야 한다 (PROGRESS 4.12 / 4.13).
    # 두 가지 이유가 겹친다. (1) F4_SLOTS 의 글리프는 원본이 쓴다 — 0x00 魔,
    # 0x04 ◀, 0x05 ▶, 0x06~0x1F 탁음 가나. 한글을 배정하면 덮인다.
    # (2) F4 의 둘째 바이트는 항상 제어 코드 값이라, F4 를 처리하지 않는
    # 메뉴·표 렌더러가 그것을 제어 코드로 읽고 게임이 멈춘다.
    check("F4 는 배정 풀에 없다", 0xF4 not in banks, f"{banks.get(0xF4)}")
    check("신규 프리픽스 $5D 255슬롯 (0xFF 제외)", banks.get(0x5D) == 255, f"{banks.get(0x5D)}")
    check("신규 프리픽스 $D5 255슬롯 (0xFF 제외)", banks.get(0xD5) == 255, f"{banks.get(0xD5)}")
    check("프리픽스 바이트는 단일바이트 배정 제외",
          not (set(krcodec.reclaimable()) & krcodec.PREFIX_BYTES))

    print("[2] 수용량")
    os.environ.pop("DH_KEEP_KANA", None)
    # 141 = 0x20~0xDF 에서 KEEP·제어·프리픽스를 뺀 수.
    # 143 이었다가 0xA0(♥) 을 KEEP 으로 옮겨 하나 줄었다. ♥ 는 본문 문장부호가
    # 아니라 UI 표시 글리프여서 회수하면 아이템 창이 깨진다 (krcodec.KEEP 주석).
    check("단일바이트 회수 141개 (프리픽스 $5D/$D5, ♥, ＋ 제외)", len(krcodec.reclaimable()) == 141, f"{len(krcodec.reclaimable())}")
    # F4 57칸을 뺀 값. 필요량은 약 836자다 (trcheck 외삽).
    # ＋(0x2B) 는 장비 강화 표시다. 회수하면 「소검＋１」 이 「소검하１」 이 된다.
    check("＋(0x2B) 는 회수 대상이 아니다", 0x2B not in krcodec.reclaimable())
    # 반각 폰트에는 한자가 없다 — 단일바이트 한자 코드의 8x8 칸은 창 장식이다.
    # 회수는 그대로 두고(대사 폰트에서는 정상 글리프 자리다) allocate 가 풀
    # 맨 뒤로 밀어 목록·필드 음절이 걸리지 않게 한다.
    ui = krcodec.hw_ui()
    check("장식칸 31개 식별 (0xDE 中·0xDF 物 포함)",
          len([c for c in krcodec.reclaimable() if c in ui]) == 31
          and 0xDE in ui and 0xDF in ui and 0x60 in ui,
          f"{len([c for c in krcodec.reclaimable() if c in ui])}")
    _s = [c for c in krcodec.reclaimable()]
    _pool = ([c for c in _s if c not in ui] + [c for c in _s if c in ui])
    check("장식칸은 단일바이트 풀 맨 뒤 31칸", all(c in ui for c in _pool[-31:]))
    check("전면 번역 수용량 1252자 (UI한자 4칸·＋ 제외)",
          krcodec.capacity() == 1256 - len(krcodec.UI_KANJI), f"{krcodec.capacity()}")
    os.environ["DH_KEEP_KANA"] = "1"
    check("가나 보존 시 단일바이트 31개", len(krcodec.reclaimable()) == 31, f"{len(krcodec.reclaimable())}")
    os.environ.pop("DH_KEEP_KANA", None)

    print("[3] 글리프 기록 주소 — 뱅크별로 올바른 폰트 영역에 써야 한다")
    BASE = {1: 0x2F0000, 0xF5: 0x2F4000, 0xF6: 0x2F8000, 0xF7: 0x2FC000}
    ROM4MB = 4 * 1024 * 1024
    for slot, want in ((bytes([0x22]), 0x2F0000 + 0x22*64),
                       (bytes([0xF5, 0x10]), 0x2F4000 + 0x10*64),
                       (bytes([0xF6, 0x10]), 0x2F8000 + 0x10*64),
                       (bytes([0xF7, 0x10]), 0x2FC000 + 0x10*64),
                       (bytes([0x5D, 0x10]), 0x300000 + 0x10*64),
                       (bytes([0xD5, 0x10]), 0x304000 + 0x10*64)):
        # 신규 프리픽스는 4MB 확장분(0x300000~)을 쓰므로 버퍼를 늘려서 검사한다
        base = bytearray(rom) + bytearray(b'\xff') * (ROM4MB - len(rom))
        buf = bytearray(base)
        pipeline.patch_font(buf, {"가": slot})
        got = [a for a in range(0x2F0000, 0x308000, 64) if buf[a:a+64] != base[a:a+64]]
        tag = f"슬롯 {slot.hex()}"
        check(f"{tag} -> {want:#08x}", got == [want], f"실제 {[hex(x) for x in got]}")

    print("[3b] 이스케이프 둘째 바이트에 0xFF 가 오면 안 된다")
    # 0xFF 는 문자열·메시지 종료자다. 단어표·이름표는 0xFF 로 엔트리를 끊으므로
    # 「컨」 이 F6 FF 를 받으면 판독이 첫 바이트에서 끊긴다. 실제로 마법 이름
    # [0x0B] 이 이 때문에 삽입 역검증 [7] 에서 걸렸다.
    for b, idxs in krcodec.BANK_SLOTS.items():
        check(f"뱅크 {b:#04x} 슬롯에 0xFF 없음", 0xFF not in idxs,
              "0xFF 가 슬롯에 있다")
    codes_ff, _, _ = krcodec.allocate(
        ["".join(chr(0xAC00+i) for i in range(krcodec.capacity()))], tbl)
    ff = [ch for ch, sl in codes_ff.items() if len(sl) == 2 and sl[1] == 0xFF]
    check("수용량을 꽉 채워도 0xFF 로 끝나는 배정 없음", not ff, f"{ff[:5]}")

    print("[4] F7 상위 슬롯은 절대 배정되지 않아야 한다 (폰트 아닌 데이터 영역)")
    # 수용량을 꽉 채워야 F7 상위 구간까지 배정 시도가 간다. 상수로 박지 않는다.
    codes, _, _ = krcodec.allocate(
        ["".join(chr(0xAC00+i) for i in range(krcodec.capacity()))], tbl)
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
    check("뱅크 태그 <D02> -> F4 02", krcodec.encode("<D02>", codes, tbl) == b'\xf4\x02')
    check("뱅크 태그 <E05> -> 5D 05", krcodec.encode("<E05>", codes, tbl) == b'\x5d\x05')
    check("뱅크 태그 <F05> -> D5 05", krcodec.encode("<F05>", codes, tbl) == b'\xd5\x05')
    check("F4 02 는 見 로 읽힌다", decode(b'\xf4\x02', tbl, {}) == '見')
    check("★ 은 F4 로 인코딩", krcodec.encode("★", codes, tbl)[:1] == b'\xf4')

    print("[6] 폰트 인코더 왕복")
    ok = all(makefont.glyph_to_rows(makefont.encode(c)) == makefont.render_rows(c)
             for c in "가나다라마바사아자차카타파하한글")
    check("makefont 왕복 일치", ok)

    print("[7] 파이프라인 왕복 (번역 없이) — 원본과 0바이트")
    out = subprocess.run([sys.executable, "darkhalf-kr/pipeline.py", "roundtrip", rom_path],
                         capture_output=True, text=True).stdout
    check("왕복 0바이트", "차이 0바이트" in out, out.strip().splitlines()[-1] if out else "")

    print("[8] 통합 빌드 회귀 — 대사·설명문·단어표·이름표를 한 배정으로")
    # patch_all.py 는 은퇴했다. 자체 배정(DH_KEEP_KANA=1)으로 폰트를 따로 덮고
    # MENU 13개가 대사 세그먼트를 잘라 먹기 때문이다. build.py 가 정본이다.
    with tempfile.TemporaryDirectory() as d:
        o = os.path.join(d, "t.sfc")
        r = subprocess.run([sys.executable, "darkhalf-kr/build.py",
                            rom_path, "darkhalf-kr/script_main.tsv", o],
                           capture_output=True, text=True)
        check("build 정상 종료", r.returncode == 0 and os.path.exists(o),
              (r.stdout + r.stderr)[-300:])
        if os.path.exists(o):
            test_ee_jumps(rom_path, o)
            test_word_padding(rom_path, o)
            test_pad_position(rom_path, o)

    test_readable_safe(rom_path)
    test_readable_roundtrip(rom_path)

    print()
    if FAIL:
        print(f"실패 {len(FAIL)}개: " + ", ".join(FAIL)); sys.exit(1)
    print("전부 통과")

# <EE> lo hi 는 같은 뱅크 안으로 뛰는 꼬리 점프다. 아래는 원본에서 **번역된
# 세그먼트의 중간**으로 뛰는 점프 전부다 (출처 <EE> 주소, 원본 착지점).
# 번역으로 착지점 앞이 짧아지면 같은 주소에 다른 바이트가 온다. 루큐 전투
# 명령 창(#60 -> #59 꼬리)이 그렇게 테두리를 잃었다.
EE_JUMPS = [
    (0x40ccc, 0x40c44), (0x40da9, 0x40c44), (0x40dc9, 0x40c4c), (0x40dd7, 0x40c4c),
    (0x40df5, 0x40c0d), (0x40e1a, 0x40c4c), (0x40e2a, 0x40de7), (0x40ec9, 0x40eae),
    (0x40f26, 0x41147), (0x40f40, 0x40ff4), (0x41026, 0x40fe5), (0x4119f, 0x41161),
    (0x41236, 0x411f9), (0x4125e, 0x418f8), (0x413b1, 0x41918), (0x413cf, 0x41918),
    (0x413e0, 0x413e7), (0x413f0, 0x40c0d), (0x413fe, 0x40c0d), (0x4141e, 0x40cc5),
    (0x415be, 0x40c0d), (0x415f4, 0x40c90), (0x4166e, 0x40c0d), (0x4171c, 0x40c0d),
    (0x418ea, 0x418d0), (0x41901, 0x40c44), (0x41937, 0x41918), (0x41952, 0x40c0d),
    (0x4195d, 0x41918), (0x419d3, 0x419b0), (0x419e3, 0x419b0), (0x419f4, 0x419b1),
    (0x41a08, 0x419b0), (0x41a6a, 0x41a37), (0x41a7b, 0x41a11), (0x41ca1, 0x41c95),
    (0x41d08, 0x40c0d), (0x4317c, 0x430a2), (0x431cf, 0x430a2), (0x43636, 0x4365e),
    (0x43970, 0x423d4), (0x449b4, 0x4494a), (0x459ad, 0x459df), (0x45f5a, 0x45f04),
    (0x4688d, 0x451c2), (0x4756b, 0x474d6), (0x49326, 0x49393), (0x4989a, 0x423d4),
    (0x4aa19, 0x4a8be), (0x4d55a, 0x444e6), (0x4d88b, 0x4d866), (0x4e492, 0x4e4b1),
    (0x4e4a3, 0x4e4b1), (0x4f0af, 0x4e0a9), (0x4f989, 0x4f95f), (0x4fd27, 0x41d0b),
    (0x4fd2c, 0x41d0b), (0x4fd31, 0x41d11), (0x4fd36, 0x41d11), (0x4fe55, 0x41d0b),
    (0x4fe75, 0x41d0b), (0x4fe95, 0x41d0b),
] + [(a, 0x4e0c6) for a in (   # 워프 목록 25개 -> #1077 「魔空城」 의 꼬리
    0x4e0e0, 0x4e0f6, 0x4e10c, 0x4e11d, 0x4e134, 0x4e149, 0x4e15a, 0x4e16c,
    0x4e17d, 0x4e190, 0x4e1a5, 0x4e1b8, 0x4e1cb, 0x4e1dc, 0x4e1ed, 0x4e200,
    0x4e211, 0x4e220, 0x4e233, 0x4efc8, 0x4efdf, 0x4eff4, 0x4f00a, 0x4f021,
    0x4f035)]
# 착지점이 문장 한가운데인 것 — 한국어에서 꼬리가 시작해야 하는 글자.
EE_TEXT_TAIL = {
    0x40c90: "못 씁니다！", 0x40cc5: "수 없습니다！", 0x40de7: "합니다<F1> 괜찮습니까？",
    0x40eae: "가<F1> 되었습니다", 0x41147: " 그만", 0x41161: "절 <F3>",
    0x413e7: "에서 해제할까요？", 0x418d0: " 의미가 없다", 0x418f8: "가 부족합니다！",
    0x41918: "\\n골라 주세요", 0x419b0: "Ｐ）이<F1>", 0x419b1: "）이<F1>",
    0x41c95: "얻었다！", 0x430a2: " 그 검을", 0x4365e: "←石<03>",
    0x444e6: " <EB><19> ５개", 0x474d6: " 여기서는 저를 믿고",
}

def _segments(rom_path):
    rows = [l.rstrip('\n').split('\t') for l in
            open("darkhalf-kr/script_main.tsv", encoding='utf-8').readlines()[1:]]
    return [(int(c[2], 16), int(c[3]), c[8] if len(c) > 8 else "") for c in rows]

def test_ee_jumps(rom_path, kr_path):
    import json, krcodec
    from dump import load_tbl
    tbl = load_tbl(os.path.join(os.path.dirname(os.path.abspath(__file__)), "darkhalf.tbl"))
    orig = open(rom_path, 'rb').read(); kr = open(kr_path, 'rb').read()
    codes = {k: bytes.fromhex(v) for k, v in
             json.load(open(kr_path + ".codes.json", encoding='utf-8')).items()}
    segs = _segments(rom_path)
    def seg(a): return next(s for s in segs if s[0] <= a < s[0] + s[1])
    print("[11] <EE> 꼬리 점프 — 번역된 세그먼트 안쪽 착지점")
    bad = []
    for src, t in EE_JUMPS:
        assert orig[src] == 0xEE and (0x040000 | orig[src+1] | orig[src+2] << 8) == t
        (sa, sl, _), (ta, tl, _) = seg(src), seg(t)
        # 출처 세그먼트 안에서 대상 세그먼트로 뛰는 <EE> 를 찾는다
        hits = [0x040000 | kr[i+1] | kr[i+2] << 8 for i in range(sa, sa + sl - 2)
                if kr[i] == 0xEE and ta < (0x040000 | kr[i+1] | kr[i+2] << 8) < ta + tl]
        if t in EE_TEXT_TAIL:
            want = krcodec.encode(EE_TEXT_TAIL[t], codes, tbl)
        else:
            want = orig[t:t+1]
        ok = hits and all(kr[h:h+len(want)] == want for h in hits)
        if not ok: bad.append((hex(src), hex(t), [hex(h) for h in hits]))
    check(f"점프 {len(EE_JUMPS)}개 착지점 일치", not bad, f"{len(bad)}개 예: {bad[:4]}")
    # 루큐 전투 명령 창: #60 의 끝 <EE> 가 #59 의 창 닫기 꼬리에 정확히 닿아야 한다
    tail = bytes.fromhex("ed2c0a0009f9070a0006fc0507dedf")
    hits = [0x040000 | kr[i+1] | kr[i+2] << 8 for i in range(0x041209, 0x041239)
            if kr[i] == 0xEE]
    check("루큐 전투 명령 창 닫기 꼬리", hits and kr[hits[-1]:hits[-1]+len(tail)] == tail,
          f"{[hex(h) for h in hits]} {kr[hits[-1]:hits[-1]+15].hex() if hits else ''}")
    # 꼬리 뒤에 남는 칸 공백이 오면 창이 닫힌 뒤 테두리 위에 그려진다
    check("창 닫기 꼬리 바로 뒤가 종료자", hits and kr[hits[-1]+len(tail)] == 0xFF,
          f"{kr[hits[-1]:hits[-1]+18].hex() if hits else ''}")

def test_pad_position(rom_path, kr_path):
    """남는 칸 공백은 한글(과 바로 뒤 문장부호) 뒤에만 끼운다.

    <E9>！者 의 ！ 는 문장부호가 아니라 명령 인자다. 그 앞뒤에 공백을 끼우자
    명령이 깨지고 者(=한글 「게」 자리)가 화면에 찍혔다 (마왕 정상 게).
    """
    import json, krcodec, eejump
    from dump import load_tbl
    tbl = load_tbl(os.path.join(os.path.dirname(os.path.abspath(__file__)), "darkhalf.tbl"))
    orig = open(rom_path, 'rb').read(); kr = open(kr_path, 'rb').read()
    codes = {k: bytes.fromhex(v) for k, v in
             json.load(open(kr_path + ".codes.json", encoding='utf-8')).items()}
    print("[13] 남는 칸 공백 위치 — 제어 인자 사이에 끼지 않는다")
    bad = []
    for a, L, tr in _segments(rom_path):
        if not tr.strip(): continue
        toks = krcodec.parse(tr)
        b, at, n = eejump.pad(a, L, tr, codes, tbl)
        if not n or b[at:at+n] == b"\xed\x24": continue
        off, prev = 0, []
        for k, v in toks:
            if off == at: break
            off += len(v if k == "raw" else krcodec.encode(v, codes, tbl)); prev.append((k, v))
        i = len(prev) - 1
        while i >= 0 and prev[i][0] == "ch" and not krcodec.is_hangul(prev[i][1]):
            i -= 1
        if i < 0 or prev[i][0] != "ch": bad.append((hex(a), tr[-30:]))
    check("공백은 한글 뒤에만", not bad, f"{len(bad)}개 예: {bad[:3]}")
    tail = bytes.fromhex("e9213ce937ff")
    check("#1077 꼬리 <E9>！者<E9>７ 보존", kr[0x4e0b7:0x4e0cc].endswith(tail),
          kr[0x4e0b7:0x4e0cc].hex())

def test_word_padding(rom_path, kr_path):
    """단어표의 남는 칸이 화면에 공백으로 찍히지 않아야 한다.

    한국어가 원문보다 짧아 남는 칸을 0x20 으로 채웠더니 「파르코⎵는」
    「마왕⎵⎵의」 처럼 단어마다 뒤에 공백이 붙었다. 렌더러가 따라 읽는 대로
    (<EE> 는 같은 뱅크로 점프) 되읽어 한국어 그대로인지 본다. 순차 주사
    루틴 때문에 0xFF 는 엔트리마다 하나, 원래 자리에만 있어야 한다.
    """
    import json, krcodec, words
    from dump import load_tbl, BANK_CH
    tbl = load_tbl(os.path.join(os.path.dirname(os.path.abspath(__file__)), "darkhalf.tbl"))
    orig = open(rom_path, 'rb').read(); kr = open(kr_path, 'rb').read()
    codes = {k: bytes.fromhex(v) for k, v in
             json.load(open(kr_path + ".codes.json", encoding='utf-8')).items()}
    print("[12] 단어표 — 남는 칸이 공백으로 찍히지 않는다")
    def follow(a):
        out = bytearray()
        for _ in range(64):
            b = kr[a]
            if b == 0xFF: return bytes(out)
            if b == 0xEE: a = (a & 0xFF0000) | kr[a+1] | kr[a+2] << 8; continue
            if b in BANK_CH: out += kr[a:a+2]; a += 2; continue   # 인덱스가 EE 일 수 있다
            out.append(b); a += 1
        return None
    pad, ff = [], []
    for k, ((a, cap), (ja, ko)) in enumerate(zip(words.slots(orig), words.WORDS)):
        if ko is None: continue
        want = krcodec.encode(ko, codes, tbl)
        if follow(a) != want: pad.append((k, ko, (follow(a) or b'').hex()))
        if kr[a:a+cap+1].count(0xFF) != 1 or kr[a+cap] != 0xFF: ff.append((k, ko))
    check("되읽은 단어 = 한국어 (남는 공백 없음)", not pad, f"{len(pad)}개 예: {pad[:3]}")
    check("0xFF 는 엔트리마다 하나, 원래 자리", not ff, f"{ff[:4]}")

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
        if c in krcodec.PREFIX_BYTES: continue   # 프리픽스는 맨바이트로 못 쓴다
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
