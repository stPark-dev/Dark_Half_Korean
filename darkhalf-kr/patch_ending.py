#!/usr/bin/env python3
"""엔딩 텍스트 한글화 — 조각을 원본 오프셋에 제자리 덮어쓴다.

## 왜 제자리인가

포인터 표가 4개뿐이라 재배치도 가능해 보이지만, 제자리로 하면 표를 아예
건드리지 않으므로 참조 문제가 원천적으로 없다. 이름표를 재배치했다가
메뉴에서 게임이 멈춘 사고(PROGRESS 4.5)를 되풀이하지 않는다.

각 조각은 원본 길이를 넘을 수 없다. 남는 자리는 공백(0x20)으로 채운다.
조각은 줄바꿈(0xF1)·페이지(0xFE) 직전에서 끝나므로 뒤쪽 공백은 보이지 않는다.

## 구조

  0x2FCFC0  포인터 표 4개 — 건드리지 않는다
  0x2FCFC8  본문 시작. 조각 오프셋은 이 지점 기준
  0x2FF780  본문 끝

자세한 근거는 PROGRESS 4.8 / ending.py 주석.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import krcodec, ending

TSV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "script_ending.tsv")


def load(tsv=None):
    """추출 TSV -> [(id, 오프셋, 원본길이, 판독문, 번역문)]"""
    path = tsv or TSV
    if not os.path.exists(path): return []
    out = []
    for line in open(path, encoding='utf-8'):
        if line.startswith('#'): continue
        c = line.rstrip('\n').split('\t')
        if len(c) < 7: continue
        out.append((c[0], int(c[1], 16), int(c[2]), c[5], c[6]))
    return out


def texts(tsv=None):
    """음절 배정에 넣어야 하는 한국어."""
    return [tr for _, _, _, _, tr in load(tsv) if tr.strip()]


def pairs(tsv=None):
    """(용량, 한국어) — 예산 우선 배정용."""
    return [(ln, tr) for _, _, ln, _, tr in load(tsv) if tr.strip()]


def apply(rom, codes, tbl, tsv=None, verbose=False):
    """제자리 덮어쓰기. 반환: 넘친 조각 목록(비어야 정상)."""
    over, n = [], 0
    for sid, off, ln, _, tr in load(tsv):
        if not tr.strip(): continue
        a = ending.BODY + off
        try:
            b = krcodec.encode(tr, codes, tbl)
        except KeyError as e:
            raise SystemExit(f"엔딩 #{sid} {tr!r} 인코딩 불가: {e}")
        if len(b) > ln:
            over.append((sid, tr, len(b), ln)); continue
        rom[a:a+ln] = b + bytes([0x20]) * (ln - len(b))
        n += 1
    if verbose and not over:
        print(f"엔딩: {n}조각 제자리 삽입 (포인터 표 {ending.BASE:#08x} 무변경)")
    return over


def verify(rom, orig, codes, tbl, tsv=None):
    """조각이 원본 오프셋에 옳게 있고 포인터 표가 그대로인지."""
    bad = []
    for sid, off, ln, _, tr in load(tsv):
        if not tr.strip(): continue
        a = ending.BODY + off
        want = krcodec.encode(tr, codes, tbl)
        got = bytes(rom[a:a+len(want)])
        if got != want: bad.append((sid, tr, got.hex(), want.hex()))
    n = 2 * ending.NPTR
    if bytes(rom[ending.BASE:ending.BASE+n]) != bytes(orig[ending.BASE:ending.BASE+n]):
        bad.append(("-", "포인터 표가 바뀌었다", "", ""))
    return bad


def written_range(tsv=None):
    """번역이 실제로 덮는 주소 구간들 (검증에서 폰트 검사 예외로 쓴다)."""
    r = []
    for _, off, ln, _, tr in load(tsv):
        if tr.strip(): r.append((ending.BODY + off, ending.BODY + off + ln))
    return r
