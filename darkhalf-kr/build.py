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
import opening
import patch_hwfont
import cutscene
import crytbl
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

# 아이템·장비·마법 이름표가 있는 구간. 목록 창이 바이트 하나를 타일 하나로
# 그리는 곳이라, 여기 음절은 전부 단일바이트여야 한다 (PROGRESS 4.34·4.37).
#
# 시작을 0x04f1c0 으로 잡았던 것이 틀렸다. 그 앞에도 목록에 실리는 것이 있다 —
# 0x04f137~0x04f17e 는 마법 목록 18행(「♥<EE>포인터」)이고, 0x04f184 부터
# 카오스오브·매직오브·희망의 빛·에셀유품이 있고, 0x04f1a8·0x04f1b7 이
# **용사 쪽** 「컨디션」「진형」이다 (마왕 쪽은 0x04f45c·0x04f466 로 딴 벌이다).
# 용사 메뉴가 그대로 깨져 보인 이유였다 (image/확인.png).
LIST_TBL = (0x04f137, 0x04f470)

# 몬스터·화자 이름표. 여기도 타일 직접이다 (PROGRESS 4.39.2).
NAME_TBL = (0x04f672, 0x04f8f9)


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
             + patch_opt.pairs() + crytbl.pairs(orig))

    # 표 항목이 원본 칸에 안 들어가면, 그 항목의 음절만 절대 우선으로 돌려
    # 다시 배정한다. 실패가 없어질 때까지 반복하므로 필요한 최소만 강제한다.
    # 표 전체 음절은 129자인데 단일바이트 칸이 141 뿐이라, 전부 강제하면
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
    # 이름표가 소유한 구간은 **내용과 무관하게 메뉴 텍스트**다.
    #
    # 장비 이름 「홀리<EE>よ<F2>」 가 `<F2>` 때문에 이야기 대사로 분류돼
    # 메뉴 안전 제약에서 빠졌다. 거기서 `<F2>` 는 초상화가 아니라 <EE> 뒤에
    # 붙는 제어 바이트다. 그 결과 「홀」 이 `5d 43` (엔진 패치 전용 프리픽스)
    # 을 받았고, 그 이름을 그리는 아이템 창이 깨졌다 (PROGRESS 4.30).
    import trbatch
    OWNED = trbatch.table_owned()

    def is_story(addr, txt):
        if any(lo <= addr < hi for lo, hi in OWNED): return False
        return "<FB>" in txt or "<F2>" in txt or txt.lstrip().startswith("「")

    menu_txt = ([txt for ad, txt in dlg_addr if not is_story(ad, txt)]
                + [txt for _, _, txt in desc_items]
                + list(words.texts()) + list(nametbl.texts())
                + list(patch_opt.texts()) + list(crytbl.texts()))
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
    # 필드는 세그먼트 경계를 넘는다. #59 의 마지막 <ED>出 이 연 필드의 본문이
    # #60 의 선두 「소울 사용  」 이다. 선두를 빼먹으면 그 칸만 이스케이프가
    # 섞여 깨진다 (「울」이 밀려 2바이트가 되자 칸이 하나 넘쳤다).
    # 선두가 필드인지는 첫 <ED> 태그로 가른다 — <ED>出 로 열리면 그 앞은
    # 질문문이고(#1 「괜찮습니까？」), <ED>界 로 닫히면 앞 세그먼트가 연 필드다.
    LEAD = _re.compile(r'(.*?)<ED>(出?)')
    # 필드를 여는 것이 <ED>出 만은 아니다. 전투 명령 #59 의 첫 칸은
    # 「<ED> <FD><09><12>공격하기」 로 **<ED>공백** 이 열고 <ED>界 가 닫는다.
    # 그래서 「공격하기」가 강제에서 빠져 실기에서 두 글자가 깨졌다
    # (image/전투화면-선택지깨짐.png).
    #
    # 닫는 쪽으로 잡는 것이 안전하다 — **<ED>界 로 닫히는 구간이 필드**다.
    # <ED>界 는 칸 위치를 지정하는 명령이라 필드 끝에만 온다. 여는 쪽으로
    # 잡으면 <ED> 가 본문에 섞인 이야기 대사(#717~#725)까지 딸려 온다.
    TOKS = _re.compile(r'(<ED>(?:<[0-9A-Fa-f]{2}>|<[魔士見入]>|.))')

    def _fields(txt):
        out = FIELD.findall(txt)
        if '<ED>出' not in txt: return out
        ps = TOKS.split(txt)
        for i in range(1, len(ps), 2):
            if i + 2 < len(ps) and ps[i+2] == '<ED>界': out.append(ps[i+1])
        m = LEAD.match(txt)
        if m and m.group(2) != '出': out.append(m.group(1))
        return out
    # 설정 화면은 칸 수를 정확히 맞춰야 해서 이스케이프 개수까지 지정된다.
    # 줄이는 수단은 단일바이트 승격뿐이다 (patch_opt.FORCE 주석 참조).
    force = {"호"} | patch_opt.FORCE
    for _, txt in dlg_addr:
        for f in _fields(txt):
            for kind, v in krcodec.parse(f):
                if kind == "ch" and krcodec.is_hangul(v): force.add(v)

    # 목록 창(마법·아이템·장비)은 **바이트 하나를 타일 하나로** 그린다.
    # 타일맵의 타일 번호가 대사 폰트의 단일바이트 코드와 그대로 같다
    # (PROGRESS 4.34). 이스케이프를 해석하지 않으므로 목록에 뜨는 이름의
    # 음절은 전부 단일바이트여야 한다. 아니면 이름이 깨지고 화면이 붕괴한다.
    #
    # 대가가 크다. 단일바이트 칸이 141 뿐이라 이름에 쓰는 만큼 대사에서 빠진다.
    # 범위별로 재 보면 (대사 초과 세그먼트 / 총 초과 바이트)
    #
    #   강제 없음  28자   11개 /  13B
    #   마법만     66자   55개 /  76B
    #   장비만     79자   74개 / 113B
    #   둘 다     101자  189개 / 503B
    #
    # 마법 이름을 먼저 했다 (한자어화로 초과를 90 -> 35 로 줄였다). 장비도
    # 같은 방법으로 음역을 한국어·한자어로 바꿔 강제 음절을 32 -> 21 자로
    # 줄이고 나서 넣었다 (PROGRESS 4.37).
    for _sp, _wl in nametbl.TABLES:
        for _ja, _kr in _wl:
            if not _kr: continue
            for kind, v in krcodec.parse(_kr):
                if kind == "ch" and krcodec.is_hangul(v): force.add(v)
    # 아이템·장비 이름표(0x04f1c0~0x04f470)도 같은 목록 창에 실린다.
    # 이 문자열은 nametbl 이 아니라 TSV 가 정본이라 주소로 골라야 한다.
    # 「상태」「대형」 같은 메뉴 라벨도 이 구간에 있고 같은 창에서 그려진다.
    for _ad, _txt in dlg_addr:
        if not (LIST_TBL[0] <= _ad < LIST_TBL[1]): continue
        for kind, v in krcodec.parse(_txt):
            if kind == "ch" and krcodec.is_hangul(v): force.add(v)
    # 이름표(0x04f672~)가 <EB> 로 끌어 쓰는 단어표 엔트리 — 인물 이름이다.
    # 그 표는 타일 직접이라 상태창에 「팔코」가 「팔?서」로 나왔다
    # (image/오류-팔코이름.png). 닿는 음절만 단일바이트로 못 박는다.
    import words as _w
    _eb = set(); _a = NAME_TBL[0]
    while _a < NAME_TBL[1]:
        _b = orig[_a]
        if _b == 0xEB: _eb.add(orig[_a+1]); _a += 2; continue
        if _b == 0xEE: _a += 3; continue
        if _b == 0xF0 and orig[_a+1] == 0xC4: _a += 4; continue
        _a += 1
    # 110칸이 몬스터 이름과 인물 이름이 함께 쓰는 예산이라 전부는 못 넣는다.
    # 재 보면 루큐·팔코·카이오스는 107자(여유 3)인데 카렌을 더하면 110자로
    # 꽉 차고 대사 초과가 11 -> 34 개로 뛴다. 카렌은 몬스터 이름(A/B/C 결정)과
    # 같은 예산을 다투므로 함께 정한다.
    NAME_EB = {0x00, 0x04, 0x0F}          # 루큐 · 팔코 · 카이오스
    for _n in (_eb & NAME_EB):
        if _n < len(_w.WORDS) and _w.WORDS[_n][1]:
            for _c in _w.WORDS[_n][1]:
                if krcodec.is_hangul(_c): force.add(_c)
    # 전투 울음소리 표(0x05b39c)도 렌더러를 못 갈랐다. 어느 쪽이든 안전하게
    # 단일바이트로 못 박는다 — 의성어라 낱말 선택이 자유로워 값이 안 든다.
    for _kr in crytbl.texts():
        for kind, v in krcodec.parse(_kr):
            if kind == "ch" and krcodec.is_hangul(v): force.add(v)
    for _ in range(8):
        codes, freq, st = tralloc.allocate(pairs, t, force=force, no_risky=no_risky,
                                           reserve_safe=patch_opt.TWIN_RESERVE)
        probe = bytearray(orig)
        miss = ([kr for _, kr, _, _ in patch_words.apply(probe, codes, t)]
                + [kr for _, _, kr, _, _ in patch_names.apply(probe, codes, t)])
        # 설정 화면은 이스케이프 개수를 정확히 맞춰야 한다. 못 맞추는 항목의
        # 음절만 강제한다 (전부 미리 강제하면 단일바이트 30칸이 묶인다).
        optneed = patch_opt.needs_force(codes)
        if not miss and not optneed: break
        for kr in miss:
            for kind, v in krcodec.parse(kr):
                if kind == "ch" and krcodec.is_hangul(v): force.add(v)
        force |= optneed
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
    # 오프닝 컷신은 스프라이트다. 글리프는 엔트리 18(압축 그래픽),
    # 문장은 (타일, OAM 속성) 스크립트다 (PROGRESS 4.18).
    rom = bytearray(opening.apply(rom, verbose=True))
    # 목록 창(마법·아이템·장비)은 바이트 하나를 타일 하나로 그린다.
    # 그 8x8 반각 폰트에도 같은 코드 자리에 한글을 넣어야 한다
    # (PROGRESS 4.34~4.35).
    rom = bytearray(patch_hwfont.apply(rom, codes, verbose=True))
    # 컷신 「復活節第N日」 은 BG 타일맵이고 글자가 16x16(2x2 타일)이다.
    # 글꼴은 엔트리 28 블록 6~17, 본문은 0x0f0b92 의 타일맵 스트림이다
    # (PROGRESS 4.41). 대사 배정과 무관해서 codes 를 받지 않는다.
    rom = bytearray(cutscene.apply(rom, verbose=True))
    # 전투 울음소리 12개 (PROGRESS 4.43)
    rom, cover = crytbl.apply(rom, codes, t); rom = bytearray(rom)
    if cover:
        print(f"!! 울음소리 초과 {len(cover)}개")
        for a, kr, n, cap in cover: print(f"   {a:#08x} 「{kr}」: {n}/{cap}")
        raise SystemExit(1)
    print(f"울음소리: {len(crytbl.WORDS)}개 제자리 삽입")
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
