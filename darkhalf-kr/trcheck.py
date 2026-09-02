#!/usr/bin/env python3
"""번역 TSV 검사 — 삽입 전 관문.

제자리 삽입이므로 세그먼트별 바이트 예산이 엄격하고, 고유 음절 수에
전역 상한(719자)이 있다. 삽입을 시도하기 전에 이 둘을 먼저 본다.

usage:
  trcheck.py <script.tsv> [--worst N]
"""
import sys, os, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dump import load_tbl
import krcodec

TBL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "darkhalf.tbl")

def load(tsv):
    rows = []
    for line in open(tsv, encoding='utf-8'):
        if line.startswith('#'): continue
        c = line.rstrip('\n').split('\t')
        if len(c) >= 8: rows.append(c)
    return rows

def report(tsv, worst=12):
    rows = load(tsv)
    tbl = load_tbl(TBL)
    tr = [(int(c[0]), int(c[3]), c[8] if len(c) > 8 else "") for c in rows]
    done = [(i, cap, t) for i, cap, t in tr if t.strip()]
    print(f"세그먼트 {len(tr)}개 / 번역됨 {len(done)}개 ({len(done)/len(tr)*100:.1f}%)")
    if not done:
        print("번역된 세그먼트가 없습니다."); return 0

    texts = [t for _, _, t in done]
    try:
        codes, freq, st = krcodec.allocate(texts, tbl)
    except SystemExit as e:
        print(f"\n!! 배정 불가: {e}")
        uniq = {v for t in texts for k, v in krcodec.parse(t)
                if k == "ch" and krcodec.is_hangul(v)}
        print(f"   고유 음절 {len(uniq)}자 / 수용량 {krcodec.capacity()}자")
        return 1

    print(f"고유 음절 {st['unique']}자 / 수용량 {st['capacity']}자 "
          f"(여유 {st['capacity']-st['unique']}자)")
    print(f"  단일바이트 {st['single_slots']}자가 출현의"
          f" {st['occ1']/(st['occ1']+st['occ2'])*100:.0f}% 담당"
          f" -> 평균 {st['avg_bytes']:.2f} 바이트/음절")

    over, bad = [], []
    used = 0
    for i, cap, t in done:
        try:
            enc = krcodec.encode(t, codes, tbl)
        except KeyError as e:
            bad.append((i, str(e))); continue
        used += cap
        if len(enc) > cap: over.append((i, len(enc), cap, t))
    if bad:
        print(f"\n!! 인코딩 불가 세그먼트 {len(bad)}개")
        for i, m in bad[:worst]: print(f"   #{i}: {m}")
    if over:
        over.sort(key=lambda x: x[1]-x[2], reverse=True)
        print(f"\n!! 예산 초과 세그먼트 {len(over)}개 / {len(done)}개")
        for i, n, cap, t in over[:worst]:
            print(f"   #{i}: {n}바이트 필요 / {cap} 가능 (초과 {n-cap})  {t[:44]}")
    if not over and not bad:
        print(f"\n예산 검사 통과 — 초과 0개, 인코딩 불가 0개")

    # 음절 빈도 꼬리: 1~2회만 쓰인 음절은 예산을 갉아먹는 주범
    tail = sorted(c for c in freq if freq[c] <= 2)
    print(f"\n출현 1~2회 음절 {len(tail)}자 (인벤토리 압박 요인)")
    if tail: print("  " + "".join(tail[:80]))
    return 1 if (over or bad) else 0

if __name__ == "__main__":
    a = sys.argv[1:]
    w = 12
    if "--worst" in a:
        k = a.index("--worst"); w = int(a[k+1]); a = a[:k] + a[k+2:]
    sys.exit(report(a[0], w))
