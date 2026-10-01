#!/usr/bin/env python3
"""<EE> 꼬리 점프 재지정 — 번역된 세그먼트의 **중간**으로 뛰는 점프.

## 무엇이 깨졌나

`<EE> lo hi` 는 같은 뱅크 안의 `hi lo` 로 뛰는 꼬리 점프다. 원본은 이것으로
꼬리를 나눠 쓴다.

    #60 루큐 전투 명령   소울 사용 … 상대 안해 <EE>→0x0411f9
    #59 용사 전투 명령   공격하기 … 모두 도망 [0x0411f9: <ED>界 … 中物]  ← 창 닫기

삽입은 세그먼트 **시작**만 지킨다. #59 가 2바이트 짧아지자 창 닫기 꼬리가
0x0411f7 로 당겨졌고, 점프는 그대로 0x0411f9 — `<ED>界` 를 건너뛴 자리 —
에 착지했다. 루큐 전투에서 명령 창이 왼쪽으로 밀리고 테두리가 사라진
원인이다 (실기 확인). 같은 부류가 예/아니오 프롬프트, 아이템 메뉴, 능력치
상승 문구 등 대사 뱅크 전체에 있었다.

## 고치는 법

포인터는 출처 쪽 2바이트다. 번역된 대상 세그먼트 안에서 **원래 착지점에
해당하는 자리**를 찾아 포인터만 고쳐 쓴다.

- 착지점이 제어 코드면 자동이다. 번역은 제어 골격을 그대로 옮기므로 끝에서
  몇 번째 제어 코드인지로 대응점을 찾는다.
- 착지점이 문장 한가운데면 사람이 정한다 (TEXT_SPLIT). 한국어에서 꼬리가
  시작할 글자를 적고, 출처 쪽 번역은 그 꼬리와 이어 읽히게 쓴다.

정하지 않은 점프가 하나라도 있으면 빌드가 멈춘다.
"""
import os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import krcodec
from dump import DAKU, CTRL

# 이름표·목록 구간은 각자의 모듈(nametbl·montbl)이 <EE> 를 정본으로 다룬다.
OWNED = [(0x04f137, 0x04f470), (0x04f672, 0x04f8f9)]

# 앞 명령의 **인자**로 들어간 0xEE. 점프로 보면 착지점이 문맥에 안 맞는다.
NOT_JUMP = {
    0x04a830: "#732 <ED><EE> — <ED> 의 인자",
    0x04ed43: "#1166 <EF>Ｉ<00><1D><EE> — 착지점이 #364 문장 한가운데(무관한 대사)",
    0x04eda4: "#1166 <E9>輪<08><EE> — <E9> 의 인자",
}

# 원본 착지점 -> 한국어에서 꼬리가 시작하는 글자 (대상 세그먼트 번역에 한 번만
# 나와야 한다). 출처 번역은 이 꼬리와 이어 읽히게 쓴다.
TEXT_SPLIT = {
    0x040c90: "못 씁니다！",          # #7 여기서|못 씁니다      <- #101 몬스터에게는
    0x040cc5: "수 없습니다！",        # #9 가질 |수 없습니다      <- #73 개봉할
    0x040de7: "합니다<F1> 괜찮습니까？",  # #26 개봉|합니다     <- #28 봉석
    0x040eae: "가<F1> 되었습니다",    # #37 N |가 되었습니다      <- #38 N개
    0x041147: " 그만",                # #56 메뉴 끝 「그만」      <- #42
    0x041161: "절 <F3>",              # #57 강림|절 N일 (컷신과 같은 표기) <- #58 부활
    0x0413e7: "에서 해제할까요？",    # #71 종|에서 해제          <- #71 <동료>
    0x0418d0: " 의미가 없다",         # #140 써도| 의미가 없다    <- #141 외워도
    0x0418f8: "가 부족합니다！",      # #142 <소울파워>|가 부족   <- #62
    0x041918: "\\n골라 주세요",       # #143 만들지|\n골라 주세요 <- #70 #144 #146
    0x0419b0: "Ｐ）이<F1>",           # #149 （Ｈ|Ｐ）이          <- #150 #151 #153 （Ａ（Ｄ（Ｍ
    0x0419b1: "）이<F1>",             # #149 （ＨＰ|）이          <- #152 （ＤＸ
    0x041c95: "얻었다！",             # #170 …을\n|얻었다         <- #171
    0x0430a2: " 그 검을",             # #253 질문 반복 루프       <- #254
    0x04365e: "←石<03>",              # #273 승낙 뒤 경로         <- #273
    0x0444e6: " <EB><19> ５개",       # #337 …밑에서| <아이템> 5개 <- #998 침대 밑에서
    0x0474d6: " 여기서는 저를 믿고",  # #523 질문 반복 루프       <- #524
}

