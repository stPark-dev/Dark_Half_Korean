#!/usr/bin/env python3
"""한글 코드 할당 및 인코딩.

원작이 '자주 쓰는 한자=1바이트, 드문 한자=2바이트'로 압축한 것과 같은 전략.
빈도 상위 음절을 단일바이트 코드에 배정해 평균 바이트/음절을 낮춘다.

회수 가능 코드 = 일본어 전용 글리프 자리 (가나 전체, 단일바이트 한자, 반각기호)
보존 코드     = 공백/숫자/문장부호/영문/제어
"""
import re, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 보존: 공백, ！, （）, 숫자, ？, A-Z, ♥, 。「」、‥
#
# 0xA0(♥) 은 본문 문장부호가 아니라 UI 가 쓰는 표시 글리프다. 마법·아이템
# 목록의 커서 표시이고, 레코드 표 0x04f139 에도 각 레코드의 셋째 바이트로
# 박혀 있다. 회수했다가 「보」 가 배정되어 아이템 창에 「보힐」 로 나왔다
# (image/problem_005.png). ★ 과 화살표(0xE0-0xE5)를 보존하는 것과 같은 이유다.
#
# 0x2B(＋) 은 장비 강화 표시다. 아이템 이름표의 강화 변형이
# 「F0 C4 <포인터> 2B 31」 = 「이름＋１」 로 조립되고, 목록 창은 그 바이트를
# 타일 하나로 그린다. 회수했더니 「소검＋１」 이 「소검하１」 로 나왔다.
# 원본 판독문에서는 十 로 보이지만 글리프는 ＋ 다 (43곳).
KEEP = {0x20, 0x21, 0x28, 0x29, 0x2B, 0x2E, 0x3F} | set(range(0x30, 0x3A)) \
     | set(range(0x41, 0x5B)) | {0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5}
# 제어 코드 영역 (건드리지 않음)
CTRL = set(range(0x00, 0x20)) | set(range(0xE0, 0x100))

# 이스케이프 프리픽스로 쓰는 바이트. 단일바이트 글리프로 배정하면
# 렌더러가 프리픽스로 해석해 다음 바이트까지 먹는다.
PREFIX_BYTES = {0xF4, 0xF5, 0xF6, 0xF7, 0x5D, 0xD5}

# 가나 글리프 (보존하면 미번역 텍스트와 메뉴가 정상 표시됨)
KANA = set(range(0x66, 0x70)) | set(range(0x71, 0x9E)) | set(range(0xA6, 0xDE))

def reclaimable():
    """한글에 배정할 수 있는 단일바이트 코드.
    DH_KEEP_KANA=1 이면 가나를 보존하고 한자/기호 슬롯만 회수한다."""
    import os
    skip = KEEP | CTRL | PREFIX_BYTES | (KANA if os.environ.get("DH_KEEP_KANA") == "1" else set())
    return sorted(c for c in range(0x20, 0xE0) if c not in skip)

# 2바이트 이스케이프 뱅크.
# F5/F6 은 전 구간이 실제 글리프다. F7 은 구간별로 성질이 다르다.
#   0x00-0x3D  실제 글리프 62개        -> 전면 번역 시 회수 가능
#   0x3E-0xDD  정체 불명 데이터 160개  -> 덮으면 무엇이 깨지는지 미확인. 쓰지 않는다
#   0xDE-0xFF  0xFF 채움 34개          -> 미사용이므로 안전
# 자세한 근거는 PROGRESS.md 1.2.1 / 2.4.
# F4 는 인덱스 0~255 로, 단일바이트로는 쓸 수 없는 제어 범위 인덱스에 닿는다.
#   0x20-0xDF 는 단일바이트로 이미 쓰므로 F4 로 중복 배정하지 않는다.
#   0xE0-0xE5 는 화살표(←→)와 ★ 로 UI 에 쓰이므로 보존한다.
F4_SLOTS = list(range(0x00, 0x20)) + list(range(0xE6, 0x100))

# 엔진 패치로 추가한 프리픽스. 실기 검증 완료 (image/002.png).
# 렌더러의 이스케이프 판별($950F, $5CFA)을 확장해 $5D -> 인덱스 상위 4,
# $D5 -> 상위 5 로 넣고, DMA 뱅크를 $EF + ($6A>>2) 로 계산하게 했다.
# 인덱스 1024~1535 는 뱅크 $F0 = ROM 0x300000~0x307FC0 (4MB 확장분).
# 자세한 근거는 PROGRESS.md 1.2.2 / patch_engine.py.
PFX_NEW = {0x5D: 256, 0xD5: 256}

