#!/usr/bin/env python3
"""한글 코드 할당 및 인코딩.

원작이 '자주 쓰는 한자=1바이트, 드문 한자=2바이트'로 압축한 것과 같은 전략.
빈도 상위 음절을 단일바이트 코드에 배정해 평균 바이트/음절을 낮춘다.

회수 가능 코드 = 일본어 전용 글리프 자리 (가나 전체, 단일바이트 한자, 반각기호)
보존 코드     = 공백/숫자/문장부호/영문/제어
"""
import re, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 보존: 공백, ！, （）, 숫자, ？, A-Z, 。「」、‥
KEEP = {0x20, 0x21, 0x28, 0x29, 0x2E, 0x3F} | set(range(0x30, 0x3A)) \
     | set(range(0x41, 0x5B)) | {0xA1, 0xA2, 0xA3, 0xA4, 0xA5}
# 제어 코드 영역 (건드리지 않음)
CTRL = set(range(0x00, 0x20)) | set(range(0xE0, 0x100))

# 가나 글리프 (보존하면 미번역 텍스트와 메뉴가 정상 표시됨)
KANA = set(range(0x66, 0x70)) | set(range(0x71, 0x9E)) | set(range(0xA6, 0xDE))

def reclaimable():
    """한글에 배정할 수 있는 단일바이트 코드.
    DH_KEEP_KANA=1 이면 가나를 보존하고 한자/기호 슬롯만 회수한다."""
    import os
    skip = KEEP | CTRL | (KANA if os.environ.get("DH_KEEP_KANA") == "1" else set())
    return sorted(c for c in range(0x20, 0xE0) if c not in skip)

# 2바이트 이스케이프 뱅크. F7 은 0x00~0x3D 까지만 폰트 데이터이고
# 0x3E 이후에는 폰트가 아닌 다른 데이터가 있다 (글리프 렌더로 확인).
# 그 위를 덮으면 롬이 깨지므로 62슬롯으로 제한한다.
BANKS = [(0xF5, 256), (0xF6, 256), (0xF7, 62)]
BANK_TAG = {'A': 0xF5, 'B': 0xF6, 'C': 0xF7}

def capacity():
    return len(reclaimable()) + sum(n for _, n in BANKS)

# 제어 코드 범위의 한자 글리프. 판독문이 <魔> 형태로 내보내므로 되받는다.
CTRL_KANJI_REV = {'魔': 0x00, '士': 0x01, '見': 0x02, '入': 0x1F}

_TAG = re.compile(r"<([0-9A-Fa-f]{2})>|<([ABCabc])([0-9A-Fa-f]{2})>|<([魔士見入])>|\\n")

def parse(text):
    """번역문 -> 토큰열. ('ch', 문자) 또는 ('raw', bytes)"""
    out = []; i = 0
    while i < len(text):
        m = _TAG.match(text, i)
        if m:
            if m.group(0) == "\\n": out.append(("raw", bytes([0xE3])))
            elif m.group(1): out.append(("raw", bytes([int(m.group(1), 16)])))
            elif m.group(4): out.append(("raw", bytes([CTRL_KANJI_REV[m.group(4)]])))
            else:
                bank = BANK_TAG[m.group(2).upper()]
                out.append(("raw", bytes([bank, int(m.group(3), 16)])))
            i = m.end()
        else:
            out.append(("ch", text[i])); i += 1
    return out

def is_hangul(ch):
    return 0xAC00 <= ord(ch) <= 0xD7A3

def allocate(texts, base_table, priority=()):
    """번역문들에서 음절 빈도를 세어 코드 배정.
    priority 에 든 문자열의 음절은 단일바이트를 먼저 받는다.
    (메뉴 라벨처럼 예산이 3~8바이트로 빡빡한 곳을 우선 보장)
    반환: {문자: bytes}, 빈도, 통계"""
    freq = {}
    for t in texts:
        for kind, v in parse(t):
            if kind == "ch" and is_hangul(v): freq[v] = freq.get(v, 0) + 1
    pri = set()
    for t in priority:
        for kind, v in parse(t):
            if kind == "ch" and is_hangul(v): pri.add(v)
    ordered = sorted(freq, key=lambda c: (c not in pri, -freq[c]))
    single = reclaimable()
    if len(ordered) > capacity():
        raise SystemExit(f"고유 음절 {len(ordered)}자 > 수용량 {capacity()}자. "
                         f"어휘를 줄여 고유 음절 수를 낮춰야 합니다 "
                         f"(뱅크는 F5/F6/F7 이 전부이고 F7 은 62슬롯이 상한).")
    codes = {}; slots = []
    for c in single: slots.append(bytes([c]))
    for bank, n in BANKS:
        for i in range(n): slots.append(bytes([bank, i]))
    for ch, slot in zip(ordered, slots): codes[ch] = slot
    n1 = sum(freq[c] for c, s in codes.items() if len(s) == 1)
    n2 = sum(freq[c] for c, s in codes.items() if len(s) == 2)
    stats = {"unique": len(ordered), "capacity": capacity(),
             "single_slots": len(single), "occ1": n1, "occ2": n2,
             "avg_bytes": (n1 + 2*n2)/max(1, n1+n2)}
    return codes, freq, stats

