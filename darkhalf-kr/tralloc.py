#!/usr/bin/env python3
"""번역문 코드 배정 — 빡빡한 세그먼트 우선.

세그먼트마다 제어 태그가 먹는 바이트가 달라서, 한글에 남는 예산이
4바이트뿐인 곳도 있고 40바이트인 곳도 있다. 빈도만으로 배정하면 빡빡한
세그먼트의 음절이 2바이트 뱅크로 밀려 예산을 넘긴다.

그래서 '예산 대비 필요 바이트' 비율이 나쁜 세그먼트를 먼저 priority 로
넘겨 단일바이트 코드를 확보한다. trcheck 와 pipeline insert 가 같은 결과를
내야 하므로 배정 로직을 이 모듈 한 곳에 둔다.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import krcodec

# 빡빡한 쪽 몇 %를 우선 배정 대상으로 볼지.
# 세그먼트 128개 시점 실측 (초과 개수 / 평균 바이트당 음절):
#   0.20 -> 2개 / 1.188    0.30 -> 0개 / 1.171    0.40 -> 0개 / 1.164
#   0.50 -> 1개 / 1.161    0.75 -> 1개 / 1.161    1.00 -> 1개 / 1.161
# 0.40 이 초과 0개를 유지하면서 평균도 가장 낮다. 코퍼스가 커지면 최적점이
# 이동할 수 있으므로 예산 초과가 잦아지면 다시 측정할 것.
TIGHT_FRACTION = 0.40

def _syl_and_fixed(text, tbl):
    """(한글 음절 수, 한글 외 바이트)"""
    syl = 0; fixed = 0
    for kind, v in krcodec.parse(text):
        if kind == "raw": fixed += len(v)
        elif krcodec.is_hangul(v): syl += 1
        else:
            try: fixed += len(krcodec.encode(v, {}, tbl))
            except KeyError: fixed += 1
    return syl, fixed

def allocate(pairs, tbl):
    """pairs: [(용량바이트, 번역문)]. 반환: krcodec.allocate 와 동일."""
    texts = [t for _, t in pairs]
    scored = []
    for cap, t in pairs:
        syl, fixed = _syl_and_fixed(t, tbl)
        if syl == 0: continue
        free = cap - fixed
        scored.append((free / syl, t))      # 음절당 쓸 수 있는 바이트. 작을수록 빡빡
    scored.sort(key=lambda x: x[0])
    n = max(1, int(len(scored) * TIGHT_FRACTION))
    priority = [t for _, t in scored[:n]]
    return krcodec.allocate(texts, tbl, priority=priority)

def tightest(pairs, tbl, n=10):
    """진단용: 음절당 예산이 가장 나쁜 세그먼트"""
    out = []
    for cap, t in pairs:
        syl, fixed = _syl_and_fixed(t, tbl)
        if syl: out.append((round((cap-fixed)/syl, 2), cap, cap-fixed, syl, t))
    out.sort()
    return out[:n]