_TOK = re.compile(r'<[0-9A-Fa-f]{2}>|<[A-Za-z][0-9A-Fa-f]{2}>|<[^>]{1,3}>|\\n|.', re.S)
_HEX1 = re.compile(r'<([0-9A-Fa-f]{2})>')
_CK = {'魔': 0x00, '士': 0x01, '見': 0x02, '入': 0x1F}
# 제어 골격. 줄바꿈(E3)은 번역에서 다시 흘리고, ★(E2·E4·E5)은 원문 판독에서
# 글자로 보이므로 뺀다. 魔士見入(00·01·02·1F)는 제어 인자이기도 하고 본문
# 글리프이기도 해서(手に入れた 의 入) 번역에서 사라질 수 있으므로 뺀다.
SKEL = set(CTRL) - {0xE3, 0xE2, 0xE4, 0xE5, 0x00, 0x01, 0x02, 0x1F}


def _unskel_f4(toks, vi):
    """`<F4>xx` 는 2바이트 글리프(魔 등)다 — 둘 다 골격에서 뺀다.
    `<EB>xx` 의 xx 는 단어 번호다 — 판독문에 글자(入)로도 태그(<1F>)로도
    적히므로 골격에서 뺀다."""
    out = list(toks)
    def drop(i): out[i] = out[i][:vi] + (None,) + out[i][vi+1:]
    for i, x in enumerate(out):
        if x[vi] == 0xF4:
            drop(i)
            if i + 1 < len(out): drop(i + 1)
        elif x[vi] == 0xEB and i + 1 < len(out):
            drop(i + 1)
    return out


def orig_tokens(text):
    """원문 판독(orig_text) -> [(토큰, 바이트 수, 골격 값|None)]."""
    out = []
    for m in _TOK.finditer(text):
        s = m.group(); v = None
        h = _HEX1.fullmatch(s)
        if h: n = 1; v = int(h.group(1), 16)
        elif len(s) == 3 and s[0] == '<' and s[1] in _CK: n = 1; v = _CK[s[1]]
        elif s == '\\n': n = 1
        elif re.fullmatch(r'<[A-Za-z][0-9A-Fa-f]{2}>', s): n = 2
        elif s in DAKU.values(): n = 2
        else: n = 1
        out.append((s, n, v if v in SKEL else None))
    return _unskel_f4(out, 2)


def kr_tokens(text, codes, tbl):
    """번역문 -> [(바이트, 골격 값|None)] (encode 와 같은 순서·같은 바이트)."""
    out = []
    for kind, v in krcodec.parse(text):
        b = v if kind == "raw" else krcodec.encode(v, codes, tbl)
        out.append((b, b[0] if kind == "raw" and len(b) == 1 and b[0] in SKEL else None))
    return _unskel_f4(out, 1)


def _owned(a):
    return any(lo <= a < hi for lo, hi in OWNED)


def jumps(rows):
    """원본의 <EE> 점프 [(출처 주소, 원본 착지점, 출처 행, 대상 행, 대상 안 토큰 번호)]
    — 착지점이 번역된 세그먼트의 중간인 것만."""
    segs = [(int(c[2], 16), int(c[3]), c) for c in rows]
    starts = sorted(segs)
    import bisect
    keys = [s for s, _, _ in starts]
    def seg_of(a):
        i = bisect.bisect_right(keys, a) - 1
        if i >= 0 and starts[i][0] <= a < starts[i][0] + starts[i][1]: return starts[i]
    out = []
    for s, l, c in segs:
        T = orig_tokens(c[6]); off = 0
        if sum(n for _, n, _ in T) != l:
            raise SystemExit(f"eejump: #{c[0]} 원문 토큰 길이 불일치")
        for i, (x, n, v) in enumerate(T):
            if v == 0xEE and off + 3 <= l:
                a = s + off
                hdr = bytes.fromhex(c[5])[off:off+3]
                t = (s & 0xFF0000) | hdr[1] | (hdr[2] << 8)
                sg = seg_of(t)
                if (a not in NOT_JUMP and not _owned(t) and sg and sg[0] != t
                        and len(sg[2]) > 8 and sg[2][8].strip()):
                    tt = orig_tokens(sg[2][6]); o2 = 0
                    for j, (_, n2, _) in enumerate(tt):
                        if o2 == t - sg[0]: break
                        o2 += n2
                    else:
                        raise SystemExit(f"eejump: {t:#08x} 가 #{sg[2][0]} 토큰 경계가 아니다")
                    out.append((a, t, c, sg[2], j))
            off += n
    return out