# 번역자가 ASCII 문장부호를 써도 게임 테이블의 전각 글자로 자동 변환
ALIAS = {'!': '！', '?': '？', '(': '（', ')': '）', '.': '。', ',': '、',
         '"': '「', "'": '「', '…': '‥', '·': '・'}

def _kanji_rev():
    """한자 -> 뱅크 이스케이프. 판독문이 뱅크 한자를 글자로 보여주므로
    그 글자를 그대로 옮겨 적어도 원래 바이트로 되돌아가야 한다.
    같은 한자가 두 코드에 있으면 낮은 코드를 쓴다(글리프가 같아 표시는 동일)."""
    try:
        from kanji import KANJI
    except Exception:
        return {}
    rev = {}
    for (b, i), ch in sorted(KANJI.items()):
        rev.setdefault(ch, bytes([b, i]))
    return rev

_KREV = None
_REV = None

# 탁음은 반드시 '기본가나 + 0x01' 로 써야 한다.
# 완성형 탁음 슬롯(0xE6~, 0x06~0x1E)은 이 게임에서 제어 코드로 재활용되고 있어서,
# 역매핑이 고른 완성형 코드를 그대로 내보내면 텍스트가 아니라 제어 바이트가 박힌다.
from dump import DAKU
DAKU_REV = {v: k for k, v in DAKU.items()}

def encode(text, codes, base_table):
    """번역문 -> ROM 바이트열.

    같은 글리프가 단일바이트와 뱅크 양쪽에 있을 때는 단일바이트가 싸지만,
    그 코드가 제어 범위(0x00~0x1F, 0xE0~)에 있으면 본문 중간에서 제어
    바이트로 해석될 위험이 있다 (魔=0x00, 士=0x01, 見=0x02, 入=0x1F).
    그래서 제어 범위 코드는 역매핑에서 빼고 뱅크 이스케이프를 쓴다.
    제어 바이트로서 정말 필요하면 <魔> 같은 태그 표기로 쓴다.

    제외 기준은 디코더와 같은 집합(dump.CTRL = 0x00~0x1F, 0xE6~)을 쓴다.
    0xE0/0xE1(←→)은 실제 표시 글리프이므로 제외하지 않는다.
    여러 코드가 공유하는 글리프(★ 등)도 제외한다 — 디코더가 태그로 내보내므로
    판독문에 맨글자로 나올 일이 없고, 잘못된 코드를 고를 위험만 남는다.
    """
    global _KREV, _REV
    if _KREV is None: _KREV = _kanji_rev()
    if _REV is None:
        from dump import CTRL as DEC_CTRL, ambiguous
        skip = set(DEC_CTRL) | ambiguous(base_table)
        _REV = {}
        for code, g in base_table.items():
            if code in skip: continue
            _REV.setdefault(g, code)
    rev = _REV
    out = bytearray()
    for kind, v in parse(text):
        if kind == "raw": out += v
        elif is_hangul(v):
            if v not in codes: raise KeyError(f"미배정 음절 {v!r}")
            out += codes[v]
        else:
            if v in DAKU_REV:                   # 탁음 -> 기본가나 + 0x01
                base = DAKU_REV[v]
                if base in rev:
                    out.append(rev[base]); out.append(0x01); continue
            ch = v if v in rev else ALIAS.get(v)
            if ch is not None and ch in rev:
                out.append(rev[ch]); continue
            if v in _KREV:                      # 뱅크 한자 (판독문에서 옮겨온 것)
                out += _KREV[v]; continue
            raise KeyError(f"테이블에 없는 문자 {v!r}")
    return bytes(out)

if __name__ == "__main__":
    r = reclaimable()
    print(f"회수 가능 단일바이트 코드 {len(r)}개")
    print("  " + " ".join(f"{c:02X}" for c in r))
    print(f"\n2바이트 뱅크: F5 256 + F6 256 = 512")
    print(f"총 수용량: {capacity()}자")
