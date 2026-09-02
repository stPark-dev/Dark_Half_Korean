#!/usr/bin/env python3
"""번역 배치 작업대.

usage:
  trbatch.py show <tsv> <start> <count>     미번역 일본어 세그먼트 나열 (예산 포함)
  trbatch.py set  <tsv> <json>              {id: 번역문} 반영
  trbatch.py stat <tsv>                     진행 통계
"""
import sys, os, json, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

KANA = re.compile(r'[ぁ-んァ-ヶ]')
JP = re.compile(r'[ぁ-んァ-ヶ一-鿿]')

# 최종 배정에서 상위 145자만 단일바이트를 받으므로 평균이 1.0 을 넘는다.
# 코퍼스가 커지면 1.3~1.4 로 수렴하니 보수적으로 잡아 재작업을 줄인다.
BYTES_PER_SYL = 1.4

def budget(readable, cap):
    """이 세그먼트에서 한글 텍스트가 쓸 수 있는 바이트와 대략 자수.

    제어 태그와 보존 문자(문장부호/숫자/영문)가 먹는 바이트를 빼고 남는 만큼이
    한글 몫이다. 일본어 구간이 먹던 바이트가 그대로 예산이 된다.
    """
    import krcodec
    from dump import load_tbl
    tbl = load_tbl(os.path.join(os.path.dirname(os.path.abspath(__file__)), "darkhalf.tbl"))
    keep = "".join(ch for kind, ch in
                   ((k, v if k == "ch" else None) for k, v in krcodec.parse(readable))
                   if kind == "ch" and ch and not JP.match(ch))
    raw_tags = sum(len(v) for k, v in krcodec.parse(readable) if k == "raw")
    try:
        keep_b = len(krcodec.encode(keep, {}, tbl))
    except KeyError:
        keep_b = len(keep)
    free = cap - raw_tags - keep_b
    return free, int(free / BYTES_PER_SYL)
HDR = "#id\trun\taddr\tlen\tptrs\torig_hex\torig_text\treadable\ttranslation\n"

def load(tsv):
    rows = []
    for line in open(tsv, encoding='utf-8'):
        if line.startswith('#'): continue
        c = line.rstrip('\n').split('\t')
        while len(c) < 9: c.append("")
        rows.append(c)
    return rows

def save(tsv, rows):
    with open(tsv, 'w', encoding='utf-8') as f:
        f.write(HDR)
        for c in rows: f.write("\t".join(c) + "\n")

def is_jp(c):
    return len(KANA.findall(c[7])) >= 2

RUN = re.compile(r'[ぁ-んァ-ヶ一-鿿]{4,}')   # 4자 이상 연속 = 산문

def todo(rows, prose_only=False):
    t = [c for c in rows if is_jp(c) and not c[8].strip()]
    if prose_only: t = [c for c in t if RUN.search(c[7])]
    return t

def cmd_show(tsv, start, count, prose_only=False):
    rows = load(tsv); t = todo(rows, prose_only)
    tag = "산문" if prose_only else "일본어"
    print(f"미번역 {tag} 세그먼트 {len(t)}개 중 {start}~{start+count-1}\n")
    for c in t[start:start+count]:
        free, syl = budget(c[7], int(c[3]))
        print(f"#{c[0]}  {c[3]}바이트  (한글 {free}바이트 ≈ {syl}자)")
        print(f"  {c[7]}")
    print(f"\n(다음 시작 인덱스: {start+count})")

def cmd_set(tsv, jf):
    rows = load(tsv)
    d = json.load(open(jf, encoding='utf-8'))
    idx = {c[0]: c for c in rows}
    n = 0
    for k, v in d.items():
        if k not in idx: raise SystemExit(f"없는 id {k}")
        idx[k][8] = v; n += 1
    save(tsv, rows)
    print(f"{n}개 반영 -> {tsv}")

def cmd_new(tsv, jf):
    """배치를 반영하기 전에 '새로 도입되는 음절'을 본다.

    고유 음절 상한(753)이 필요량(~1,600)보다 훨씬 작으므로, 새 음절 도입을
    의식적으로 억제해야 한다. 새 음절이 많으면 기존 음절로 바꿔 쓴다.
    """
    import krcodec
    rows = load(tsv)
    cur = set()
    for c in rows:
        for k, v in krcodec.parse(c[8]):
            if k == "ch" and krcodec.is_hangul(v): cur.add(v)
    d = json.load(open(jf, encoding='utf-8'))
    new = {}
    for seg, t in d.items():
        for k, v in krcodec.parse(t):
            if k == "ch" and krcodec.is_hangul(v) and v not in cur:
                new.setdefault(v, []).append(seg)
    print(f"현재 인벤토리 {len(cur)}자 -> 이 배치 반영 후 {len(cur)+len(new)}자")
    print(f"새 음절 {len(new)}자")
    if new:
        print("  " + "".join(sorted(new)))
        once = [v for v, segs in new.items() if len(segs) == 1]
        print(f"  이 중 1회만 쓰인 것 {len(once)}자: " + "".join(sorted(once)))

def cmd_stat(tsv):
    rows = load(tsv)
    jp = [c for c in rows if is_jp(c)]
    done = [c for c in jp if c[8].strip()]
    tb = sum(int(c[3]) for c in jp); db = sum(int(c[3]) for c in done)
    print(f"일본어 세그먼트 {len(jp)}개 / {tb}바이트")
    print(f"  번역 완료 {len(done)}개 ({len(done)/len(jp)*100:.1f}%) / {db}바이트 ({db/tb*100:.1f}%)")

if __name__ == "__main__":
    c = sys.argv[1]
    if   c == "show": cmd_show(sys.argv[2], int(sys.argv[3]), int(sys.argv[4]),
                               "--prose" in sys.argv)
    elif c == "set":  cmd_set(sys.argv[2], sys.argv[3])
    elif c == "new":  cmd_new(sys.argv[2], sys.argv[3])
    elif c == "stat": cmd_stat(sys.argv[2])
