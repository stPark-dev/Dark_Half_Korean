#!/usr/bin/env python3
"""설정(옵션) 화면 텍스트 — 제자리 삽입.

## 어떻게 찾았나

설정 화면이 「면공가했ジ땠곧」 처럼 깨져 보였다. 그 18자를 `codes.json` 에서
찾아보니 **전부 대사 폰트에 배정된 글자**였다. 즉 이 화면은 대사 폰트를 쓰고,
우리가 한글로 회수한 가나 자리가 그대로 보이는 것이다 (4.1 의 원래 증상).

그래서 화면에 보이는 글자의 **코드로 롬을 검색**해 텍스트 위치를 찾았다.

    「면공가했」 = 92 6f 7e b0  ->  0x2ff706  (원본과 바이트 동일 = 미번역)

`0x2FF700`~`0x2FF748` 이다. §4.9 에서 이 구간(0x2FD32E~0x2FF780)을 「텍스트가
아니다」 라고 판단했는데 **틀렸다.** 일부가 텍스트다.

## 한글 글리프와 겹치지 않는다

이 구간은 F7 슬롯 `0xDC`~`0xDD` 이고, 배정 제외 구간(`0x3E`~`0xDD`) 안이다.
한글이 쓰는 상위 슬롯은 `0xDE`(`0x2FF780`) 부터다.

## 제자리다

문자열이 종료자 없이 빽빽하게 붙어 있다. `0x2FF706` 의 「メッセージ速度」 는
10바이트/7칸이고 바로 다음 `0x2FF710` 이 「遅い」 다. 종료자가 없으니 그리기
루틴이 길이를 따로 안다는 뜻이다 — 칸 수 고정이거나 바이트 수 고정이다.
어느 쪽인지는 정적으로 못 가른다.

그래서 **바이트 수를 정확히 맞추고** 남으면 공백(`0x20`)으로 채운다.

## 남는 공백이 칸을 늘리는 문제

공백도 1칸을 먹는다. 그래서 6개 필드가 원문보다 칸이 늘어난다.

    メッセージ速度 7칸 -> 메시지 속도 8칸 (8바이트 + 공백 2)
    移動方向      4칸 -> 이동방향   5칸 (6바이트 + 공백 1)
    右 下 上      1칸 -> 우 하 상   2칸 (1바이트 + 공백 1)
    サウンド      4칸 -> 사운드     5칸 (3바이트 + 공백 2)

**그래도 안전하다고 판단했다.** 늘어난 칸은 전부 **뒤쪽 공백**이다.

  - 칸 고정이면: 루틴이 앞에서 nc 칸만 읽는다. 내 글자가 앞에 있으니 그대로
    보이고, 읽는 바이트 수는 항상 예산 이하라 다음 필드를 침범하지 않는다.
  - 바이트 고정이면: 뒤에 빈 칸 하나가 더 그려진다. 공백은 안 보인다.

두 해석 모두 **화면에 보이는 모습이 같다.** 그래서 검사는 「글자가 칸에
들어가는가(`len(kr) <= nc`)」 와 「바이트가 예산에 들어가는가」 만 본다.

한 줄에 두 필드가 나란히 놓이는 곳(遅い/速い, ＯＮ/ＯＦＦ, ステレオ/モノラル)은
칸이 늘지 않도록 맞췄다. 좌우 배치가 밀릴 수 있는 곳만 엄격히 본 것이다.

## 못 쓴 말

  「빠름」 4바이트 > 3   -> 「빨리」 3바이트
  「스테레오」 5바이트 > 4 -> 「입체」 3바이트
  「모노랄」            -> 「모노」

「좌」 는 대사 폰트에 배정이 없었다. 이 파일의 텍스트를 `build.plan` 의 배정
입력에 넣어서 해결했다 (설명문·엔딩과 같은 방식). 그 결과 배정이 803 -> 804
음절로 늘었고 예산 초과는 0건이었다.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import krcodec

# (주소, 바이트 예산, 칸 수, 원문, 한국어)
#
# 미식별 한자를 렌더해 확정했다: F7 2F = 速, F7 30 = 遲, F7 31 = 左, F7 32 = 右.
# 화살표 십자 주위의 네 글자가 右·下·左·上 이다.
ITEMS = [
    (0x2ff706, 10, 7, "メッセージ速度", "메시지 속도"),
    (0x2ff710,  3, 2, "遅い",           "느림"),
    (0x2ff713,  3, 2, "速い",           "빨리"),     # 「빠름」은 4바이트로 넘친다
    (0x2ff716,  7, 4, "移動方向",        "이동방향"),
    (0x2ff71d,  2, 1, "右",             "우"),
    (0x2ff71f,  2, 1, "下",             "하"),
    (0x2ff721,  2, 1, "左",             "좌"),
    (0x2ff723,  2, 1, "上",             "상"),
    (0x2ff725,  9, 7, "魔法エフェクト",   "마법 효과"),
    (0x2ff734,  5, 4, "サウンド",        "사운드"),
    (0x2ff739,  4, 4, "ステレオ",        "스테레오"),
    (0x2ff73d,  4, 4, "モノラル",        "모노"),
]
# ＯＮ / ＯＦＦ / ＥＸＩＴ / ← → 는 그대로 둔다 (ASCII 와 화살표는 원본 글리프다)

# 「스테레오」의 「테」와 「모노」의 「노」는 이스케이프가 0개여야 하는 칸에
# 들어간다. 이스케이프를 줄이는 방법은 단일바이트 승격뿐이라 강제한다.
# 「스테레오」의 「테」와 「모노」의 「노」는 이스케이프가 0개여야 하는 칸에
# 들어간다. 이스케이프를 줄이는 방법은 단일바이트 승격뿐이라 강제한다.
#
# 그 밖의 음절은 **필요할 때만** 강제한다. 배정이 바뀌어 어떤 음절이
# 이스케이프로 밀리면 그 항목만 못 맞추게 되는데, 전부 미리 강제하면
# 단일바이트 30칸을 묶어 두게 되어 대사 초과가 50건 늘었다. build.plan 의
# 배정 반복이 `needs_force()` 로 부족한 것만 찾아 넣는다.
FORCE = {"테", "노"}

# 쌍둥이용으로 할당기에서 빼 둘 메뉴 안전 슬롯 수. 실제 필요분은 6이고
# 문구를 고칠 여유로 2를 더 뒀다. 배정 결과를 보고서야 필요분을 알 수 있으므로
# (단일바이트인지 이스케이프인지가 배정에 달렸다) 상수로 예약한다.
TWIN_RESERVE = 8


def needs_force(codes):
    """이 배정으로는 못 맞추는 항목의 음절들. 배정 반복이 이걸 force 에 넣는다.

    이 화면은 칸 = 바이트 - 이스케이프 이므로 이스케이프 개수가 원문과
    **정확히** 같아야 한다. 자연 이스케이프가 필요치보다 많으면 줄일 수단이
    단일바이트 승격뿐이다.
    """
    out = set()
    for _, nb, nc, _, kr in ITEMS:
        need = nb - nc
        nat = sum(_elen(c, codes) - 1 for c in kr if c in codes or c == " ")
        if nat > need:
            out |= {c for c in kr if c != " "}
    return out


def orig_cells(rom, addr, nb):
    """원본 바이트의 칸 수를 센다.

    `nc` 를 손으로 적었다가 한 번 틀렸다. 「メッセージ速度」를 8칸으로 셌는데
    7칸이었다 — `7c 01` 이 「シ + 탁음」이고 **탁음 바이트 0x01 은 칸을 늘리지
    않는다**. 그래서 상수를 믿지 않고 원본에서 세어 대조한다.
    """
    n = i = 0
    while i < nb:
        v = rom[addr + i]
        if v == 0x01: i += 1; continue          # 탁음 결합 — 칸 없음
        i += 2 if v in (0xF4, 0xF5, 0xF6, 0xF7, 0x5D, 0xD5) else 1
        n += 1
    return n


def check_nc(rom):
    """표에 적은 nc 가 원본과 맞는지 확인한다."""
    return [(hex(a), jp, nc, orig_cells(rom, a, nb))
            for a, nb, nc, jp, _ in ITEMS if orig_cells(rom, a, nb) != nc]


def _elen(ch, codes):
    """이 음절의 바이트 수. 공백은 0x20 한 바이트다."""
    return 1 if ch == " " else len(codes[ch])


def plan_item(kr, nb, nc, codes):
    """이 항목을 어떻게 인코딩할지 정한다.

    반환: (승격할 문자 인덱스 목록, 남는 공백 수)
    """
    need = nb - nc                     # 원문의 이스케이프 개수
    nat = sum(_elen(c, codes) - 1 for c in kr)
    cand = [i for i, c in enumerate(kr) if c != " " and _elen(c, codes) == 1]
    promote = need - nat
    if promote < 0:
        raise ValueError(f"「{kr}」 이스케이프 {nat}개 > 필요 {need}개 — 줄일 수 "
                         f"없다. 단일바이트 음절로 다시 쓰거나 FORCE 에 넣어라")
    if promote > len(cand):
        raise ValueError(f"「{kr}」 이스케이프 {nat}개 -> {need}개 로 올려야 "
                         f"하는데 올릴 수 있는 음절이 {len(cand)}개뿐이다")
    idx = cand[:promote]
    used = sum(_elen(c, codes) for c in kr) + promote
    pad = nb - used
    if pad < 0:
        raise ValueError(f"「{kr}」 {used}/{nb}바이트")
    if len(kr) + pad != nc:
        raise ValueError(f"「{kr}」 칸 {len(kr)+pad} != {nc}")
    return idx, pad


def twin_syllables(codes):
    """쌍둥이가 필요한 음절 (중복 없이, 나오는 순서)."""
    out = []
    for _, nb, nc, _, kr in ITEMS:
        idx, _ = plan_item(kr, nb, nc, codes)
        for i in idx:
            if kr[i] not in out: out.append(kr[i])
    return out


def twins(codes, reserved):
    """같은 글리프를 여분 이스케이프 슬롯에 하나 더 배정한다.

    「우」·「하」·「상」 은 단일바이트라 1바이트 1칸이다. 그런데 원문 「右」는
    2바이트 1칸이다. 칸을 맞추려면 **2바이트로 1칸**을 써야 하고, 그 방법은
    같은 글자를 이스케이프 슬롯에도 하나 더 두는 것뿐이다. 대사는 계속 싼
    단일바이트를 쓰고, 설정 화면만 쌍둥이를 쓴다.

    메뉴 안전 슬롯만 쓴다. 설정 화면 렌더러가 5D/D5(엔진 패치가 추가)를 아는지
    확인되지 않았고, 둘째 바이트가 0x20 미만이면 제어 코드로 읽힌다.
    """
    used = set(codes.values())
    free = [s for s in reserved if s not in used and krcodec.menu_safe(s)]
    need = twin_syllables(codes)
    if len(need) > len(free):
        raise ValueError(f"쌍둥이 {len(need)}개 필요, 여분 {len(free)}칸")
    return {ch: free[k] for k, ch in enumerate(need)}


def encode_item(kr, nb, nc, codes, twin):
    idx, pad = plan_item(kr, nb, nc, codes)
    out = bytearray()
    for i, c in enumerate(kr):
        if c == " ": out.append(0x20)
        elif i in idx: out += twin[c]
        else: out += codes[c]
    return bytes(out) + bytes([0x20]) * pad


def texts():
    return [kr for _, _, _, _, kr in ITEMS]


def pairs():
    """(용량, 한국어) — 예산 우선 배정용."""
    return [(nb, kr) for _, nb, _, _, kr in ITEMS]


def apply(rom, codes, tbl, reserved, verbose=False):
    bad = check_nc(rom)
    if bad: raise SystemExit(f"설정 화면 nc 값이 원본과 다르다: {bad}")
    twin = twins(codes, reserved)
    for addr, nb, nc, jp, kr in ITEMS:
        b = encode_item(kr, nb, nc, codes, twin)
        assert len(b) == nb, (addr, kr, len(b), nb)
        rom[addr:addr+nb] = b
    if verbose:
        print(f"설정 화면: {len(ITEMS)}항목 제자리 삽입 "
              f"(0x2ff706~0x2ff740, 쌍둥이 글리프 {len(twin)}자)")
    return []


def verify(new, orig, codes, tbl, reserved):
    twin = twins(codes, reserved)
    bad = [(a, jp, f"nc {nc} != 원본 {real}") for a, jp, nc, real in check_nc(orig)]
    for addr, nb, nc, jp, kr in ITEMS:
        want = encode_item(kr, nb, nc, codes, twin)
        if bytes(new[addr:addr+nb]) != want:
            bad.append((hex(addr), kr, new[addr:addr+nb].hex()))
    return bad


def written_range():
    return [(a, a + nb) for a, nb, _, _, _ in ITEMS]
