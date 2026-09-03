#!/usr/bin/env python3
"""번역 TSV 검사 — 삽입 전 관문.

제자리 삽입이므로 세그먼트별 바이트 예산이 엄격하고, 고유 음절 수에
전역 상한(719자)이 있다. 삽입을 시도하기 전에 이 둘을 먼저 본다.

usage:
  trcheck.py <script.tsv> [--worst N]
"""
import sys, os, re, collections
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

    import tralloc
    texts = [t for _, _, t in done]
    try:
        codes, freq, st = tralloc.allocate([(cap, t) for _, cap, t in done], tbl)
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

    # 일본어 잔존 검사.
    # 뱅크 한자와 가나는 인코딩이 정상 통과하므로 예산·인코딩 검사에 걸리지
    # 않는다. 한국어 문장 중간에 일본어가 박혀 나오는 것을 눈으로만 잡아야
    # 했는데(실제로 #472 의 守り 를 놓쳤다), 여기서 자동으로 잡는다.
    #
    # 어려운 점: 제어 바이트가 글리프로 렌더돼 판독문에 일본어처럼 보인다
    # (出 ミ 者 手 生 등). 그건 보존해야 하는 바이트라 누락이 아니다.
    # 구분 규칙: 제어 바이트는 <XX> 태그 바로 뒤에 붙고, 진짜 누락은
    # 한글에 붙어 있다. 그래서 '태그 직후가 아니고 한글에 인접한' 일본어만
    # 잡는다.
    JP_RUN = re.compile(r'[ぁ-んァ-ヶ一-鿿]+')
    HANGUL = re.compile(r'[가-힣]')
    leftover = []
    for i, cap, t in done:
        for m in JP_RUN.finditer(t):
            before = t[m.start()-1] if m.start() else ''
            after = t[m.end()] if m.end() < len(t) else ''
            if before == '>':            # 제어 바이트 (태그 직후)
                continue
            if not (HANGUL.match(before or ' ') or HANGUL.match(after or ' ')):
                continue                 # 한글에 인접하지 않으면 제어 골격으로 본다
            lo, hi = max(0, m.start()-12), min(len(t), m.end()+12)
            leftover.append((i, m.group(), t[lo:hi]))
    if leftover:
        print(f"\n!! 일본어가 남은 것으로 보이는 곳 {len(leftover)}건")
        for i, ch, ctx in leftover[:worst]:
            print(f"   #{i}: {ch}   …{ctx}…")

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
    if not over and not bad and not leftover:
        print(f"\n검사 통과 — 예산 초과 0, 인코딩 불가 0, 일본어 잔존 0")

    # 최종 인벤토리 외삽 — 상한 753자를 넘길지 진행 중에 알아야 한다.
    # Heaps 법칙 V = K*N^b. 번역이 진행될수록 b 가 내려가므로 추정은 보수적이다.
    import math
    KANA = re.compile(r'[ぁ-んァ-ヶ]')
    tot_syl = sum(freq.values())
    done_cap = sum(cap for _, cap, _ in done)
    left_cap = sum(int(c[3]) for c in rows
                   if len(KANA.findall(c[7])) >= 2 and not (c[8] if len(c) > 8 else "").strip())
    if tot_syl > 200 and done_cap:
        # 두 점 피팅 대신 (N, V) 한 점과 경험적 b=0.60 을 쓴다.
        # 초기 표본의 b(0.65)는 과대추정이고, 코퍼스가 커지면 0.55~0.60 으로 수렴한다.
        b = 0.60
        K = st['unique'] / (tot_syl ** b)
        est_N = int((done_cap + left_cap) * (tot_syl / done_cap))
        est_V = int(K * est_N ** b)
        print(f"\n최종 인벤토리 외삽: 전체 약 {est_N}음절 -> 고유 약 {est_V}자 "
              f"(상한 {st['capacity']})")
        if est_V > st['capacity']:
            print(f"  !! {est_V - st['capacity']}자 초과 예상. 새 음절 도입을 줄여야 한다.")
        else:
            print(f"  여유 {st['capacity'] - est_V}자")

    # 구간별 가드레일. Heaps 가 sublinear 이므로 초반에 더 많이 늘어나는 것이
    # 정상이다. 아래를 넘으면 후반에 벽을 만난다.
    prog = done_cap / max(1, done_cap + left_cap)
    cap = st['capacity']
    limit = int(cap * (0.52 + 0.48 * prog ** 1.6))
    mark = "OK" if st['unique'] <= limit else "초과"
    print(f"가드레일: 진행 {prog*100:.0f}% 시점 상한 {limit}자 / 현재 {st['unique']}자  [{mark}]")
    if st['unique'] > limit:
        print(f"  !! {st['unique']-limit}자 초과. 새 음절 도입을 억제하고 기존 음절로 바꿔 쓸 것.")

    # 음절 빈도 꼬리: 1~2회만 쓰인 음절은 인벤토리를 갉아먹는 주범
    tail = sorted(c for c in freq if freq[c] <= 2)
    print(f"출현 1~2회 음절 {len(tail)}자 (이 음절들을 기존 음절로 바꾸면 여유가 생긴다)")
    if tail: print("  " + "".join(tail[:80]))
    return 1 if (over or bad or leftover) else 0

if __name__ == "__main__":
    a = sys.argv[1:]
    w = 12
    if "--worst" in a:
        k = a.index("--worst"); w = int(a[k+1]); a = a[:k] + a[k+2:]
    sys.exit(report(a[0], w))