def _kr_offset_of_target(t, trow, j, codes, tbl):
    """대상 세그먼트 번역 안에서 원본 착지점(토큰 j)에 해당하는 바이트 오프셋."""
    tr = trow[8]
    if t in TEXT_SPLIT:
        key = TEXT_SPLIT[t]
        if tr.count(key) != 1:
            raise SystemExit(f"eejump: {t:#08x} 꼬리 「{key}」 가 #{trow[0]} 번역에 "
                             f"{tr.count(key)}번 나온다 (한 번이어야 한다)")
        p = tr.index(key)
        head = krcodec.encode(tr[:p], codes, tbl)
        if head + krcodec.encode(tr[p:], codes, tbl) != krcodec.encode(tr, codes, tbl):
            raise SystemExit(f"eejump: {t:#08x} 꼬리 「{key}」 가 토큰 경계가 아니다")
        return len(head)
    ot = orig_tokens(trow[6])
    if ot[j][2] is None:
        raise SystemExit(f"eejump: {t:#08x} (#{trow[0]}) 착지점이 문장 가운데다 — "
                         f"TEXT_SPLIT 에 한국어 꼬리를 정해야 한다: {''.join(x for x, _, _ in ot[j:])[:40]!r}")
    os_ = [v for _, _, v in ot if v is not None]
    kt = kr_tokens(trow[8], codes, tbl)
    ks = [v for _, v in kt if v is not None]
    if os_ != ks:
        raise SystemExit(f"eejump: #{trow[0]} 제어 골격이 원문과 다르다")
    c = sum(1 for _, _, v in ot[j:] if v is not None)       # 끝에서 c 번째
    idx = [i for i, (_, v) in enumerate(kt) if v is not None][len(ks) - c]
    return sum(len(b) for b, _ in kt[:idx])


def _kr_offset_of_source(a, srow, codes, tbl):
    """출처 세그먼트 안에서 이 <EE> 의 바이트 오프셋 (미번역이면 원본 그대로)."""
    s = int(srow[2], 16)
    if not (len(srow) > 8 and srow[8].strip()): return a - s
    ot = orig_tokens(srow[6]); off = 0; k = 0
    for x, n, v in ot:
        if s + off == a: break
        if v == 0xEE: k += 1
        off += n
    kt = kr_tokens(srow[8], codes, tbl)
    ee = [i for i, (_, v) in enumerate(kt) if v == 0xEE]
    if len(ee) != sum(1 for _, _, v in ot if v == 0xEE):
        raise SystemExit(f"eejump: #{srow[0]} 번역의 <EE> 개수가 원문과 다르다")
    return sum(len(b) for b, _ in kt[:ee[k]])


class MenuGap(ValueError):
    pass


# 남는 칸에서 문장을 끝낼 글자 — 공백은 이 뒤에 둔다.
_TEXT_END = set("！？‥。」』…）")


