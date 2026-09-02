#!/usr/bin/env python3
"""식별 워크시트를 배치 단위로 출력하고 결정을 기록한다.

usage:
  kanjibatch.py show <worksheet.json> <start> <count> [decided.json]
  kanjibatch.py wide <worksheet.json> <code> [decided.json]   후보 30개 전체
  kanjibatch.py stat <worksheet.json> [decided.json]
"""
import sys, json, re

def load(p):
    return json.load(open(p, encoding='utf-8'))

def trim(ctx, w=16):
    """【】 초점 주변만 잘라 표시 (판독에 필요한 만큼)"""
    i = ctx.find('【')
    if i < 0: return ctx[:2*w]
    j = ctx.find('】', i)
    return ctx[max(0, i-w):min(len(ctx), j+1+w)]

def cmd_show(wp, start, count, dp=None):
    ws = load(wp)
    dec = load(dp) if dp else {}
    keys = [k for k in ws if not ws[k]["known"] and k not in dec]
    print(f"미결정 {len(keys)}개 중 {start}~{start+count-1} 표시\n")
    for k in keys[start:start+count]:
        v = ws[k]
        print(f"{k}  n={v['n']}  후보: {' '.join(v['cand'][:8])}  ({v['score'][0]:.2f})")
        for c in v["ctx"][:3]:
            print(f"    {trim(c)}")
    print(f"\n(다음 시작 인덱스: {start+count})")

def cmd_wide(wp, code, dp=None):
    v = load(wp)[code]
    print(f"{code}  n={v['n']}")
    print("후보 30: " + ' '.join(f"{c}{s:.2f}" for c, s in zip(v['cand'], v['score'])))
    for c in v["ctx"]:
        print(f"    {trim(c, 24)}")

def cmd_stat(wp, dp=None):
    ws = load(wp); dec = load(dp) if dp else {}
    known = sum(1 for v in ws.values() if v["known"])
    print(f"전체 코드 {len(ws)}개 / 기존 식별 {known}개 / 이번 결정 {len(dec)}개")
    left = [k for k in ws if not ws[k]["known"] and k not in dec]
    print(f"미결정 {len(left)}개  (출현 5회 이상 {sum(1 for k in left if ws[k]['n']>=5)}개)")

if __name__ == "__main__":
    c = sys.argv[1]
    if   c == "show": cmd_show(sys.argv[2], int(sys.argv[3]), int(sys.argv[4]),
                               sys.argv[5] if len(sys.argv) > 5 else None)
    elif c == "wide": cmd_wide(sys.argv[2], sys.argv[3])
    elif c == "stat": cmd_stat(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
