#!/usr/bin/env python3
"""통합 빌드 — 한 배정으로 대사·설명문·메뉴·단어표를 모두 넣는다.

## 왜 통합해야 하는가

pipeline insert 와 patch_all 이 각자 음절 배정을 하고 각자 폰트를 덮었다.
정책도 어긋났다. patch_all 은 DH_KEEP_KANA=1 (가나 보존, 단일바이트 33자),
pipeline 은 회수 (143자). 두 배정이 같은 폰트 영역을 쓰므로 나중에 돌린
쪽이 이기고, 먼저 돌린 쪽의 텍스트는 엉뚱한 글리프를 가리킨다.

그래서 배정은 한 번만 한다. 모든 한국어를 한자리에 모아 배정하고,
폰트를 한 번 덮고, 각 구간에 넣고, 체크섬을 마지막에 한 번 맞춘다.

## 가나 회수는 되돌릴 수 없다

가나 슬롯을 한글에 내주면 아직 일본어인 텍스트는 깨져 보인다.
보존하는 쪽은 재 봤더니 쓸 수 없었다. 단일바이트가 143 -> 33 자로 줄어
평균이 1.18 -> 1.50 바이트/음절이 되고, 번역한 535개 중 354개가 예산을
넘긴다 (최대 96바이트 초과). 그래서 회수를 유지한다.

남은 일본어가 깨져 보이는 것은 이 설계의 필연이고 전량 번역으로만
해소된다. 지금 깨져 보이는 것: 미번역 대사, 엔딩, 인물 이름표,
몬스터·아이템 이름표.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import krcodec, tralloc, words, patch_words, nametbl, patch_names, patch_ending, pipeline
from dump import load_tbl
from patch_desc import find_runs, KO as DESC, PREFIX

# patch_desc 계열이 import 시점에 DH_KEEP_KANA=1 을 설정할 수 있다. 통합
# 빌드는 회수 정책을 쓰므로 명시적으로 지운다 (krcodec 은 호출 시점에 읽는다).
os.environ.pop("DH_KEEP_KANA", None)

# 메뉴 라벨은 넣지 않는다. patch_all.MENU 13개는 전부 대사 세그먼트 안에
# 들어 있고 (예/아니오 -> #1, 시전 -> #44, 사용·버리기·설명 -> #48,
# 장비 -> #49, 전투 명령 -> #59·#60, 되돌림 -> #139) 그 세그먼트들은 이미
# TSV 에서 번역됐다. 따로 덮으면 TSV 번역을 잘라 먹는다. TSV 가 정본이다.

TBL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "darkhalf.tbl")


def load_tsv(tsv):
    rows = []
    for line in open(tsv, encoding='utf-8'):
        if line.startswith('#'): continue
        rows.append(line.rstrip('\n').split('\t'))
    return rows


def plan(orig, rows, t):
    """음절 배정을 한 번에 결정한다. build 와 trcheck 가 같이 쓴다.

    두 곳이 각자 배정하면 예산 초과 예측이 실제 빌드와 어긋난다. 실제로
    trcheck 가 689자, build 가 703자로 갈려 trcheck 만 초과를 보고했다.
    그래서 입력 구성과 force 반복을 여기 한 곳에 둔다.

    반환: (codes, freq, st, force, desc_items, dlg)
    """
    runs = find_runs(orig)
    desc_items = [(runs[i][0] + PREFIX, runs[i][1] - PREFIX, txt)
                  for i, txt in DESC.items()]
    dlg = [(int(c[3]), c[8]) for c in rows if len(c) > 8 and c[8].strip()]
    # (주소, 번역문) — 메뉴·표 구역 판별에 쓴다
    dlg_addr = [(int(c[2], 16), c[8]) for c in rows if len(c) > 8 and c[8].strip()]

    # 단어표·이름표는 원본 칸이 좁다 (腕輪 는 2바이트). extra 로 넘기면 우선
    # 배정을 못 받아 2바이트 코드가 걸리고 칸을 넘긴다. 용량과 함께 pairs 로
    # 넘겨 우선 배정 대상에 들어가게 한다.
    pairs = (dlg + [(cap, txt) for _, cap, txt in desc_items]
             + words.pairs(orig) + nametbl.pairs(orig) + patch_ending.pairs())

    # 표 항목이 원본 칸에 안 들어가면, 그 항목의 음절만 절대 우선으로 돌려
    # 다시 배정한다. 실패가 없어질 때까지 반복하므로 필요한 최소만 강제한다.
    # 표 전체 음절은 129자인데 단일바이트 칸이 142 뿐이라, 전부 강제하면
    # 대사 쪽에 남는 칸이 13개가 되어 예산이 무너진다.
    #
    # 엔딩은 이 반복에 넣지 않는다. 넣었더니 대사 예산 초과가 2개에서 72개로
    # 뛰었다. 엔딩 조각이 1바이트 넘치면 그 조각 음절 열 개가 전부 강제 배정을
    # 받는데, 1바이트를 아끼려 단일바이트 칸 열 개를 쓰는 거래다. 밀려난
    # 고빈도 음절은 대사 1000개에 걸쳐 비용을 낸다.
    #
    # 단어표·이름표는 칸이 고정이라(腕輪 는 2바이트) 강제가 유일한 수단이지만,
    # 엔딩 조각은 8~17바이트이고 가운데맞춤 공백까지 있어 고쳐 쓸 여지가 넓다.
    # 그래서 엔딩 초과는 endbatch check 로 드러내고 사람이 문장을 고친다.
    # 화자 이름표(0x04f8aa~)의 「호세」는 칸이 2바이트인데 「호」가 2바이트라
    # 3이 필요하다. tralloc 의 priority 는 free/syl 이 1.0 인 이 세그먼트를
    # 최우선으로 넣지만, 우선 대상 음절 수가 단일바이트 칸보다 많아 밀린다.
    # 같은 표의 다른 엔트리(노파·용병Ｅ·시체·분신)는 이미 한국어라, 하나만
    # 일본어로 남으면 화자 이름이 섞인다. 그래서 「호」만 명시로 강제한다.
    # 메뉴·표 영역에 실리는 음절은 F4 이스케이프를 받으면 안 된다.
    # 그 렌더러들은 F4 를 처리하지 않아 두 번째 바이트를 제어 코드로 읽는다
    # (krcodec.allocate 의 no_f4 주석 참조 — #1222 「진형」이 메뉴를 멈췄다).
    #
    # 경계를 0x04e000 으로 둔다. 정지를 실제로 낸 것은 0x04f000 이상의 표뿐이고
    # (이분 탐색 E 롬), 그 아래 0x04e000 대에는 일반 대사도 섞여 있다. 그래도
    # 넓게 막는 이유는 이동 목록이 거기 있기 때문이다 — E 롬은 이동 목록에 F4 가
    # 있는 채로 메뉴가 열렸지만(#1087 은 f4 13 까지 있다), 이동 목록은 메뉴를
    # 여는 것만으로는 그려지지 않는다. 그려질 때 멈출 수 있다.
    #
    # 넓게 막아도 비용이 없다. F4 슬롯 57칸은 0x04e000 아래 대사 음절이 그대로
    # 받으므로 5D/D5 로 넘치지 않는다 (확인: 단일 142 / F4 57 / F5 255 / F6 255
    # / F7 95, 5D·D5 0).
    menu_txt = [txt for cap, txt in dlg_addr if cap >= 0x04e000]
    no_f4 = set()
    for txt in menu_txt + list(words.texts()) + list(nametbl.texts()):
        for kind, v in krcodec.parse(txt):
            if kind == "ch" and krcodec.is_hangul(v): no_f4.add(v)

    force = {"호"}
    for _ in range(8):
        codes, freq, st = tralloc.allocate(pairs, t, force=force, no_f4=no_f4)
        probe = bytearray(orig)
        miss = ([kr for _, kr, _, _ in patch_words.apply(probe, codes, t)]
                + [kr for _, _, kr, _, _ in patch_names.apply(probe, codes, t)])
        if not miss: break
        for kr in miss:
            for kind, v in krcodec.parse(kr):
                if kind == "ch" and krcodec.is_hangul(v): force.add(v)
    return codes, freq, st, force, desc_items, dlg


def main(src, tsv, dst, engine=False):
    rom = bytearray(open(src, 'rb').read())
    orig = bytes(rom)          # 칸 계산은 원본 배치로만 해야 한다
    t = load_tbl(TBL)
    rows = load_tsv(tsv)
    segs = pipeline.segments(bytes(rom))[0]
    assert len(rows) == len(segs), f"행 수 불일치 {len(rows)} != {len(segs)}"

    # --- 1) 모든 한국어를 모아 한 번만 배정 ---
    codes, freq, st, force, desc_items, dlg = plan(orig, rows, t)
    if force:
        print(f"표 칸을 맞추려 절대 우선으로 돌린 음절 {len(force)}자: "
              f"{''.join(sorted(force))}")
    print(f"배정: 고유 음절 {st['unique']}/{st['capacity']}자 | "
          f"단일바이트 {st['single_slots']}자가 출현의"
          f" {st['occ1']/(st['occ1']+st['occ2'])*100:.0f}% | "
          f"평균 {st['avg_bytes']:.2f} 바이트/음절")

    hi = sorted(ch for ch, sl in codes.items()
                if len(sl) == 2 and sl[0] in (0x5D, 0xD5))
    if hi and not engine:
        print(f"!! 고유 음절이 엔진 패치 없는 상한(809자)을 넘었습니다.")
        print(f"   $5D/$D5 슬롯 {len(hi)}자: {''.join(hi[:20])}")
        print(f"   --engine 을 주십시오.")
        sys.exit(1)
    if engine:
        import patch_engine
        rom = patch_engine.patch(rom, verbose=False)
        print(f"엔진 패치 적용 (롬 {len(rom)}바이트)")

    # --- 2) 폰트 ---
    pipeline.patch_font(rom, codes)

    # --- 3) 각 구간 삽입. 전부 제자리(원본 길이)라 포인터를 건드리지 않는다 ---
    over = []

    def put(addr, cap, txt, tag):
        b = krcodec.encode(txt, codes, t)
        if len(b) > cap:
            over.append((tag, addr, len(b), cap, txt)); return
        rom[addr:addr+cap] = b + bytes([0x20]) * (cap - len(b))

    for c, sg in zip(rows, segs):
        tr = c[8] if len(c) > 8 else ""
        if tr.strip():
            put(sg["addr"], sg["len"], tr, f"대사 #{c[0]}")
        else:
            b = bytes.fromhex(c[5])
            rom[sg["addr"]:sg["addr"]+len(b)] = b
    for ad, cap, txt in desc_items: put(ad, cap, txt, "설명문")

    if over:
        print(f"!! 예산 초과 {len(over)}개")
        for tag, a, n, cap, x in over[:12]:
            print(f"   {tag} {a:#08x}: {n}/{cap}바이트 (초과 {n-cap})  {x[:40]}")
        sys.exit(1)

    # --- 4) 단어표·이름표는 대사 뒤에 쓴다 ---
    # 이름표 문자열이 대사 뱅크(0x040C00~0x050000) 안에 있어서, 추출기가
    # 그것까지 대사 세그먼트로 잡는다. 마법 이름 문자열 0x04f3d3 은
    # 세그먼트 #1295 다. 그 세그먼트는 미번역이므로 위에서 원본 바이트를
    # 되쓴다. 이름표를 먼저 쓰면 그 되쓰기에 덮인다.
    # 실제로 처음에는 이 순서 때문에 [7] 이 17건 전부 불일치였다.
    wover = patch_words.apply(rom, codes, t, verbose=True)
    nover = patch_names.apply(rom, codes, t, verbose=True)
    eover = patch_ending.apply(rom, codes, t, verbose=True)
    if eover:
        print(f"!! 엔딩 조각 초과 {len(eover)}개 (제자리라 늘릴 수 없다)")
        for sid, kr, n, cap in eover[:12]:
            print(f"   엔딩 #{sid} {kr[:30]!r}: {n}/{cap}바이트")
        sys.exit(1)
    if wover or nover:
        print(f"!! 표 칸 초과 {len(wover)+len(nover)}개 (제자리라 늘릴 수 없다)")
        for k, kr, n, cap in wover:
            print(f"   단어표 [{k:02X}] {kr!r}: {n}/{cap}바이트")
        for nm, k, kr, n, cap in nover:
            print(f"   {nm} [{k:02X}] {kr!r}: {n}/{cap}바이트")
        sys.exit(1)

    pipeline.fix_checksum(rom)
    open(dst, 'wb').write(rom)
    print(f"대사 {len(dlg)}개 + 설명문 {len(desc_items)}개"
          f" + 단어표 {words.COUNT}개 + 이름표 {len(nametbl.TABLES)}종"
          f" -> {dst} ({len(rom)}바이트)")

    import json
    json.dump({ch: sl.hex() for ch, sl in codes.items()},
              open(dst + ".codes.json", "w"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    a = [x for x in sys.argv[1:] if not x.startswith("--")]
    main(a[0], a[1], a[2], engine="--engine" in sys.argv)
