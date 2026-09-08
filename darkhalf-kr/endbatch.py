#!/usr/bin/env python3
"""엔딩 번역 작업대 — script_ending.tsv 를 배치로 다룬다.

show  : 미번역 조각 목록과 조각별 예산
set   : JSON 으로 번역문 반영
stat  : 진행률
check : 예산·인코딩 검사 (build 와 같은 배정을 쓴다)
"""
import sys, os, json, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import patch_ending, krcodec
from dump import load_tbl

TSV = patch_ending.TSV
TBL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "darkhalf.tbl")
KANA = re.compile(r'[ぁ-んァ-ヶ]')


def rows():
    return [l.rstrip('\n').split('\t') for l in open(TSV, encoding='utf-8')]


def save(rs):
    with open(TSV, 'w', encoding='utf-8') as f:
        for r in rs: f.write("\t".join(r) + "\n")


def todo(rs):
    """번역할 조각 = 가나가 있고 아직 비어 있는 것."""
    return [r for r in rs[1:] if len(r) >= 7 and not r[6].strip()
            and KANA.search(r[5])]


def cmd_show(start, count):
    rs = rows(); t = todo(rs)
    print(f"미번역 조각 {len(t)}개 중 {start}~{start+count-1}\n")
    for c in t[start:start+count]:
        print(f"#{c[0]}  {c[2]}바이트  (끝 {c[3] or '-'})")
        print(f"  {c[5]}")
    print(f"\n(다음 시작 인덱스: {start+count})")


def cmd_set(jf):
    rs = rows()
    d = json.load(open(jf, encoding='utf-8'))
    idx = {r[0]: r for r in rs[1:] if r}
    n = 0
    for k, v in d.items():
        if k not in idx: raise SystemExit(f"없는 조각 {k}")
        idx[k][6] = v; n += 1
    save(rs)
    print(f"{n}개 반영 -> {TSV}")


def cmd_stat():
    rs = rows(); t = todo(rs)
    all_txt = [r for r in rs[1:] if len(r) >= 7 and KANA.search(r[5])]
    done = [r for r in all_txt if r[6].strip()]
    tb = sum(int(r[2]) for r in all_txt)
    db = sum(int(r[2]) for r in done)
    print(f"엔딩 텍스트 조각 {len(all_txt)}개 / {tb}바이트")
    print(f"  번역 완료 {len(done)}개 ({len(done)*100//max(1,len(all_txt))}%)"
          f" / {db}바이트 ({db*100//max(1,tb)}%)")


def cmd_check():
    """build 와 같은 배정으로 예산·인코딩을 본다."""
    import build, pipeline
    rom = open("Dark Half (Japan).sfc", 'rb').read()
    tbl = load_tbl(TBL)
    mrows = build.load_tsv("darkhalf-kr/script_main.tsv")
    codes, freq, st, force, _, _ = build.plan(rom, mrows, tbl)
    over = patch_ending.apply(bytearray(rom), codes, tbl)
    if over:
        print(f"!! 예산 초과 {len(over)}개")
        for sid, kr, n, cap in over[:12]:
            print(f"   #{sid}: {n}/{cap}바이트  {kr[:40]}")
    else:
        print("검사 통과 — 예산 초과 0, 인코딩 불가 0")
    return 1 if over else 0


if __name__ == "__main__":
    c = sys.argv[1]
    if   c == "show":  cmd_show(int(sys.argv[2]), int(sys.argv[3]))
    elif c == "set":   cmd_set(sys.argv[2])
    elif c == "stat":  cmd_stat()
    elif c == "check": sys.exit(cmd_check())