# 이스케이프의 둘째 바이트로 0xFF 를 쓰면 안 된다.
# 0xFF 는 문자열·메시지 종료자다. 단어표와 이름표는 0xFF 로 엔트리를 끊으므로
# 「컨」 이 F6 FF 를 받으면 판독이 첫 바이트에서 끊긴다.
# 실제로 마법 이름 [0x0B] 이 이 때문에 삽입 역검증 [7] 에서 걸렸다.
# 슬롯 6개(뱅크별 1개)를 잃는다. 수용량 1320 -> 1314.
_NO_FF = lambda xs: [i for i in xs if i != 0xFF]

# F4 는 배정에서 뺐다 (PROGRESS 4.13).
#
# F4 xx 는 글리프 xx 를 가리키고, F4_SLOTS 는 "바이트 값이 제어 코드와 겹쳐
# 단일바이트로 못 쓰는 글리프"다. 그런데 그 글리프들은 원본이 쓰고 있다.
#
#   0x00 魔  0x01 士  0x02 見  0x1F 入   원문 <F4><魔> 등 (CTRL_KANJI_REV)
#   0x04 ◀   0x05 ▶                      메뉴 화살표
#   0x06~0x1F ガギグゲゴ…                미번역 이름의 탁음 가나
#
# 여기에 한글을 배정하면 그 글리프가 덮인다. 실제로 57칸 전부 덮고 있었다.
# 게다가 F4 의 둘째 바이트는 항상 제어 코드 값이라, F4 를 처리하지 않는
# 메뉴·표 렌더러에서 게임이 멈춘다 (4.12, #1222 「진형」).
#
# 대신 엔진 패치의 5D/D5 를 쓴다. 수용량 1314 -> 1257 이고 필요량은 약 836 이다.
# CTRL_KANJI_REV 의 F4 인코딩은 그대로 둔다 — 원본 한자를 되돌리는 경로이고,
# 배정에서 빠졌으니 이제 그 글리프가 온전하다.
# UI 가 **직접 그리는** 뱅크 한자. 회수하면 안 된다.
#
# 필드의 이동 방향 표시가 東西南北 을 뱅크 한자로 직접 그린다. 이름표나 대사를
# 거치지 않으므로 no_risky·menu_safe 로는 막히지 않는다. 회수했더니 화면에
# 「형 조 숨 예」 가 나왔다 (image/동서남북.png, PROGRESS 4.31).
#
#   F5 4D = 東   F5 4E = 西   F5 4F = 南   F5 50 = 北
#
# 같은 종류가 더 있을 수 있다. 화면에서 한자가 한글로 바뀐 것이 보이면 그
# 글자의 코드를 되짚어 여기에 넣는다.
UI_KANJI = {(0xF5, c) for c in range(0x4D, 0x51)}

# 반각 폰트에는 한자가 없다 — 그 자리는 창 장식 그래픽이다.
#
# 목록 창은 8x8 반각 폰트(압축 그래픽 엔트리 0)를 쓴다. 반각에 한자를 넣을
# 수는 없으니, **단일바이트 한자 코드 31개의 8x8 칸은 다른 그림**이다.
# 원본 시트를 보면 창 테두리 레일(0x5B~0x65)·모서리 장식·게이지다.
#
# 타일맵으로 확인했다 (item2 덤프, 문자 베이스 0x200).
#
#   행14  0x229 0x22a 0x22b 0x22c    = 코드 29 2A 2B 2C   4x2 모서리 장식
#   행15  0x239 0x23a 0x23b 0x23c    = 코드 39 3A 3B 3C
#   행18  0x22f 0x22e 0x22d          = 코드 2F 2E 2D      3x2 (좌우 반전)
#   행19  0x23f 0x23e 0x23d          = 코드 3F 3E 3D
#
# 여기에 한글을 쓰면 창 귀퉁이에 글자가 나온다 — 0xDE(中)·0xDF(物) 이
# 「당」「전」을 받아 대화창 모서리에 「당전」이 떴다 (image/확인.png).
#
# 그런데 **대사 폰트(16x16)에서는 이 코드가 정상 글리프 자리**다. 그래서
# 회수 자체를 막을 필요는 없다. 나누면 된다.
#
#   대사에만 나오는 음절  -> 이 코드를 줘도 된다 (16x16 만 덮는다)
#   목록·필드에 나오는 음절 -> 주면 안 된다 (8x8 이 장식이라 못 덮는다)
#
# 그래서 (1) patch_hwfont 는 이 코드의 8x8 칸을 건드리지 않고,
# (2) allocate 는 단일바이트 풀에서 이 코드를 **맨 뒤로** 밀어 force 음절이
# 걸리지 않게 한다. force 는 「바이트 하나 = 타일 하나로 그려지는 자리」의
# 음절 집합이므로 그것만 피하면 된다.
def _hw_ui():
    """8x8 칸이 글자가 아닌 단일바이트 코드. 원문이 한자인 코드가 그것이다."""
    import os as _os, re as _re
    from dump import load_tbl
    tbl = load_tbl(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)),
                                 "darkhalf.tbl"))
    txt = _re.compile(r'[ぁ-んァ-ヶー・０-９Ａ-Ｚ0-9A-Z！？（）．。「」、‥ 　♥★←→]')
    out = set()
    for c in range(0x20, 0xE0):
        ch = tbl.get(bytes([c])) or tbl.get(c)
        if ch and not txt.match(ch): out.add(c)
    return out

