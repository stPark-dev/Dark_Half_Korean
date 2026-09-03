#!/usr/bin/env python3
"""단어표 뒤 조사 일치 검사·수정.

<EB>xx 는 런타임에 단어를 끼워 넣는다 (words.py). 한국어 조사는 앞
음절의 종성에 따라 형태가 갈리므로, 삽입되는 단어가 무엇인지 알아야
조사를 고를 수 있다. 단어표를 해독하기 전에는 알 수 없어서
「파티아을」 「소울파워이」 「마물가」 같은 것이 그대로 들어가 있었다.

받침 유무로 고른다. ㄹ 종성만 예외인 조사(로/으로)는 따로 처리한다.
"""
import os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import words
from dump import load_tbl

TBL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "darkhalf.tbl")

# (받침 있을 때, 받침 없을 때). 긴 형태를 먼저 둬야 짧은 쪽에 먼저 걸리지 않는다.
PAIRS = [("으로", "로"), ("이라", "라"), ("이나", "나"), ("이란", "란"),
         ("을", "를"), ("이", "가"), ("은", "는"), ("과", "와")]

# 자동으로 고치지 않는 것. 호격 '아/야' 와 계사 '이야/야' 가 형태를 공유해서
# 「카렌아」(부름) 와 「마왕이야」(서술) 를 규칙으로 가를 수 없다.
# 걸린 자리만 보고하고 사람이 판단한다.
MANUAL = [("아", "야"), ("이야", "야")]

_REF = re.compile(r'<EB>(?:<([0-9A-Fa-f]{2})>|(.))')


def _jong(ch):
    """종성 있음? (한글 음절만)"""
    if not ('가' <= ch <= '힣'): return None
    return (ord(ch) - 0xAC00) % 28 != 0


def _rieul(ch):
    return ('가' <= ch <= '힣') and (ord(ch) - 0xAC00) % 28 == 8


def _glyph_to_code(tbl):
    m = {}
    for c, g in tbl.items(): m.setdefault(g, c)
    return m


def scan(texts_by_id, tbl):
    """[(id, 잘못된 조사, 고친 조사, 위치, 문맥)]"""
    g2c = _glyph_to_code(tbl)
    out, manual = [], []
    for sid, t in texts_by_id:
        for m in _REF.finditer(t):
            b = int(m.group(1), 16) if m.group(1) else g2c.get(m.group(2))
            if b is None: continue
            k = b - 1
            if not (0 <= k < words.COUNT): continue
            kr = words.WORDS[k][1]
            if not kr: continue
            last = kr.rstrip()[-1:]
            has = _jong(last)
            if has is None: continue
            tail = t[m.end():]
            for withj, without in PAIRS:
                want = withj if has else without
                wrong = without if has else withj
                # '으로' 는 ㄹ 종성이면 '로' 를 쓴다
                if withj == "으로" and _rieul(last): want, wrong = "로", "으로"
                if not tail.startswith(wrong): continue
                # 조사 뒤에 한글이 바로 이어지면 조사가 아니라 낱말의 첫 글자다.
                # 「인간 가족」 의 '가' 를 '이' 로 바꾸는 오탐을 막는다.
                nxt = tail[len(wrong):len(wrong)+1]
                if '가' <= nxt <= '힣': break
                lo = max(0, m.start() - 12)
                out.append((sid, wrong, want, m.end(),
                            t[lo:m.start()] + f"【{kr}】" + tail[:12]))
                break
            else:
                for withj, without in MANUAL:
                    wrong = without if has else withj
                    if tail.startswith(wrong):
                        lo = max(0, m.start() - 12)
                        manual.append((sid, wrong, withj if has else without,
                                       t[lo:m.start()] + f"【{kr}】" + tail[:12]))
                        break
    return out, manual


def load(tsv):
    rows = [l.rstrip('\n').split('\t') for l in open(tsv, encoding='utf-8')]
    return rows, [(r[0], r[8]) for r in rows[1:] if len(r) > 8 and r[8].strip()]


def main(tsv, write=False):
    tbl = load_tbl(TBL)
    rows, pairs = load(tsv)
    bad, manual = scan(pairs, tbl)
    print(f"조사 불일치 {len(bad)}건")
    for sid, w, want, pos, ctx in bad:
        print(f"  #{sid:<5} {w} -> {want}   …{ctx}…")
    if manual:
        print(f"\n손으로 판단할 것 {len(manual)}건 (호격 '아/야' 와 계사 '이야/야')")
        for sid, w, alt, ctx in manual:
            print(f"  #{sid:<5} {w} (?-> {alt})   …{ctx}…")
    if write and bad:
        byid = {}
        for sid, w, want, pos, ctx in bad: byid.setdefault(sid, []).append((pos, w, want))
        for r in rows[1:]:
            if len(r) < 9 or r[0] not in byid: continue
            for pos, w, want in sorted(byid[r[0]], reverse=True):
                assert r[8][pos:pos+len(w)] == w, (r[0], pos, w)
                r[8] = r[8][:pos] + want + r[8][pos+len(w):]
        with open(tsv, 'w', encoding='utf-8') as f:
            for r in rows: f.write("\t".join(r) + "\n")
        print(f"{len(byid)}개 세그먼트 수정 -> {tsv}")
    return len(bad)


if __name__ == "__main__":
    sys.exit(0 if main(sys.argv[1], "--write" in sys.argv) == 0 else 1)
