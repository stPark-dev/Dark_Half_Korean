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

    diff = sum(1 for c in rows
               if not (c[8] if len(c) > 8 else "").strip()
               and new[int(c[2],16):int(c[2],16)+int(c[3])]
                != orig[int(c[2],16):int(c[2],16)+int(c[3])])
    print(f"[2] 미번역 세그먼트 원본 보존: 차이 {diff}개"); fail += diff

    want_addr = {slot_addr(s) for s in codes.values()}
    changed = {a for a in range(*FONT, 64) if new[a:a+64] != orig[a:a+64]}
    same = changed == want_addr
    print(f"[3] 폰트 변경 슬롯 {len(changed)}개 / 배정 {len(want_addr)}개  일치={same}")
    if not same:
        fail += 1
        extra = sorted(changed - want_addr)[:5]
        if extra: print(f"    배정 밖 변경: {[hex(x) for x in extra]}")

    mis = [ch for ch, s in codes.items()
           if new[slot_addr(s):slot_addr(s)+64] != makefont.encode(ch)]
    print(f"[4] 글리프 내용 일치: 불일치 {len(mis)}개 {mis[:8]}"); fail += len(mis)

    # 단어표(<EB>xx) 구간. 포인터 표와 문자열, 그리고 짧아져 0xFF 로 지운 꼬리까지.
    import words, patch_words
    WORD_PTR = (words.PTR_TABLE, words.PTR_TABLE + 2*words.COUNT)
    WORD_STR = (words.DATA, words.DATA_LIMIT)

    out = [i for i in range(len(orig)) if orig[i] != new[i]
           and not (TEXT[0] <= i < TEXT[1]) and not (FONT[0] <= i < FONT[1])
           and not (WORD_PTR[0] <= i < WORD_PTR[1])
           and not (WORD_STR[0] <= i < WORD_STR[1])
           and not (0xFFDC <= i <= 0xFFDF)]
    print(f"[5] 허용 영역 밖 변경 {len(out)}바이트"); fail += len(out)

    # 포인터를 실제로 따라가 되읽는다. 포인터와 문자열이 함께 옳아야 통과한다.
    wbad = patch_words.verify(new, codes, tbl)
    print(f"[6] 단어표 포인터 왕복: 불일치 {len(wbad)}개"
          + (f" {[(hex(k), kr) for k, kr, _, _ in wbad[:4]]}" if wbad else ""))
    fail += len(wbad)

    print("\n" + ("전부 통과" if not fail else f"실패 {fail}건"))
    return 1 if fail else 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2], sys.argv[3]))
