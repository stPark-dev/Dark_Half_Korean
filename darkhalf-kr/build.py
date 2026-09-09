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
import patch_opt
import patch_menu
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
             + words.pairs(orig) + nametbl.pairs(orig) + patch_ending.pairs()
             + patch_opt.pairs())

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
    # 메뉴·표 영역에 실리는 음절은 위험 프리픽스(F4·5D·D5)를 받으면 안 된다.
    # F4 는 둘째 바이트가 제어 코드 값이고(#1222 「진형」이 메뉴를 멈췄다),
    # 5D·D5 는 엔진 패치가 추가한 것이라 대사·옵션·엔딩 렌더러만 안다.
    # krcodec.RISKY_PREFIX 주석 참조.
    #
    # 무엇이 "메뉴·표에서 그려지는 글"인가.
    #
    # 처음엔 주소로 갈랐다(0x04e000 이상). 틀렸다. 시스템 메시지는 대사 뱅크
    # **앞쪽**에 몰려 있다 — #1 「괜찮습니까？」 #4 「장비 못 합니다！」
    # #8 「못 버린다！！」 #145 「〜을 버려도 괜찮습니까？」. 그리고 설명문을
    # 아예 빼먹어서, 힐을 선택하면(설명문 표시) 게임이 멈췄다.
    #
    # 기준을 뒤집었다. **이야기 대사가 아니면 메뉴로 본다.** 이야기 대사는
    # 이름표(<FB>)·초상화(<F2>)를 달거나 「 로 시작하고, 패치된 대사
    # 렌더러($950F)가 그린다. 그 밖은 전부 시스템·UI·표다.
    #
    #   이야기 대사 780개 / 그 밖 286개
    #   합집합 고유 음절 494자 / 메뉴 안전 슬롯 651칸 (여유 157칸)
    def is_story(txt):
        return "<FB>" in txt or "<F2>" in txt or txt.lstrip().startswith("「")

    menu_txt = ([txt for _, txt in dlg_addr if not is_story(txt)]
                + [txt for _, _, txt in desc_items]
                + list(words.texts()) + list(nametbl.texts())
                + list(patch_opt.texts()))
    no_risky = set()
    for txt in menu_txt:
        for kind, v in krcodec.parse(txt):
            if kind == "ch" and krcodec.is_hangul(v): no_risky.add(v)

    # 선택·명령 필드(<ED>出 … <ED>)의 음절은 반드시 단일바이트여야 한다.
    #
    # 이 필드는 바이트 하나를 타일 하나로 그린다. 이스케이프를 넣으면 두
    # 글리프로 갈라져 깨진다 (PROGRESS 4.15.3~4.16). 아이템 메뉴의
    # 「사용」「설명」, 전투 메뉴의 「마법 사용」이 그렇게 깨졌다.
    #
    # 칸 수도 원문과 맞춰야 한다. 단일바이트만 쓰면 칸 = 바이트이므로,
    # 원문 바이트 수를 맞추면 칸 수도 맞는다.
    import re as _re
    FIELD = _re.compile(r'<ED>出(.*?)<ED>')
    # 설정 화면은 칸 수를 정확히 맞춰야 해서 이스케이프 개수까지 지정된다.
    # 줄이는 수단은 단일바이트 승격뿐이다 (patch_opt.FORCE 주석 참조).
    force = {"호"} | patch_opt.FORCE
    for _, txt in dlg_addr:
        for f in FIELD.findall(txt):
            for kind, v in krcodec.parse(f):
                if kind == "ch" and krcodec.is_hangul(v): force.add(v)
    for _ in range(8):
        codes, freq, st = tralloc.allocate(pairs, t, force=force, no_risky=no_risky,
                                           reserve_safe=patch_opt.TWIN_RESERVE)
        probe = bytearray(orig)
        miss = ([kr for _, kr, _, _ in patch_words.apply(probe, codes, t)]
                + [kr for _, _, kr, _, _ in patch_names.apply(probe, codes, t)])
        if not miss: break
        for kr in miss:
            for kind, v in krcodec.parse(kr):
                if kind == "ch" and krcodec.is_hangul(v): force.add(v)
    return codes, freq, st, force, desc_items, dlg


def main(src, tsv, dst, engine=True):
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
    # 설정 화면 칸 맞춤용 쌍둥이 글리프 (같은 글자를 이스케이프 슬롯에도)
    opt_twin = patch_opt.twins(codes, st['reserved_safe'])
    pipeline.patch_font(rom, codes, extra=opt_twin.items())

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
    oover = patch_opt.apply(rom, codes, t, st['reserved_safe'], verbose=True)
    # 메뉴 폰트(4bpp 압축)는 대사 폰트와 별개 렌더러다. gfx.py 로 풀고 다시
    # 압축해 제자리에 넣는다 (PROGRESS 4.17).
    rom = bytearray(patch_menu.apply(rom, verbose=True))
    if oover:
        print(f"!! 설정 화면 초과/불가 {len(oover)}개")
        for a, kr, n, cap in oover: print(f"   {a:#08x} 「{kr}」: {n}/{cap}")
        raise SystemExit(1)
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
    # 쌍둥이는 같은 음절이 두 슬롯을 쓰므로 codes 에 못 담는다. 따로 적는다.
    json.dump({ch: sl.hex() for ch, sl in opt_twin.items()},
              open(dst + ".twins.json", "w"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    a = [x for x in sys.argv[1:] if not x.startswith("--")]
    main(a[0], a[1], a[2], engine="--no-engine" not in sys.argv)