HW_UI = None      # 첫 사용 때 채운다 (dump 를 import 하면 순환이 된다)


def hw_ui():
    global HW_UI
    if HW_UI is None: HW_UI = _hw_ui()
    return HW_UI

def _no_ui(bank, idxs):
    return [i for i in idxs if (bank, i) not in UI_KANJI]

BANK_SLOTS = {
    0xF5: _no_ui(0xF5, _NO_FF(range(0, 256))),
    0xF6: _NO_FF(range(0, 256)),
    0xF7: _NO_FF(list(range(0x00, 0x3E)) + list(range(0xDE, 0x100))),
    0x5D: _NO_FF(range(0, 256)),
    0xD5: _NO_FF(range(0, 256)),
}
BANKS = [(b, len(v)) for b, v in BANK_SLOTS.items()]

# 패치한 렌더러만 아는 프리픽스. 메뉴·표 렌더러는 모른다.
#
# F4 는 원본 렌더러가 처리하지만 F4_SLOTS 의 둘째 바이트가 제어 코드 값이라
# 위험하고, 지금은 배정 풀에서 빠져 있다. 5D/D5 는 엔진 패치가 추가한 것이라
# 대사·옵션·엔딩 렌더러만 안다 (patch_engine 이 $950F / $5CFA 두 곳을 고친다).
RISKY_PREFIX = {0xF4, 0x5D, 0xD5}

# 메뉴·표에 실을 수 있는 슬롯 (PROGRESS 4.15).
#
# 이스케이프의 둘째 바이트가 0x20 미만이면 메뉴·표 렌더러가 그것을 제어 코드로
# 읽는다. 실기에서 확인한 대조군:
#
#   괜 = f5 64   정상        찮 = f5 58   정상
#   예 = f5 1e   깨짐        힐 = f7 13   깨짐
#   진 = f4 1f   정지 (F4 프리픽스까지 겹치면 멈춘다)
#
# 원본 표가 F5~F7 을 쓰므로(몬스터 이름 14곳) 프리픽스 자체는 문제가 아니다.
# 둘째 바이트 값이 문제다.
#
# 안전 슬롯 수: 단일 142 + F5 223 + F6 223 + F7 63 = 651.
# 메뉴·표 고유 음절은 359자라 여유가 있다.
MENU_MIN_IDX = 0x20


def menu_safe(slot):
    """이 슬롯을 메뉴·표 문자열에 써도 되는가."""
    if len(slot) == 1: return True
    return slot[0] not in RISKY_PREFIX and slot[1] >= MENU_MIN_IDX
BANK_TAG = {'D': 0xF4, 'A': 0xF5, 'B': 0xF6, 'C': 0xF7, 'E': 0x5D, 'F': 0xD5}

def capacity():
    return len(reclaimable()) + sum(n for _, n in BANKS)

# 제어 코드 범위의 한자 글리프. 판독문이 <魔> 형태로 내보내므로 되받는다.
CTRL_KANJI_REV = {'魔': 0x00, '士': 0x01, '見': 0x02, '入': 0x1F}