def pad(addr, cap, text, codes, tbl):
    """번역 세그먼트를 칸에 맞춘 바이트와 (끼운 위치, 끼운 길이).

    남는 칸을 **끝에 공백으로 채우면 그 공백이 그려진다.** 용사·루큐 전투
    명령 창(#59)은 끝이 창 닫기(`FC 05 07` + 장식 글자 `de df`)인데, 그 뒤의
    공백 두 칸이 테두리 위에 찍혀 창 위·왼쪽 테두리가 사라졌다 (실기 확인).

      끝이 <EE> 점프      남는 칸에 도달하지 않는다 — 끝에 공백
      3바이트 이상 남음   <EE>→세그먼트 끝(종료자 또는 다음 세그먼트)으로 건너뛴다
      1~2바이트 남음      마지막 한글·문장부호 바로 뒤에 공백 (같은 줄의 빈칸)
    """
    toks = krcodec.parse(text)
    b = krcodec.encode(text, codes, tbl)
    gap = cap - len(b)
    if gap <= 0: return b, len(b), 0
    if len(toks) >= 3 and toks[-3] == ("raw", b"\xee"):
        return b + b"\x20" * gap, len(b), 0
    end = addr + cap
    if gap >= 3 and 0xFF not in (end & 0xFF, (end >> 8) & 0xFF):
        return b + bytes([0xEE, end & 0xFF, (end >> 8) & 0xFF]) + b"\x20" * (gap - 3), len(b), 0
    if "<ED>界" in text or "<E9>Ａ<03>" in text:
        # 메뉴 창(<ED>界 항목·<E9>Ａ 선택지)은 1~2칸을 공백으로 두면 어디든 창이
        # 깨진다. 창 닫기 뒤에 두면 테두리 위에 그려지고(루큐 전투), 항목 안에
        # 두면 항목이 넘친다(용사 전투). 항목을 줄여도 그 줄에 구멍이 난다.
        #
        # 원본 항목은 탁점(げ = け+01) 때문에 칸보다 바이트가 많다. 한글은 칸 =
        # 바이트라 2바이트가 모자라는 것이 보통이다. 마지막 <ED>出(글자 속성
        # 지정, 엔진 $911F) 을 한 번 더 넣어 메운다. 같은 값을 두 번 지정하는
        # 것이라 그려지는 것이 없다.
        if gap == 2:
            enc = _encoded(toks, codes, tbl)
            i = max((j for j in range(len(toks) - 1)
                     if toks[j] == ("raw", b"\xed") and toks[j+1] == ("ch", "出")),
                    default=None)
            if i is not None:
                at = sum(len(x) for x in enc[:i])
                return b[:at] + b"\xed\x24" + b[at:], at, 2
        if gap == 1 and "<ED>界" not in text:
            # 선택지 프롬프트(<E9>Ａ, #139 「돌리기/그만」)는 선택 필드의 칸 수가
            # 고정이고(trcheck [10]) 칸 없는 1바이트 채움이 없다. 이전 빌드와
            # 같이 선택 명령 뒤 맨 끝에 둔다.
            return b + b"\x20", len(b), 0
        raise MenuGap(f"{addr:#08x} 메뉴 창 번역이 {gap}바이트 남는다 "
                      f"(0 이거나 3 이상이어야 한다): {text[-40:]!r}")
    # 마지막 한글, 그리고 그 바로 뒤에 붙은 문장부호까지. 제어 코드 뒤의 ！
    # 같은 글자는 명령 인자다(<E9>！者) — 그 사이에 끼우면 명령이 깨진다.
    last = max((i for i, (k, v) in enumerate(toks)
                if k == "ch" and krcodec.is_hangul(v)), default=None)
    while last is not None and last + 1 < len(toks) \
            and toks[last+1][0] == "ch" and toks[last+1][1] in _TEXT_END:
        last += 1
    if last is None:
        return b + b"\x20" * gap, len(b), 0
    head = sum(len(x) for x in _encoded(toks[:last + 1], codes, tbl))
    return b[:head] + b"\x20" * gap + b[head:], head, gap


def _encoded(toks, codes, tbl):
    return [v if k == "raw" else krcodec.encode(v, codes, tbl) for k, v in toks]


def _shift(row, off, codes, tbl):
    """encode 기준 오프셋을 pad() 배치 기준으로."""
    if not (len(row) > 8 and row[8].strip()): return off
    _, at, n = pad(int(row[2], 16), int(row[3]), row[8], codes, tbl)
    return off + n if off >= at and n else off


def plan(rows, codes, tbl):
    """[(출처 <EE> 의 한글판 주소, 새 착지점, 원본 착지점)]"""
    out = []
    for a, t, srow, trow, j in jumps(rows):
        ts = int(trow[2], 16)
        nt = ts + _shift(trow, _kr_offset_of_target(t, trow, j, codes, tbl), codes, tbl)
        ns = int(srow[2], 16) + _shift(srow, _kr_offset_of_source(a, srow, codes, tbl), codes, tbl)
        if 0xFF in (nt & 0xFF, (nt >> 8) & 0xFF):
            raise SystemExit(f"eejump: {t:#08x} 새 착지점 {nt:#08x} 에 0xFF 가 섞인다")
        out.append((ns, nt, t))
    return out


def apply(rom, rows, codes, tbl, verbose=False):
    """대사를 넣은 뒤에 부른다. 포인터 2바이트만 고친다."""
    p = plan(rows, codes, tbl)
    for ns, nt, t in p:
        if rom[ns] != 0xEE:
            raise SystemExit(f"eejump: {ns:#08x} 가 <EE> 가 아니다 ({rom[ns]:02x})")
        rom[ns+1] = nt & 0xFF; rom[ns+2] = (nt >> 8) & 0xFF
    if verbose:
        moved = sum(1 for _, nt, t in p if nt != t)
        print(f"<EE> 꼬리 점프: {len(p)}개 확인, {moved}개 재지정 "
              f"(문장 꼬리 {len(TEXT_SPLIT)}곳은 TEXT_SPLIT)")
    return p
