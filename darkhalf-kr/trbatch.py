#!/usr/bin/env python3
"""번역 배치 작업대.

usage:
  trbatch.py show <tsv> <start> <count>     미번역 일본어 세그먼트 나열 (예산 포함)
  trbatch.py set  <tsv> <json>              {id: 번역문} 반영
  trbatch.py stat <tsv>                     진행 통계
"""
import sys, os, json, re

KANA = re.compile(r'[ぁ-んァ-ヶ]')
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

def todo(rows):
    return [c for c in rows if is_jp(c) and not c[8].strip()]

def cmd_show(tsv, start, count):
    rows = load(tsv); t = todo(rows)
    print(f"미번역 일본어 세그먼트 {len(t)}개 중 {start}~{start+count-1}\n")
    for c in t[start:start+count]:
        print(f"#{c[0]}  {c[3]}바이트")
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

def cmd_stat(tsv):
    rows = load(tsv)
    jp = [c for c in rows if is_jp(c)]
    done = [c for c in jp if c[8].strip()]
    tb = sum(int(c[3]) for c in jp); db = sum(int(c[3]) for c in done)
    print(f"일본어 세그먼트 {len(jp)}개 / {tb}바이트")
    print(f"  번역 완료 {len(done)}개 ({len(done)/len(jp)*100:.1f}%) / {db}바이트 ({db/tb*100:.1f}%)")

if __name__ == "__main__":
    c = sys.argv[1]
    if   c == "show": cmd_show(sys.argv[2], int(sys.argv[3]), int(sys.argv[4]))
    elif c == "set":  cmd_set(sys.argv[2], sys.argv[3])
    elif c == "stat": cmd_stat(sys.argv[2])