_TAG = re.compile(r"<([0-9A-Fa-f]{2})>|<([A-Fa-f])([0-9A-Fa-f]{2})>|<([魔士見入])>|\\n")

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

def allocate(texts, base_table, priority=(), force=(), no_risky=(),
             reserve_safe=0):
    """번역문들에서 음절 빈도를 세어 코드 배정.
    priority 에 든 문자열의 음절은 단일바이트를 먼저 받는다.
    (메뉴 라벨처럼 예산이 3~8바이트로 빡빡한 곳을 우선 보장)

    force 는 음절 집합이고 priority 보다 앞선다. 단어표·이름표처럼 원본
    칸이 2~4바이트로 고정돼 모든 음절이 단일바이트여야만 들어가는 자리에
    쓴다. priority 만으로는 부족하다 — 우선 집합의 음절 수가 단일바이트
    칸(143)보다 많으면 그 안에서 다시 빈도순으로 밀리고, 표에 쓰는 음절은
    희귀해서 매번 밀린다.

    reserve_safe 는 배정에서 빼 둘 메뉴 안전 슬롯 수다. 설정 화면이 칸을
    맞추려면 「우」처럼 단일바이트인 음절을 **2바이트 1칸**으로도 써야 하는데
    (원문 「右」가 2바이트 1칸이다), 그러려면 같은 글리프를 이스케이프 슬롯에
    하나 더 둬야 한다. 안전 슬롯 651칸이 음절 804자에 전부 소진되므로 미리
    빼 두지 않으면 남는 칸이 없다. 빠진 슬롯은 stats["reserved_safe"] 로 돈다.

    반환: {문자: bytes}, 빈도, 통계"""
    freq = {}
    for t in texts:
        for kind, v in parse(t):
            if kind == "ch" and is_hangul(v): freq[v] = freq.get(v, 0) + 1
    pri = set()
    for t in priority:
        for kind, v in parse(t):
            if kind == "ch" and is_hangul(v): pri.add(v)
    fs = set(force)
    ordered = sorted(freq, key=lambda c: (c not in fs, c not in pri, -freq[c]))
    # 8x8 칸이 창 장식인 코드는 단일바이트 풀의 **맨 뒤**로 민다. ordered 는
    # force 가 앞이므로, 목록·필드에 실리는 음절은 이 코드를 받지 않는다.
    _ui = hw_ui()
    single = ([c for c in reclaimable() if c not in _ui]
              + [c for c in reclaimable() if c in _ui])
    if len(ordered) > capacity():
        raise SystemExit(f"고유 음절 {len(ordered)}자 > 수용량 {capacity()}자. "
                         f"어휘를 줄여 고유 음절 수를 낮춰야 합니다 "
                         f"(뱅크는 F5/F6/F7 이 전부이고 F7 은 62슬롯이 상한).")
    codes = {}; slots = []
    for c in single: slots.append(bytes([c]))
    for bank, idxs in BANK_SLOTS.items():
        for i in idxs: slots.append(bytes([bank, i]))

    # no_f4: 이 음절들에는 F4 이스케이프를 주지 않는다.
    #
    # F4 는 다른 뱅크와 성질이 다르다. F4 xx 는 글리프 xx 를 가리키는데,
    # 단일바이트로 쓸 수 있는 글리프는 단일바이트로 쓰므로 F4 는 "바이트 값이
    # 제어 코드와 겹쳐 단일바이트로 못 쓰는 글리프"에만 남는다. 즉 F4 의 두 번째
    # 바이트는 항상 제어 코드 값이다 (F4_SLOTS = 0x00~0x1F, 0xE6~0xFF).
    #
    # 대사 렌더러는 F4 를 처리한다 (원문도 <F4><魔> 로 魔 를 쓴다). 그러나
    # 메뉴 라벨·이름표 렌더러는 처리하지 않는다. 원본 표를 전수 확인한 결과:
    #
    #   라벨 표     F4 0개 / F5~F7 0개
    #   몬스터 이름  F4 0개 / F5~F7 14개
    #   화자 이름표  F4 0개 / F5~F7 0개
    #   아이템표     F4 1개 / F5~F7 1개
    #
    # F5~F7 은 쓰는데 F4 는 안 쓴다. 그래서 #1222 「진형」을 f4 1f f4 ef 로
    # 넣었더니 라벨 렌더러가 0x1F 를 제어 코드로 읽고 메뉴에서 멈췄다.
    #
    # 뱅크 이스케이프는 어느 뱅크든 2바이트라 재배치 비용이 0이다. 표 음절이
    # 건너뛴 F4 슬롯은 뒤의 대사 전용 음절이 받으므로 총 슬롯 소비도 같다
    # (5D/D5 로 흘러넘치지 않는다).
    nf = set(no_risky)
    safe  = [x for x in slots if     menu_safe(x)]
    risky = [x for x in slots if not menu_safe(x)]

    # 예약분은 뒤에서 뗀다. 안전 슬롯은 빈도순으로 앞에서 소진되므로 뒤쪽이
    # 가장 늦게 쓰이는 칸이다 (단일바이트는 앞쪽이라 예약에 걸리지 않는다).
    reserved = []
    if reserve_safe:
        if reserve_safe > len(safe):
            raise SystemExit(f"예약 {reserve_safe}칸 > 안전 슬롯 {len(safe)}칸")
        reserved = safe[len(safe)-reserve_safe:]
        safe = safe[:len(safe)-reserve_safe]

    # 뒤에 남은 no_risky 음절 수를 미리 세어 안전 슬롯을 그만큼 남겨 둔다.
    # 남겨 두지 않으면 희귀한 표 음절이 배정을 못 받는다 — 단어표 [07] 「에놋」
    # 의 「놋」 이 그렇게 걸렸다. 빈도순으로 안전 슬롯이 먼저 소진되고, 뒤에 온
    # 「놋」 은 남은 5D/D5 를 전부 건너뛰다가 빈손이 됐다.
    remain = [0] * (len(ordered) + 1)
    for i in range(len(ordered) - 1, -1, -1):
        remain[i] = remain[i + 1] + (1 if ordered[i] in nf else 0)

    si = ri = 0
    for i, ch in enumerate(ordered):
        if ch in nf or len(safe) - si > remain[i + 1]:
            if si >= len(safe):
                raise SystemExit(f"메뉴 안전 슬롯 부족: 메뉴·표 음절 {len(nf)}자 > "
                                 f"{len(safe)}칸. 표에 쓰는 어휘를 줄여야 합니다.")
            codes[ch] = safe[si]; si += 1
        else:
            if ri >= len(risky):
                raise SystemExit(f"슬롯 부족: 고유 음절 {len(ordered)}자.")
            codes[ch] = risky[ri]; ri += 1
    n1 = sum(freq[c] for c, s in codes.items() if len(s) == 1)
    n2 = sum(freq[c] for c, s in codes.items() if len(s) == 2)
    stats = {"unique": len(ordered), "capacity": capacity(),
             "single_slots": len(single), "occ1": n1, "occ2": n2,
             "avg_bytes": (n1 + 2*n2)/max(1, n1+n2),
             "reserved_safe": reserved}
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
        from dump import ambiguous
        # 맨바이트로 내보내면 안 되는 코드.
        #   0x00-0x1F : 0x00/0x01/0x02 는 결합 부호다. 렌더러($5D10)가 '다음'
        #               바이트를 보고 앞 글자의 인덱스를 보정하므로, 한자 뒤에
        #               맨 0x01 을 두면 앞 글자가 엉뚱한 글리프로 바뀐다.
        #               원문이 士를 F4 01 로 쓰는 이유다. 0x03-0x1F 도 같은 위험.
        #   0xE6-0xFF : 완성형 탁음 슬롯. 이 게임은 제어 코드로 재활용한다.
        # dump.CTRL 은 0x01 을 discard 하므로 그대로 쓰면 안 된다.
        skip = (set(range(0x00, 0x20)) | set(range(0xE6, 0x100))
                | PREFIX_BYTES | ambiguous(base_table))
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
            # 제어 범위에만 있는 글리프는 F4 이스케이프로 내보낸다 (★ ゾ ド 등)
            for code, g in sorted(base_table.items()):
                if g == v and code in CTRL:
                    out.append(0xF4); out.append(code); break
            else:
                raise KeyError(f"테이블에 없는 문자 {v!r}")
            continue
    return bytes(out)

if __name__ == "__main__":
    r = reclaimable()
    print(f"회수 가능 단일바이트 코드 {len(r)}개")
    print("  " + " ".join(f"{c:02X}" for c in r))
    print(f"\n2바이트 뱅크: F5 256 + F6 256 = 512")
    print(f"총 수용량: {capacity()}자")
