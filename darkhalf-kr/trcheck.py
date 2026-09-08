#!/usr/bin/env python3
"""번역 TSV 검사 — 삽입 전 관문.

제자리 삽입이므로 세그먼트별 바이트 예산이 엄격하고, 고유 음절 수에
전역 상한(719자)이 있다. 삽입을 시도하기 전에 이 둘을 먼저 본다.

usage:
  trcheck.py <script.tsv> [--worst N]
"""
import sys, os, re, collections
from collections import Counter

# 표 칸 크기는 원본 배치로만 계산할 수 있다
ROM_FOR_SLOTS = "Dark Half (Japan).sfc"
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
        # 배정은 build.plan 한 곳에서만 한다. 여기서 따로 배정하면 예측이
        # 실제 빌드와 갈린다 (실제로 trcheck 689자 / build 703자로 갈려
        # trcheck 만 초과를 보고했다).
        import build
        orig = open(ROM_FOR_SLOTS, 'rb').read()
        codes, freq, st, _force, _desc, _dlg = build.plan(orig, rows, tbl)
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

    # 장음 부호 검사.
    # 'ー'(0xB0) 는 가나 영역이라 회수 대상이고, 지금은 한글이 배정돼 있다.
    # 그런데 일본어 잔존 검사의 문자 범위(ぁ-ん ァ-ヶ 一-鿿)가 U+30FC 를
    # 포함하지 않아 그냥 통과했다. 실제로 내가 번역문에 「아ー」 를 써서
    # 화면에 「아람」 이 나오는 상태를 만들었다.
    #
    # 다만 원문 제어 골격에도 0xB0 이 파라미터로 들어 있다 (<EE>ー<19>,
    # <E9>輪ーＹ). 그것은 그려지지 않으므로 보존해야 한다.
    # 구분: 태그 직후('>')가 아니고, 한글이나 문장부호에 붙어 있으면 텍스트다.
    LONG = re.compile(r'[・-ヿ゙-ゟ]')
    PUNCT = '！？。‥」　'
    longbad = []
    for i, cap, t in done:
        for m in LONG.finditer(t):
            before = t[m.start()-1] if m.start() else ''
            after = t[m.end()] if m.end() < len(t) else ''
            if before == '>': continue                     # 제어 파라미터
            if not (HANGUL.match(before or ' ') or HANGUL.match(after or ' ')
                    or before in PUNCT or after in PUNCT):
                continue                                   # 제어 골격으로 본다
            lo, hi = max(0, m.start()-12), min(len(t), m.end()+12)
            longbad.append((i, m.group(), t[lo:hi]))
    if longbad:
        print(f"\n!! 장음 부호가 텍스트에 남았다 {len(longbad)}건"
              f" (0xB0 은 한글이 배정돼 있다)")
        for i, ch, ctx in longbad[:worst]:
            print(f"   #{i}: {ch!r}   …{ctx}…")

    # 표 구간 침범 검사.
    # 이름표·단어표 문자열이 대사 뱅크 안에 있어서 추출기가 그것까지 대사
    # 세그먼트로 잡는다 (마법 이름 0x04f3d3 = #1295 등). 그 자리를 대사로
    # 번역하면 표와 충돌한다. build 는 대사를 먼저 쓰고 표를 나중에 쓰므로
    # 표가 이기지만, 대사 쪽 길이와 종료자가 어긋나 역검증 [1] 이 깨진다.
    #
    # 실제로 배치 79 에서 마법 이름 7개를 대사로도 번역해 [1] 이 7건
    # 불일치였다. 표가 정본이므로 그 자리는 미번역으로 두어야 한다.
    # 배치 42 의 MENU 충돌과 같은 종류이고, 이번이 세 번째다.
    import nametbl, words
    OWNED = [(sp["data"], sp["limit"], sp["name"]) for sp, _ in nametbl.TABLES]
    OWNED.append((words.DATA, words.DATA_LIMIT, "단어표"))
    invade = []
    for c in rows:
        if len(c) < 9 or not c[8].strip(): continue
        a = int(c[2], 16)
        for lo, hi, nm in OWNED:
            if lo <= a < hi:
                invade.append((c[0], nm, c[8][:20])); break
    if invade:
        print(f"\n!! 표 구간을 대사로 번역했다 {len(invade)}건 (표가 정본이다)")
        for i, nm, t in invade[:worst]:
            print(f"   #{i}: {nm} 구간   {t}")

    # 단어표 뒤 조사 일치 검사.
    # <EB>xx 는 런타임에 단어를 끼워 넣으므로, 삽입되는 단어의 종성에 따라
    # 뒤 조사의 형태가 갈린다. 단어표를 해독하기 전에는 알 수 없어서
    # 「파티아을」 「소울파워이」 「마물가」 가 그대로 들어가 있었다.
    import wordfix
    jbad, jman = wordfix.scan([(i, t) for i, _, t in done], tbl)
    if jbad:
        print(f"\n!! 단어표 뒤 조사 불일치 {len(jbad)}건"
              f"  (wordfix.py --write 로 일괄 수정)")
        for sid, w, want, _, ctx in jbad[:worst]:
            print(f"   #{sid}: {w} -> {want}   …{ctx}…")
    if jman:
        print(f"\n?? 호격/계사 '아·야' 손판단 {len(jman)}건")
        for sid, w, alt, ctx in jman[:worst]:
            print(f"   #{sid}: {w}   …{ctx}…")

    # 한글 속 이스케이프 검사.
    # 원문 <F4><見>る 를 「보다」 로 옮길 때 <F4><見> 를 지우지 않으면
    # 「見다」 처럼 한국어 단어 안에 일본어 한자가 박힌다. 태그가 둘 다
    # 붙어 있어 고아 프리픽스 검사는 통과하고, 인코딩·예산도 통과한다.
    # 실제로 배치 65 시점에 30건이 쌓여 있었다 (발見했습니다, 성기士,
    # 병士여, <見>았느냐 등). 여러 배치에 걸쳐 누적된 것이다.
    #
    # 정당한 경우가 없다. 원문 제어 골격은 한글에 인접하지 않고,
    # 일본어를 일부러 남긴 자리도 한글에 붙지 않는다.
    EMBED = re.compile(r'<F[4-7]><[魔士見入]>|<F[4-7]><[0-9A-Fa-f]{2}>')
    embed = []
    for i, cap, t in done:
        for m in EMBED.finditer(t):
            before = t[m.start()-1] if m.start() else ''
            after = t[m.end()] if m.end() < len(t) else ''
            if not (HANGUL.match(before or ' ') or HANGUL.match(after or ' ')):
                continue
            lo, hi = max(0, m.start()-12), min(len(t), m.end()+10)
            embed.append((i, m.group(), t[lo:hi]))
    if embed:
        print(f"\n!! 한글 속에 일본어 이스케이프가 남았다 {len(embed)}건")
        for i, g, ctx in embed[:worst]:
            print(f"   #{i}: {g}   …{ctx}…")

    # 고아 프리픽스 검사.
    # 원문의 <F4><魔> 같은 이스케이프는 두 태그가 한 글리프를 이룬다.
    # 悪<F4><魔> 를 '악마' 로 옮길 때 <魔> 만 지우고 <F4> 를 남기면,
    # 인코더는 0xF4 를 그냥 내보내고 예산·인코딩 검사도 통과한다.
    # 그런데 렌더러는 0xF4 를 프리픽스로 보고 다음 바이트를 글리프
    # 인덱스로 먹으므로, 뒤 글자가 엉뚱한 글리프로 바뀌고 한 글자가 사라진다.
    # 바이트 역검증(verify_insert)도 인코더 출력과 ROM 을 비교할 뿐이라
    # 이 오류를 잡지 못한다. 실기에서만 드러나므로 여기서 막는다.
    # 태그 뒤에 태그가 오는 <F4><魔> 형태는 정상이므로 제외한다.
    # 예외: 세그먼트 맨 끝의 프리픽스는 정상일 수 있다.
    # 추출기의 0xFF 스캔이 이스케이프를 모르기 때문에, 원문에 「Fx FF」 형태의
    # 글리프 참조가 있으면 그 FF 를 메시지 종료자로 오인해 거기서 쪼갠다.
    # 그래서 원문 자체가 프리픽스로 끝나는 세그먼트가 17개 있다 (#364 #802 ...).
    # 그 자리에서 프리픽스를 지우면 뒤 FF 가 진짜 종료자가 되어 이어지는
    # 내용이 잘린다. 실제로 #364 에서 <F5> 를 지워 뒷부분을 잘라먹었다.
    # 원문이 같은 프리픽스로 끝나면 번역문 말미의 프리픽스를 허용한다.
    orig_last = {}
    for c in rows:
        if len(c) > 5 and c[5]:
            orig_last[int(c[0])] = int(c[5][-2:], 16)

    ORPHAN = re.compile(r'<(F4|F5|F6|F7|5D|D5)>(?!<)', re.I)
    orphan = []
    for i, cap, t in done:
        for m in ORPHAN.finditer(t):
            if m.end() == len(t) and orig_last.get(i) == int(m.group(1), 16):
                continue                      # 원문 구조 보존
            lo, hi = max(0, m.start()-10), min(len(t), m.end()+10)
            orphan.append((i, m.group(), t[lo:hi]))
    if orphan:
        print(f"\n!! 고아 프리픽스 {len(orphan)}건"
              f" (다음 글자를 글리프 인덱스로 먹는다)")
        for i, ch, ctx in orphan[:worst]:
            print(f"   #{i}: {ch}   …{ctx}…")

    # [9] 제어 코드 보존 — 메뉴 정지를 낸 결함이 이 부류였다.
    #
    # #1095 「<EB><15>の頂<EE>に←」 를 예산에 맞추려 「<EB><15>의 정상←」 으로
    # 줄이면서 <EE> 를 지웠다. 이동 목록(메뉴)에서 게임이 멈췄다. 다른 네
    # 항목에는 <EE> 를 남겼는데 이것만 빠졌다.
    #
    # 바이트 역검증([1])은 이걸 못 잡는다. 길이만 맞으면 통과하기 때문이다.
    # 고아 프리픽스 검사도 못 잡는다. 그건 F4~F7·5D·D5 만 본다.
    #
    # F4~F7 은 글리프 프리픽스라 한자를 한국어로 바꾸면 같이 사라지는 게
    # 맞으므로 제외한다. <EB> 는 단어표 참조라 넣고 빼는 게 번역 선택이므로
    # 제외한다. 나머지 E5~FE 는 개수가 보존돼야 한다.
    CTL = re.compile(r'<(E[5-9ACDEF]|F[0-3]|F[89ABCDE])>')
    orig_txt = {int(c[0]): c[7] for c in rows if len(c) > 7}
    ctlbad = []
    for i, cap, t in done:
        a = Counter(CTL.findall(orig_txt.get(i, "")))
        b = Counter(CTL.findall(t))
        lost, gain = a - b, b - a
        if lost or gain: ctlbad.append((i, dict(lost), dict(gain), t))
    if ctlbad:
        print(f"\n!! 제어 코드 불일치 {len(ctlbad)}건 (지우면 렌더러가 멈출 수 있다)")
        for i, lo, gi, t in ctlbad[:worst]:
            print(f"   #{i}: 잃음={lo} 얻음={gi}  {t[:44]}")

    # [10] 선택 항목(<ED>出 … <ED> )은 단일바이트 음절만 써야 한다.
    #
    # 이 필드는 바이트 하나를 타일 하나로 그린다. 이스케이프를 넣으면 두
    # 글리프로 갈라진다. 「예」(f5 3e)가 확인 창에서 깨진 글리프 두 개로
    # 나왔다 (image/problem_015.png). 「네」(0x9a)로 바꿔 해결했다.
    #
    # 같은 창의 「괜찮습니까？」 는 이스케이프를 써도 정상이다. 창이 아니라
    # 필드가 다르다.
    # 선택 필드는 **칸** 수가 고정이다. 원문보다 글자가 많으면 밀려서 잘리고
    # (탐침에서 「ＹＥＳ」의 Ｙ가 왼쪽으로 잘려 나갔다), 적으면 남은 칸에
    # 이전 타일이 남는다 (「네」 1칸을 3칸 필드에 넣어 2칸이 쓰레기가 됐다).
    #
    # 이스케이프는 2칸으로 갈라진다. 원문의 탁점 결합 부호(c4 01 = ど)는
    # 2바이트 1칸인데, 그것과 달리 F5~F7 이스케이프는 1칸으로 묶이지 않는다.
    # 그래서 선택 필드는 단일바이트만 쓰고, 칸 수를 원문과 맞춘다.
    CHOICE = re.compile(r'<ED>出(.*?)<ED> ')
    one = {c for c, v in codes.items() if len(v) == 1}
    orig_txt2 = {int(c[0]): c[7] for c in rows if len(c) > 7}

    def cells(field, single_only):
        """필드의 칸 수. 이스케이프는 2칸으로 센다."""
        n = 0
        for kind, v in krcodec.parse(field):
            if kind != "ch": continue          # 제어 코드는 칸을 차지하지 않는다
            n += 1 if (not krcodec.is_hangul(v) or v in single_only) else 2
        return n

    chbad = []
    for i, cap, t in done:
        got = CHOICE.findall(t)
        was = CHOICE.findall(orig_txt2.get(i, ""))
        if len(got) != len(was):
            chbad.append((i, f"필드 수 {len(was)} -> {len(got)}", "")); continue
        for g, w in zip(got, was):
            esc = [c for c in g if krcodec.is_hangul(c) and c not in one]
            if esc:
                chbad.append((i, g, f"이스케이프 {''.join(esc)}")); continue
            # 원문 칸 수는 판독문 글자 수로 센다 (탁점 결합 부호는 한 칸)
            wn = cells(w, one)
            gn = cells(g, one)
            if gn != wn:
                chbad.append((i, g, f"칸 {wn} -> {gn}"))
    if chbad:
        print(f"\n!! 선택 항목 {len(chbad)}건 (칸 수 고정 필드다)")
        for i, f, e in chbad[:worst]:
            print(f"   #{i}: |{f}|  {e}")

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
    if not (over or bad or leftover or orphan or jbad or longbad or embed
            or invade or ctlbad or chbad):
        print(f"\n검사 통과 — 예산 초과 0, 인코딩 불가 0, 일본어 잔존 0,"
              f" 고아 프리픽스 0, 조사 불일치 0, 장음 0, 한글속한자 0, 표침범 0,"
              f" 제어 코드 불일치 0, 선택항목 0")

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
    return 1 if (over or bad or leftover or orphan or jbad or longbad or embed or invade) else 0

if __name__ == "__main__":
    a = sys.argv[1:]
    w = 12
    if "--worst" in a:
        k = a.index("--worst"); w = int(a[k+1]); a = a[:k] + a[k+2:]
    sys.exit(report(a[0], w))
