#!/usr/bin/env python3
"""삽입 결과 바이트 역검증.

제자리 삽입이므로 다음 5가지가 모두 성립해야 한다.
  1. 번역 세그먼트가 기대 바이트 + 공백 패딩과 일치
  2. 미번역 세그먼트는 원본과 완전 동일
  3. 폰트 영역에서 '배정된 슬롯만' 변경됨
  4. 그 슬롯의 내용이 실제 해당 한글 글리프
  5. 텍스트/폰트 영역과 체크섬 밖은 한 바이트도 안 바뀜

usage: verify_insert.py <orig.sfc> <new.sfc> <script.tsv>
       (코드 배정은 <new.sfc>.codes.json 에서 읽는다)
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import krcodec, makefont
from dump import load_tbl
from pipeline import FONT_BASE      # 폰트 주소 계산은 pipeline 한 곳에만 둔다

TBL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "darkhalf.tbl")
TEXT = (0x040C00, 0x050000)
FONT = (0x2F0000, 0x300000)

def slot_addr(s):
    return FONT_BASE[None] + s[0]*64 if len(s) == 1 else FONT_BASE[s[0]] + s[1]*64

def main(orig_p, new_p, tsv):
    orig = open(orig_p, 'rb').read(); new = open(new_p, 'rb').read()
    codes = {k: bytes.fromhex(v) for k, v in
             json.load(open(new_p + ".codes.json", encoding='utf-8')).items()}
    twins = {k: bytes.fromhex(v) for k, v in
             json.load(open(new_p + ".twins.json", encoding='utf-8')).items()}
    tbl = load_tbl(TBL)
    rows = [l.rstrip('\n').split('\t')
            for l in open(tsv, encoding='utf-8').readlines()[1:]]
    fail = 0

    ok = bad = 0
    for c in rows:
        a, L, tr = int(c[2], 16), int(c[3]), (c[8] if len(c) > 8 else "")
        if not tr.strip(): continue
        want = krcodec.encode(tr, codes, tbl); got = new[a:a+L]
        if got[:len(want)] == want and got[len(want):] == b'\x20'*(L-len(want)):
            ok += 1
        else:
            bad += 1
            if bad <= 5: print(f"  #{c[0]} 불일치\n    기대 {want.hex()}\n    실제 {got.hex()}")
    print(f"[1] 번역 세그먼트 바이트 일치 {ok}/{ok+bad}"); fail += bad

    # 이름표 문자열이 대사 뱅크 안에 있어 추출기가 대사 세그먼트로 잡는다
    # (마법 이름 0x04f3d3 = 세그먼트 #1295). 그 자리는 이름표가 정본이므로
    # '미번역 세그먼트 원본 보존' 검사에서 뺀다.
    import nametbl
    NAME_OWN = [(sp["data"], sp["limit"]) for sp, _ in nametbl.TABLES]
    def name_owned(a, n):
        return any(a < hi and a + n > lo for lo, hi in NAME_OWN)

    diff = sum(1 for c in rows
               if not (c[8] if len(c) > 8 else "").strip()
               and not name_owned(int(c[2],16), int(c[3]))
               and new[int(c[2],16):int(c[2],16)+int(c[3])]
                != orig[int(c[2],16):int(c[2],16)+int(c[3])])
    print(f"[2] 미번역 세그먼트 원본 보존: 차이 {diff}개"); fail += diff

    # 엔딩 텍스트는 폰트 영역 안(0x2FCFC0~0x2FF780)에 있다. 그 자리는 글리프가
    # 아니므로 폰트 슬롯 검사에서 제외한다 (PROGRESS 4.8).
    import patch_ending, patch_opt
    # 설정 화면 텍스트도 폰트 영역 안(F7 슬롯 0xDC~0xDD)에 있다. 글리프가
    # 아니므로 폰트 슬롯 검사에서 제외한다 (PROGRESS 4.17.13).
    ewr = patch_ending.written_range() + patch_opt.written_range()
    def in_ending(a):
        return any(lo <= a < hi or lo < a+64 <= hi for lo, hi in ewr)

    # 쌍둥이 슬롯도 글리프가 쓰인 자리다 (설정 화면 칸 맞춤용).
    want_addr = ({slot_addr(s) for s in codes.values()}
                 | {slot_addr(s) for s in twins.values()})
    # 엔진 패치를 켜면 인덱스 1024~ 가 뱅크 $F0 = ROM 0x300000 에 놓인다.
    # 롬이 4MB 로 늘어나므로 그 구간까지 훑어야 한다 (PROGRESS 1.2.2).
    hi_end = min(len(orig), len(new))
    scan_end = 0x308000 if len(new) > FONT[1] else FONT[1]
    changed = {a for a in range(FONT[0], scan_end, 64)
               if new[a:a+64] != (orig[a:a+64] if a < hi_end else b'\xff'*64)
               and not in_ending(a)}
    same = changed == want_addr
    print(f"[3] 폰트 변경 슬롯 {len(changed)}개 / 배정 {len(want_addr)}개  일치={same}")
    if not same:
        fail += 1
        extra = sorted(changed - want_addr)[:5]
        if extra: print(f"    배정 밖 변경: {[hex(x) for x in extra]}")

    mis = [ch for ch, s in list(codes.items()) + list(twins.items())
           if new[slot_addr(s):slot_addr(s)+64] != makefont.encode(ch)]
    print(f"[4] 글리프 내용 일치: 불일치 {len(mis)}개 {mis[:8]}"); fail += len(mis)

    # 단어표(<EB>xx) 구간. 포인터 표와 문자열, 그리고 짧아져 0xFF 로 지운 꼬리까지.
    import words, patch_words
    WORD_PTR = (words.PTR_TABLE, words.PTR_TABLE + 2*words.COUNT)
    WORD_STR = (words.DATA, words.DATA_LIMIT)

    # 설명문 구간. build.py 가 대사와 같은 배정으로 함께 넣는다.
    from patch_desc import find_runs, KO as DESC, PREFIX
    druns = find_runs(orig)
    DESC_R = [(druns[i][0] + PREFIX, druns[i][0] + druns[i][1]) for i in DESC]

    # 이름표(마법 등) 구간. 포인터 표와 문자열.
    import nametbl, patch_names
    NAME_R = []
    for spec, _ in nametbl.TABLES:
        NAME_R.append((spec["ptr"], spec["ptr"] + 2*spec["count"]))
        NAME_R.append((spec["data"], spec["limit"]))

    # 엔진 패치가 고치는 자리 (PROGRESS 1.2.2 / patch_engine.py).
    # 이스케이프 판별 두 곳, DMA 꼬리, 그리고 새 코드를 놓는 빈 공간.
    ENGINE_R = [(0x00950F, 0x00950F + 39), (0x005CFA, 0x005CFA + 37),
                (0x009548, 0x009548 + 63),
                (0x00F200, 0x00F240), (0x00F260, 0x00F2A0),
                (0x00F300, 0x00F360)]

    # 메뉴 폰트 블록 (4bpp 압축). 다시 압축하면 길이가 줄어서 블록 안쪽만
    # 바뀌지만, 어디까지 바뀔지는 블록 한도까지다.
    import patch_menu
    MENU_R = []
    for a in {addr for addr, _, _ in patch_menu.GLYPHS}:
        cap = patch_menu.block_limit(orig, a)
        MENU_R.append((a - 1, a - 1 + (cap or 0)))

    out = [i for i in range(len(orig)) if orig[i] != new[i]
           and not (TEXT[0] <= i < TEXT[1]) and not (FONT[0] <= i < FONT[1])
           and not (WORD_PTR[0] <= i < WORD_PTR[1])
           and not (WORD_STR[0] <= i < WORD_STR[1])
           and not any(a <= i < b for a, b in DESC_R)
           and not any(a <= i < b for a, b in NAME_R)
           and not (0xFFDC <= i <= 0xFFDF)
           and not any(a <= i < b for a, b in ENGINE_R)
           and not any(a <= i < b for a, b in MENU_R)]
    print(f"[5] 허용 영역 밖 변경 {len(out)}바이트"); fail += len(out)

    # 포인터를 실제로 따라가 되읽는다. 포인터와 문자열이 함께 옳아야 통과한다.
    wbad = patch_words.verify(new, orig, codes, tbl)
    print(f"[6] 단어표 제자리·포인터 무변경: 불일치 {len(wbad)}개"
          + (f" {[(hex(k), kr) for _, k, kr, _, _ in wbad[:4]]}" if wbad else ""))
    fail += len(wbad)

    ebad = patch_ending.verify(new, orig, codes, tbl)
    print(f"[8] 엔딩 제자리·포인터 무변경: 불일치 {len(ebad)}개"
          + (f" {[(sid, kr[:14]) for sid, kr, _, _ in ebad[:3]]}" if ebad else ""))
    fail += len(ebad)

    nbad = patch_names.verify(new, orig, codes, tbl)
    print(f"[7] 이름표 제자리·포인터 무변경: 불일치 {len(nbad)}개"
          + (f" {[(nm, hex(k), kr) for nm, k, kr, _, _ in nbad[:4]]}" if nbad else ""))
    fail += len(nbad)

    # 설명문·단어표 항목 (주소, 칸, 한국어). 대사 세그먼트만 보면 부족하다.
    import build as _b, words as _w
    DESC_ITEMS = _b.plan(orig, rows, tbl)[4]
    WORD_ITEMS = [(i, a, n, kr)
                  for i, ((a, n), (_, kr)) in enumerate(zip(_w.slots(orig),
                                                            _w.WORDS))
                  if kr]

    # [9] 메뉴·표 영역에 위험 이스케이프가 없어야 한다 (PROGRESS 4.12 / 4.15).
    #
    # F4 의 두 번째 바이트는 항상 제어 코드 값이다. F4 를 처리하지 않는 메뉴·표
    # 렌더러가 그 바이트를 제어 코드로 읽으면 게임이 멈춘다. #1222 「진형」이
    # f4 1f 로 들어가 메뉴에서 멈췄고, 이분 탐색으로 롬 다섯 개를 만들어 찾았다.
    #
    # 배정기가 no_f4 로 막지만, 막혔는지는 삽입된 바이트로 확인해야 한다.
    # 검사 대상은 배정 제약과 같은 기준이어야 한다 (build.plan 의 is_story).
    # 처음엔 0x04e000 이상만 봤는데, 시스템 메시지는 대사 뱅크 앞쪽에 몰려
    # 있고 설명문은 아예 빠져 있었다. 그래서 힐 설명문의 f6 03 / f5 1c 를
    # 못 잡았고, 힐을 선택하면 게임이 멈췄다.
    def is_story(txt):
        return "<FB>" in txt or "<F2>" in txt or txt.lstrip().startswith("「")

    targets = [(int(c[2], 16), int(c[3]), c[0], (c[8] if len(c) > 8 else ""))
               for c in rows
               if (c[8] if len(c) > 8 else "").strip()
               and not is_story(c[8])]
    targets += [(a, cap, f"설명문{a:#x}", txt) for a, cap, txt in DESC_ITEMS]
    targets += [(a, n, f"단어표[{i}]", kr) for i, a, n, kr in WORD_ITEMS]

    f4bad = []
    for a, n, sid, tr in targets:
        # 바이트를 단순 스캔하면 이스케이프의 '둘째' 바이트까지 잡는다
        # (F5 F4 를 F4 이스케이프로 오인). 렌더러와 같은 규칙으로 걷는다:
        # F4~F7·5D·D5 는 2바이트, 나머지는 1바이트.
        #
        # 그래도 제어 코드의 파라미터는 구분하지 못한다. 제어 코드마다 파라미터
        # 길이가 다르고 우리는 그 표를 갖고 있지 않다. #1187 「<FD>ゆ<F0>」 의
        # ゆ(0xD5)는 FD 의 파라미터인데 프리픽스로 오인됐다.
        #
        # 그래서 절대 개수가 아니라 원본과의 차이를 본다. 원본에 있던 것은
        # 게임이 그대로 돌던 것이므로 문제가 아니다. 우리가 새로 넣은 것만 잡는다.
        def risky(buf):
            r, i = [], 0
            while i < len(buf) - 1:
                if buf[i] in (0xF4, 0xF5, 0xF6, 0xF7, 0x5D, 0xD5):
                    if not krcodec.menu_safe(buf[i:i+2]):
                        r.append((hex(buf[i]), hex(buf[i+1])))
                    i += 2
                else: i += 1
            return r
        got, was = risky(new[a:a+n]), risky(orig[a:a+n])
        if len(got) > len(was):
            f4bad.append((sid, tr[:16], got))
    print(f"[9] 메뉴·표 영역 위험 이스케이프: {len(f4bad)}건"
          + (f" {f4bad[:4]}" if f4bad else ""))
    fail += len(f4bad)

    obad = patch_opt.verify(new, orig, codes, tbl, list(twins.values()))
    print(f"[10] 설정 화면 제자리: 불일치 {len(obad)}개"
          + (f" {obad[:3]}" if obad else ""))
    fail += len(obad)

    # 메뉴 폰트는 압축이라 바이트 비교가 안 된다. 풀어서 타일을 비교한다.
    import gfx, menufont
    mbad = []
    for addr, tile, ch in patch_menu.GLYPHS:
        buf = bytearray(gfx.unpack(bytes(new), addr))
        want = bytearray(0x400); menufont.put(want, tile, menufont.render(ch))
        idx = [tile*32 + k for k in range(32)] + [(tile+16)*32 + k for k in range(32)]
        if any(buf[i] != want[i] for i in idx if i < 0x400):
            mbad.append((hex(addr), tile, ch))
    print(f"[11] 메뉴 폰트 글리프 {len(patch_menu.GLYPHS)}개: 불일치 {len(mbad)}개"
          + (f" {mbad[:3]}" if mbad else ""))
    fail += len(mbad)

    print("\n" + ("전부 통과" if not fail else f"실패 {fail}건"))
    return 1 if fail else 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2], sys.argv[3]))
